"use client";

import React, { useState, useEffect, useRef } from "react";

interface ResearchConsoleProps {
  onResearch: (ticker: string, fast: boolean) => void;
  loading?: boolean;
}

const QUICK_PICKS = ["NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "GOOGL", "SPY", "META"];
const HISTORY_KEY  = "omnisignal_history";

function loadHistory(): string[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]"); }
  catch { return []; }
}
function pushHistory(ticker: string, prev: string[]): string[] {
  const next = [ticker, ...prev.filter((t) => t !== ticker)].slice(0, 5);
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(next)); } catch {}
  return next;
}

export default function ResearchConsole({ onResearch, loading }: ResearchConsoleProps) {
  const [ticker,  setTicker]  = useState("");
  const [mode,    setMode]    = useState<"full" | "fast">("full");
  const [history, setHistory] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setHistory(loadHistory()); }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const run = (t: string) => {
    const clean = t.trim().toUpperCase();
    if (!clean || loading) return;
    setTicker(clean);
    setHistory((prev) => pushHistory(clean, prev));
    onResearch(clean, mode === "fast");
  };

  const handleSubmit = (e: React.FormEvent) => { e.preventDefault(); run(ticker); };

  const inputBase: React.CSSProperties = {
    background: "var(--card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--r)",
    color: "var(--t1)",
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 13,
    fontWeight: 500,
    letterSpacing: "0.04em",
    outline: "none",
    transition: "border-color 0.15s",
  };

  return (
    <div>
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>
        {/* Ticker input */}
        <div style={{ flex: 1, position: "relative" }}>
          <svg
            width="13" height="13" viewBox="0 0 24 24" fill="none"
            stroke="var(--t3)" strokeWidth="2"
            style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
          >
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="Ticker symbol  (e.g. AAPL, NVDA, SPY)"
            maxLength={10}
            disabled={loading}
            style={{ ...inputBase, width: "100%", paddingLeft: 32, paddingRight: 12, paddingTop: 9, paddingBottom: 9 }}
            onFocus={(e)  => { e.currentTarget.style.borderColor = "rgba(59,130,246,0.4)"; }}
            onBlur={(e)   => { e.currentTarget.style.borderColor = "var(--border)"; }}
          />
        </div>

        {/* Mode toggle */}
        <button
          type="button"
          onClick={() => setMode((m) => m === "full" ? "fast" : "full")}
          style={{
            ...inputBase,
            padding: "9px 14px",
            cursor: "pointer",
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: "0.06em",
            display: "flex", alignItems: "center", gap: 6,
            color: mode === "fast" ? "var(--amber)" : "var(--t2)",
            borderColor: mode === "fast" ? "rgba(245,158,11,0.3)" : "var(--border)",
          }}
          title={mode === "fast" ? "Fast mode: skips sentiment analysis" : "Full mode: macro + technical + sentiment"}
        >
          {mode === "fast"
            ? <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polygon points="13,2 3,14 12,14 11,22 21,10 12,10" /></svg>
            : <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></svg>
          }
          {mode === "fast" ? "Fast" : "Full"}
        </button>

        {/* Analyze button */}
        <button
          type="submit"
          disabled={loading || !ticker.trim()}
          style={{
            background: (loading || !ticker.trim()) ? "var(--card)" : "var(--blue)",
            color: (loading || !ticker.trim()) ? "var(--t3)" : "#fff",
            border: (loading || !ticker.trim()) ? "1px solid var(--border)" : "1px solid var(--blue)",
            borderRadius: "var(--r)",
            padding: "9px 20px",
            fontSize: 13, fontWeight: 600,
            cursor: (loading || !ticker.trim()) ? "not-allowed" : "pointer",
            display: "flex", alignItems: "center", gap: 7,
            letterSpacing: "0.01em",
            transition: "background 0.15s",
          }}
        >
          {loading
            ? <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ animation: "spin 1s linear infinite" }}>
                <path d="M21 12a9 9 0 1 1-6.219-8.56" />
              </svg>
            : <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
          }
          {loading ? "Analyzing" : "Analyze"}
        </button>
      </form>

      {/* Ticker chips */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
        {history.length > 0 && (
          <>
            <span style={{ fontSize: 10, color: "var(--t3)", fontWeight: 500, letterSpacing: "0.07em", textTransform: "uppercase" }}>Recent</span>
            {history.map((t) => (
              <Chip key={`h-${t}`} label={t} onClick={() => run(t)} disabled={loading} accent />
            ))}
            <span style={{ width: 1, height: 12, background: "var(--border-md)", display: "inline-block" }} />
          </>
        )}
        <span style={{ fontSize: 10, color: "var(--t3)", fontWeight: 500, letterSpacing: "0.07em", textTransform: "uppercase" }}>Quick picks</span>
        {QUICK_PICKS.map((t) => (
          <Chip key={t} label={t} onClick={() => run(t)} disabled={loading} />
        ))}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function Chip({ label, onClick, disabled, accent }: { label: string; onClick: () => void; disabled?: boolean; accent?: boolean }) {
  const [hover, setHover] = useState(false);
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: accent
          ? hover ? "rgba(59,130,246,0.15)" : "rgba(59,130,246,0.08)"
          : hover ? "var(--card-hover)" : "var(--card)",
        border: `1px solid ${accent ? "rgba(59,130,246,0.25)" : "var(--border)"}`,
        color: accent ? "var(--blue)" : "var(--t2)",
        borderRadius: 4,
        padding: "3px 9px",
        fontSize: 11,
        fontFamily: "'IBM Plex Mono', monospace",
        fontWeight: 500,
        letterSpacing: "0.06em",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background 0.12s",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {label}
    </button>
  );
}
