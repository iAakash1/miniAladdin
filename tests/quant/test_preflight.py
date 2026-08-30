"""
Pre-holdout gates — every one must be able to refuse.

A gate that cannot fail is not a gate. Each test here constructs the condition
the gate exists to catch and asserts it blocks, then constructs the clean case
and asserts it passes.
"""

from __future__ import annotations

import json
from datetime import date as Date
from pathlib import Path

import pytest

from src.quant.audit.preflight import (
    Check,
    PreflightReport,
    check_contract,
    check_folds_chronological,
    check_holdout_untouched,
    check_no_random_split,
    check_regime_balance,
    compute_fingerprint,
)
from src.quant.models.registry import (
    PRODUCTION_THRESHOLDS,
    ModelEntry,
    ModelRegistry,
    PromotionRefused,
)


def _study(*, holdout_start="2025-08-28", last_validation_end="2025-05-09",
           gap=26, horizon=21, embargo=5) -> dict:
    return {
        "labels": {
            "fwd_rank_21": {
                "walk_forward_plan": {
                    "holdout_start": holdout_start,
                    "holdout_end": "2026-08-28",
                    "label_horizon_sessions": horizon,
                    "embargo_sessions": embargo,
                    "folds": [
                        {"index": 0, "train_start": "2014-04-01", "train_end": "2023-01-01",
                         "validation_start": "2023-02-10", "validation_end": "2024-02-01",
                         "gap_sessions": gap},
                        {"index": 1, "train_start": "2014-04-01", "train_end": "2024-03-01",
                         "validation_start": "2024-04-10", "validation_end": last_validation_end,
                         "gap_sessions": gap},
                    ],
                }
            }
        },
        "regimes": {"rules": {"distribution": {"low_vol_bull": 426, "stress": 34}}},
    }


# ── holdout isolation ───────────────────────────────────────────────────────


def test_a_fold_reaching_into_the_holdout_blocks():
    report = PreflightReport()
    check_holdout_untouched(_study(last_validation_end="2025-12-01"), report)
    failed = [c for c in report.checks if c.name == "no_fold_reaches_holdout"]
    assert failed and not failed[0].passed and failed[0].blocking


def test_folds_ending_before_the_holdout_pass():
    report = PreflightReport()
    check_holdout_untouched(_study(), report)
    assert all(c.passed for c in report.checks)


def test_labels_disagreeing_on_the_holdout_start_block():
    study = _study()
    study["labels"]["fwd_ret_21"] = json.loads(json.dumps(study["labels"]["fwd_rank_21"]))
    study["labels"]["fwd_ret_21"]["walk_forward_plan"]["holdout_start"] = "2025-01-01"
    report = PreflightReport()
    check_holdout_untouched(study, report)
    consistency = [c for c in report.checks if c.name == "holdout_range_consistent"][0]
    assert not consistency.passed


# ── fold geometry ───────────────────────────────────────────────────────────


def test_an_insufficient_purge_gap_blocks():
    report = PreflightReport()
    check_folds_chronological(_study(gap=3), report)
    check = [c for c in report.checks if c.name == "folds_chronological_and_purged"][0]
    assert not check.passed and check.blocking


def test_a_full_gap_passes():
    report = PreflightReport()
    check_folds_chronological(_study(gap=26), report)
    assert report.checks[0].passed


# ── random splitting ────────────────────────────────────────────────────────


def test_random_splitter_scan_passes_on_the_real_package():
    """The research path must contain no random splitter.

    Detection is by AST: the first implementation used a substring scan and
    flagged the audit module's own banned-token list.
    """
    report = PreflightReport()
    check_no_random_split(report)
    check = report.checks[0]
    assert check.passed, check.detail
    assert check.evidence["scanned"] > 20


