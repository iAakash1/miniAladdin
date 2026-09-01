"""
The ten-gate promotion standard, and the hole that made it ten.

EXP-007 produced a finalist that cleared all eight of the original gates while
posting a deflated-Sharpe probability of 0.0485 and a PBO of 0.929. The eight
gates could pass a selection artifact: `survives_search_size` compares an *IC*
t-statistic against a threshold derived for *Sharpe* selection, and nothing
consulted the two statistics this project already computes for exactly that
question.

These tests pin the fix. They use EXP-007's real recorded numbers, so a
regression that reopens the hole fails against the case that exposed it.
"""

from __future__ import annotations

from src.quant.study.heavy import (
    DEFLATED_SHARPE_MINIMUM, PBO_MAXIMUM, evaluate_gates, selection_verdict,
)

#: The EXP-007 finalist that passed all eight original gates.
#: artifacts/experiments/EXP-007/final_selection.json
EXP007_RANDOM_FOREST = {
    "mean_ic": 0.045674530385196886,
    "ic_t_stat": 3.4702,
    "train_ic_gap": 0.0956,
    "gross_sharpe": 0.4203,
    "net_sharpe": 0.0638,
    "alpha_t_stat": 0.3160,
    "annualised_turnover": 17.72,
}
EXP007_BASELINE_IC = 0.02086784167670688
EXP007_TRIALS = 1029
EXP007_THRESHOLD = 3.38


def _gates(**overrides):
    payload = {
        "candidate": EXP007_RANDOM_FOREST,
        "best_baseline_ic": EXP007_BASELINE_IC,
        "cumulative_trials": EXP007_TRIALS,
        "expected_max_t": EXP007_THRESHOLD,
        "deflated_probability": 0.0485,
        "pbo": 0.9286,
    }
    payload.update(overrides)
    candidate = payload.pop("candidate")
    return evaluate_gates(candidate, **payload)


def test_the_configuration_that_passed_eight_gates_fails_the_standard():
    """The regression case. This model looks promotable and is not."""
    gates = _gates()
    verdict = selection_verdict(gates)

    assert len(gates) == 10
    assert verdict["status"] == "NO PRODUCTION CANDIDATE"
    assert set(verdict["failed"]) == {"deflated_sharpe", "selection_carries_information"}

    # Everything else about it really does pass — that is what made it dangerous.
    passed = {g.name for g in gates if g.passed}
    assert "survives_search_size" in passed, (
        "t = 3.47 clears the 3.38 search-size bar; the point of this test is that "
        "clearing it is not enough"
    )
    assert "net_sharpe" in passed and "alpha_credible" in passed


def test_a_missing_statistic_fails_its_gate_rather_than_skipping_it():
    """A candidate that cannot be deflated has not passed deflation.

    The parameters are optional in the signature because a caller may not have
    computed them. They must not be optional in effect: silently skipping a gate
    when its input is absent is how a safety check becomes decorative.
    """
    gates = {g.name: g for g in _gates(deflated_probability=None, pbo=None)}
    assert gates["deflated_sharpe"].passed is False
    assert gates["selection_carries_information"].passed is False


def test_the_thresholds_are_the_published_ones():
    """Neither threshold was chosen to fit a result."""
    assert DEFLATED_SHARPE_MINIMUM == 0.95      # Bailey & Lopez de Prado
    assert PBO_MAXIMUM == 0.20


def test_a_genuinely_clean_candidate_still_passes():
    """The standard must be passable, or it is not a standard.

    Same candidate, but with a deflated probability and a PBO that a real
    discovery would produce.
    """
    verdict = selection_verdict(_gates(deflated_probability=0.97, pbo=0.12))
    assert verdict["passed"] is True
    assert verdict["status"] == "DEVELOPMENT CANDIDATE"
    # Passing every gate is still not production.
    assert "holdout" in verdict["note"].lower()
