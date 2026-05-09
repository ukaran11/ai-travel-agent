import type { ChatMessage } from "../types";
import { formatTime } from "../utils/formatters";
import { RecommendationCard } from "./RecommendationCard";

interface MessageBubbleProps {
    message: ChatMessage;
}

/** Renders a single chat message — user or assistant. */
export function MessageBubble({ message }: MessageBubbleProps) {
    const isUser = message.role === "user";

    return (
        <div
            className={`flex ${isUser ? "justify-end" : "justify-start"} animate-slide-up`}
        >
            <div className={`max-w-[85%] md:max-w-[75%] ${isUser ? "order-2" : "order-1"}`}>
                {/* Avatar */}
                {!isUser && (
                    <div className="flex items-center gap-2 mb-1">
                        <span className="text-xl">✈️</span>
                        <span className="text-xs font-medium text-gray-500">Travel Agent</span>
                    </div>
                )}

                {/* Bubble */}
                <div
                    className={`
            px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm
            ${isUser
                            ? "bg-sky-500 text-white rounded-tr-sm ml-auto"
                            : "bg-white text-gray-800 rounded-tl-sm"
                        }
          `}
                >
                    {message.content}
                    {message.isStreaming && (
                        <span className="inline-block w-0.5 h-4 bg-sky-400 ml-0.5 animate-pulse align-middle" />
                    )}
                </div>

                {/* Recommendation cards */}
                {!isUser && message.places && message.places.length > 0 && (
                    <div className="mt-3 space-y-3">
                        {message.places.map((place) => (
                            <RecommendationCard key={place.place_id} place={place} />
                        ))}
                    </div>
                )}

                {/* Timestamp */}
                <p
                    className={`text-[10px] text-gray-400 mt-1 ${isUser ? "text-right" : "text-left"}`}
                >
                    {formatTime(message.timestamp)}
                </p>
            </div>
        </div>
    );
}
