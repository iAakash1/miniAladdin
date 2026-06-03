"use client";

import React from "react";

interface RiskGaugeProps {
  value: number;
  status?: string;
  loading?: boolean;
}

const ZONES: [number, string, string][] = [
  [1.0, "var(--green)",  "Stable"],
  [1.2, "var(--amber)", "Elevated"],
  [1.4, "#f97316",      "High Risk"],
  [1.6, "var(--red)",   "Critical"],
];

function getZone(v: number) {
  return ZONES.find(([max]) => v <= max) ?? ZONES[ZONES.length - 1];
}

export default function RiskGauge({ value, status, loading }: RiskGaugeProps) {
  const MIN = 0.5, MAX = 1.6;
  const clamped = Math.max(MIN, Math.min(MAX, value));
  const pct     = ((clamped - MIN) / (MAX - MIN)) * 100;

  // Semicircle: cx=110, cy=100, r=80
  const CX = 110, CY = 100, R = 80;
  const circ  = Math.PI * R;
  const offset = circ - (pct / 100) * circ;

  const [, color, label] = getZone(clamped);
  const displayLabel = status && !["STABLE", "ELEVATED", "CRITICAL"].includes(status) ? status : label;

  // Needle position
  const angle = (pct / 100) * Math.PI;
  const needleX = CX - R * Math.cos(angle);
  const needleY = CY - R * Math.sin(angle);

  if (loading) {
    return (
      <div className="panel" style={{ padding: 14 }}>
        <div className="shimmer" style={{ width: "55%", height: 11, marginBottom: 16 }} />
        <div className="shimmer" style={{ width: 180, height: 100, borderRadius: 90, margin: "0 auto" }} />
        <div className="shimmer" style={{ width: 80, height: 11, margin: "14px auto 0" }} />
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-label">Systemic Risk</span>
        <span
          className="badge"
          style={{
            marginLeft: "auto",
            background: `${color}15`,
            color,
            fontSize: 10,
          }}
        >
          {displayLabel}
        </span>
      </div>

      <div className="panel-body" style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        <svg width="220" height="130" viewBox="0 0 220 130" style={{ overflow: "visible" }}>
          {/* Track */}
          <path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
            className="gauge-track"
          />
          {/* Fill */}
          <path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
            className="gauge-fill"
            stroke={color}
            strokeDasharray={circ}
            strokeDashoffset={offset}
          />
          {/* Needle dot */}
          <circle cx={needleX} cy={needleY} r={4} fill={color} />
          {/* Center value */}
          <text
            x={CX} y={CY - 14}
            textAnchor="middle"
            fill="var(--t1)"
            fontSize="28"
            fontWeight="600"
            fontFamily="'IBM Plex Mono', monospace"
          >
            {clamped.toFixed(2)}
          </text>
          <text x={CX} y={CY + 6} textAnchor="middle" fill={color} fontSize="9.5" fontWeight="600" letterSpacing="2">
            SRM
          </text>
          {/* Scale */}
          <text x={CX - R - 4} y={CY + 20} textAnchor="end" fill="var(--t3)" fontSize="9" fontFamily="'IBM Plex Mono', monospace">0.5</text>
          <text x={CX + R + 4} y={CY + 20} textAnchor="start" fill="var(--t3)" fontSize="9" fontFamily="'IBM Plex Mono', monospace">1.6</text>
        </svg>

        {/* Zone legend */}
        <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
          {ZONES.map(([, c, l]) => (
            <div key={l} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{
                width: 5, height: 5, borderRadius: "50%",
                background: c,
                opacity: displayLabel === l ? 1 : 0.3,
              }} />
              <span style={{
                fontSize: 9,
                color: displayLabel === l ? c : "var(--t3)",
                fontWeight: displayLabel === l ? 600 : 400,
                letterSpacing: "0.04em",
              }}>
                {l}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