def test_random_splitter_scan_catches_a_real_import(tmp_path):
    module = tmp_path / "offender.py"
    module.write_text(
        "from sklearn.model_selection import train_test_split\n"
        "def go(x, y):\n    return train_test_split(x, y)\n",
        encoding="utf-8",
    )
    report = PreflightReport()
    check_no_random_split(report, root=tmp_path)
    assert not report.checks[0].passed


def test_random_splitter_scan_ignores_a_mention_in_a_docstring(tmp_path):
    module = tmp_path / "clean.py"
    module.write_text(
        '"""We deliberately do not use train_test_split or KFold here."""\n'
        "VALUE = 1\n",
        encoding="utf-8",
    )
    report = PreflightReport()
    check_no_random_split(report, root=tmp_path)
    assert report.checks[0].passed


# ── contract ────────────────────────────────────────────────────────────────


def test_a_missing_contract_blocks(tmp_path):
    report = PreflightReport()
    assert check_contract(tmp_path / "absent.md", report) is None
    assert not report.checks[0].passed and report.checks[0].blocking


def test_an_incomplete_contract_blocks(tmp_path):
    path = tmp_path / "c.md"
    path.write_text("# HOLDOUT RANGE\nPRIMARY CANDIDATE: x\n", encoding="utf-8")
    report = PreflightReport()
    check_contract(path, report)
    complete = [c for c in report.checks if c.name == "contract_complete"][0]
    assert not complete.passed


def test_an_unarmed_contract_blocks_even_when_complete():
    """Section presence is weak; a contract can name every heading and register
    no candidate. The ARMED marker is the strong test."""
    report = PreflightReport()
    check_contract(Path("docs/HOLDOUT_CONTRACT.md"), report)
    complete = [c for c in report.checks if c.name == "contract_complete"][0]
    armed = [c for c in report.checks if c.name == "contract_armed"][0]
    assert complete.passed
    assert not armed.passed, "the shipped contract must not be armed"


# ── advisories ──────────────────────────────────────────────────────────────


def test_thin_regimes_warn_without_blocking():
    report = PreflightReport()
    check_regime_balance(_study(), report, minimum=60)
    check = report.checks[0]
    assert not check.passed
    assert not check.blocking, "regime imbalance bounds a claim; it does not invalidate one"
    assert report.ready or True  # advisory alone must not set blocking failures
    assert not report.blocking_failures


# ── fingerprint ─────────────────────────────────────────────────────────────


def test_fingerprint_changes_when_anything_frozen_changes():
    base = dict(
        study={"dataset": {"dataset_version": "ds-1", "content_hash": "h"},
               "features_used": ["a", "b"], "seed": 0},
        contract_sha="c", commit="g",
    )
    original = compute_fingerprint(**base)
    assert compute_fingerprint(**base) == original

    moved = dict(base)
    moved["study"] = {**base["study"], "features_used": ["a", "b", "c"]}
    assert compute_fingerprint(**moved) != original

    moved = dict(base, contract_sha="different")
    assert compute_fingerprint(**moved) != original

    moved = dict(base, commit="other")
    assert compute_fingerprint(**moved) != original


def test_fingerprint_ignores_feature_order():
    a = compute_fingerprint(
        study={"dataset": {}, "features_used": ["b", "a"], "seed": 0},
        contract_sha="c", commit="g")
    b = compute_fingerprint(
        study={"dataset": {}, "features_used": ["a", "b"], "seed": 0},
        contract_sha="c", commit="g")
    assert a == b


# ── production thresholds ───────────────────────────────────────────────────


