"""
`evaluate_batch` must checkpoint each configuration as it lands.

The regression this guards: a tune stage is one `evaluate_specs` call over
several hundred specs. When the checkpoint was written only after that call
returned, an interruption six hours in lost six hours — while the module
docstring promised the opposite. `on_complete` fires per spec, so the fix is to
write from there.

Two properties are asserted, and the second matters as much as the first:

1. every configuration reaches disk exactly once, and
2. the RETURNED list is in declared spec order, not completion order.

Completion order depends on the worker count. `rank_candidates` and
`competitive_families` sort by value, but ties would break differently, and the
PBO matrix downstream partitions columns in insertion order — so a result that
changed with `--workers` would be a real defect, not a cosmetic one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.pit.calendar import TradingCalendar
from src.quant.study.heavy import Checkpoint, SearchContext, evaluate_batch


class _Definition:
    seed = 0
    step_sessions = 5
    validation_sessions = 60
    min_train_sessions = 120
    embargo_sessions = 5
    holdout_sessions = 60

    @property
    def start(self):
        return pd.Timestamp("2015-01-02").date()


def _panel() -> tuple[pd.DataFrame, list]:
    """A small synthetic panel with a real (weak) relationship in it."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2015-01-02", periods=400)
    symbols = [f"S{i:02d}" for i in range(40)]
    rows = []
    for date in dates:
        signal = rng.normal(size=len(symbols))
        noise = rng.normal(size=len(symbols))
        for index, symbol in enumerate(symbols):
            rows.append({
                "date": date.date(),
                "symbol": symbol,
                "in_universe": True,
                "mom_252_21_xs": float(signal[index]),
                "vol_63_xs": float(noise[index]),
                "fwd_rank_21": float(0.2 * signal[index] + noise[index]),
            })
    frame = pd.DataFrame(rows)
    return frame, TradingCalendar.from_dates(dates.date)


def test_every_configuration_is_checkpointed_once_and_returned_in_order(tmp_path):
    frame, calendar = _panel()
    features = ["mom_252_21_xs", "vol_63_xs"]

    class _Manifest:
        pass

    context = SearchContext(
        frame=frame, manifest=_Manifest(), calendar=calendar,
        available_features=features,
    )
    # Bypass the arm registry: this test is about batching, not arm membership.
    context.arm_cache["TEST"] = features

    checkpoint = Checkpoint(tmp_path / "configs.jsonl")
    planned = [
        (f"cfg-{i:02d}", "ridge", {"alpha": float(10 ** (i - 2))}, "TEST", "fwd_rank_21")
        for i in range(6)
    ]

    streamed: list[str] = []
    results = evaluate_batch(
        planned, context, _Definition(), workers=2, stage="screen",
        checkpoint=checkpoint, on_result=lambda r: streamed.append(r.config_id),
    )

    on_disk = [line for line in checkpoint.path.read_text().splitlines() if line.strip()]
    ids_on_disk = [r.config_id for r in checkpoint.load().values()]

    assert len(on_disk) == len(planned), "every configuration is written exactly once"
    assert set(ids_on_disk) == {p[0] for p in planned}
    assert sorted(streamed) == sorted(p[0] for p in planned), "each is reported once"

    # The returned order is the declared order, whatever order they finished in.
    assert [r.config_id for r in results] == [p[0] for p in planned]


def test_resume_skips_what_is_recorded(tmp_path):
    """A reloaded checkpoint is keyed by config id, so a resume cannot double-count."""
    frame, calendar = _panel()
    features = ["mom_252_21_xs", "vol_63_xs"]

    class _Manifest:
        pass

    context = SearchContext(frame=frame, manifest=_Manifest(), calendar=calendar,
                            available_features=features)
    context.arm_cache["TEST"] = features
    checkpoint = Checkpoint(tmp_path / "configs.jsonl")
    planned = [("cfg-a", "ridge", {"alpha": 1.0}, "TEST", "fwd_rank_21")]

    evaluate_batch(planned, context, _Definition(), workers=1, stage="screen",
                   checkpoint=checkpoint)
    first = checkpoint.load()

    evaluate_batch(planned, context, _Definition(), workers=1, stage="screen",
                   checkpoint=checkpoint)
    second = checkpoint.load()

    assert set(first) == set(second) == {"cfg-a"}
    assert second["cfg-a"].mean_ic == first["cfg-a"].mean_ic, (
        "the same configuration on the same folds must reproduce exactly"
    )


def test_a_torn_final_line_costs_one_configuration_not_the_file(tmp_path):
    """Append-only means a crash mid-write loses a line, never the history."""
    path = tmp_path / "configs.jsonl"
    checkpoint = Checkpoint(path)
    with path.open("w", encoding="utf-8") as handle:
        handle.write('{"config_id": "a", "stage": "screen", "family": "ridge", '
                     '"params": {}, "arm": "T", "target": "y", "feature_count": 2, '
                     '"ok": true, "mean_ic": 0.01}\n')
        handle.write('{"config_id": "b", "stage": "screen", "fam')  # crash here

    loaded = checkpoint.load()
    assert set(loaded) == {"a"}, "the readable line survives; the torn one is skipped"
    assert loaded["a"].mean_ic == 0.01


def test_a_line_missing_a_required_field_is_skipped_not_fatal(tmp_path):
    """A checkpoint from an older schema must not take down the whole resume.

    `from_dict` returns None for an unusable record rather than raising. Losing
    one configuration to a schema change costs one refit; raising here would
    cost every hour the checkpoint was protecting.
    """
    path = tmp_path / "configs.jsonl"
    checkpoint = Checkpoint(path)
    path.write_text(
        # valid
        '{"config_id": "a", "stage": "screen", "family": "ridge", "params": {}, '
        '"arm": "T", "target": "y", "feature_count": 2, "ok": true}\n'
        # parses as JSON, but has no feature_count — an older writer
        '{"config_id": "b", "stage": "screen", "family": "ridge", "params": {}, '
        '"arm": "T", "target": "y", "ok": true}\n',
        encoding="utf-8",
    )
    loaded = checkpoint.load()
    assert set(loaded) == {"a"}
