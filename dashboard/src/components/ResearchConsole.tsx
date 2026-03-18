"use client";

import React, { useState } from "react";
import { Search, Loader2, Zap, Globe } from "lucide-react";

interface ResearchConsoleProps {
    onResearch: (ticker: string, fast: boolean) => void;
    loading?: boolean;
}

export default function ResearchConsole({ onResearch, loading }: ResearchConsoleProps) {
    const [ticker, setTicker] = useState("");
    const [mode, setMode] = useState<"full" | "fast">("full");

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const t = ticker.trim().toUpperCase();
        if (t && !loading) {
            onResearch(t, mode === "fast");
        }
    };

    const quickTickers = ["NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "GOOGL"];

    return (
        <div className="glass-card px-8 py-7 animate-fade-in">
            <div className="section-title">
                <span className="title-dot" />
                Research Console
            </div>

            <form onSubmit={handleSubmit} className="flex gap-3">
                <div className="flex-1 relative">
                    <Search
                        size={16}
                        className="absolute left-4 top-1/2 -translate-y-1/2"
                        style={{ color: "var(--text-muted)" }}
                    />
                    <input
                        id="ticker-input"
                        type="text"
                        value={ticker}
                        onChange={(e) => setTicker(e.target.value.toUpperCase())}
                        placeholder="Enter ticker (e.g. AAPL)"
                        maxLength={10}
                        className="w-full pl-11 pr-5 py-3.5 rounded-xl text-sm font-medium outline-none transition-all"
                        style={{
                            background: "rgba(20, 28, 48, 0.6)",
                            border: "1px solid var(--border-subtle)",
                            color: "var(--text-primary)",
                            fontFamily: "'JetBrains Mono', monospace",
                            fontSize: "0.875rem",
                            letterSpacing: "0.05em",
                        }}
                        onFocus={(e) => {
                            e.currentTarget.style.borderColor = "var(--border-glow)";
                            e.currentTarget.style.boxShadow = "0 0 24px rgba(99, 102, 241, 0.1)";
                        }}
                        onBlur={(e) => {
                            e.currentTarget.style.borderColor = "var(--border-subtle)";
                            e.currentTarget.style.boxShadow = "none";
                        }}
                        disabled={loading}
                    />
                </div>

                {/* Mode toggle */}
                <button
                    type="button"
                    onClick={() => setMode(mode === "full" ? "fast" : "full")}
                    className="px-5 py-3.5 rounded-xl text-xs font-bold transition-all flex items-center gap-2"
                    style={{
                        background: mode === "fast" ? "rgba(34, 211, 238, 0.1)" : "rgba(99, 102, 241, 0.1)",
                        border: `1px solid ${mode === "fast" ? "rgba(34, 211, 238, 0.2)" : "rgba(99, 102, 241, 0.2)"}`,
                        color: mode === "fast" ? "#22d3ee" : "#818cf8",
                        letterSpacing: "0.05em",
                    }}
                    title={mode === "fast" ? "Fast mode: skips sentiment" : "Full mode: includes sentiment"}
                >
                    {mode === "fast" ? <Zap size={14} /> : <Globe size={14} />}
                    {mode === "fast" ? "Fast" : "Full"}
                </button>

                <button
                    id="research-btn"
                    type="submit"
                    disabled={loading || !ticker.trim()}
                    className="px-7 py-3.5 rounded-xl text-sm font-bold transition-all flex items-center gap-2.5"
                    style={{
                        background: loading || !ticker.trim() ? "rgba(99, 102, 241, 0.15)" : "var(--gradient-primary)",
                        color: loading || !ticker.trim() ? "var(--text-muted)" : "white",
                        cursor: loading || !ticker.trim() ? "not-allowed" : "pointer",
                        letterSpacing: "0.03em",
                    }}
                >
                    {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                    {loading ? "Analyzing..." : "Research"}
                </button>
            </form>

            {/* Quick tickers */}
            <div className="flex gap-2.5 mt-5 flex-wrap">
                {quickTickers.map((t) => (
                    <button
                        key={t}
                        onClick={() => {
                            setTicker(t);
                            if (!loading) onResearch(t, mode === "fast");
                        }}
                        disabled={loading}
                        className="px-4 py-2 rounded-lg text-xs font-semibold transition-all hover:scale-105 active:scale-95"
                        style={{
                            background: "rgba(20, 28, 48, 0.5)",
                            border: "1px solid var(--border-subtle)",
                            color: "var(--text-secondary)",
                            cursor: loading ? "not-allowed" : "pointer",
                            letterSpacing: "0.08em",
                        }}
                    >
                        {t}
                    </button>
                ))}
            </div>
        </div>
    );
}
