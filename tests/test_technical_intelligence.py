"""
Technical Intelligence Engine (v4.5) — deterministic unit tests.

Synthetic OHLCV frames with known shapes; assertions target the engine's
classifications and contract, not third-party libraries.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.scoring import technical_intelligence as ti


def _frame(closes: np.ndarray, volumes: np.ndarray | None = None) -> pd.DataFrame:
    n = len(closes)
    if volumes is None:
        volumes = np.full(n, 1_000_000.0)
    highs = closes * 1.01
    lows = closes * 0.99
    return pd.DataFrame(
        {
            "Open": closes,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
        },
        index=pd.bdate_range("2025-01-02", periods=n),
    )


@pytest.fixture()
def uptrend() -> pd.DataFrame:
    # Steady +0.3%/day for 260 bars with volume growing alongside price.
    closes = 100 * (1.003 ** np.arange(260))
    volumes = np.linspace(1e6, 2e6, 260)
    return _frame(closes, volumes)


@pytest.fixture()
def downtrend() -> pd.DataFrame:
    # A FRESH decline after a long gentle rise. Verified numerically: the MACD
    # histogram is only negative while the downturn is younger than the EMA
    # lag (~2-3 weeks) — after that both EMAs converge onto the decline path
    # and the line contracts with the shrinking price scale (MACD is
    # price-scale dependent). 15 crash bars keeps all three momentum reads
    # (MACD, RSI, ROC) genuinely bearish at once.
    rise = 100 * (1.0005 ** np.arange(245))
    crash = rise[-1] * (0.99 ** np.arange(1, 16))
    return _frame(np.concatenate([rise, crash]))


class TestContract:
    def test_none_on_thin_history(self):
        assert ti.build(None) is None
        assert ti.build(_frame(100 * np.ones(30))) is None

    def test_block_shape(self, uptrend):
        block = ti.build(uptrend)
        assert block is not None
        assert set(block) == {"indicators", "regimes", "levels", "findings", "as_of", "bars"}
        assert set(block["regimes"]) == {"trend", "momentum", "volatility", "volume"}
        keys = {row["key"] for row in block["indicators"]}
        assert {"sma", "macd", "rsi", "adx", "atr", "bollinger", "stoch",
                "obv", "mfi", "cci", "aroon", "vwap"} <= keys
        for row in block["indicators"]:
            assert row["tone"] in ("pos", "neg", "neutral")
        for finding in block["findings"]:
            assert finding["tone"] in ("pos", "neg", "neutral")
        assert block["bars"] == 260

    def test_deterministic(self, uptrend):
        assert ti.build(uptrend) == ti.build(uptrend)


class TestClassification:
    def test_uptrend_reads_bullish(self, uptrend):
        block = ti.build(uptrend)
        assert block["regimes"]["trend"]["tone"] == "pos"
        assert block["regimes"]["momentum"]["label"] == "Bullish momentum"
        assert block["regimes"]["volume"]["label"] == "Volume confirms"
        macd = next(r for r in block["indicators"] if r["key"] == "macd")
        assert macd["state"] == "bullish"
        roc = next(r for r in block["indicators"] if r["key"] == "roc")
        assert roc["state"] == "positive"

    def test_downtrend_reads_bearish(self, downtrend):
        block = ti.build(downtrend)
        assert block["regimes"]["trend"]["tone"] == "neg"
        assert block["regimes"]["momentum"]["label"] == "Bearish momentum"
        macd = next(r for r in block["indicators"] if r["key"] == "macd")
        assert macd["state"] == "bearish"

    def test_golden_cross_detected(self):
        # 200 flat bars, then a strong rally: the 50d crosses above the 200d.
        closes = np.concatenate([np.full(200, 100.0), 100 * (1.01 ** np.arange(1, 61))])
        block = ti.build(_frame(closes))
        cross = next((r for r in block["indicators"] if r["key"] == "cross"), None)
        assert cross is not None and cross["state"] == "golden"

    def test_death_cross_detected(self):
        # Gentle rise first so the 50d sits strictly above the 200d, then a
        # hard decline drags the 50d through it (a flat prelude gives exact
        # equality, and equality can't flip a strict > comparison).
        rise = 100 * (1.0005 ** np.arange(200))
        decline = rise[-1] * (0.99 ** np.arange(1, 61))
        block = ti.build(_frame(np.concatenate([rise, decline])))
        cross = next((r for r in block["indicators"] if r["key"] == "cross"), None)
        assert cross is not None and cross["state"] == "death"

    def test_support_resistance_bracket_price(self, uptrend):
        levels = ti.build(uptrend)["levels"]
        assert levels["support"] <= levels["close"] <= levels["resistance"]

    def test_zero_volume_degrades_gracefully(self):
        closes = 100 * (1.002 ** np.arange(260))
        block = ti.build(_frame(closes, np.zeros(260)))
        assert block is not None
        assert block["regimes"]["volume"]["label"] == "No volume data"
        keys = {row["key"] for row in block["indicators"]}
        assert "obv" not in keys and "vwap" not in keys


class TestIndicatorSanity:
    def test_rsi_extremes(self):
        up = ti.build(_frame(100 * (1.01 ** np.arange(120))))
        rsi_row = next(r for r in up["indicators"] if r["key"] == "rsi")
        assert float(rsi_row["value"]) > 70

        down = ti.build(_frame(100 * (0.99 ** np.arange(120))))
        rsi_row = next(r for r in down["indicators"] if r["key"] == "rsi")
        assert float(rsi_row["value"]) < 30

    def test_flat_series_is_neutral(self):
        # A strict sawtooth has zero directional persistence — the honest
        # "no trend" fixture for ADX. (A random-walk "flat" series is wrong
        # here: ADX measures persistence and random walks trend locally.)
        closes = 100 + 0.1 * ((-1.0) ** np.arange(260))
        block = ti.build(_frame(closes))
        assert block["regimes"]["trend"]["label"] == "Range-bound"
