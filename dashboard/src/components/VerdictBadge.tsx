"use client";

import React from "react";

interface VerdictBadgeProps {
    verdict: string | null;
    confidence?: number;
    rationale?: string;
    elapsed?: number;
    loading?: boolean;
}

function getVerdictStyle(verdict: string): { className: string; emoji: string } {
    const v = verdict.toLowerCase();
    if (v === "strong buy") return { className: "verdict-strong-buy", emoji: "🚀" };
    if (v === "buy") return { className: "verdict-buy", emoji: "📈" };
    if (v === "strong sell") return { className: "verdict-strong-sell", emoji: "🔻" };
    if (v === "sell") return { className: "verdict-sell", emoji: "📉" };
    return { className: "verdict-hold", emoji: "➡️" };
}

export default function VerdictBadge({ verdict, confidence, rationale, elapsed, loading }: VerdictBadgeProps) {
    if (loading) {
        return (
            <div className="glass-card px-8 py-10">
                <div className="shimmer mx-auto" style={{ width: 220, height: 72, borderRadius: 18 }} />
            </div>
        );
    }

    if (!verdict) return null;

    const style = getVerdictStyle(verdict);

    return (
        <div className="glass-card px-8 py-8 animate-fade-in animate-fade-in-delay-1">
            <div className="section-title justify-center">
                <span className="title-dot" style={{ background: "var(--accent-amber)" }} />
                OmniSignal Verdict
            </div>

            <div className="flex flex-col items-center mt-2">
                {/* Badge */}
                <div
                    className={`${style.className} px-10 py-5 rounded-2xl text-center shadow-xl float-subtle`}
                    style={{ boxShadow: "0 10px 40px rgba(0,0,0,0.35)" }}
                >
                    <span className="text-2xl mr-2.5">{style.emoji}</span>
                    <span className="text-2xl font-extrabold text-white tracking-wide">
                        {verdict}
                    </span>
                </div>

                {/* Confidence */}
                {confidence != null && (
                    <div className="mt-6 w-full max-w-xs">
                        <div className="flex justify-between text-xs mb-2">
                            <span className="tracking-wider" style={{ color: "var(--text-muted)" }}>Confidence</span>
                            <span className="font-bold mono">
                                {(confidence * 100).toFixed(0)}%
                            </span>
                        </div>
                        <div className="w-full h-2.5 rounded-full" style={{ background: "rgba(148, 163, 184, 0.08)" }}>
                            <div
                                className="h-2.5 rounded-full transition-all duration-1000"
                                style={{
                                    width: `${confidence * 100}%`,
                                    background: "var(--gradient-primary)",
                                    boxShadow: "0 0 12px rgba(99, 102, 241, 0.3)",
                                }}
                            />
                        </div>
                    </div>
                )}

                {/* Rationale */}
                {rationale && (
                    <p className="mt-5 text-xs text-center leading-relaxed max-w-md tracking-wide" style={{ color: "var(--text-muted)" }}>
                        {rationale}
                    </p>
                )}

                {/* Elapsed */}
                {elapsed != null && (
                    <p className="mt-2 text-[11px] mono" style={{ color: "var(--text-muted)" }}>
                        Processed in {elapsed}s
                    </p>
                )}
            </div>
        </div>
    );
}
