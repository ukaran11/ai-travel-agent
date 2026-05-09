/** Animated three-dot typing indicator shown while the agent is thinking. */
export function LoadingIndicator() {
    return (
        <div className="flex items-center gap-1 px-4 py-3 bg-white rounded-2xl rounded-bl-sm shadow-sm max-w-[80px]">
            <span className="sr-only">Agent is thinking…</span>
            {[0, 1, 2].map((i) => (
                <span
                    key={i}
                    className="w-2 h-2 rounded-full bg-sky-400"
                    style={{
                        display: "inline-block",
                        animation: `pulseDot 1.4s ease-in-out ${i * 0.2}s infinite`,
                    }}
                />
            ))}
        </div>
    );
}
