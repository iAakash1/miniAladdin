"use client";

import React from "react";
import type { SentimentData, Headline } from "@/types/api";

interface SentimentPanelProps {
  data: SentimentData | null;
  loading?: boolean;
}

function labelClass(l: string): string {
  const v = l.toLowerCase();
  if (v === "bullish") return "badge-green";
  if (v === "bearish") return "badge-red";
  return "badge-slate";
}

function scoreColor(s: number): string {
  if (s > 0.01)  return "var(--green)";
  if (s < -0.01) return "var(--red)";
  return "var(--t2)";
}

function HeadlineRow({ h }: { h: Headline }) {
  const cls = labelClass(h.label);
  return (
    <div style={{
      paddingTop: 10, paddingBottom: 10,
      borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "flex-start", gap: 10,
    }}>
      {/* Sentiment dot */}
      <div style={{
        width: 6, height: 6, borderRadius: "50%", flexShrink: 0, marginTop: 5,
        background:
          h.label.toLowerCase() === "bullish" ? "var(--green)"
          : h.label.toLowerCase() === "bearish" ? "var(--red)"
          : "var(--t3)",
      }} />

      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: 12, lineHeight: 1.5, color: "var(--t1)" }}>{h.title}</p>
        {h.source && (
          <p style={{ fontSize: 10.5, color: "var(--t3)", marginTop: 3 }}>{h.source}</p>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
        <span className={`badge ${cls}`}>{h.label}</span>
        <span className="mono" style={{ fontSize: 10.5, fontWeight: 500, color: scoreColor(h.score) }}>
          {h.score >= 0 ? "+" : ""}{h.score.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

export default function SentimentPanel({ data, loading }: SentimentPanelProps) {
  if (loading) {
    return (
      <div className="panel">
        <div className="panel-header"><div className="shimmer" style={{ width: 100, height: 11 }} /></div>
        <div className="panel-body">
          <div className="shimmer" style={{ height: 64, marginBottom: 12 }} />
          {[1,2,3].map(i => <div key={i} className="shimmer" style={{ height: 56, marginBottom: 8 }} />)}
        </div>
      </div>
    );
  }

  // Error state
  if (data?.error && !data.headline_count) {
    return (
      <div className="panel">
        <div className="panel-header"><span className="panel-label">Sentiment Edge</span></div>
        <div className="panel-body">
          <div style={{
            padding: "10px 12px",
            background: "var(--amber-dim)", border: "1px solid rgba(245,158,11,0.2)",
            borderRadius: "var(--r)",
          }}>
            <p style={{ fontSize: 11.5, fontWeight: 500, color: "var(--amber)", marginBottom: 3 }}>Sentiment unavailable</p>
            <p style={{ fontSize: 11, color: "var(--t3)", lineHeight: 1.5 }}>
              {data.note ?? data.error}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // No data
  if (!data || data.headline_count === 0) {
    return (
      <div className="panel">
        <div className="panel-header"><span className="panel-label">Sentiment Edge</span></div>
        <div className="panel-body" style={{ textAlign: "center", paddingTop: 32, paddingBottom: 32 }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--t3)" strokeWidth="1.5" style={{ margin: "0 auto 8px" }}>
            <path d="M4 22h16a2 2 0 002-2V4a2 2 0 00-2-2H8a2 2 0 00-2 2v16a2 2 0 01-2 2zm0 0a2 2 0 01-2-2v-9c0-1.1.9-2 2-2h2"/>
            <path d="M18 14h-8M15 18h-5M10 6h8v4h-8z"/>
          </svg>
          <p style={{ fontSize: 12, color: "var(--t3)" }}>No sentiment data</p>
          <p style={{ fontSize: 11, color: "var(--t3)", marginTop: 3, opacity: 0.7 }}>Switch to Full mode</p>
        </div>
      </div>
    );
  }

  const counts = data.headlines.reduce(
    (acc, h) => { const k = h.label.toLowerCase(); if (k in acc) (acc as Record<string, number>)[k]++; return acc; },
    { bullish: 0, bearish: 0, neutral: 0 } as { bullish: number; bearish: number; neutral: number }
  );

  const dominantClass = labelClass(data.dominant_label);
  const scoreNorm = Math.min(Math.abs(data.average_score) * 500, 100);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-label">Sentiment Edge</span>
        <span className={`badge ${dominantClass}`} style={{ marginLeft: "auto" }}>
          {data.dominant_label}
        </span>
      </div>

      <div className="panel-body">
        {/* Summary row */}
        <div style={{
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: "var(--r)", padding: "10px 12px", marginBottom: 12,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div>
              <p style={{ fontSize: 10, color: "var(--t3)", fontWeight: 500, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 3 }}>Avg Score</p>
              <p className="mono" style={{ fontSize: 18, fontWeight: 600, color: scoreColor(data.average_score) }}>
                {data.average_score >= 0 ? "+" : ""}{data.average_score.toFixed(4)}
              </p>
            </div>
            <div style={{ textAlign: "right" }}>
              <p style={{ fontSize: 10, color: "var(--t3)", fontWeight: 500, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 3 }}>Headlines</p>
              <p className="mono" style={{ fontSize: 18, fontWeight: 600 }}>{data.headline_count}</p>
            </div>
          </div>

          {/* Score bar */}
          <div className="conf-track" style={{ marginBottom: 8 }}>
            <div
              className="conf-fill"
              style={{ width: `${scoreNorm}%`, background: scoreColor(data.average_score) }}
            />
          </div>

          {/* Breakdown */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
            {[
              { k: "bullish", label: "Bullish", c: "var(--green)", count: counts.bullish },
              { k: "neutral", label: "Neutral", c: "var(--t3)",   count: counts.neutral },
              { k: "bearish", label: "Bearish", c: "var(--red)",  count: counts.bearish },
            ].map(({ k, label, c, count }) => (
              <div key={k} style={{ textAlign: "center", padding: "5px 4px" }}>
                <p className="mono" style={{ fontSize: 15, fontWeight: 600, color: c }}>{count}</p>
                <p style={{ fontSize: 9.5, color: "var(--t3)", letterSpacing: "0.05em" }}>{label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Headlines */}
        <div style={{ maxHeight: 280, overflowY: "auto" }}>
          {data.headlines.map((h, i) => (
            <HeadlineRow key={i} h={h} />
          ))}
          <div style={{ height: 6 }} />
        </div>
      </div>
    </div>
  );
}
