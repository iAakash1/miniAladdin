"""EXP-013: arm construction, the attribution rule, placebo columns, the reproduction gate and the registration guard."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant.study import exp012, exp013

ROOT = Path(__file__).resolve().parents[2]


def synthetic(n_dates=40, n_names=30, seed=5):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-01", periods=n_dates, freq="7D").date
    frame = pd.DataFrame([(d, f"S{i:02d}") for d in dates for i in range(n_names)], columns=["date", "symbol"])
    for col in {*exp013.A1_FEATURES, *exp013.A5_FEATURES}:
        frame[col] = rng.uniform(-1, 1, len(frame))
    frame["in_universe"] = True
    frame[exp013.LABEL] = rng.normal(0, 1, len(frame))
    return frame


def test_counts_match_the_registered_design():
    assert len(exp013.ARMS) == 22
    assert len(exp013.tasks()) == 34
    assert sum(1 for a in exp013.ARMS.values() if a.get("placebo")) == 6


def test_add_arms_add_exactly_their_columns_and_drop_arms_remove_exactly_theirs():
    for name, col in exp013.COLUMNS.items():
        add = exp013.ARMS[f"C_{name}"]["features"]
        drop = exp013.ARMS[f"D_{name}"]["features"]
        assert add == [*exp013.A1_FEATURES, col]
        assert set(exp013.A5_FEATURES) - set(drop) == {col} and len(drop) == len(exp013.A5_FEATURES) - 1
    assert exp013.ARMS["C_P"]["features"] == [*exp013.A1_FEATURES, *[exp013.COLUMNS[n] for n in exp013.PROCESS]]
    assert set(exp013.A5_FEATURES) - set(exp013.ARMS["D_P"]["features"]) == {exp013.COLUMNS[n] for n in exp013.PROCESS}


def test_reference_arms_use_the_exp012_feature_lists_in_the_same_order():
    assert exp013.ARMS["B1"]["features"] == exp012.arm_features("A1")
    assert exp013.ARMS["B5"]["features"] == exp012.arm_features("A5")


def test_every_arm_resolves_to_columns_a_frame_can_hold():
    frame = synthetic()
    for arm, spec in exp013.ARMS.items():
        assert not [f for f in spec["features"] if f not in frame.columns], arm


def test_a_placebo_changes_only_its_declared_columns():
    frame = synthetic()
    out = exp013.arm_frame(frame, "XPperm", 1)
    changed = [c for c in frame.columns if c != "date" and c != "symbol" and not np.array_equal(out[c].to_numpy(), frame[c].to_numpy())]
    assert set(changed) == {exp013.COLUMNS[n] for n in exp013.PROCESS}
    shifted = exp013.arm_frame(frame, "XUshift", 0)
    assert shifted["rel_u_xs"].isna().sum() > 0 and shifted["rel_missing_xs"].equals(frame["rel_missing_xs"])
    assert exp013.arm_frame(frame, "C_u", 0) is frame           # a real arm leaves the frame alone


def _contrast(diff, p, folds):
    return {"mean_diff": diff, "p_one_sided": p, "positive_folds": folds}


def _ic(**over):
    base = {"B1": 0.0149, "B5": 0.0200, "C_P": 0.0150, "D_P": 0.0190, "C_missing": 0.0150, "D_missing": 0.0199, "C_u": 0.0190, "D_u": 0.0160}
    base.update(over)
    return base


def _contrasts(group, perm=0.004, shift=0.002, perm_p=0.02, add_folds=7, add_p=0.01):
    return {f"{group}_vs_perm": _contrast(perm, perm_p, 8), f"{group}_vs_shift": _contrast(shift, 0.2, 6), f"G_{group}": _contrast(0.004, add_p, add_folds)}


def test_attribution_carries_needs_resolution_both_shares_both_placebos_and_folds():
    a = exp013.attribute("U", _ic(), _contrasts("U"))
    assert a["label"] == "CARRIES" and a["add_share"] == pytest.approx((0.0190 - 0.0149) / 0.0051) and a["drop_share"] == pytest.approx((0.0200 - 0.0160) / 0.0051)
    assert exp013.attribute("U", _ic(), _contrasts("U", shift=-0.001))["label"] == "SHARES"          # a placebo is not beaten
    assert exp013.attribute("U", _ic(), _contrasts("U", perm_p=0.4))["label"] == "SHARES"             # permuted-placebo p too large
    assert exp013.attribute("U", _ic(), _contrasts("U", add_folds=5))["label"] == "SHARES"            # too few positive folds
    assert exp013.attribute("U", _ic(C_u=0.0170, D_u=0.0190), _contrasts("U"))["label"] == "SHARES"   # shares between 0.25 and 0.5


def test_a_share_without_a_resolvable_contribution_is_not_a_label():
    assert exp013.attribute("U", _ic(), _contrasts("U", add_p=0.3))["label"] == "NOT_CARRYING"       # large shares of a noisy contribution mean nothing
    assert exp013.attribute("U", _ic(), _contrasts("U", add_p=0.1))["label"] == "NOT_CARRYING"       # the threshold is strict (< 0.10)


def test_attribution_not_carrying_and_no_gain():
    assert exp013.attribute("M", _ic(), _contrasts("M"))["label"] == "NOT_CARRYING"
    assert exp013.attribute("U", _ic(B5=0.0149), _contrasts("U"))["label"] == "NO_GAIN"              # no gain to attribute
    assert exp013.attribute("U", _ic(B5=0.0100), _contrasts("U"))["label"] == "NO_GAIN"


def _gate_inputs(tmp_path, *, b1=0.01488, b5=0.02003, parent=(0.01488, 0.02003)):
    (tmp_path / "experiments" / "EXP-012").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"arm": ["A1", "A5", "A0"], "seed": [0, 0, 0], "mean_rank_ic": [parent[0], parent[1], 0.005]}).to_csv(tmp_path / exp013.PARENT_METRICS, index=False)
    frame = synthetic(n_dates=4, n_names=3)
    pred = frame[["date", "symbol"]].assign(prediction=np.linspace(-1, 1, len(frame)))
    return frame, {("B1", 0): pred, ("B5", 0): pred.copy()}, {("B1", 0): {"mean_rank_ic": b1}, ("B5", 0): {"mean_rank_ic": b5}}


def test_acceptance_gate_passes_aborts_and_rehearses(tmp_path):
    frame, predictions, reports = _gate_inputs(tmp_path)
    assert max(exp013.acceptance_checks(tmp_path, frame, predictions, reports)["reproduction_abs_difference"].values()) < 1e-12
    frame, predictions, reports = _gate_inputs(tmp_path, b5=0.02003 + 1e-6)
    with pytest.raises(RuntimeError, match="do not reproduce"):
        exp013.acceptance_checks(tmp_path, frame, predictions, reports)
    predictions[("B1", 0)].loc[predictions[("B1", 0)].index[0], "prediction"] = np.nan
    with pytest.raises(RuntimeError, match="non-finite"):
        exp013.acceptance_checks(tmp_path, frame, predictions, reports)
    frame, predictions, reports = _gate_inputs(tmp_path, b1=0.9)
    assert exp013.acceptance_checks(tmp_path, frame, predictions, reports, rehearsal=True)["reproduction"].startswith("skipped")


def test_the_registration_document_embeds_the_current_fingerprint():
    doc = ROOT / exp013.PREREG_DOC
    if not doc.exists():
        pytest.skip("not registered yet")
    assert f"Definition fingerprint: `{exp013.definition_fingerprint(ROOT)}`" in doc.read_text(encoding="utf-8")
