import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type FormEvent,
    type KeyboardEvent,
} from "react";
import { useChat } from "../hooks/useChat";
import { ErrorBoundary } from "./ErrorBoundary";
import { LoadingIndicator } from "./LoadingIndicator";
import { MessageBubble } from "./MessageBubble";

const SUGGESTED_PROMPTS = [
    "Find a rooftop restaurant in Bandra under ₹1500 for a date night 🌆",
    "Best rated cafes near Connaught Place, Delhi ☕",
    "Family-friendly restaurants in Indiranagar, Bangalore 👨‍👩‍👧",
    "Budget street food spots in Colaba, Mumbai 🍜",
];

/** Main chat interface — WhatsApp-style layout. */
export function ChatInterface() {
    const { messages, isLoading, error, sendChat, clearChat, setError } = useChat();
    const [input, setInput] = useState("");
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    // Auto-scroll to bottom on new messages
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, isLoading]);

    // Focus input on mount
    useEffect(() => {
        inputRef.current?.focus();
    }, []);

    const handleSubmit = useCallback(
        async (text: string) => {
            const trimmed = text.trim();
            if (!trimmed || isLoading) return;
            setInput("");
            await sendChat(trimmed);
            inputRef.current?.focus();
        },
        [isLoading, sendChat],
    );

    const handleFormSubmit = (e: FormEvent) => {
        e.preventDefault();
        handleSubmit(input);
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(input);
        }
    };

    const handleSuggestedPrompt = (prompt: string) => {
        if (!isLoading) handleSubmit(prompt);
    };

    return (
        <ErrorBoundary>
            <div className="flex flex-col h-screen bg-slate-50">
                {/* ── Header ────────────────────────────────────────────────── */}
                <header className="flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200 shadow-sm">
                    <div className="flex items-center gap-3">
                        <span className="text-2xl">✈️</span>
                        <div>
                            <h1 className="text-base font-bold text-gray-900 leading-tight">
                                AI Travel Agent
                            </h1>
                            <p className="text-[11px] text-green-500 font-medium">● Online</p>
                        </div>
                    </div>
                    <button
                        onClick={clearChat}
                        title="Start a new conversation"
                        className="text-xs text-gray-400 hover:text-gray-600 transition-colors px-3 py-1.5 rounded-lg hover:bg-gray-100"
                    >
                        New chat
                    </button>
                </header>

                {/* ── Messages ──────────────────────────────────────────────── */}
                <main className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
                    {/* Welcome state */}
                    {messages.length === 0 && !isLoading && (
                        <div className="flex flex-col items-center justify-center h-full text-center pb-8">
                            <div className="text-6xl mb-4">🗺️</div>
                            <h2 className="text-xl font-semibold text-gray-700 mb-2">
                                Where do you want to go?
                            </h2>
                            <p className="text-sm text-gray-400 mb-8 max-w-xs">
                                Ask me to find restaurants, cafes, attractions, or anything else. I'll
                                show you the best options nearby.
                            </p>

                            {/* Suggested prompts */}
                            <div className="w-full max-w-sm space-y-2">
                                {SUGGESTED_PROMPTS.map((prompt) => (
                                    <button
                                        key={prompt}
                                        onClick={() => handleSuggestedPrompt(prompt)}
                                        className="w-full text-left text-sm px-4 py-3 bg-white border border-gray-200 rounded-xl hover:border-sky-400 hover:bg-sky-50 transition-all text-gray-700 shadow-sm"
                                    >
                                        {prompt}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Chat messages */}
                    {messages.map((msg) => (
                        <MessageBubble key={msg.id} message={msg} />
                    ))}

                    {/* Loading indicator */}
                    {isLoading && messages.at(-1)?.role !== "assistant" && (
                        <div className="flex justify-start animate-fade-in">
                            <div>
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="text-xl">✈️</span>
                                    <span className="text-xs font-medium text-gray-500">Travel Agent</span>
                                </div>
                                <LoadingIndicator />
                            </div>
                        </div>
                    )}

                    {/* Error banner */}
                    {error && (
                        <div className="flex justify-center animate-fade-in">
                            <div className="bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl px-4 py-3 max-w-sm flex items-center gap-2">
                                <span>⚠️</span>
                                <span>{error}</span>
                                <button
                                    onClick={() => setError(null)}
                                    className="ml-auto text-red-400 hover:text-red-600"
                                >
                                    ✕
                                </button>
                            </div>
                        </div>
                    )}

                    <div ref={messagesEndRef} />
                </main>

                {/* ── Input area ────────────────────────────────────────────── */}
                <footer className="px-4 py-3 bg-white border-t border-gray-200">
                    <form onSubmit={handleFormSubmit} className="flex items-end gap-2">
                        <div className="flex-1 relative">
                            <textarea
                                ref={inputRef}
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="Ask me anything… 'Find a rooftop bar in Bandra'"
                                rows={1}
                                disabled={isLoading}
                                className="w-full resize-none rounded-2xl border border-gray-200 px-4 py-3 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100 disabled:opacity-50 max-h-40 min-h-[48px]"
                                style={{ height: "auto" }}
                                onInput={(e) => {
                                    const target = e.target as HTMLTextAreaElement;
                                    target.style.height = "auto";
                                    target.style.height = `${Math.min(target.scrollHeight, 160)}px`;
                                }}
                            />
                        </div>
                        <button
                            type="submit"
                            disabled={!input.trim() || isLoading}
                            className="flex-shrink-0 w-12 h-12 rounded-full bg-sky-500 hover:bg-sky-600 active:bg-sky-700 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors shadow-sm"
                            aria-label="Send message"
                        >
                            {isLoading ? (
                                <svg
                                    className="animate-spin w-5 h-5 text-white"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                >
                                    <circle
                                        className="opacity-25"
                                        cx="12"
                                        cy="12"
                                        r="10"
                                        stroke="currentColor"
                                        strokeWidth="4"
                                    />
                                    <path
                                        className="opacity-75"
                                        fill="currentColor"
                                        d="M4 12a8 8 0 018-8v8H4z"
                                    />
                                </svg>
                            ) : (
                                <svg
                                    className="w-5 h-5 text-white translate-x-0.5"
                                    fill="currentColor"
                                    viewBox="0 0 20 20"
                                >
                                    <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                                </svg>
                            )}
                        </button>
                    </form>
                    <p className="text-center text-[10px] text-gray-400 mt-2">
                        Powered by Gemini 2.0 Flash · Google Places API
                    </p>
                </footer>
            </div>
        </ErrorBoundary>
    );
}
