"""The set of securities Explore is willing to score.

A universe is not a recommendation list. Membership says only that this stack
can obtain the inputs its factor model needs for a name; it makes no claim
about the name, and absence makes no claim either. That distinction is the
whole reason this is a static file and the rankings built on it are not:
*which* securities are considered is a configuration decision, and *how they
rank* is a model output, and hard-coding the second is how a product ends up
recommending whatever its author happened to like.

Versioned because a ranking is only reproducible against the universe it was
computed over. A result that says "3rd of 77" means nothing without knowing
which 77, so `universe_version` travels with every Explore response.

US-scoped on purpose. The macro gate underneath these scores is built from
FRED, the Federal Funds rate, US CPI, the US yield curve and SPY. Those are
not global facts, and applying them to a non-US listing would silently price
one market's regime into another market's securities.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

logger = logging.getLogger("omnisignal.universe")

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = _ROOT / "config" / "universe_us_v1.json"

_lock = threading.Lock()
_cached: Optional["Universe"] = None


class Constituent(BaseModel):
    symbol: str
    company_name: str
    sector: str
    asset_type: str = "common_equity"


class Universe(BaseModel):
    universe_version: str
    market: str
    as_of: str
    constituents: list[Constituent]

    @property
    def symbols(self) -> list[str]:
        return [c.symbol for c in self.constituents]

    def by_symbol(self, symbol: str) -> Optional[Constituent]:
        upper = symbol.upper()
        for c in self.constituents:
            if c.symbol.upper() == upper:
                return c
        return None

    def sectors(self) -> list[str]:
        return sorted({c.sector for c in self.constituents})


def _load(path: Path) -> Universe:
    raw: dict[str, Any] = json.loads(path.read_text())
    universe = Universe(
        universe_version=raw["universe_version"],
        market=raw["market"],
        as_of=raw["as_of"],
        constituents=[Constituent(**c) for c in raw["constituents"]],
    )
    seen: set[str] = set()
    for c in universe.constituents:
        upper = c.symbol.upper()
        if upper in seen:
            raise ValueError(f"duplicate symbol in universe: {c.symbol}")
        seen.add(upper)
    return universe


def load_universe(path: Optional[Path] = None) -> Universe:
    """The configured universe, parsed once and shared.

    Cached because it is read on every Explore request and never changes
    within a process. A parse failure raises rather than returning an empty
    universe: an Explore page over nothing would look like "no security
    qualified today", which is a finding, not a missing config file.
    """
    global _cached
    if path is not None:
        return _load(path)
    with _lock:
        if _cached is None:
            _cached = _load(_DEFAULT_PATH)
        return _cached


def reset_cache_for_testing() -> None:
    global _cached
    with _lock:
        _cached = None
