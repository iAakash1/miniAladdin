"""
Feature audit — provenance and leakage surface for every registered feature.

Generated from the registry rather than written by hand, so it cannot drift
from the code it describes. Each entry answers the questions an auditor asks
before a holdout is spent:

* where does the raw data come from, and what is its point-in-time class?
* how far back does one value reach, and when does it become available?
* is anything *fitted* to produce it — and if so, inside what scope?
* what would a leak look like here, and which test would catch it?

The `leakage_mechanism` field is deliberately populated even for features
believed safe. "None known" is a weaker claim than silence, and it puts the
burden on the next reader to disprove rather than to notice an absence.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from src.quant.datasets import catalog as dataset_catalog
from src.quant.features.registry import REGISTRY, FeatureGroup

#: Which raw dataset each feature group ultimately reads from.
_GROUP_SOURCES: dict[FeatureGroup, tuple[str, ...]] = {
    FeatureGroup.PRICE: ("dolthub_stocks_ohlcv", "dolthub_stocks_split", "dolthub_stocks_dividend"),
    FeatureGroup.VOLATILITY: ("dolthub_stocks_ohlcv", "dolthub_stocks_split", "dolthub_stocks_dividend"),
    FeatureGroup.VOLUME: ("dolthub_stocks_ohlcv",),
    FeatureGroup.STRUCTURE: ("dolthub_stocks_ohlcv", "dolthub_stocks_split", "dolthub_stocks_dividend"),
    FeatureGroup.OPTIONS: ("dolthub_options_volatility_history", "dolthub_options_chain_daily"),
    FeatureGroup.FUNDAMENTAL: ("dolthub_earnings_eps_history", "dolthub_earnings_calendar"),
    FeatureGroup.MACRO: ("dolthub_rates_us_treasury", "dolthub_stocks_ohlcv"),
    FeatureGroup.CROSS_SECTIONAL: ("dolthub_stocks_ohlcv_monthly",),
}

#: How each group is produced, and therefore what could go wrong.
_GROUP_MECHANICS: dict[FeatureGroup, dict[str, Any]] = {
    FeatureGroup.PRICE: {
        "stage": "per_symbol_rolling",
        "requires_fitting": False,
        "fit_scope": None,
        "leakage_mechanism": (
            "A centred window, a negative shift, or min_periods below the full "
            "window would let a later bar reach an earlier row."
        ),
        "leakage_test": "tests/quant/test_leakage.py::test_no_registered_feature_depends_on_the_future",
    },
    FeatureGroup.VOLATILITY: {
        "stage": "per_symbol_rolling",
        "requires_fitting": False,
        "fit_scope": None,
        "leakage_mechanism": "As price: a forward-looking window.",
        "leakage_test": "tests/quant/test_leakage.py::test_no_registered_feature_depends_on_the_future",
    },
    FeatureGroup.VOLUME: {
        "stage": "per_symbol_rolling",
        "requires_fitting": False,
        "fit_scope": None,
        "leakage_mechanism": (
            "As price. Note amihud_21 is a RATIO of two perturbed inputs, so a "
            "uniform-scale leakage probe cancels inside it and proves nothing; "
            "the probe uses distinct per-column factors."
        ),
        "leakage_test": "tests/quant/test_leakage.py::test_no_registered_feature_depends_on_the_future",
    },
    FeatureGroup.STRUCTURE: {
        "stage": "per_symbol_rolling",
        "requires_fitting": False,
        "fit_scope": None,
        "leakage_mechanism": "As price.",
        "leakage_test": "tests/quant/test_leakage.py::test_no_registered_feature_depends_on_the_future",
    },
    FeatureGroup.OPTIONS: {
        "stage": "asof_join",
        "requires_fitting": False,
        "fit_scope": None,
        "leakage_mechanism": (
            "THREE, all realised at least once. (1) merge_asof discards the left "
            "index, so writing results back positionally attaches values to the "
            "wrong rows — this occurred and was fixed. (2) direction='nearest' "
            "would match a Monday to Tuesday's snapshot. (3) an unbounded "
            "forward-fill would turn a data gap into a confident flat signal; "
            "capped at 21 days."
        ),
        "leakage_test": "tests/quant/test_earnings_options.py::test_asof_option_join_aligns_to_the_original_row_order",
    },
    FeatureGroup.FUNDAMENTAL: {
        "stage": "asof_join",
        "requires_fitting": False,
        "fit_scope": None,
        "leakage_mechanism": (
            "The largest in the corpus. eps_history is keyed by period end with "
            "no announcement date; used raw it inserts a quarter's result ~30 "
            "days before it was public (measured on AAPL). Closed by joining to "
            "earnings_calendar and honouring the before-open / after-close "
            "session rule. Also subject to the merge_asof alignment defect above."
        ),
        "leakage_test": "tests/quant/test_earnings_options.py::test_attached_features_never_precede_availability",
    },
    FeatureGroup.MACRO: {
        "stage": "date_broadcast",
        "requires_fitting": False,
        "fit_scope": None,
        "leakage_mechanism": (
            "The Treasury curve is published after the close of the day it "
            "describes, so a same-day read is a one-session leak. Applied once in "
            "lagged_macro_frame. Market-regime features are rolling windows over "
            "the daily cross-sectional mean and must be computed BEFORE the "
            "observation stride — computing them after would make a 252-row "
            "window span 1,260 sessions."
        ),
        "leakage_test": "tests/quant/test_leakage.py::test_no_registered_feature_depends_on_the_future",
    },
    FeatureGroup.CROSS_SECTIONAL: {
        "stage": "per_date_rank",
        "requires_fitting": True,
        "fit_scope": "per_date_within_point_in_time_universe",
        "leakage_mechanism": (
            "Ranking against whatever rows happen to be loaded rather than "
            "against point-in-time universe membership. That is both "
            "irreproducible and quietly survivorship-biased, since the names "
            "that load are the ones that still have data."
        ),
        "leakage_test": "tests/quant/test_leakage.py::test_cross_sectional_values_ignore_non_members",
    },
}


def _source_entries(group: FeatureGroup) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for dataset_id in _GROUP_SOURCES.get(group, ()):
        try:
            spec = dataset_catalog.get(dataset_id)
        except KeyError:
            continue
        out.append(
            {
                "dataset_id": dataset_id,
                "repository": spec.repository,
                "table": spec.table,
                "point_in_time_class": spec.point_in_time.value,
                "survivorship_class": spec.survivorship.value,
                "admissible_as_feature": spec.historical_training_allowed,
            }
        )
    return out


def audit_feature(name: str, *, cross_sectional: bool = False) -> dict[str, Any]:
    """One feature's full provenance and leakage surface."""
    definition = REGISTRY.get(name)
    group = FeatureGroup.CROSS_SECTIONAL if cross_sectional else definition.group
    mechanics = _GROUP_MECHANICS[group]

    return {
        "feature": f"{name}_xs" if cross_sectional else name,
        "base_feature": name if cross_sectional else None,
        "group": group.value,
        "description": definition.description,
        "rationale": definition.rationale,
        "formula": definition.formula,
        "raw_fields": list(definition.required_columns),
        "sources": _source_entries(definition.group),
        "lookback_sessions": definition.lookback_sessions,
        "earliest_required_observation_sessions_before": (
            definition.lookback_sessions + definition.availability_lag_sessions
        ),
        "availability_lag_sessions": definition.availability_lag_sessions,
        "uses_future_information": False,
        "declared_point_in_time_safe": definition.point_in_time_safe,
        "is_cross_sectional": cross_sectional,
        "requires_fitting": mechanics["requires_fitting"],
        "fit_scope": mechanics["fit_scope"],
        "fitted_inside_training_fold": (
            # Cross-sectional ranks are fitted per DATE, which is strictly
            # narrower than per fold and needs no fold awareness. Nothing else
            # here is fitted at all; the only fold-scoped fit in the pipeline is
            # FoldImputer, which is not a feature.
            "not_applicable_fitted_per_date" if mechanics["requires_fitting"] else "not_applicable_no_fit"
        ),
        "missing_data_behaviour": (
            "NULL, never zero or forward-filled. Absence is carried explicitly; "
            "imputation happens once, per fold, in FoldImputer using the "
            "training fold's median."
        ),
        "leakage_mechanism": mechanics["leakage_mechanism"],
        "leakage_test": mechanics["leakage_test"],
        "direction_hypothesis": definition.direction.value,
        "citation": definition.citation or None,
        "version": definition.version,
        "notes": list(definition.notes),
    }


