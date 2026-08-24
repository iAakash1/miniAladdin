"""
Decision provenance — the audit trail for a single research run.

## Why this exists

Every number OmniSignal shows is already the product of a fallback chain:
prices come from whichever of Polygon / TwelveData / FMP / MarketStack /
yfinance answered first, news from whichever of NewsAPI / GNews / Yahoo /
Tavily answered, fundamentals from Alpha Vantage / Finnhub / FMP. Each of
those calls returns a ``ProviderResult`` that already knows which vendor
answered, which were tried, how confident the orchestrator is in the answer,
whether it came from cache, and whether the cache was stale.

Until now all of that was written to a log line and discarded. The response
carried the *conclusion* but not the *chain of custody*, so a reader had no
way to distinguish "BUY, from fresh Polygon bars and twelve fresh headlines"
from "BUY, from a four-day-old stale cache because every price vendor was
down". Those are not the same claim, and a system that presents them
identically is asking to be trusted on faith.

The ledger below is assembled from objects the request already holds. It
computes nothing new about the market and it cannot disagree with the
analysis, because it is a record of the same inputs the analysis consumed.

## What a reader can do with it

* See which vendor actually answered, and which were tried and passed over.
* See how old the data is, in the unit that matters for that input (trading
  days for prices, hours for news).
* See where the answer was degraded — stale cache, fallback vendor, vendor
  disagreement — and by how much that lowered confidence.
* See which inputs the scoring engine did *not* receive, so an absent factor
  reads as absent rather than as neutral.

## What it deliberately does not do

It does not grade the decision. A ledger that said "this verdict looks
unreliable" would be a second opinion competing with the engine's own
confidence score, which is already computed from these same degradations
(``ScoreCard.confidence_losses``). This reports; the engine judges.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

# Confidence at or below this means the answer came from a degraded path —
# a stale cache (0.30) or materially disagreeing vendors (0.50). Matches the
# scale documented on ProviderResult.
DEGRADED_CONFIDENCE = 0.55

# A single ledger entry's health, in the vocabulary the UI already uses for
# tone. Not a judgement about the market — a judgement about the *input*.
Health = str  # "ok" | "degraded" | "missing"


def _age_text(fetched_at: Optional[datetime], now: Optional[datetime] = None) -> Optional[str]:
    """How long ago an input was fetched, in the coarsest honest unit.

    Coarse on purpose: "4h ago" is actionable, "4h 13m 22s ago" implies a
    precision that a cache TTL of fifteen minutes does not have.
    """
    if fetched_at is None:
        return None
    now = now or datetime.now(timezone.utc)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    seconds = max(0.0, (now - fetched_at).total_seconds())
    if seconds < 90:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86_400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86_400)}d ago"


class Ledger:
    """Collects one entry per input consumed by a research run.

    Deliberately a plain mutable object rather than a context manager or a
    decorator: the research handler fetches its inputs in several concurrent
    branches, and the recording has to happen wherever each branch happens to
    land. Recording is append-only and never raises — a provenance failure
    must not be able to fail the analysis it is describing.
    """

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        self._entries: list[dict[str, Any]] = []
        self._notes: list[str] = []

    # ── recording ─────────────────────────────────────────────────────────

    def record(
        self,
        *,
        label: str,
        kind: str,
        result: Any = None,
        detail: Optional[str] = None,
        used_for: Iterable[str] = (),
        missing_reason: Optional[str] = None,
    ) -> None:
        """Record one input.

        `result` is a ProviderResult when the input came through the provider
        orchestrator, and None when it did not (a locally computed input, or
        one that was never obtained). Duck-typed rather than imported so this
        module stays free of a dependency on the provider package — it is a
        recorder, and it should not care who it is recording.
        """
        try:
            entry: dict[str, Any] = {
                "label": label,
                "kind": kind,
                "detail": detail,
                "used_for": list(used_for),
            }

            if result is None:
                entry.update(
                    health="missing",
                    source=None,
                    sources_consulted=[],
                    confidence=None,
                    cached=False,
                    stale=False,
                    age=None,
                    note=missing_reason or "not available for this run",
                )
                self._entries.append(entry)
                return

            ok = bool(getattr(result, "ok", getattr(result, "data", None) is not None))
            confidence = float(getattr(result, "confidence", 0.0) or 0.0)
            stale = bool(getattr(result, "stale", False))
            disagreement = bool(getattr(result, "disagreement", False))
            consulted = list(getattr(result, "sources_consulted", []) or [])
            source = getattr(result, "source", "") or None

            if not ok:
                health: Health = "missing"
            elif stale or disagreement or confidence <= DEGRADED_CONFIDENCE:
                health = "degraded"
            else:
                health = "ok"

            # The note is the *reason* for the health, so a degraded row is
            # never just a colour the reader has to interpret.
            note = None
            if not ok:
                note = getattr(result, "error", None) or "every source failed"
            elif stale:
                note = "served from stale cache — every live source failed"
            elif disagreement:
                note = "sources disagreed materially; lowest-variance reading used"
            elif consulted and source and consulted[0] != source:
                note = f"primary ({consulted[0]}) unavailable, fell back"

            entry.update(
                health=health,
                source=source,
                sources_consulted=consulted,
                confidence=round(confidence, 2),
                cached=bool(getattr(result, "cached", False)),
                stale=stale,
                age=_age_text(getattr(result, "fetched_at", None)),
                note=note,
            )
            self._entries.append(entry)
        except Exception:  # noqa: BLE001 — a recorder must never break its subject
            pass

    def record_fabric(
        self,
        *,
        label: str,
        kind: str,
        evidence: list,
        detail: Optional[str] = None,
        used_for: Iterable[str] = (),
    ) -> None:
        """Record a *parallel* multi-vendor collection as one entry.

        The single-vendor `record` above answers "who told us this". This
        answers a different and stronger question: "who did we ask, who
        answered, and did they agree" — which only exists because the fabric
        asks every capable vendor rather than stopping at the first.

        A collection is `ok` when anyone answered, `degraded` when some
        vendors failed or the answers conflict, and `missing` only when every
        vendor came back empty. A partial result is a real result.
        """
        try:
            answered = [e for e in evidence if getattr(e, "ok", False)]
            failed = [e for e in evidence if not getattr(e, "ok", False)]

            if not evidence:
                health = "missing"
                note = "no configured vendor can answer this"
            elif not answered:
                health = "missing"
                note = "; ".join(
                    f"{e.provider}: {e.status}" for e in failed[:4]
                ) or "every vendor failed"
            elif failed:
                health = "degraded"
                note = "; ".join(f"{e.provider}: {e.status}" for e in failed[:4])
            else:
                health = "ok"
                note = None

            self._entries.append({
                "label": label,
                "kind": kind,
                "detail": detail,
                "used_for": list(used_for),
                "health": health,
                # The vendor list *is* the source here — there is no single
                # winner to name, which is the whole point of the fan-out.
                "source": ", ".join(sorted(e.provider for e in answered)) or None,
                "sources_consulted": sorted(getattr(e, "provider", "?") for e in evidence),
                # Answered / asked, so the reader sees the denominator.
                "confidence": round(len(answered) / len(evidence), 2) if evidence else None,
                "cached": False,
                "stale": False,
                "age": "just now" if answered else None,
                "note": note,
                # Per-vendor detail, so a degraded row can be opened rather
                # than merely coloured.
                "contributors": [
                    {
                        "provider": e.provider,
                        "ok": bool(e.ok),
                        "status": e.status,
                        "latency_ms": e.latency_ms,
                        "error": e.error,
                    }
                    for e in sorted(evidence, key=lambda x: (not x.ok, x.provider))
                ],
                "parallel": True,
            })
        except Exception:  # noqa: BLE001 — a recorder must never break its subject
            pass

    def note(self, text: str) -> None:
        """A fact about the run that is not tied to one input."""
        if text:
            self._notes.append(text)

    # ── assembly ──────────────────────────────────────────────────────────

    def build(
        self,
        *,
        engine_version: Optional[str] = None,
        elapsed_seconds: Optional[float] = None,
        confidence_losses: Optional[list[dict[str, Any]]] = None,
        ai_generated: Optional[bool] = None,
        ai_model: Optional[str] = None,
    ) -> dict[str, Any]:
        """The finished ledger, plus a summary a header can render.

        `confidence_losses` is passed straight through from the scorecard
        rather than recomputed: the engine already decided what each
        degradation cost, and a second calculation here could disagree with
        the confidence number shown beside it.
        """
        degraded = [e for e in self._entries if e["health"] == "degraded"]
        missing = [e for e in self._entries if e["health"] == "missing"]
        live = [e for e in self._entries if e["health"] == "ok"]

        return {
            "ticker": self.ticker,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine_version": engine_version,
            "elapsed_seconds": elapsed_seconds,
            "inputs": self._entries,
            "summary": {
                "total": len(self._entries),
                "ok": len(live),
                "degraded": len(degraded),
                "missing": len(missing),
                # Distinct vendors that actually answered. The count a reader
                # cares about is "how many independent sources is this built
                # on", not how many calls were made.
                "sources": sorted({e["source"] for e in self._entries if e.get("source")}),
            },
            # What the engine itself docked confidence for, verbatim.
            "confidence_losses": confidence_losses or [],
            "ai": {
                # Whether the narrative was model-written or the deterministic
                # fallback. A reader deciding how much weight to give the prose
                # needs to know which one they are reading.
                "generated": ai_generated,
                "model": ai_model,
                "role": "explanation only — never produces verdict, confidence, "
                        "risk level or any factor value",
            },
            "notes": self._notes,
        }
