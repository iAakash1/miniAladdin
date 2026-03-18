"use client";

import React from "react";
import { TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";

interface MacroData {
    risk_multiplier: number;
    yield_spread?: number;
    inflation_rate?: string;
    fed_funds_rate?: string;
    yield_curve_inverted?: boolean;
    recession_warning?: boolean;
    status?: string;
}

interface MacroPanelProps {
    data: MacroData | null;
    loading?: boolean;
}

export default function MacroPanel({ data, loading }: MacroPanelProps) {
    if (loading) {
        return (
            <div className="glass-card px-8 py-8">
                <div className="shimmer mb-6" style={{ width: "60%", height: 16 }} />
                {[1, 2, 3].map((i) => (
                    <div key={i} className="shimmer mb-4" style={{ width: "100%", height: 52 }} />
                ))}
            </div>
        );
    }

    if (!data) return null;

    const cleanInflation = data.inflation_rate?.replace("%", "") || "N/A";
    const cleanFedRate = data.fed_funds_rate?.replace("%", "") || "N/A";

    const items = [
        {
            label: "Yield Spread (10Y-2Y)",
            value: data.yield_spread != null ? `${data.yield_spread.toFixed(2)}%` : "N/A",
            icon: data.yield_curve_inverted ? (
                <AlertTriangle size={16} className="text-red-400" />
            ) : (
                <TrendingUp size={16} className="text-emerald-400" />
            ),
            note: data.yield_curve_inverted ? "INVERTED" : undefined,
        },
        {
            label: "Inflation (YoY CPI)",
            value: cleanInflation === "N/A" ? "N/A" : `${cleanInflation}%`,
            icon: <TrendingUp size={16} className="text-amber-400" />,
        },
        {
            label: "Fed Funds Rate",
            value: cleanFedRate === "N/A" ? "N/A" : `${cleanFedRate}%`,
            icon: <TrendingDown size={16} className="text-cyan-400" />,
        },
    ];

    return (
        <div className="glass-card px-8 py-8 animate-fade-in animate-fade-in-delay-2">
            <div className="section-title">
                <span className="title-dot" style={{ background: "var(--accent-emerald)" }} />
                Macro Indicators
            </div>

            <div className="space-y-3">
                {items.map((item) => (
                    <div key={item.label} className="data-row">
                        <div className="row-label">
                            {item.icon}
                            <span>{item.label}</span>
                        </div>
                        <div className="flex items-center gap-3">
                            <span className="row-value">
                                {item.value}
                            </span>
                            {item.note && (
                                <span className="text-[10px] font-bold px-2 py-1 rounded-md bg-red-500/15 text-red-400 border border-red-500/20">
                                    {item.note}
                                </span>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            {data.recession_warning && (
                <div
                    className="mt-5 flex items-center gap-3 rounded-xl px-5 py-3.5"
                    style={{
                        background: "rgba(248, 113, 113, 0.08)",
                        border: "1px solid rgba(248, 113, 113, 0.15)",
                    }}
                >
                    <AlertTriangle size={15} className="text-red-400 shrink-0" />
                    <span className="text-xs font-medium text-red-400 tracking-wide">
                        Recession Warning — Yield curve is inverted
                    </span>
                </div>
            )}
        </div>
    );
}
