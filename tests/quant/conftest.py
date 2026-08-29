"""
Shared fixtures — synthetic market data with known properties.

Synthetic on purpose. A test that depends on a network source measures the
source's availability, not our correctness, and cannot be reproduced by someone
reading it later. Every fixture here has properties the tests assert against:
a known split, a known dividend, a known momentum structure.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest


def business_days(start: Date, count: int) -> list[Date]:
    out: list[Date] = []
    cursor = start
    while len(out) < count:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor += timedelta(days=1)
    return out


@pytest.fixture
def sessions() -> list[Date]:
    return business_days(Date(2018, 1, 1), 900)


@pytest.fixture
def synthetic_prices(sessions) -> pd.DataFrame:
    """Ten symbols with a deliberate cross-sectional momentum structure.

    Symbols are given persistent drifts so momentum genuinely predicts forward
    returns. That matters for the tests that assert the *pipeline* works: on
    pure noise a correct pipeline and a broken one both report no signal, so a
    dataset with no signal cannot distinguish them.
    """
    rng = np.random.default_rng(11)
    rows: list[dict] = []
    for index in range(10):
        symbol = f"SYM{index:02d}"
        drift = 0.0012 * (index - 4.5) / 4.5
        price = 50.0 + index * 10
        volume_base = 1e6 * (index + 1)
        for day in sessions:
            shock = rng.normal(drift, 0.018)
            price = max(1.0, price * (1.0 + shock))
            rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "open": price * 0.998,
                    "high": price * 1.012,
                    "low": price * 0.988,
                    "close": price,
                    "volume": float(volume_base * rng.uniform(0.6, 1.6)),
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_splits() -> pd.DataFrame:
    """A single 4:1 split, on a date the tests know."""
    return pd.DataFrame(
        {"symbol": ["SYM03"], "date": [Date(2019, 6, 3)], "to_factor": [4.0], "for_factor": [1.0]}
    )


@pytest.fixture
def synthetic_dividends() -> pd.DataFrame:
    return pd.DataFrame(
        {"symbol": ["SYM05", "SYM05"], "date": [Date(2019, 3, 1), Date(2019, 9, 2)],
         "amount": [0.50, 0.55]}
    )


@pytest.fixture
def synthetic_treasury(sessions) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    level = 2.0
    rows = []
    for day in sessions:
        level = max(0.05, level + rng.normal(0, 0.02))
        rows.append(
            {
                "date": day,
                "3_month": level - 0.4, "6_month": level - 0.3, "1_year": level - 0.2,
                "2_year": level - 0.1, "3_year": level, "5_year": level + 0.1,
                "7_year": level + 0.2, "10_year": level + 0.3, "20_year": level + 0.5,
                "30_year": level + 0.6, "1_month": level - 0.5,
            }
        )
    return pd.DataFrame(rows)
