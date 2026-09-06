"""Documentation that can go stale silently is documentation nobody can trust.

`.env.example` is the file someone reads before their first deployment. It
claimed the market-data chain ran "Polygon → TwelveData → FMP → MarketStack →
yfinance" long after Massive and Tiingo were put in front of it, so the first
two vendors a request actually reaches were not mentioned at all.

Correcting it once fixes today. Pinning it to the code is what stops the next
drift.
"""

import inspect
import re
from pathlib import Path

import pytest

from src.providers.providers import MarketDataProvider
from src.services.paper_access import OWNERS_ENV

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = (ROOT / ".env.example").read_text()


def _price_chain() -> list[str]:
    src = inspect.getsource(MarketDataProvider.get_price)
    return re.findall(r"ChainLink\(self\.(\w+)", src)


def test_the_documented_market_chain_matches_the_code():
    chain = _price_chain()
    assert chain, "no chain links found; the source shape changed"
    documented = ENV_EXAMPLE.lower()
    for vendor in chain:
        assert vendor.lower() in documented, (
            f"{vendor} leads or sits in the price chain and .env.example never "
            "names it"
        )


def _documented_chain_line() -> str:
    """The comment that states the market-data order, joined across its wrap.

    Scoped deliberately: every vendor's name also appears on its own
    `#VENDOR_API_KEY=` line further down, so searching the whole file finds
    those instead and the order check passes on the wrong text.
    """
    lines = ENV_EXAMPLE.splitlines()
    start = next(i for i, l in enumerate(lines) if "Market data:" in l)
    block = [lines[start]]
    for line in lines[start + 1:]:
        if not line.startswith("#") or "=" in line:
            break
        block.append(line)
    return " ".join(block).lower()


def test_the_documented_order_is_the_real_order():
    """Not just present — in sequence. Order is the whole content of a chain."""
    chain = _price_chain()
    documented = _documented_chain_line()
    positions = [documented.find(v.lower()) for v in chain]
    missing = [v for v, pos in zip(chain, positions) if pos < 0]
    assert not missing, f"the chain comment does not name {missing}"
    assert positions == sorted(positions), (
        "the vendors are documented in a different order from the one the "
        f"chain uses: code is {' → '.join(chain)}"
    )


def test_the_paper_owner_variable_is_documented():
    """Paper trading fails closed without it, so an undocumented name is a
    deployment that silently has no paper workspace and no stated reason."""
    assert OWNERS_ENV in ENV_EXAMPLE, (
        f"{OWNERS_ENV} gates every paper route and is not in .env.example"
    )


def test_no_credential_value_is_committed_in_the_example():
    """Names only. An example that carries a real key is a leaked key."""
    for line in ENV_EXAMPLE.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if "=" not in stripped or stripped.startswith("//"):
            continue
        name, _, value = stripped.partition("=")
        if not name.isupper() or not value:
            continue
        # Obvious placeholders are the point of this file.
        if re.search(r"your_|_here|xxx|<.*>|change_?me|example", value, re.I):
            continue
        assert not re.fullmatch(r"[A-Za-z0-9_\-]{20,}", value), (
            f"{name} in .env.example carries what looks like a real value"
        )


def test_the_alpaca_host_is_documented_as_fixed():
    """It is a security control, and a reader must not think it is a knob."""
    assert "paper-api.alpaca.markets" in ENV_EXAMPLE
    assert "not configurable" in ENV_EXAMPLE.lower()
