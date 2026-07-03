"""
Data vendors: Alpha Vantage (delegates to the existing client — no logic
duplication) and FRED (macro series via fredapi).
"""

from __future__ import annotations

from typing import Optional

from src.providers.base import VendorClient, VendorError
from src.providers.schemas import (
    AnalystTargets,
    CompanyProfile,
    FundamentalsData,
    MacroSnapshot,
)


class AlphaVantageVendor(VendorClient):
    """Thin adapter over src/alpha_vantage.AlphaVantageClient."""

    NAME = "alpha_vantage"
    KEY_ENV = "ALPHA_VANTAGE_KEY"
    DEFAULT_RPM = 5  # free tier: 5/min, 25/day

    def __init__(self, session=None):
        super().__init__(session)
        from src.alpha_vantage import AlphaVantageClient

        self._client = AlphaVantageClient()

    def get_fundamentals(self, symbol: str) -> Optional[FundamentalsData]:
        raw = self.timed_call(lambda: self._client.get_fundamentals(symbol))
        if raw.error:
            return None
        return FundamentalsData(
            symbol=symbol,
            pe_ratio=raw.pe_ratio,
            forward_pe=raw.forward_pe,
            eps=raw.eps,
            beta=raw.beta,
            week_52_high=raw.week_52_high,
            week_52_low=raw.week_52_low,
            dividend_yield=raw.dividend_yield,
            profit_margin=raw.profit_margin,
            profile=CompanyProfile(
                symbol=symbol,
                name=raw.name or "",
                sector=raw.sector or "",
                market_cap=raw.market_cap,
            ),
        )

    def get_analyst_targets(self, symbol: str) -> Optional[AnalystTargets]:
        raw = self.timed_call(lambda: self._client.get_fundamentals(symbol))
        if raw.error or raw.analyst_target is None:
            return None
        return AnalystTargets(symbol=symbol, target_mean=raw.analyst_target)


class FredVendor(VendorClient):
    """FRED macro series. Only vendor for macro — chain degrades to demo values."""

    NAME = "fred"
    KEY_ENV = "FRED_API_KEY"
    DEFAULT_RPM = 30
    COOLDOWN_SECONDS = 120.0

    YIELD_CURVE_SERIES = "T10Y2Y"
    CPI_SERIES = "CPIAUCNS"
    FED_FUNDS_SERIES = "FEDFUNDS"

    def __init__(self, session=None):
        super().__init__(session)
        self._fred = None

    def _client(self):
        if self._fred is None:
            from fredapi import Fred

            self._fred = Fred(api_key=self.api_key)
        return self._fred

    def get_macro(self) -> Optional[MacroSnapshot]:
        def _fetch() -> MacroSnapshot:
            fred = self._client()
            spread_series = fred.get_series(self.YIELD_CURVE_SERIES).dropna()
            cpi = fred.get_series(self.CPI_SERIES).dropna()
            current, year_ago = float(cpi.iloc[-1]), float(cpi.iloc[-13])
            inflation = round(((current - year_ago) / year_ago) * 100, 2)
            try:
                fed_rate = float(fred.get_series(self.FED_FUNDS_SERIES).dropna().iloc[-1])
            except Exception:  # noqa: BLE001 — optional series
                fed_rate = None
            return MacroSnapshot(
                yield_spread=float(spread_series.iloc[-1]),
                inflation_rate=inflation,
                fed_funds_rate=fed_rate,
            )

        if not self.available:
            raise VendorError("fred: FRED_API_KEY not configured", transient=False)
        return self.timed_call(_fetch)
