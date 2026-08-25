"""Cross-vendor daily-close reconciliation.

The property under test is the one that makes this worth having at all: an
*adjustment mismatch* and *ordinary venue noise* must not be reported as the
same thing. A single vendor's series can be checked against nothing, so these
tests construct disagreement deliberately and assert the classifier separates
the two causes.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.providers import fabric
from src.providers.fabric import Evidence
from src.providers.schemas import OHLCVBar, PriceSeries


def _series(symbol: str, closes: list[float], start: str = "2026-01-05") -> PriceSeries:
    """A series of consecutive weekday sessions with the given closes."""
    d = date.fromisoformat(start)
    bars = []
    for close in closes:
        while d.weekday() >= 5:            # skip weekends; sessions are weekdays
            d += timedelta(days=1)
        bars.append(OHLCVBar(date=d.isoformat(), close=close))
        d += timedelta(days=1)
    return PriceSeries(symbol=symbol, bars=bars)


def _ev(provider: str, series: PriceSeries) -> Evidence:
    return Evidence(provider=provider, capability="series", symbol=series.symbol,
                    ok=True, data=series)


BASE = [100.0, 101.0, 102.5, 101.75, 103.0, 104.25, 103.5, 105.0, 106.0, 105.5]


def test_agreeing_vendors_report_no_conflict():
    ev = [_ev("alpha", _series("AAPL", BASE)),
          _ev("beta", _series("AAPL", BASE))]
    out = fabric.reconcile_series(ev)
    assert out["agreement_pct"] == 100.0
    assert out["conflict_count"] == 0
    assert out["adjustment_mismatch"] == []
    assert out["shared_sessions"] == len(BASE)


def test_unadjusted_vendor_is_reported_as_a_systematic_split_not_as_noise():
    """The error this whole function exists to catch.

    A vendor returning raw closes for a 4-for-1 split disagrees enormously and
    *consistently*. Reporting that as a large average divergence would bury
    the cause; naming it as a stable 4:1 ratio identifies it.
    """
    ev = [_ev("adjusted_a", _series("AAPL", BASE)),
          _ev("adjusted_b", _series("AAPL", BASE)),
          _ev("raw", _series("AAPL", [c * 4 for c in BASE]))]
    out = fabric.reconcile_series(ev)

    assert len(out["adjustment_mismatch"]) == 1
    hit = out["adjustment_mismatch"][0]
    assert hit["provider"] == "raw"
    assert abs(hit["ratio"] - 4.0) < 0.01
    assert hit["likely_split"] == "4:1"
    # Stability is what separates this from a wrong print: the ratio does not
    # wander from session to session.
    assert hit["stability"] > 0.99
    # The two correct vendors are not accused of anything.
    assert {m["provider"] for m in out["adjustment_mismatch"]} == {"raw"}


def test_random_venue_noise_is_not_called_a_split():
    """Small, *varying* differences are venue and close-time effects.

    These must produce no adjustment finding, or every multi-venue comparison
    would report a phantom split.
    """
    jittered = [c * (1.0 + (0.004 if i % 2 else -0.004)) for i, c in enumerate(BASE)]
    ev = [_ev("alpha", _series("AAPL", BASE)),
          _ev("beta", _series("AAPL", jittered))]
    out = fabric.reconcile_series(ev)
    assert out["adjustment_mismatch"] == []


def test_divergence_is_measured_against_the_median_so_one_bad_vendor_cannot_move_it():
    """Three vendors, one wrong. The two that agree must remain the reference."""
    wrong = [c * 1.5 for c in BASE]
    ev = [_ev("a", _series("AAPL", BASE)),
          _ev("b", _series("AAPL", BASE)),
          _ev("c", _series("AAPL", wrong))]
    out = fabric.reconcile_series(ev)
    # Every shared session conflicts, and the divergence reported is c's
    # distance from the good median (50%), not a diluted three-way average.
    assert out["conflict_count"] == len(BASE)
    assert abs(out["max_divergence_pct"] - 50.0) < 0.5
    assert out["adjustment_mismatch"][0]["provider"] == "c"


def test_a_dropped_session_inside_the_shared_window_is_reported_as_a_gap():
    """A missing session and a wrong close have different causes and fixes."""
    full = _series("AAPL", BASE)
    holey = _series("AAPL", BASE)
    del holey.bars[4]                        # one session absent mid-window
    out = fabric.reconcile_series([_ev("full", full), _ev("holey", holey)])
    assert out["session_gaps"] == {"holey": 1}
    # The sessions they share still agree — the gap is not a disagreement.
    assert out["conflict_count"] == 0
    assert out["agreement_pct"] == 100.0


def test_a_shorter_window_is_not_a_gap():
    """The correctness fix this function needed, pinned.

    Vendors interpret a period like "3mo" differently — measured live, Twelve
    Data returned 92 sessions where Polygon returned 63 for the same request.
    Differencing against the union counted that as Polygon "missing 29
    sessions", penalising a vendor for someone else's longer window and
    inviting exactly the wrong conclusion. Gaps are counted only inside the
    range every vendor covers, so a short-but-complete series is clean.
    """
    ev = [_ev("long", _series("AAPL", BASE)),
          _ev("short", _series("AAPL", BASE[:6]))]
    out = fabric.reconcile_series(ev)
    assert out["session_gaps"] == {}
    # Coverage still reports the difference honestly — it is a fact about the
    # window, just not a defect.
    assert out["coverage"] == {"long": len(BASE), "short": 6}
    assert out["shared_sessions"] == 6
    assert out["agreement_pct"] == 100.0


def test_a_single_vendor_yields_no_reconciliation():
    """Nothing to check against is honestly reported as nothing, not as 100%."""
    assert fabric.reconcile_series([_ev("only", _series("AAPL", BASE))]) is None
    assert fabric.reconcile_series([]) is None


def test_failed_evidence_is_excluded_from_the_comparison():
    ev = [_ev("good", _series("AAPL", BASE)),
          _ev("also_good", _series("AAPL", BASE)),
          Evidence(provider="dead", capability="series", symbol="AAPL",
                   ok=False, error="429", status="rate_limited")]
    out = fabric.reconcile_series(ev)
    assert out["providers"] == ["also_good", "good"]
    assert "dead" not in out["coverage"]


def test_mismatch_requires_enough_sessions_to_be_a_pattern():
    """Four sessions is a coincidence; the threshold refuses to call it a split."""
    short = BASE[:4]
    ev = [_ev("a", _series("AAPL", short)),
          _ev("b", _series("AAPL", [c * 2 for c in short]))]
    out = fabric.reconcile_series(ev)
    assert out["adjustment_mismatch"] == []
    # The disagreement is still reported — it is only the *diagnosis* that is
    # withheld for want of evidence.
    assert out["conflict_count"] == 4


# ── ledger copy ───────────────────────────────────────────────────────────

def test_ledger_detail_strings_are_grammatical_at_one():
    """Observed in production: "1 line items from 1 vendors".

    Small, but the provenance ledger's entire claim is that this system is
    careful about what it reports. A reader who catches sloppy grammar there
    has been given a reason to doubt the numbers next to it.
    """
    from api.index import _plural

    assert _plural(1, "vendor") == "1 vendor"
    assert _plural(2, "vendor") == "2 vendors"
    assert _plural(0, "vendor") == "0 vendors"
    assert _plural(1, "line item") == "1 line item"
    assert _plural(1, "recent filing") == "1 recent filing"
    assert _plural(3, "recent filing") == "3 recent filings"
    # Irregulars stay expressible rather than needing a special case at the
    # call site.
    assert _plural(1, "company", "companies") == "1 company"
    assert _plural(4, "company", "companies") == "4 companies"
