"use client";

import React, { useState, useCallback } from "react";
import { Shield, Activity, Zap } from "lucide-react";
import RiskGauge from "@/components/RiskGauge";
import MacroPanel from "@/components/MacroPanel";
import TechnicalPanel from "@/components/TechnicalPanel";
import SentimentPanel from "@/components/SentimentPanel";
import VerdictBadge from "@/components/VerdictBadge";
import ResearchConsole from "@/components/ResearchConsole";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || (typeof window !== "undefined" ? window.location.origin : "");

interface ResearchResult {
  ticker: string;
  macro: Record<string, unknown>;
  technicals: Record<string, unknown>;
  sentiment: Record<string, unknown> | null;
  verdict: string;
  elapsed_seconds: number;
  mode: string;
}

export default function Dashboard() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchResult | null>(null);

  const handleResearch = useCallback(async (ticker: string, fast: boolean) => {
    setLoading(true);
    setError(null);

    try {
      const url = `${API_BASE}/api/research/${ticker}${fast ? "?fast=true" : ""}`;
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`API returned ${res.status}`);
      }
      const data: ResearchResult = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch research data");
    } finally {
      setLoading(false);
    }
  }, []);

  const macroData = result?.macro || null;
  const techData = result?.technicals || null;
  const sentimentData = result?.sentiment || null;

  return (
    <div className="min-h-screen px-6 py-10 md:px-10 lg:px-16">
      {/* ── Header ──────────────────────────────────────────────── */}
      <header className="max-w-[1400px] mx-auto mb-10 animate-fade-in">
        <div className="flex items-center gap-4">
          <div
            className="p-3 rounded-2xl shadow-lg"
            style={{ background: "var(--gradient-primary)" }}
          >
            <Shield size={24} className="text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight">
              OmniSignal
            </h1>
            <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
              Agentic Multi-Factor Risk Intelligence Engine
            </p>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <div
              className="flex items-center gap-2 px-4 py-2 rounded-full"
              style={{
                background: "rgba(34, 211, 238, 0.08)",
                border: "1px solid rgba(34, 211, 238, 0.15)",
              }}
            >
              <Activity size={13} className="text-cyan-400 pulse-glow" />
              <span className="text-xs font-semibold text-cyan-400">Live</span>
            </div>
            <div
              className="flex items-center gap-2 px-4 py-2 rounded-full"
              style={{
                background: "rgba(99, 102, 241, 0.08)",
                border: "1px solid rgba(99, 102, 241, 0.12)",
              }}
            >
              <Zap size={13} className="text-indigo-400" />
              <span className="text-xs font-semibold text-indigo-400">v1.0.0</span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto space-y-8">
        {/* ── Research Console ──────────────────────────────────── */}
        <ResearchConsole onResearch={handleResearch} loading={loading} />

        {/* ── Error ─────────────────────────────────────────────── */}
        {error && (
          <div
            className="glass-card px-6 py-5 animate-fade-in"
            style={{ borderColor: "rgba(248, 113, 113, 0.2)" }}
          >
            <p className="text-sm text-red-400 font-medium">
              <strong>Error:</strong> {error}
            </p>
            <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
              Make sure the API server is running:{" "}
              <code className="mono text-xs px-2 py-0.5 rounded" style={{ background: "rgba(30, 41, 59, 0.6)" }}>
                uvicorn api.index:app --port 8000
              </code>
            </p>
          </div>
        )}

        {/* ── Results Grid ──────────────────────────────────────── */}
        {(result || loading) && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Left: Gauge + Macro */}
            <div className="lg:col-span-4 space-y-8">
              <RiskGauge
                value={typeof macroData?.risk_multiplier === "number" ? macroData.risk_multiplier : 1.0}
                status={typeof macroData?.status === "string" ? macroData.status : undefined}
                loading={loading}
              />
              <MacroPanel
                data={macroData as Record<string, unknown> & { risk_multiplier: number } | null}
                loading={loading}
              />
            </div>

            {/* Center: Verdict + Technicals */}
            <div className="lg:col-span-4 space-y-8">
              <VerdictBadge
                verdict={result?.verdict || null}
                confidence={0.72}
                rationale={`Mode: ${result?.mode || "full"}`}
                elapsed={result?.elapsed_seconds}
                loading={loading}
              />
              <TechnicalPanel
                data={techData as Record<string, unknown> & { current_price: number } | null}
                loading={loading}
              />
            </div>

            {/* Right: Sentiment */}
            <div className="lg:col-span-4 space-y-8">
              <SentimentPanel
                data={sentimentData as Record<string, unknown> & { headline_count: number; average_score: number; dominant_label: string; headlines: Array<{ title: string; score: number; label: string; source?: string }> } | null}
                loading={loading}
              />
            </div>
          </div>
        )}

        {/* ── Empty State ───────────────────────────────────────── */}
        {!result && !loading && !error && (
          <div className="glass-card py-28 flex flex-col items-center justify-center animate-fade-in">
            <div className="float-subtle">
              <Shield size={56} className="mb-5" style={{ color: "var(--accent-indigo)", opacity: 0.2 }} />
            </div>
            <p className="text-xl font-semibold mb-2" style={{ color: "var(--text-secondary)" }}>
              Enter a ticker to begin
            </p>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              OmniSignal will analyze macro risk, technicals, and sentiment
            </p>
          </div>
        )}
      </main>

      {/* ── Footer ──────────────────────────────────────────────── */}
      <footer className="max-w-[1400px] mx-auto mt-16 pb-8 text-center">
        <div className="h-px mb-6 mx-20" style={{ background: "linear-gradient(to right, transparent, var(--border-subtle), transparent)" }} />
        <p className="text-xs tracking-wide" style={{ color: "var(--text-muted)" }}>
          OmniSignal v1.0.0 · Built on MASFIN · For research and educational purposes only
        </p>
      </footer>
    </div>
  );
}
