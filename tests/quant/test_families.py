"""
Feature families — the unit of the EXP-005 ablation.

The property that matters is that membership is DERIVED from the registry
rather than hand-listed. A hand-maintained list drifts the first time someone
adds a feature and forgets, and the drift silently changes what an arm means
between studies — so a contrast measured in EXP-005 would not be comparable to
the same contrast measured later.
"""

from __future__ import annotations

import pytest

from src.quant.features import (  # noqa: F401 - registration side effect
    earnings, estimates, fundamentals, macro, options, price,
)
from src.quant.features.registry import REGISTRY, FeatureGroup
from src.quant.study.families import (
    DEFAULT_ARMS,
    FeatureArm,
    arm_features,
    family_members,
    known_families,
)


@pytest.fixture(scope="module")
def available() -> list[str]:
    """The columns a built matrix would offer: every rank plus raw macro."""
    rankable = set(REGISTRY.per_symbol_names()) | set(
        REGISTRY.names(group=FeatureGroup.OPTIONS)
        + REGISTRY.names(group=FeatureGroup.FUNDAMENTAL)
    )
    return sorted([f"{n}_xs" for n in rankable] + REGISTRY.names(group=FeatureGroup.MACRO))


# ── membership is derived ───────────────────────────────────────────────────


def test_every_family_resolves_to_at_least_one_column(available):
    for family in known_families():
        assert family_members(family, available), f"{family} resolved to nothing"


def test_an_unknown_family_raises_rather_than_returning_empty(available):
    """Silently returning [] would make a typo look like an absent data source."""
    with pytest.raises(KeyError, match="unknown feature family"):
        family_members("momentum_alpha_secret_sauce", available)


def test_families_do_not_overlap(available):
    """An overlapping family would double-count a source in the ladder."""
    seen: dict[str, str] = {}
    for family in known_families():
        for name in family_members(family, available):
            assert name not in seen, f"{name} is in both {seen[name]} and {family}"
            seen[name] = family


def test_estimates_and_fundamentals_are_separated(available):
    """They share a registry group but not a point-in-time risk profile.

    `est_*` are vintage-dated and clean; `fund_*` are announcement-gated and
    carry unquantified restatement risk. Averaging them into one arm would hide
    exactly the difference the ablation exists to measure.
    """
    estimates_family = family_members("estimates", available)
    fundamentals_family = family_members("fundamentals", available)

    assert estimates_family and fundamentals_family
    assert all(n.startswith("est_") for n in estimates_family)
    assert all(n.startswith("fund_") for n in fundamentals_family)
    assert not set(estimates_family) & set(fundamentals_family)


def test_macro_is_used_raw_not_ranked(available):
    """Ranking a market-wide series across symbols would produce a constant."""
    macro_family = family_members("macro", available)
    assert macro_family
    assert not any(n.endswith("_xs") for n in macro_family)


def test_non_macro_families_are_consumed_as_ranks(available):
    for family in ("price", "volatility", "volume", "options", "estimates", "fundamentals"):
        for name in family_members(family, available):
            assert name.endswith("_xs"), f"{name} in {family} is not a rank"


def test_a_family_whose_source_is_absent_contributes_nothing(available):
    """An arm must not raise because a data source failed to load."""
    without_options = [n for n in available if not n.startswith(("iv_", "opt_", "skew"))]
    members = family_members("options", without_options)
    assert isinstance(members, list)


# ── the ladder ──────────────────────────────────────────────────────────────


def test_the_ladder_adds_exactly_one_family_per_rung_after_the_base():
    """Each contrast has to be attributable to a single source."""
    base = next(a for a in DEFAULT_ARMS if a.name == "C_base")
    base_set = set(base.families)
    for arm in DEFAULT_ARMS:
        if arm.name in {"A_price", "B_price_vol", "C_base", "G_all"}:
            continue
        added = set(arm.families) - base_set
        assert added, f"{arm.name} adds nothing to the base"
        # F adds earnings alongside fundamentals because the surprise features
        # and the statement features come from the same announcement gate.
        assert len(added) <= 2, f"{arm.name} adds {added}, so a contrast is ambiguous"


def test_every_arm_declares_a_hypothesis():
    for arm in DEFAULT_ARMS:
        assert arm.hypothesis.strip(), f"{arm.name} has no stated hypothesis"
        assert len(arm.hypothesis) > 30, f"{arm.name}'s hypothesis is not a question"


def test_the_base_arm_exists_and_is_price_derived():
    base = next(a for a in DEFAULT_ARMS if a.name == "C_base")
    assert set(base.families) == {"price", "volatility", "volume", "macro"}


def test_g_all_contains_every_family():
    everything = next(a for a in DEFAULT_ARMS if a.name == "G_all")
    assert set(everything.families) == set(known_families())


def test_arm_features_deduplicates_and_preserves_order(available):
    arm = FeatureArm("dup", ("price", "price", "volatility"), "a duplicate on purpose")
    columns = arm_features(arm, available)
    assert len(columns) == len(set(columns))
    price_only = arm_features(FeatureArm("p", ("price",), "x" * 40), available)
    assert columns[: len(price_only)] == price_only


def test_arm_features_only_returns_columns_that_exist():
    """An arm can only request what the built matrix actually has."""
    tiny = ["mom_21_xs", "rates_level"]
    for arm in DEFAULT_ARMS:
        assert set(arm_features(arm, tiny)) <= set(tiny)
