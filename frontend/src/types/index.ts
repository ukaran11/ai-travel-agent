// ── API response types ────────────────────────────────────────────────────────

export interface UserLocation {
    lat: number;
    lng: number;
}

export interface ChatRequest {
    message: string;
    session_id: string;
    location?: UserLocation;
}

export interface Place {
    place_id: string;
    name: string;
    rating: number;
    price_level: number;
    price_symbol: string;
    address: string;
    lat: number;
    lng: number;
    photo_url: string;
    is_open: boolean | null;
    types: string[];
    total_ratings: number;
    distance_meters: number | null;
    maps_url: string;
    directions_url: string;
    phone?: string | null;
    website?: string | null;
}

export interface ChatResponse {
    response: string;
    places: Place[];
    session_id: string;
    follow_up: string | null;
    turn_count: number;
}

// ── UI / chat state types ─────────────────────────────────────────────────────

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
    id: string;
    role: MessageRole;
    content: string;
    places?: Place[];
    timestamp: Date;
    isStreaming?: boolean;
}

// ── Streaming event payloads ──────────────────────────────────────────────────

export type StreamEventType = "token" | "places" | "done" | "error";

export interface StreamEvent {
    type: StreamEventType;
    content: string | Place[];
}

// ── Health check ──────────────────────────────────────────────────────────────

export interface HealthResponse {
    status: string;
    version: string;
    environment: string;
    uptime_seconds: number;
    dependencies: Record<string, string>;
}
