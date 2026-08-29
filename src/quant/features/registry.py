"""
Feature registry — every feature declares what it is before it may be used.

## Why a registry rather than a module of functions

A feature is not just a computation. It is a computation plus a claim about
*when its value became knowable*, and that second half is what a model
consumes and what a leakage test checks. A bare function cannot be asked
whether it looks forward; a `FeatureDefinition` can, and
`src/quant/pit/dataset.py` does ask, refusing to build a training set from a
feature that has not declared itself.

Three fields carry the weight:

``lookback_sessions``
    How many prior sessions the value needs. The dataset builder uses it to
    decide when a feature first becomes computable, so a feature is NULL at
    the start of a series rather than computed from a short window and
    silently meaning something different there.

``availability_lag_sessions``
    Sessions between the data being observed and the feature being usable.
    Zero for a close-derived feature (a close is known at that close). One for
    the Treasury curve, which is published after the day it describes.

``point_in_time_safe``
    False bars the feature from a historical training set outright. Nothing is
    computed and then flagged; it is refused.

## The one rule that is not negotiable

Every feature is computed from a **backward-looking window only**, and the
implementations here express that structurally — `rolling(...)`, `shift(n)`
with positive `n`, `cumprod` — never `shift(-n)`, never `.rolling(...,
center=True)`. `tests/quant/test_leakage.py` enforces it from the outside by
perturbing future values and asserting no present feature moves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import pandas as pd


class FeatureGroup(str, Enum):
    PRICE = "price"
    VOLUME = "volume"
    STRUCTURE = "structure"
    VOLATILITY = "volatility"
    CROSS_SECTIONAL = "cross_sectional"
    MACRO = "macro"
    OPTIONS = "options"
    FUNDAMENTAL = "fundamental"


class Direction(str, Enum):
    """The sign of the *hypothesised* relationship, recorded before testing.

    Written down in advance so that a factor which works with the opposite
    sign is visibly a surprise rather than retroactively "what we expected".
    `DESCRIPTIVE` means no directional hypothesis is claimed.
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"
    TWO_SIDED = "two_sided"
    DESCRIPTIVE = "descriptive"


@dataclass(frozen=True)
class FeatureDefinition:
    """One feature: what it measures, what it needs, and when it is knowable."""

    name: str
    group: FeatureGroup
    description: str
    rationale: str
    formula: str
    lookback_sessions: int
    required_columns: tuple[str, ...]
    direction: Direction = Direction.DESCRIPTIVE
    availability_lag_sessions: int = 0
    point_in_time_safe: bool = True
    cross_sectional: bool = False
    version: str = "1.0"
    citation: str = ""
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "group": self.group.value,
            "description": self.description,
            "rationale": self.rationale,
            "formula": self.formula,
            "lookback_sessions": self.lookback_sessions,
            "required_columns": list(self.required_columns),
            "direction": self.direction.value,
            "availability_lag_sessions": self.availability_lag_sessions,
            "point_in_time_safe": self.point_in_time_safe,
            "cross_sectional": self.cross_sectional,
            "version": self.version,
            "citation": self.citation,
            "notes": list(self.notes),
        }


#: A feature computer receives one symbol's history sorted ascending by date
#: and returns a series aligned to its index. It must never index forward.
FeatureFn = Callable[[pd.DataFrame], pd.Series]


@dataclass
class FeatureRegistry:
    """The set of features a dataset build is allowed to draw from."""

    definitions: dict[str, FeatureDefinition] = field(default_factory=dict)
    computers: dict[str, FeatureFn] = field(default_factory=dict)

    def register(
        self, definition: FeatureDefinition, computer: Optional[FeatureFn] = None
    ) -> FeatureDefinition:
        if definition.name in self.definitions:
            raise ValueError(f"feature {definition.name!r} is already registered")
        self.definitions[definition.name] = definition
        if computer is not None:
            self.computers[definition.name] = computer
        return definition

    def get(self, name: str) -> FeatureDefinition:
        if name not in self.definitions:
            raise KeyError(f"unknown feature {name!r}")
        return self.definitions[name]

    def computer(self, name: str) -> FeatureFn:
        if name not in self.computers:
            raise KeyError(
                f"feature {name!r} is declared but has no computer — it is defined "
                "by a cross-sectional or join stage, not a per-symbol function"
            )
        return self.computers[name]

    def names(self, *, group: Optional[FeatureGroup] = None, pit_only: bool = True) -> list[str]:
        return sorted(
            name
            for name, definition in self.definitions.items()
            if (group is None or definition.group is group)
            and (not pit_only or definition.point_in_time_safe)
        )

    def per_symbol_names(self, *, pit_only: bool = True) -> list[str]:
        """Features computable from one symbol's own history."""
        return sorted(
            name
            for name in self.names(pit_only=pit_only)
            if name in self.computers and not self.definitions[name].cross_sectional
        )

    def max_lookback(self, names: Optional[list[str]] = None) -> int:
        chosen = names or list(self.definitions)
        return max(
            (self.definitions[name].lookback_sessions for name in chosen), default=0
        )

    def unsafe(self) -> list[str]:
        """Features barred from historical training, named rather than hidden."""
        return sorted(
            name for name, d in self.definitions.items() if not d.point_in_time_safe
        )

    def catalog(self) -> list[dict[str, Any]]:
        return [
            self.definitions[name].as_dict() for name in sorted(self.definitions)
        ]


#: The registry every builder uses. Populated by importing the feature modules.
REGISTRY = FeatureRegistry()
