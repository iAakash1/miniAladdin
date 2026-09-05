"""A completed experiment must not be listed as unreadable.

EXP-007 is the experiment this product is built around: its recorded verdict
is NO PRODUCTION CANDIDATE and its holdout is untouched. It does not write
`metrics.json` — a hyperparameter search writes `search.json` and records its
verdict in a selection artifact — and the registry listing therefore showed it
in the State column as "unreadable", which is the word for a system failure.

"No candidate" and "cannot be read" are different statements and the second
one is false.
"""

import json

import pytest

from src.services import quant_service


def _rows(out):
    return out["experiments"] if isinstance(out, dict) and "experiments" in out else out


def test_exp_007_is_complete_not_unreadable():
    row = next(r for r in _rows(quant_service.experiments())
               if r["experiment_id"] == "EXP-007")
    assert row["status"] == "complete", (
        "the experiment carrying the NO PRODUCTION CANDIDATE result is listed "
        f"as {row['status']!r}"
    )
    assert row["artifact"] == "selection", "the artifact shape is not recorded"


def test_the_recorded_verdict_is_carried_verbatim():
    """The artifact is the record. Nothing restates or softens it."""
    row = next(r for r in _rows(quant_service.experiments())
               if r["experiment_id"] == "EXP-007")
    assert row["verdict"] == "NO PRODUCTION CANDIDATE"
    assert row["verdict_passed"] is False
    # And it matches the artifact on disk exactly.
    with open("artifacts/experiments/EXP-007/final_selection.json") as fh:
        recorded = json.load(fh)["verdict"]
    assert row["verdict"] == recorded["status"]
    assert row["verdict_passed"] == recorded["passed"]


def test_the_holdout_is_reported_untouched():
    """"No candidate" and "holdout unspent" are separate load-bearing facts."""
    row = next(r for r in _rows(quant_service.experiments())
               if r["experiment_id"] == "EXP-007")
    assert row["holdout_touched"] is False


def test_an_experiment_with_neither_artifact_is_still_unreadable(tmp_path):
    """The honest status survives. This is not a blanket 'assume complete'."""
    (tmp_path / "EXP-999").mkdir()
    rows = _rows(quant_service.experiments(root=tmp_path))
    row = next(r for r in rows if r["experiment_id"] == "EXP-999")
    assert row["status"] == "unreadable"
    assert row["detail"] == "no metrics.json"


def test_no_experiment_is_reported_as_a_production_candidate():
    """The firewall, asserted at the listing layer."""
    for row in _rows(quant_service.experiments()):
        assert row.get("verdict_passed") is not True, (
            f"{row['experiment_id']} is listed as having passed its gates"
        )