def build_feature_audit(feature_set: Optional[list[str]] = None) -> dict[str, Any]:
    """The complete audit, optionally restricted to a study's actual feature set."""
    per_symbol = REGISTRY.per_symbol_names()
    join_stage = REGISTRY.names(group=FeatureGroup.OPTIONS) + REGISTRY.names(
        group=FeatureGroup.FUNDAMENTAL
    )
    macro = REGISTRY.names(group=FeatureGroup.MACRO)
    rankable = sorted(set(per_symbol) | set(join_stage))

    entries: list[dict[str, Any]] = []
    for name in sorted(per_symbol + join_stage + macro):
        entries.append(audit_feature(name))
    for name in sorted(rankable):
        entries.append(audit_feature(name, cross_sectional=True))

    if feature_set is not None:
        chosen = set(feature_set)
        for entry in entries:
            entry["used_in_study"] = entry["feature"] in chosen

    unsafe = [e["feature"] for e in entries if not e["declared_point_in_time_safe"]]
    fitted = [e["feature"] for e in entries if e["requires_fitting"]]

    return {
        "schema_version": 1,
        "feature_count": len(entries),
        "declared_unsafe": unsafe,
        "requires_fitting": fitted,
        "fit_scopes": sorted({e["fit_scope"] for e in entries if e["fit_scope"]}),
        "groups": {
            group.value: sum(1 for e in entries if e["group"] == group.value)
            for group in FeatureGroup
            if any(e["group"] == group.value for e in entries)
        },
        "features": entries,
    }


def write_feature_audit(path: str, feature_set: Optional[list[str]] = None) -> dict[str, Any]:
    payload = build_feature_audit(feature_set)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=False)
    return payload
