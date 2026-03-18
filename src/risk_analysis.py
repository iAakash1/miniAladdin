"""
OmniSignal Risk Analysis Engine
Connects to FRED to calculate the Systemic Risk Multiplier (SRM).
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

from src.models import MacroIndicators, MacroStatus, RiskAssessment

load_dotenv()


class OmniSignalRiskEngine:
    """
    Calculates a Systemic Risk Multiplier from Federal Reserve macro data.

    The multiplier ranges from 0.5 (very low risk) to 1.6 (extreme risk)
    and is used to dampen or boost prediction confidence.
    """

    # FRED API key (direct integration)
    _DEFAULT_FRED_KEY = "6e050ad2ed98fb11706fb33f7ae2b279"

    # FRED series IDs
    YIELD_CURVE_SERIES = "T10Y2Y"       # 10-Year minus 2-Year Treasury spread
    CPI_SERIES = "CPIAUCNS"             # Consumer Price Index (All Urban)
    FED_FUNDS_SERIES = "FEDFUNDS"       # Effective Federal Funds Rate

    # Thresholds
    INFLATION_THRESHOLD = 4.0           # percent YoY
    FED_RATE_THRESHOLD = 5.0            # percent
    YIELD_INVERSION_THRESHOLD = 0.0     # negative = inverted

    # Multiplier adjustments
    BASE_MULTIPLIER = 1.0
    INVERSION_PENALTY = 0.3
    INFLATION_PENALTY = 0.2
    FED_RATE_PENALTY = 0.1
    MIN_MULTIPLIER = 0.5
    MAX_MULTIPLIER = 1.6

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("FRED_API_KEY") or self._DEFAULT_FRED_KEY
        self._fred = None

    @property
    def fred(self):
        """Lazy-initialize the FRED client."""
        if self._fred is None:
            try:
                from fredapi import Fred
                self._fred = Fred(api_key=self._api_key)
            except ImportError:
                raise ImportError(
                    "fredapi is required. Install with: pip install fredapi"
                )
            except Exception as e:
                raise ConnectionError(f"Failed to initialize FRED client: {e}")
        return self._fred

    def _fetch_yield_spread(self) -> float:
        """Fetch the latest 10Y-2Y Treasury yield spread."""
        series = self.fred.get_series(self.YIELD_CURVE_SERIES)
        return float(series.dropna().iloc[-1])

    def _fetch_inflation_rate(self) -> float:
        """Calculate year-over-year CPI inflation rate."""
        cpi = self.fred.get_series(self.CPI_SERIES)
        cpi = cpi.dropna()
        current = float(cpi.iloc[-1])
        year_ago = float(cpi.iloc[-13])  # ~12 months prior
        return round(((current - year_ago) / year_ago) * 100, 2)

    def _fetch_fed_funds_rate(self) -> Optional[float]:
        """Fetch the effective Federal Funds Rate."""
        try:
            series = self.fred.get_series(self.FED_FUNDS_SERIES)
            return float(series.dropna().iloc[-1])
        except Exception:
            return None

    def get_macro_indicators(self) -> MacroIndicators:
        """Fetch all macro indicators from FRED."""
        yield_spread = self._fetch_yield_spread()
        inflation_rate = self._fetch_inflation_rate()
        fed_funds_rate = self._fetch_fed_funds_rate()

        return MacroIndicators(
            yield_spread=yield_spread,
            inflation_rate=inflation_rate,
            fed_funds_rate=fed_funds_rate,
        )

    def calculate_multiplier(self, indicators: MacroIndicators) -> RiskAssessment:
        """
        Calculate the Systemic Risk Multiplier from macro indicators.

        Logic:
            - Base multiplier = 1.0
            - Yield curve inverted (< 0): +0.3
            - Inflation > 4%: +0.2
            - Fed Funds > 5%: +0.1
            - Clamp to [0.5, 1.6]
        """
        multiplier = self.BASE_MULTIPLIER
        yield_inverted = indicators.yield_spread < self.YIELD_INVERSION_THRESHOLD

        if yield_inverted:
            multiplier += self.INVERSION_PENALTY

        if indicators.inflation_rate > self.INFLATION_THRESHOLD:
            multiplier += self.INFLATION_PENALTY

        if (
            indicators.fed_funds_rate is not None
            and indicators.fed_funds_rate > self.FED_RATE_THRESHOLD
        ):
            multiplier += self.FED_RATE_PENALTY

        multiplier = max(self.MIN_MULTIPLIER, min(self.MAX_MULTIPLIER, multiplier))

        # Determine status
        if multiplier > 1.3:
            status = MacroStatus.CRITICAL
        elif multiplier > 1.1:
            status = MacroStatus.ELEVATED
        else:
            status = MacroStatus.STABLE

        return RiskAssessment(
            risk_multiplier=round(multiplier, 2),
            yield_curve_inverted=yield_inverted,
            status=status,
            indicators=indicators,
            recession_warning=yield_inverted,
        )

    def get_systemic_risk_multiplier(self) -> tuple[float, dict]:
        """
        High-level API: fetch macro data and compute the SRM.

        Returns:
            tuple of (risk_multiplier: float, stats: dict)
        """
        try:
            indicators = self.get_macro_indicators()
            assessment = self.calculate_multiplier(indicators)
            stats = {
                "yield_spread": indicators.yield_spread,
                "inflation_rate": f"{indicators.inflation_rate:.2f}%",
                "fed_funds_rate": (
                    f"{indicators.fed_funds_rate:.2f}%"
                    if indicators.fed_funds_rate is not None
                    else "N/A"
                ),
                "yield_curve_inverted": assessment.yield_curve_inverted,
                "status": assessment.status.value,
                "recession_warning": assessment.recession_warning,
            }
            return assessment.risk_multiplier, stats
        except Exception as e:
            print(f"[OmniSignal] Error fetching macro data: {e}")
            return self.BASE_MULTIPLIER, {"status": MacroStatus.DATA_ERROR.value, "error": str(e)}


if __name__ == "__main__":
    engine = OmniSignalRiskEngine()
    multiplier, stats = engine.get_systemic_risk_multiplier()
    print(f"Systemic Risk Multiplier: {multiplier}")
    for key, value in stats.items():
        print(f"  {key}: {value}")
