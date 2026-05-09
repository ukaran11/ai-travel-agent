import { useCallback, useRef, useState } from "react";
import type { Place } from "../types";

interface StreamState {
    text: string;
    places: Place[];
    isDone: boolean;
    error: string | null;
}

/**
 * useStream — low-level hook for reading an SSE stream from POST endpoints.
 *
 * Usage:
 *   const { state, startStream, reset } = useStream();
 *   startStream("/api/v1/chat/stream", body);
 */
export function useStream() {
    const [state, setState] = useState<StreamState>({
        text: "",
        places: [],
        isDone: false,
        error: null,
    });
    const abortRef = useRef<AbortController | null>(null);

    const reset = useCallback(() => {
        abortRef.current?.abort();
        setState({ text: "", places: [], isDone: false, error: null });
    }, []);

    const startStream = useCallback(async (url: string, body: unknown) => {
        reset();
        abortRef.current = new AbortController();

        try {
            const response = await fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "text/event-stream",
                },
                body: JSON.stringify(body),
                signal: abortRef.current.signal,
            });

            if (!response.ok || !response.body) {
                setState((s) => ({
                    ...s,
                    error: `HTTP ${response.status}`,
                    isDone: true,
                }));
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() ?? "";

                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    const raw = line.slice(6).trim();
                    if (!raw) continue;

                    try {
                        const event = JSON.parse(raw) as { type: string; content: unknown };

                        if (event.type === "token") {
                            setState((s) => ({ ...s, text: s.text + (event.content as string) }));
                        } else if (event.type === "places") {
                            setState((s) => ({ ...s, places: event.content as Place[] }));
                        } else if (event.type === "done") {
                            setState((s) => ({ ...s, isDone: true }));
                            return;
                        } else if (event.type === "error") {
                            setState((s) => ({
                                ...s,
                                error: event.content as string,
                                isDone: true,
                            }));
                            return;
                        }
                    } catch {
                        // Ignore parse errors for individual chunks
                    }
                }
            }
        } catch (err: unknown) {
            if ((err as Error)?.name !== "AbortError") {
                setState((s) => ({
                    ...s,
                    error: (err as Error).message ?? "Stream error",
                    isDone: true,
                }));
            }
        } finally {
            setState((s) => (s.isDone ? s : { ...s, isDone: true }));
        }
    }, [reset]);

    const abort = useCallback(() => {
        abortRef.current?.abort();
        setState((s) => ({ ...s, isDone: true }));
    }, []);

    return { state, startStream, reset, abort };
}
