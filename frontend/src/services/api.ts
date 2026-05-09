/// <reference types="vite/client" />
import axios from "axios";
import type { ChatRequest, ChatResponse, HealthResponse, Place } from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api/v1";

const api = axios.create({
    baseURL: BASE_URL,
    headers: { "Content-Type": "application/json" },
    timeout: 60_000,
});

// ── Chat (synchronous) ────────────────────────────────────────────────────────

export async function sendMessage(request: ChatRequest): Promise<ChatResponse> {
    const { data } = await api.post<ChatResponse>("/chat", request);
    return data;
}

// ── Chat (streaming via fetch + SSE) ─────────────────────────────────────────

export async function sendMessageStream(
    request: ChatRequest,
    onToken: (token: string) => void,
    onPlaces: (places: Place[]) => void,
    onDone: () => void,
    onError: (error: string) => void,
): Promise<void> {
    const response = await fetch(`${BASE_URL}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(request),
    });

    if (!response.ok || !response.body) {
        onError(`HTTP ${response.status}: ${response.statusText}`);
        return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let doneSignalled = false;

    try {
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
                        onToken(event.content as string);
                    } else if (event.type === "places") {
                        onPlaces(event.content as Place[]);
                    } else if (event.type === "done") {
                        doneSignalled = true;
                        onDone();
                        return;
                    } else if (event.type === "error") {
                        doneSignalled = true;
                        onError(event.content as string);
                        return;
                    }
                } catch {
                    // Ignore malformed SSE chunks
                }
            }
        }
    } catch {
        // Connection closed by server — expected when SSE stream ends
    }

    if (!doneSignalled) onDone();
}

// ── Session ───────────────────────────────────────────────────────────────────

export async function clearSession(sessionId: string): Promise<void> {
    await api.delete(`/session/${sessionId}`);
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
    const { data } = await api.get<HealthResponse>("/health");
    return data;
}
