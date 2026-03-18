"use client";

import React from "react";

interface RiskGaugeProps {
    value: number;       // 0.5 – 1.6
    status?: string;     // STABLE | ELEVATED | CRITICAL | DATA_ERROR
    loading?: boolean;
}

export default function RiskGauge({ value, status, loading }: RiskGaugeProps) {
    const min = 0.5;
    const max = 1.6;
    const clamped = Math.max(min, Math.min(max, value));
    const pct = ((clamped - min) / (max - min)) * 100;

    // SVG arc params (180° semicircle)
    const cx = 140, cy = 120, r = 100;
    const circumference = Math.PI * r;
    const offset = circumference - (pct / 100) * circumference;

    const getColor = () => {
        if (clamped <= 1.0) return "#34d399";
        if (clamped <= 1.2) return "#fbbf24";
        if (clamped <= 1.4) return "#fb923c";
        return "#f87171";
    };

    const getLabel = () => {
        if (status) return status;
        if (clamped <= 1.0) return "STABLE";
        if (clamped <= 1.2) return "ELEVATED";
        return "CRITICAL";
    };

    if (loading) {
        return (
            <div className="glass-card px-8 py-10 flex flex-col items-center justify-center" style={{ minHeight: 320 }}>
                <div className="shimmer" style={{ width: 220, height: 220, borderRadius: "50%" }} />
                <div className="shimmer mt-5" style={{ width: 140, height: 20 }} />
            </div>
        );
    }

    return (
        <div className="glass-card px-8 py-8 flex flex-col items-center animate-fade-in animate-fade-in-delay-1">
            <div className="section-title w-full justify-center">
                <span className="title-dot" />
                Macro Risk Gauge
            </div>

            <svg width="280" height="160" viewBox="0 0 280 160" className="mt-2">
                {/* Glow filter */}
                <defs>
                    <filter id="gauge-glow">
                        <feGaussianBlur stdDeviation="4" result="blur" />
                        <feMerge>
                            <feMergeNode in="blur" />
                            <feMergeNode in="SourceGraphic" />
                        </feMerge>
                    </filter>
                </defs>

                {/* Track */}
                <path
                    d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
                    className="gauge-track"
                />
                {/* Fill */}
                <path
                    d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
                    className="gauge-fill"
                    stroke={getColor()}
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    filter="url(#gauge-glow)"
                />

                {/* Center value */}
                <text
                    x={cx} y={cy - 18}
                    textAnchor="middle"
                    fill="var(--text-primary)"
                    fontSize="34"
                    fontWeight="800"
                    fontFamily="'JetBrains Mono', monospace"
                >
                    {clamped.toFixed(2)}
                </text>
                <text
                    x={cx} y={cy + 8}
                    textAnchor="middle"
                    fill={getColor()}
                    fontSize="11"
                    fontWeight="700"
                    letterSpacing="3"
                >
                    {getLabel()}
                </text>

                {/* Scale labels */}
                <text x={cx - r - 8} y={cy + 22} textAnchor="end" fill="var(--text-muted)" fontSize="11" fontFamily="'JetBrains Mono', monospace">0.5</text>
                <text x={cx + r + 8} y={cy + 22} textAnchor="start" fill="var(--text-muted)" fontSize="11" fontFamily="'JetBrains Mono', monospace">1.6</text>
            </svg>

            <p className="text-xs mt-3 tracking-wider" style={{ color: "var(--text-muted)" }}>
                Systemic Risk Multiplier
            </p>
        </div>
    );
}
