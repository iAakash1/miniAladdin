"""EXP-009D: the duplicate-axis hygiene study."""

from pathlib import Path

import pytest

from src.quant.study import exp009b
from src.quant.study import exp009d as D
from src.quant.study import prereg

REPO = Path(__file__).resolve().parents[2]


def test_it_drops_exactly_one_feature_and_keeps_its_twin():
    full, dedup = exp009b.FEATURES, D.DEFINITION["data"]["features_dedup"]
    assert len(full) == 27 and len(dedup) == 26
    assert set(full) - set(dedup) == {D.DROPPED}
    assert D.KEPT in dedup and D.DROPPED not in dedup


def test_the_frozen_experiments_keep_their_27_features():
    assert len(exp009b.FEATURES) == 27 and D.DROPPED in exp009b.FEATURES


@pytest.mark.parametrize("d_ic, se, d_sharpe, ratio, label", [
    (0.0005, 0.0003, 0.02, 1.00, "EQUIVALENT"),
    (0.0030, 0.0003, 0.02, 1.00, "DIFFERENT"),          # mean outside +-0.002
    (0.0010, 0.0020, 0.02, 1.00, "DIFFERENT"),          # interval too wide to call equivalent
    (0.0005, 0.0003, 0.15, 1.00, "DIFFERENT"),          # economics moved
    (0.0005, 0.0003, 0.02, 1.25, "DIFFERENT"),          # turnover moved
])
def test_equivalence_needs_both_ordering_and_economics(d_ic, se, d_sharpe, ratio, label):
    out = D.classify({"mean_difference": d_ic, "hac_se": se}, {"net_sharpe_difference": d_sharpe, "turnover_ratio": ratio})
    assert out["classification"] == label
    assert out["promotion"] == "NOT ASSESSED"


def test_run_study_calls_the_gate_first(tmp_path, monkeypatch):
    for name in D.METHOD_SOURCES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / name).read_text())
    touched = []
    monkeypatch.setattr(exp009b, "load_frame", lambda *a, **k: touched.append(1))
    with pytest.raises(prereg.PreregistrationError):
        D.run_study(tmp_path)
    assert touched == []


def test_the_frozen_panel_really_holds_a_perfect_anticorrelation():
    import pandas as pd
    path = REPO / exp009b.FRAME_CACHE
    if not path.exists():
        pytest.skip("frozen panel not built locally")
    frame = pd.read_parquet(path, columns=["in_universe", D.DROPPED, D.KEPT])
    rows = frame[frame["in_universe"]]
    assert abs(float(rows[[D.DROPPED, D.KEPT]].corr().iloc[0, 1])) >= 0.99999
