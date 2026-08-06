"""
Universe definition — which symbols a panel build covers.

A frank limitation, stated here rather than buried: these universes are
**current** membership, not historical. A panel built over 2016–2026 using
today's S&P 100 contains only companies that survived to today, which is
textbook **survivorship bias** — it silently inflates every backtest
statistic computed over it, because the failures were never in the sample.

This is not fixed by trying harder. It requires point-in-time index
membership, which has no free source. The honest options were:

  1. Pretend the problem does not exist.
  2. Build fake historical membership.
  3. State it, and shape the API so the fix is additive.

Option 3. `Universe.members()` takes an `as_of` date it currently ignores,
and `Universe.point_in_time` reports whether membership is genuinely
historical. Every consumer therefore already passes the date that a real
implementation will need, and no call site changes when one arrives.

Do not report a backtest over these universes as though it were unbiased.
`docs/PANEL.md` restates this where a reader will see it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Optional

# Deliberately small and liquid. A first panel should be fast enough to
# rebuild in a coffee break — research iteration speed matters more than
# coverage until the pipeline is proven.
_DEV: tuple[str, ...] = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL")

_MEGA_CAP: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "JPM", "V", "MA", "UNH", "JNJ", "WMT", "PG", "HD", "XOM", "CVX",
    "KO", "PEP", "ABBV", "MRK", "COST", "ADBE", "CRM", "AMD", "INTC",
    "ORCL", "CSCO", "NFLX",
)

_REGISTRY: dict[str, tuple[str, ...]] = {
    "dev": _DEV,
    "mega30": _MEGA_CAP,
}


@dataclass(frozen=True)
class Universe:
    """An immutable, named set of symbols.

    Frozen because a universe that mutates between the start and end of a
    build produces a panel whose contents cannot be reproduced from its
    manifest — which would defeat the entire point of content addressing.
    """

    name: str
    symbols: tuple[str, ...]

    #: True only when membership is genuinely historical. Guards any claim
    #: of an unbiased backtest; see the module docstring.
    point_in_time: bool = False

    @classmethod
    def named(cls, name: str) -> "Universe":
        key = name.strip().lower()
        if key not in _REGISTRY:
            raise KeyError(f"unknown universe {name!r}; available: {sorted(_REGISTRY)}")
        return cls(name=key, symbols=_REGISTRY[key])

    @classmethod
    def custom(cls, symbols: list[str], name: str = "custom") -> "Universe":
        cleaned = tuple(sorted({s.strip().upper() for s in symbols if s.strip()}))
        if not cleaned:
            raise ValueError("universe requires at least one symbol")
        return cls(name=name, symbols=cleaned)

    def members(self, as_of: Optional[Date] = None) -> tuple[str, ...]:
        """Membership on a date.

        `as_of` is accepted and currently ignored — see the module
        docstring. It is in the signature so that point-in-time membership
        becomes a change to this method alone.
        """
        return self.symbols

    def __len__(self) -> int:
        return len(self.symbols)


def available() -> list[str]:
    return sorted(_REGISTRY)
