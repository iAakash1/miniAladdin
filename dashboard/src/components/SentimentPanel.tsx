"use client";

import React from "react";
import { Newspaper, TrendingUp, TrendingDown, Minus } from "lucide-react";

interface Headline {
    title: string;
    score: number;
    label: string;
    source?: string;
}

interface SentimentData {
    headline_count: number;
    average_score: number;
    dominant_label: string;
    headlines: Headline[];
}

interface SentimentPanelProps {
    data: SentimentData | null;
    loading?: boolean;
}

function labelIcon(label: string) {
    const l = label.toLowerCase();
    if (l === "bullish") return <TrendingUp size={14} className="text-emerald-400" />;
    if (l === "bearish") return <TrendingDown size={14} className="text-red-400" />;
    return <Minus size={14} className="text-slate-400" />;
}

function labelBadge(label: string) {
    const l = label.toLowerCase();
    if (l === "bullish") return "bg-emerald-500/15 text-emerald-400 border-emerald-500/20";
    if (l === "bearish") return "bg-red-500/15 text-red-400 border-red-500/20";
    return "bg-slate-500/15 text-slate-400 border-slate-500/20";
}

function scoreColor(score: number) {
    if (score > 0) return "#34d399";
    if (score < 0) return "#f87171";
    return "var(--text-muted)";
}

export default function SentimentPanel({ data, loading }: SentimentPanelProps) {
    if (loading) {
        return (
            <div className="glass-card px-8 py-8">
                <div className="shimmer mb-6" style={{ width: "60%", height: 16 }} />
                {[1, 2, 3].map((i) => (
                    <div key={i} className="shimmer mb-4" style={{ width: "100%", height: 56 }} />
                ))}
            </div>
        );
    }

    if (!data || data.headline_count === 0) {
        return (
            <div className="glass-card px-8 py-8 animate-fade-in animate-fade-in-delay-4">
                <div className="section-title">
                    <span className="title-dot" style={{ background: "var(--accent-amber)" }} />
                    Sentiment Edge
                </div>
                <div className="flex flex-col items-center py-12" style={{ color: "var(--text-muted)" }}>
                    <Newspaper size={36} className="mb-3 opacity-25" />
                    <p className="text-sm">No sentiment data available</p>
                    <p className="text-xs mt-1 opacity-60">Try full mode for sentiment analysis</p>
                </div>
            </div>
        );
    }

    return (
        <div className="glass-card px-8 py-8 animate-fade-in animate-fade-in-delay-4">
            <div className="section-title">
                <span className="title-dot" style={{ background: "var(--accent-amber)" }} />
                Sentiment Edge
            </div>

            {/* Summary bar */}
            <div className="flex items-center gap-6 mb-6 rounded-xl px-5 py-4" style={{ background: "var(--bg-row)" }}>
                <div>
                    <p className="text-[10px] uppercase tracking-widest mb-1.5" style={{ color: "var(--text-muted)" }}>Score</p>
                    <p className="text-xl font-bold mono" style={{
                        color: scoreColor(data.average_score),
                    }}>
                        {data.average_score >= 0 ? "+" : ""}{data.average_score.toFixed(4)}
                    </p>
                </div>
                <div className="ml-auto">
                    <span className={`text-xs font-bold px-4 py-1.5 rounded-full border ${labelBadge(data.dominant_label)}`}>
                        {data.dominant_label}
                    </span>
                </div>
                <div className="text-right">
                    <p className="text-[10px] uppercase tracking-widest mb-1.5" style={{ color: "var(--text-muted)" }}>Headlines</p>
                    <p className="text-lg font-bold mono">{data.headline_count}</p>
                </div>
            </div>

            {/* Headlines */}
            <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                {data.headlines.map((h, i) => (
                    <div
                        key={i}
                        className="flex items-start gap-4 rounded-xl px-4 py-4 transition-colors"
                        style={{ background: "rgba(13, 18, 32, 0.5)" }}
                    >
                        <div className="mt-1 shrink-0">{labelIcon(h.label)}</div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm leading-relaxed" style={{ color: "var(--text-primary)", lineHeight: "1.6" }}>
                                {h.title}
                            </p>
                            {h.source && (
                                <p className="text-[11px] mt-1.5 tracking-wide" style={{ color: "var(--text-muted)" }}>
                                    {h.source}
                                </p>
                            )}
                        </div>
                        <span className="mono text-xs font-semibold shrink-0 mt-0.5" style={{
                            color: scoreColor(h.score),
                        }}>
                            {h.score >= 0 ? "+" : ""}{h.score.toFixed(2)}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}
