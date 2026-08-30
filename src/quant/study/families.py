"""
Feature families — the unit of an ablation.

## Why families rather than features

"Does this feature help?" is the wrong question to ask 103 times. Asking it once
per feature costs 103 trials, each of which inflates the multiple-testing
correction, and the answers are not independent because the features inside a
family are heavily correlated by construction — `mom_21_xs` and `mom_63_xs`
measure the same thing over different windows.

The question worth 47 trials is "does this SOURCE add information over the
sources already in?", and that is a question about families: price, volatility,
volume, options, estimates, fundamentals. Each family maps to a distinct
upstream dataset with a distinct acquisition cost and a distinct set of
point-in-time hazards, so a negative answer for a family is directly actionable
— it means stop paying for that data.

## Membership is derived, never hand-listed

A family is defined by the registry's `FeatureGroup` plus the `_xs` naming
convention, so adding a feature to a group automatically puts it in the right
arm. A hand-maintained list would drift the first time someone adds a feature
and forgets, and the drift would silently change what an arm means between
studies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.quant.features.registry import REGISTRY, FeatureGroup

#: Which registry groups constitute each family.
FAMILY_GROUPS: dict[str, tuple[FeatureGroup, ...]] = {
    "price": (FeatureGroup.PRICE, FeatureGroup.STRUCTURE),
    "volatility": (FeatureGroup.VOLATILITY,),
    "volume": (FeatureGroup.VOLUME,),
    "options": (FeatureGroup.OPTIONS,),
    "macro": (FeatureGroup.MACRO,),
}

#: Fundamental-group features split by their source table, because they carry
#: very different point-in-time risk. Estimates are vintage-dated and clean;
#: statement fundamentals are announcement-gated and carry unquantified
#: restatement risk. Averaging them into one arm would hide that difference.
ESTIMATE_PREFIX = "est_"
FUNDAMENTAL_PREFIX = "fund_"
EARNINGS_PREFIX = "earn_"

FAMILY_DESCRIPTIONS: dict[str, str] = {
    "price": "Returns, momentum, reversal, moving-average distance, breakout.",
    "volatility": "Realised, downside and ratio volatility measures.",
    "volume": "Dollar volume, turnover and volume surprise.",
    "options": "IV level, rank, term structure, skew and IV-RV spread.",
    "earnings": "EPS surprise and drift, gated on the announcement date.",
    "estimates": "Analyst revisions, dispersion and coverage. Vintage-dated, no gate needed.",
    "fundamentals": "Margins, returns, leverage, accruals and growth. Announcement-gated; UNQUANTIFIED restatement risk.",
    "macro": "Treasury curve level, slope, curvature and market state.",
}


@dataclass(frozen=True)
class FeatureArm:
    """One pre-registered combination of families."""

    name: str
    families: tuple[str, ...]
    hypothesis: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "families": list(self.families),
            "hypothesis": self.hypothesis,
        }


def family_members(family: str, available: Sequence[str]) -> list[str]:
    """The columns of `available` belonging to `family`.

    `available` is the built matrix's column list, so an arm can only ever
    request columns that actually exist — a family whose source was missing at
    build time contributes nothing rather than raising.
    """
    present = set(available)

    if family in FAMILY_GROUPS:
        base: set[str] = set()
        for group in FAMILY_GROUPS[family]:
            base.update(REGISTRY.names(group=group))
        # Macro features are used raw; everything else is consumed as its
        # cross-sectional rank, which is what the models actually see.
        if family == "macro":
            return sorted(n for n in present if n in base)
        return sorted(n for n in present if n.endswith("_xs") and n[:-3] in base)

    prefix = {
        "estimates": ESTIMATE_PREFIX,
        "fundamentals": FUNDAMENTAL_PREFIX,
        "earnings": EARNINGS_PREFIX,
    }.get(family)
    if prefix is None:
        raise KeyError(f"unknown feature family {family!r}; known: {sorted(known_families())}")
    return sorted(n for n in present if n.startswith(prefix) and n.endswith("_xs"))


def known_families() -> list[str]:
    return sorted(set(FAMILY_GROUPS) | {"estimates", "fundamentals", "earnings"})


def arm_features(arm: FeatureArm, available: Sequence[str]) -> list[str]:
    """Every column an arm may use, de-duplicated and ordered."""
    chosen: list[str] = []
    seen: set[str] = set()
    for family in arm.families:
        for name in family_members(family, available):
            if name not in seen:
                seen.add(name)
                chosen.append(name)
    return chosen


#: The pre-registered ladder. Declared here, before EXP-005 runs, so the arms
#: cannot be adjusted once results are visible.
#:
#: It is a LADDER, not a power set: each arm adds one family to a fixed base, so
#: the comparison that matters — arm minus base — is a single clean contrast.
#: Testing all 2^7 subsets would answer more questions and cost 128x the trials
#: to answer any of them convincingly.
DEFAULT_ARMS: tuple[FeatureArm, ...] = (
    FeatureArm(
        "A_price", ("price",),
        "Price alone. The floor: whatever momentum and reversal already capture.",
    ),
    FeatureArm(
        "B_price_vol", ("price", "volatility"),
        "Does volatility add information over price alone?",
    ),
    FeatureArm(
        "C_base", ("price", "volatility", "volume", "macro"),
        "The base. Everything derivable from the price panel plus the rate curve.",
    ),
    FeatureArm(
        "D_base_options", ("price", "volatility", "volume", "macro", "options"),
        "Does the 8 GB options dataset add information over the base? "
        "This is the question that justifies its storage and ingestion cost.",
    ),
    FeatureArm(
        "E_base_estimates", ("price", "volatility", "volume", "macro", "estimates"),
        "Do analyst revisions add information over the base? Untested before "
        "EXP-005 and the only genuinely new signal family in this study.",
    ),
    FeatureArm(
        "F_base_fundamentals",
        ("price", "volatility", "volume", "macro", "earnings", "fundamentals"),
        "Do announcement-gated statement fundamentals add information over the "
        "base? Isolated so their UNQUANTIFIED restatement risk can be discounted "
        "separately rather than contaminating a combined result.",
    ),
    FeatureArm(
        "G_all",
        ("price", "volatility", "volume", "macro", "options", "earnings",
         "estimates", "fundamentals"),
        "Everything. If G does not beat C, the additional sources add nothing "
        "jointly and the negative result covers all of them at once.",
    ),
)
