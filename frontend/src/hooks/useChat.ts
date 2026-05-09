import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, Place } from "../types";
import { clearSession, sendMessage, sendMessageStream } from "../services/api";

const SESSION_KEY = "travel_agent_session_id";
const MESSAGES_KEY = "travel_agent_messages";
const USE_STREAMING = true; // toggle for SSE streaming vs synchronous

/** Generate a UUIDv4 without the `uuid` package dependency. */
function generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function getOrCreateSessionId(): string {
    const existing = localStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const id = generateId();
    localStorage.setItem(SESSION_KEY, id);
    return id;
}

function loadPersistedMessages(): ChatMessage[] {
    try {
        const raw = localStorage.getItem(MESSAGES_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw) as ChatMessage[];
        // Revive Date objects
        return parsed.map((m) => ({ ...m, timestamp: new Date(m.timestamp) }));
    } catch {
        return [];
    }
}

export function useChat() {
    const [messages, setMessages] = useState<ChatMessage[]>(loadPersistedMessages);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const sessionId = useRef<string>(getOrCreateSessionId());

    // Persist messages to localStorage
    useEffect(() => {
        localStorage.setItem(MESSAGES_KEY, JSON.stringify(messages));
    }, [messages]);

    const addMessage = useCallback((msg: ChatMessage) => {
        setMessages((prev) => [...prev, msg]);
    }, []);

    const updateLastAssistantMessage = useCallback(
        (updater: (prev: ChatMessage) => ChatMessage) => {
            setMessages((prev) => {
                const copy = [...prev];
                for (let i = copy.length - 1; i >= 0; i--) {
                    if (copy[i].role === "assistant") {
                        copy[i] = updater(copy[i]);
                        break;
                    }
                }
                return copy;
            });
        },
        [],
    );

    const sendChat = useCallback(
        async (text: string) => {
            if (!text.trim() || isLoading) return;
            setError(null);

            const userMsg: ChatMessage = {
                id: generateId(),
                role: "user",
                content: text.trim(),
                timestamp: new Date(),
            };
            addMessage(userMsg);
            setIsLoading(true);

            if (USE_STREAMING) {
                // ── Streaming path ───────────────────────────────────────────────
                const assistantId = generateId();
                const placeholderMsg: ChatMessage = {
                    id: assistantId,
                    role: "assistant",
                    content: "",
                    places: [],
                    timestamp: new Date(),
                    isStreaming: true,
                };
                addMessage(placeholderMsg);

                try {
                    await sendMessageStream(
                        { message: text.trim(), session_id: sessionId.current },
                        // onToken
                        (token) => {
                            updateLastAssistantMessage((m) => ({
                                ...m,
                                content: m.content + token,
                            }));
                        },
                        // onPlaces
                        (places: Place[]) => {
                            updateLastAssistantMessage((m) => ({ ...m, places }));
                        },
                        // onDone
                        () => {
                            updateLastAssistantMessage((m) => ({ ...m, isStreaming: false }));
                            setIsLoading(false);
                        },
                        // onError
                        (errMsg: string) => {
                            updateLastAssistantMessage((m) => ({
                                ...m,
                                content: m.content || "Sorry, something went wrong. Please try again.",
                                isStreaming: false,
                            }));
                            setError(errMsg);
                            setIsLoading(false);
                        },
                    );
                } catch {
                    // Unexpected throw from sendMessageStream (e.g. network abort before onDone)
                    updateLastAssistantMessage((m) => ({ ...m, isStreaming: false }));
                } finally {
                    setIsLoading(false);
                }
            } else {
                // ── Synchronous path ─────────────────────────────────────────────
                try {
                    const response = await sendMessage({
                        message: text.trim(),
                        session_id: sessionId.current,
                    });
                    const assistantMsg: ChatMessage = {
                        id: generateId(),
                        role: "assistant",
                        content: response.response,
                        places: response.places,
                        timestamp: new Date(),
                    };
                    addMessage(assistantMsg);
                } catch (err) {
                    const msg = err instanceof Error ? err.message : "Unknown error";
                    setError(msg);
                    const errorMsg: ChatMessage = {
                        id: generateId(),
                        role: "assistant",
                        content: "I'm having trouble connecting right now. Please try again.",
                        timestamp: new Date(),
                    };
                    addMessage(errorMsg);
                } finally {
                    setIsLoading(false);
                }
            }
        },
        [isLoading, addMessage, updateLastAssistantMessage],
    );

    const clearChat = useCallback(async () => {
        try {
            await clearSession(sessionId.current);
        } catch {
            // Ignore errors on clear
        }
        setMessages([]);
        setError(null);
        const newId = generateId();
        sessionId.current = newId;
        localStorage.setItem(SESSION_KEY, newId);
        localStorage.removeItem(MESSAGES_KEY);
    }, []);

    return {
        messages,
        isLoading,
        error,
        sessionId: sessionId.current,
        sendChat,
        clearChat,
        setError,
    };
}
