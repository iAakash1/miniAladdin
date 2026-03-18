"use client";

import React from "react";
import { BarChart3, Activity, TrendingUp, TrendingDown } from "lucide-react";

interface TechnicalData {
    ticker?: string;
    current_price?: number | null;
    return_5d?: number | null;
    return_21d?: number | null;
    volatility?: number | null;
    sharpe_ratio?: number | null;
    sortino_ratio?: number | null;
    rsi_14?: number | null;
    max_drawdown?: number | null;
    momentum?: number | null;
    raw_signal?: string | null;
    risk_adjusted_signal?: string | null;
}

interface TechnicalPanelProps {
    data: TechnicalData | null;
    loading?: boolean;
}

function formatPct(v: number | null | undefined): string {
    if (v == null) return "N/A";
    return `${(v * 100).toFixed(2)}%`;
}

function formatNum(v: number | null | undefined, decimals = 2): string {
    if (v == null) return "N/A";
    return v.toFixed(decimals);
}

function signalColor(signal: string | null | undefined): string {
    if (!signal) return "var(--text-muted)";
    const s = signal.toLowerCase();
    if (s.includes("strong buy")) return "#34d399";
    if (s.includes("buy")) return "#6ee7b7";
    if (s.includes("strong sell")) return "#f87171";
    if (s.includes("sell")) return "#fb923c";
    return "#fbbf24";
}

export default function TechnicalPanel({ data, loading }: TechnicalPanelProps) {
    if (loading) {
        return (
            <div className="glass-card px-8 py-8">
                <div className="shimmer mb-6" style={{ width: "60%", height: 16 }} />
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="shimmer mb-4" style={{ width: "100%", height: 44 }} />
                ))}
            </div>
        );
    }

    if (!data) return null;

    const rows = [
        { label: "5-Day Return", value: formatPct(data.return_5d), icon: <TrendingUp size={15} /> },
        { label: "21-Day Return", value: formatPct(data.return_21d), icon: <TrendingDown size={15} /> },
        { label: "Volatility (Ann.)", value: formatPct(data.volatility), icon: <Activity size={15} /> },
        { label: "Sharpe Ratio", value: formatNum(data.sharpe_ratio, 4), icon: <BarChart3 size={15} /> },
        { label: "Sortino Ratio", value: formatNum(data.sortino_ratio, 4), icon: <BarChart3 size={15} /> },
        { label: "RSI-14", value: formatNum(data.rsi_14), icon: <Activity size={15} /> },
        { label: "Max Drawdown", value: formatPct(data.max_drawdown), icon: <TrendingDown size={15} /> },
        { label: "Momentum (21d)", value: data.momentum != null ? `$${data.momentum.toFixed(2)}` : "N/A", icon: <TrendingUp size={15} /> },
    ];

    return (
        <div className="glass-card px-8 py-8 animate-fade-in animate-fade-in-delay-3">
            <div className="section-title">
                <span className="title-dot" style={{ background: "var(--accent-cyan)" }} />
                Technical Analysis
            </div>

            {/* Price hero */}
            {data.current_price != null && (
                <div className="mb-6 flex items-baseline gap-3">
                    <span className="text-4xl font-extrabold mono" style={{ letterSpacing: "-0.02em" }}>
                        ${data.current_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </span>
                    <span className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>{data.ticker}</span>
                </div>
            )}

            {/* Metrics */}
            <div className="space-y-2.5">
                {rows.map((row) => (
                    <div key={row.label} className="data-row">
                        <div className="row-label">
                            {row.icon}
                            <span>{row.label}</span>
                        </div>
                        <span className="row-value">{row.value}</span>
                    </div>
                ))}
            </div>

            {/* Signal boxes */}
            <div className="mt-6 pt-5 flex gap-4" style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <div className="flex-1 text-center rounded-xl py-4" style={{ background: "var(--bg-row)" }}>
                    <p className="text-[10px] uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>Raw Signal</p>
                    <p className="text-base font-extrabold" style={{ color: signalColor(data.raw_signal) }}>
                        {data.raw_signal || "N/A"}
                    </p>
                </div>
                <div className="flex-1 text-center rounded-xl py-4" style={{ background: "var(--bg-row)" }}>
                    <p className="text-[10px] uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>Risk-Adjusted</p>
                    <p className="text-base font-extrabold" style={{ color: signalColor(data.risk_adjusted_signal) }}>
                        {data.risk_adjusted_signal || "N/A"}
                    </p>
                </div>
            </div>
        </div>
    );
}
