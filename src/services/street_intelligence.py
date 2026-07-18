"""
Street & Insider Intelligence engine (v4.5, P0-B).

Deterministic interpretation of StreetData (analyst recommendation trends,
EPS-surprise history, insider sentiment) into the same shape the Technical
Intelligence block uses: structured readings + toned plain-language findings.
Pure function of its input — no I/O, fully unit-testable. Presentation layer
only; the scoring engine's verdict is unchanged by this block.
"""

from __future__ import annotations

from typing import Any, Optional

from src.providers.schemas import RecommendationMonth, StreetData

Tone = str  # 'pos' | 'neg' | 'neutral'

# MSPR (monthly share purchase ratio) runs −100…100; Finnhub's own guidance
# treats |20| as a meaningful conviction threshold.
MSPR_SIGNAL = 20.0
TREND_DELTA = 0.05  # buy-ratio change that counts as a real shift


def _buy_ratio(month: RecommendationMonth) -> Optional[float]:
    total = month.strong_buy + month.buy + month.hold + month.sell + month.strong_sell
    if total == 0:
        return None
    return (month.strong_buy + month.buy) / total


def build(street: Optional[StreetData]) -> Optional[dict[str, Any]]:
    if street is None:
        return None
    findings: list[dict[str, str]] = []
    block: dict[str, Any] = {"findings": findings}

    # ── analyst recommendation trend ─────────────────────────────────────────
    if street.recommendations:
        latest = street.recommendations[0]
        oldest = street.recommendations[-1]
        ratio_now = _buy_ratio(latest)
        ratio_then = _buy_ratio(oldest)
        total = latest.strong_buy + latest.buy + latest.hold + latest.sell + latest.strong_sell
        trend = "steady"
        if ratio_now is not None and ratio_then is not None and len(street.recommendations) > 1:
            if ratio_now - ratio_then >= TREND_DELTA:
                trend = "improving"
            elif ratio_then - ratio_now >= TREND_DELTA:
                trend = "deteriorating"
        block["recommendations"] = {
            "period": latest.period,
            "analysts": total,
            "strong_buy": latest.strong_buy,
            "buy": latest.buy,
            "hold": latest.hold,
            "sell": latest.sell,
            "strong_sell": latest.strong_sell,
            "buy_ratio": None if ratio_now is None else round(ratio_now, 3),
            "trend": trend,
            "months": len(street.recommendations),
        }
        if ratio_now is not None:
            tone: Tone = "pos" if ratio_now >= 0.6 else "neg" if ratio_now <= 0.35 else "neutral"
            trend_note = (
                f", and the mix has been {trend} over the covered months"
                if trend != "steady" else ""
            )
            findings.append({
                "text": (
                    f"{total} analysts currently cover the name; "
                    f"{100 * ratio_now:.0f}% rate it a buy{trend_note}."
                ),
                "tone": "pos" if trend == "improving" else "neg" if trend == "deteriorating" else tone,
            })

    # ── earnings execution ───────────────────────────────────────────────────
    scored = [s for s in street.surprises if s.surprise_pct is not None]
    if scored:
        beats = sum(1 for s in scored if s.surprise_pct > 0)
        avg = sum(s.surprise_pct for s in scored) / len(scored)
        block["surprises"] = {
            "quarters": len(scored),
            "beats": beats,
            "avg_surprise_pct": round(avg, 2),
            "last_surprise_pct": scored[0].surprise_pct,
            "last_period": scored[0].period,
        }
        if beats == len(scored):
            findings.append({
                "text": (
                    f"Management has beaten EPS estimates in all {len(scored)} reported quarters "
                    f"(average surprise {avg:+.1f}%) — a consistent execution record."
                ),
                "tone": "pos",
            })
        elif beats == 0:
            findings.append({
                "text": (
                    f"EPS has missed estimates in all {len(scored)} recent quarters "
                    f"(average surprise {avg:+.1f}%) — estimates are running ahead of delivery."
                ),
                "tone": "neg",
            })
        else:
            findings.append({
                "text": (
                    f"EPS beat estimates in {beats} of the last {len(scored)} quarters "
                    f"(average surprise {avg:+.1f}%)."
                ),
                "tone": "pos" if avg > 0 else "neg",
            })

    # ── insider sentiment ────────────────────────────────────────────────────
    if street.insider_mspr is not None:
        mspr = street.insider_mspr
        read = "buying" if mspr >= MSPR_SIGNAL else "selling" if mspr <= -MSPR_SIGNAL else "neutral"
        block["insider"] = {
            "mspr": round(mspr, 1),
            "net_shares": street.insider_net_shares,
            "read": read,
        }
        if read != "neutral":
            findings.append({
                "text": (
                    f"Insider sentiment (MSPR {mspr:+.0f}) shows meaningful insider {read} "
                    f"over the last six months — insiders trade on conviction, not obligation."
                    if read == "buying" else
                    f"Insider sentiment (MSPR {mspr:+.0f}) shows net insider selling over the last "
                    f"six months — common for compensation reasons, but worth monitoring at this magnitude."
                ),
                "tone": "pos" if read == "buying" else "neg",
            })

    # Nothing usable → no block (frontend hides the panel).
    if len(block) == 1:
        return None
    return block
