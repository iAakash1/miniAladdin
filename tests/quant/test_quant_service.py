"""
Quant service — the product's read layer, and the verdict it is not allowed to lie about.

The tests that matter here are the refusals. A research platform's failure mode
is not a wrong number on a chart; it is a page that renders a research finding
in the shape of a product promise. So: `production_status` must say NO_MODEL
while the registry is empty of production entries no matter how good a
leaderboard looks, `symbol_view` must refuse to produce a prediction, and
`verdict` must agree with the promotion gates by construction.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services import quant_service as service


def _metrics(**overrides):
    base = {
        "experiment": {
            "experiment_id": "EXP-TEST",
            "objective": "a test",
            "targets": ["fwd_rank_21"],
            "primary_target": "fwd_rank_21",
            "model_count": 2,
            "declared_evaluations": 2,
            "cumulative_evaluations": 82,
            "execution_lag_periods": 1,
        },
        "fingerprint": "abc123",
        "generated_at": "2026-08-30T00:00:00Z",
        "git_commit": "deadbeef",
        "dataset": {"dataset_version": "ds-test", "rows": 100, "symbols": 5, "dates": 20},
        "features_used": ["mom_21_xs"],
        "integrity": {"clean": True},
        "negative_controls": {"blocking_failed": []},
        "holdout": {"touched": False},
        "labels": {
            "fwd_rank_21": {
                "leaderboard": [
                    {"model_id": "random_forest", "kind": "tree", "mean_ic": 0.024,
                     "ic_t_stat": 1.91, "train_mean_ic": 0.31, "train_ic_gap": 0.28,
                     "fold_ic_positive_rate": 0.75},
                    {"model_id": "baseline_momentum", "kind": "baseline", "mean_ic": 0.016,
                     "ic_t_stat": 0.88, "train_mean_ic": 0.009, "train_ic_gap": -0.007,
                     "fold_ic_positive_rate": 0.75},
                ],
                "backtests": {
                    "random_forest": {"metrics": {"gross_sharpe": -0.28, "net_sharpe": -0.60}},
                },
                "significance": {
                    "random_forest": {
                        "deflated_sharpe": {"deflated_probability": 0.0, "trials": 80},
                    },
                },
            }
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def artifact(tmp_path: Path) -> Path:
    directory = tmp_path / "EXP-TEST"
    directory.mkdir()
    (directory / "metrics.json").write_text(json.dumps(_metrics()), encoding="utf-8")
    return tmp_path


# ── the honest empty state ──────────────────────────────────────────────────


def test_production_status_is_no_model_when_nothing_is_promoted():
    result = service.production_status()
    assert result["deployment_status"] in {"NO_MODEL", "EXPERIMENTAL"}
    assert result["production"] == 0
    assert result["serving_predictions"] is False
    assert "No production-grade predictive model" in result["message"] or result[
        "deployment_status"] == "EXPERIMENTAL"


def test_symbol_view_refuses_to_invent_a_prediction():
    """The single most important refusal in the product."""
    view = service.symbol_view("AAPL")
    assert view["prediction"] is None
    assert view["model"] is None
    assert view["deployment_status"] != "PRODUCTION"
    assert "No production-approved model" in view["disclosure"]


def test_symbol_view_normalises_the_symbol():
    assert service.symbol_view("aapl")["symbol"] == "AAPL"


def test_missing_experiment_reports_a_remedy_not_an_empty_page():
    result = service.experiment("EXP-NOPE", root="/nonexistent")
    assert result["status"] == "unavailable"
    assert "python -m src.quant.study.run" in result["remedy"]


# ── the verdict cannot outrun the evidence ──────────────────────────────────


def test_a_negative_gross_sharpe_is_untradeable_however_good_the_ic():
    """EXP-004's random_forest: positive IC, loses money before costs."""
    result = service.verdict({
        "mean_ic": 0.024, "ic_t_stat": 2.5, "gross_sharpe": -0.28,
        "net_sharpe": -0.60, "train_ic_gap": 0.02, "beats_best_baseline": True,
    })
    assert result["label"] == "UNTRADEABLE"
    assert "does not survive becoming a book" in result["reason"]


def test_a_large_train_gap_is_overfit_before_anything_else_is_considered():
    result = service.verdict({
        "mean_ic": 0.022, "ic_t_stat": 2.09, "gross_sharpe": 1.5,
        "net_sharpe": 1.2, "train_ic_gap": 0.72, "beats_best_baseline": True,
    })
    assert result["label"] == "OVERFIT"
    assert "0.72" in result["reason"] or "+0.720" in result["reason"]


def test_a_failed_blocking_control_rejects_everything():
    result = service.verdict(
        {"mean_ic": 0.30, "ic_t_stat": 12.0, "gross_sharpe": 3.0, "net_sharpe": 2.8,
         "train_ic_gap": 0.01, "beats_best_baseline": True},
        controls_passed=False,
    )
    assert result["label"] == "REJECTED"
    assert "manufactures" in result["reason"]


def test_failed_integrity_rejects_everything():
    result = service.verdict(
        {"mean_ic": 0.30, "ic_t_stat": 12.0, "gross_sharpe": 3.0, "net_sharpe": 2.8,
         "train_ic_gap": 0.01, "beats_best_baseline": True},
        integrity_clean=False,
    )
    assert result["label"] == "REJECTED"