def _complete_entry(**holdout) -> ModelEntry:
    """An entry carrying every required evidence block, and validation numbers
    that clear `CANDIDATE_THRESHOLDS`.

    The candidate bars have to be satisfied here, otherwise these tests would be
    asserting the *validation*-side refusal while claiming to test the holdout
    thresholds — and would keep passing if the production thresholds were
    deleted entirely.
    """
    return ModelEntry(
        model_id="gb", version="1.0", task="regression", label="fwd_rank_21",
        walk_forward={"mean_ic": 0.03, "ic_t_stat": 2.8},
        validation_methodology="8-fold expanding",
        baseline_comparison={"beat_best_baseline": True},
        backtest={"net_sharpe": 0.03, "gross_sharpe": 0.51},
        factor_attribution={"alpha_t_stat": 0.44}, regime_stability={"by_regime": []},
        multiple_testing={"trials": 46}, leakage_evidence={"probe": "pass"},
        stability_evidence={"fold_positive": 0.75}, turnover_evidence={"annualised": 20.7},
        reproducibility={"seed": 0}, holdout_metrics=holdout,
    )


def test_candidate_thresholds_are_checked_before_the_holdout_ones(tmp_path):
    """A model that fails on validation never reaches the holdout thresholds.

    Ordering matters: the holdout bars read `holdout_metrics`, and consulting
    them for a model whose validation numbers are already negative would imply
    the holdout had been spent on it.
    """
    registry = ModelRegistry(tmp_path)
    entry = registry.register(_complete_entry(
        holdout_ic_t_stat=2.7, holdout_net_sharpe=0.5, beats_best_baseline=True,
        sign_matches_validation=True, cost_share_of_gross=0.2,
        deflated_sharpe_probability=0.99,
    ))
    entry.backtest = {"net_sharpe": -0.60, "gross_sharpe": -0.28}
    with pytest.raises(PromotionRefused, match="candidate thresholds"):
        registry.promote(entry.key, "production")
    assert entry.status == "experimental"


def test_complete_evidence_still_fails_on_the_numbers(tmp_path):
    """The two refusals are distinct: evidence existing, and evidence passing."""
    registry = ModelRegistry(tmp_path)
    entry = registry.register(_complete_entry(
        holdout_ic_t_stat=2.7, holdout_net_sharpe=0.03, beats_best_baseline=True,
        sign_matches_validation=True,
        cost_share_of_gross=0.91,              # above the 0.75 ceiling
        deflated_sharpe_probability=0.0121,    # below the 0.95 floor
    ))
    with pytest.raises(PromotionRefused, match="production thresholds"):
        registry.promote(entry.key, "production")
    assert set(entry.thresholds_not_met()) == {
        "cost_share_of_gross", "deflated_sharpe_probability"
    }


def test_an_unrecorded_threshold_counts_as_unmet(tmp_path):
    """Absent evidence is not passing evidence."""
    registry = ModelRegistry(tmp_path)
    entry = registry.register(_complete_entry(holdout_ic_t_stat=3.0))
    unmet = entry.thresholds_not_met()
    assert unmet["holdout_net_sharpe"] == "not recorded"
    with pytest.raises(PromotionRefused):
        registry.promote(entry.key, "production")


def test_a_model_clearing_every_threshold_is_promotable(tmp_path):
    registry = ModelRegistry(tmp_path)
    entry = registry.register(_complete_entry(
        holdout_ic_t_stat=3.1, holdout_net_sharpe=0.62, beats_best_baseline=True,
        sign_matches_validation=True, cost_share_of_gross=0.30,
        deflated_sharpe_probability=0.97,
    ))
    registry.promote(entry.key, "production", reason="cleared holdout")
    assert entry.status == "production"


def test_a_negated_holdout_sign_blocks_promotion(tmp_path):
    """An equal-and-opposite result is not a success at any magnitude."""
    registry = ModelRegistry(tmp_path)
    entry = registry.register(_complete_entry(
        holdout_ic_t_stat=3.1, holdout_net_sharpe=0.62, beats_best_baseline=True,
        sign_matches_validation=False, cost_share_of_gross=0.30,
        deflated_sharpe_probability=0.97,
    ))
    with pytest.raises(PromotionRefused):
        registry.promote(entry.key, "production")


def test_every_threshold_states_why_it_exists():
    for name, rule in PRODUCTION_THRESHOLDS.items():
        assert rule.get("why"), f"{name} has no stated rationale"
