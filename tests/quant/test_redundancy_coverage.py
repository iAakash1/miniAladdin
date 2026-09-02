"""An independence claim must not be built on pairs that were never observed.

`analyse_redundancy` fills unmeasured factor pairs with zero correlation,
because eigenvalues need a complete matrix and a correlation that was never
observed cannot be invented. The fill is unavoidable. What was wrong was
calling it conservative: understating redundancy overstates independence, and
"largely independent" is exactly the verdict this metric flatters toward.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.research.redundancy import MIN_PAIR_COVERAGE, Redundancy


def _effective(matrix: np.ndarray) -> float:
    ev = np.clip(np.linalg.eigvalsh(matrix), 0.0, None)
    total = ev.sum()
    return float(total**2 / np.square(ev).sum()) if total > 0 else 0.0


def test_the_zero_fill_inflates_apparent_independence() -> None:
    """The direction. Six factors all correlated 0.9 are heavily redundant."""
    k = 6
    true = np.full((k, k), 0.9)
    np.fill_diagonal(true, 1.0)
    complete = _effective(true)

    blanked = true.copy()
    pairs = [(i, j) for i in range(k) for j in range(i + 1, k)][:12]
    for i, j in pairs:
        blanked[i, j] = blanked[j, i] = 0.0

    assert _effective(blanked) > complete
    assert _effective(blanked) / complete > 2.5, (
        "blanking pairs must be shown to move the number materially"
    )


def test_more_missing_pairs_never_lowers_the_independence_estimate() -> None:
    """Monotone in the flattering direction — the property that makes it unsafe."""
    k = 6
    true = np.full((k, k), 0.9)
    np.fill_diagonal(true, 1.0)
    order = [(i, j) for i in range(k) for j in range(i + 1, k)]
    seen = []
    for n_missing in (0, 3, 6, 9, 12):
        m = true.copy()
        for i, j in order[:n_missing]:
            m[i, j] = m[j, i] = 0.0
        seen.append(_effective(m))
    assert seen == sorted(seen)


def test_thin_coverage_withholds_the_verdict() -> None:
    r = Redundancy(
        factors=["a", "b", "c"], matrix=[], effective_factors=2.9,
        redundant_pairs=[], dates=100, measured_pairs=1, total_pairs=3,
    )
    assert r.pair_coverage == pytest.approx(1 / 3)
    assert "too little overlap" in r.assessment
    assert "largely independent" not in r.assessment


def test_full_coverage_reports_the_verdict_unqualified() -> None:
    r = Redundancy(
        factors=["a", "b", "c"], matrix=[], effective_factors=2.9,
        redundant_pairs=[], dates=100, measured_pairs=3, total_pairs=3,
    )
    assert r.pair_coverage == 1.0
    assert "largely independent" in r.assessment
    assert "observed pairs" not in r.assessment


def test_partial_coverage_qualifies_rather_than_hides() -> None:
    r = Redundancy(
        factors=["a", "b", "c", "d"], matrix=[], effective_factors=3.8,
        redundant_pairs=[], dates=100, measured_pairs=5, total_pairs=6,
    )
    assert r.pair_coverage > MIN_PAIR_COVERAGE
    assert "5 of 6 observed pairs" in r.assessment


def test_coverage_is_none_when_there_are_no_pairs() -> None:
    r = Redundancy(
        factors=[], matrix=[], effective_factors=0.0,
        redundant_pairs=[], dates=0, measured_pairs=0, total_pairs=0,
    )
    assert r.pair_coverage is None