def test_robust_is_unreachable_while_the_holdout_is_locked():
    """Nothing measured in development may earn that word."""
    strong = {
        "mean_ic": 0.05, "ic_t_stat": 3.4, "gross_sharpe": 1.4,
        "net_sharpe": 1.1, "train_ic_gap": 0.02, "beats_best_baseline": True,
    }
    assert service.verdict(strong, holdout_spent=False)["label"] == "PROMISING"
    assert service.verdict(strong, holdout_spent=True)["label"] == "ROBUST"


def test_a_measured_but_weak_model_is_experimental_and_says_what_failed():
    """Tradeable, not overfit, but too weak to be a candidate.

    Both Sharpes are positive so UNTRADEABLE does not apply and the gap is
    small so OVERFIT does not either — this isolates the ordinary case, where
    the model is simply not good enough and the reason names which bars it
    missed.
    """
    result = service.verdict({
        "mean_ic": 0.01, "ic_t_stat": 1.1, "gross_sharpe": 0.2,
        "net_sharpe": 0.05, "train_ic_gap": 0.03, "beats_best_baseline": False,
    })
    assert result["label"] == "EXPERIMENTAL"
    assert "ic_t_stat" in result["reason"]
    assert "beats_best_baseline" in result["reason"]


def test_untradeable_outranks_experimental():
    """A model that loses money is named for that, not for its weak t-statistic.

    Ordering matters: 'EXPERIMENTAL' reads as 'promising but early', which is
    the wrong thing to say about a strategy with a negative gross Sharpe.
    """
    result = service.verdict({
        "mean_ic": 0.01, "ic_t_stat": 1.1, "gross_sharpe": -0.2,
        "net_sharpe": -0.6, "train_ic_gap": 0.03, "beats_best_baseline": False,
    })
    assert result["label"] == "UNTRADEABLE"


def test_the_verdict_thresholds_come_from_the_promotion_gates():
    """A card and a promotion refusal must never disagree.

    If someone loosens the UI threshold without touching the registry, this
    fails — which is the point. The constants have exactly one home.
    """
    from src.quant.models.registry import CANDIDATE_THRESHOLDS

    minimum = CANDIDATE_THRESHOLDS["ic_t_stat"]["minimum"]
    just_under = service.verdict({
        "mean_ic": 0.02, "ic_t_stat": minimum - 0.01, "gross_sharpe": 1.0,
        "net_sharpe": 0.8, "train_ic_gap": 0.01, "beats_best_baseline": True,
    })
    just_over = service.verdict({
        "mean_ic": 0.02, "ic_t_stat": minimum + 0.01, "gross_sharpe": 1.0,
        "net_sharpe": 0.8, "train_ic_gap": 0.01, "beats_best_baseline": True,
    })
    assert just_under["label"] == "EXPERIMENTAL"
    assert just_over["label"] == "PROMISING"


def test_every_verdict_exposes_its_gates_for_rendering():
    result = service.verdict({
        "mean_ic": 0.02, "ic_t_stat": 1.5, "gross_sharpe": -0.3,
        "net_sharpe": -0.6, "train_ic_gap": 0.05, "beats_best_baseline": False,
    })
    for gate in ("ic_t_stat", "gross_sharpe", "net_sharpe", "beats_best_baseline"):
        assert gate in result["gates"]
        assert "observed" in result["gates"][gate]
        assert "required" in result["gates"][gate]


# ── artifacts ───────────────────────────────────────────────────────────────


def test_an_experiment_renders_with_a_verdict_on_every_row(artifact):
    result = service.experiment("EXP-TEST", root=artifact)
    assert result["status"] == "ok"
    assert len(result["leaderboard"]) == 2
    for row in result["leaderboard"]:
        assert row["verdict"]["label"] in {
            "REJECTED", "OVERFIT", "UNTRADEABLE", "EXPERIMENTAL", "PROMISING", "ROBUST",
        }


def test_the_baseline_comparison_uses_the_best_baseline(artifact):
    result = service.experiment("EXP-TEST", root=artifact)
    rows = {r["model_id"]: r for r in result["leaderboard"]}
    assert rows["random_forest"]["beats_best_baseline"] is True   # 0.024 > 0.016
    assert rows["baseline_momentum"]["beats_best_baseline"] is False  # ties itself


def test_the_deflated_sharpe_is_read_from_its_actual_nesting(artifact):
    """A misread path yields None, which renders as an em dash.

    That is the dangerous shape: a multiple-testing correction that was never
    found looks exactly like one that was never computed, and the page shows a
    blank column either way. So the value is asserted, not merely its presence.
    """
    result = service.experiment("EXP-TEST", root=artifact)
    row = next(r for r in result["leaderboard"] if r["model_id"] == "random_forest")
    assert row["deflated_sharpe_probability"] == 0.0
    assert row["deflated_sharpe_trials"] == 80


def test_void_experiments_are_listed_not_hidden():
    listing = service.experiments()
    ids = {e["experiment_id"]: e for e in listing["experiments"]}
    assert "EXP-002" in ids, "a void study must remain visible"
    assert ids["EXP-002"]["void"] is True
    assert "VOID" in ids["EXP-002"]["void_reason"]


def test_firewall_status_reports_the_lock():
    status = service.firewall_status()
    assert status["contract_armed"] is False
    assert "LOCKED" in status["headline"]
