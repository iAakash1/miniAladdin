"""Official macro series used only for explicitly equivalent FRED fallbacks."""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Optional

from src.providers.base import FailureClass, VendorClient, VendorError


class BlsVendor(VendorClient):
    """Public BLS data for CPI and unemployment; no account required."""

    NAME = "bls"
    KEY_ENV = None
    DEFAULT_RPM = 5
    URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    SERIES = {"CPIAUCSL": "CUSR0000SA0", "UNRATE": "LNS14000000"}

    def _validate_payload(self, payload) -> None:
        if not isinstance(payload, dict) or payload.get("status") != "REQUEST_SUCCEEDED":
            raise VendorError(
                "BLS returned an API-level error", transient=False,
                failure_class=FailureClass.UNAVAILABLE,
            )

    def get_official_series(self, series_id: str, count: int = 15) -> Optional[list[tuple[str, float]]]:
        bls_id = self.SERIES.get(series_id)
        if bls_id is None:
            return None
        year = date.today().year
        data = self._post_json(
            self.URL,
            {"seriesid": [bls_id], "startyear": str(year - 2), "endyear": str(year)},
            operation="official_macro_series",
        )
        if not isinstance(data, dict) or data.get("status") != "REQUEST_SUCCEEDED":
            return None
        rows = ((data.get("Results") or {}).get("series") or [{}])[0].get("data") or []
        observations = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            period = str(row.get("period") or "")
            year_text = str(row.get("year") or "")
            if not re.fullmatch(r"M(0[1-9]|1[0-2])", period) or not re.fullmatch(r"\d{4}", year_text):
                continue
            try:
                value = float(str(row.get("value") or "").replace(",", ""))
            except ValueError:
                continue
            if math.isfinite(value):
                observations.append((f"{year_text}-{period[1:]}-01", value))
        return sorted(observations)[-count:] or None


class BeaVendor(VendorClient):
    """BEA's real GDP growth series, matching FRED's BEA-sourced headline."""

    NAME = "bea"
    KEY_ENV = "BEA_API_KEY"
    DEFAULT_RPM = 5
    URL = "https://apps.bea.gov/api/data/"
    SERIES = "A191RL1Q225SBEA"

    def _validate_payload(self, payload) -> None:
        if not isinstance(payload, dict):
            raise VendorError(
                "BEA returned an invalid response", transient=False,
                failure_class=FailureClass.PARSE,
            )
        root = payload.get("BEAAPI")
        if not isinstance(root, dict):
            raise VendorError(
                "BEA returned an invalid response", transient=False,
                failure_class=FailureClass.PARSE,
            )
        result = root.get("Results") or {}
        error = result.get("Error") if isinstance(result, dict) else None
        if not isinstance(error, dict):
            return
        code = str(error.get("APIErrorCode") or "")
        if code in {"1", "3", "4"}:
            raise VendorError(
                "BEA credential rejected or inactive", transient=False,
                failure_class=FailureClass.AUTH_FAILURE,
            )
        raise VendorError(
            "BEA returned an API-level error", transient=False,
            failure_class=FailureClass.UNAVAILABLE,
        )

    def get_official_series(self, series_id: str, count: int = 8) -> Optional[list[tuple[str, float]]]:
        if series_id != self.SERIES:
            return None
        data = self._get_json(
            self.URL,
            params={
                "UserID": self.api_key,
                "method": "GetData",
                "DataSetName": "NIPA",
                "TableName": "T10101",
                "Frequency": "Q",
                "Year": ",".join(str(year) for year in range(date.today().year - 4, date.today().year + 1)),
                "ResultFormat": "JSON",
            },
            operation="official_macro_series",
        )
        rows = ((data or {}).get("BEAAPI") or {}).get("Results") or {}
        if not isinstance(rows, dict):
            return None
        observations = []
        for row in rows.get("Data") or []:
            if not isinstance(row, dict) or str(row.get("LineNumber") or "") != "1":
                continue
            if row.get("SeriesCode") and row["SeriesCode"] != "A191RL":
                continue
            if row.get("CL_UNIT") and row["CL_UNIT"] != "Percent change, annual rate":
                continue
            period = str(row.get("TimePeriod") or "")
            match = re.fullmatch(r"(\d{4})Q([1-4])", period)
            if not match:
                continue
            try:
                value = float(str(row.get("DataValue") or "").replace(",", ""))
            except ValueError:
                continue
            if math.isfinite(value):
                month = (int(match.group(2)) - 1) * 3 + 1
                observations.append((f"{match.group(1)}-{month:02d}-01", value))
        return sorted(observations)[-count:] or None


class EiaVendor(VendorClient):
    """Monthly Cushing WTI spot price, in dollars per barrel."""

    NAME = "eia"
    KEY_ENV = "EIA_API_KEY"
    DEFAULT_RPM = 5
    URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
    SERIES = "EIA_WTI_M"

    def get_energy_series(self, series_id: str, count: int = 8) -> Optional[list[tuple[str, float]]]:
        if series_id != self.SERIES:
            return None
        data = self._get_json(
            self.URL,
            params={
                "api_key": self.api_key,
                "frequency": "monthly",
                "data[0]": "value",
                "facets[series][]": "RWTC",
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "offset": 0,
                "length": min(max(count, 1), 24),
            },
            operation="energy_context",
        )
        rows = ((data or {}).get("response") or {}).get("data") or []
        observations = []
        for row in rows:
            if not isinstance(row, dict) or row.get("series") != "RWTC":
                continue
            period = str(row.get("period") or "")
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
                continue
            try:
                value = float(str(row.get("value") or "").replace(",", ""))
            except ValueError:
                continue
            if math.isfinite(value) and value > 0:
                observations.append((f"{period}-01", value))
        return sorted(observations)[-count:] or None


def _finite(raw) -> Optional[float]:
    try:
        value = float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


class TreasuryFiscalVendor(VendorClient):
    """Treasury Fiscal Data: the average rate paid on marketable federal debt."""

    NAME = "treasury_fiscal"
    KEY_ENV = None
    DEFAULT_RPM = 10
    URL = (
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
        "v2/accounting/od/avg_interest_rates"
    )
    #: Our series id -> the dataset's own security description. The dataset
    #: carries one row per security class per month; only the exact total is
    #: read, never a sum of its parts.
    SERIES = {"TSY_AVG_RATE": "Total Marketable"}

    def get_context_series(self, series_id: str, count: int = 8) -> Optional[list[tuple[str, float]]]:
        description = self.SERIES.get(series_id)
        if description is None:
            return None
        data = self._get_json(
            self.URL,
            params={
                "filter": f"security_desc:eq:{description}",
                "sort": "-record_date",
                "page[size]": min(max(count, 1), 36),
                "fields": "record_date,security_desc,avg_interest_rate_amt",
            },
            operation="macro_context",
        )
        observations = []
        for row in (data or {}).get("data") or []:
            if not isinstance(row, dict) or row.get("security_desc") != description:
                continue
            day = str(row.get("record_date") or "")
            value = _finite(row.get("avg_interest_rate_amt"))
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) and value is not None:
                observations.append((day, value))
        return sorted(observations)[-count:] or None


class EcbVendor(VendorClient):
    """ECB Data Portal: the deposit facility rate and the euro reference rate."""

    NAME = "ecb"
    KEY_ENV = None
    DEFAULT_RPM = 10
    BASE = "https://data-api.ecb.europa.eu/service/data/"
    #: The deposit rate is stored as the level set at each decision, so its
    #: observations are decision dates rather than a daily repetition.
    SERIES = {
        "ECB_DFR": "FM/B.U2.EUR.4F.KR.DFR.LEV",
        "ECB_EURUSD": "EXR/M.USD.EUR.SP00.A",
    }

    def get_context_series(self, series_id: str, count: int = 8) -> Optional[list[tuple[str, float]]]:
        key = self.SERIES.get(series_id)
        if key is None:
            return None
        data = self._get_json(
            self.BASE + key,
            params={"lastNObservations": min(max(count, 1), 36), "format": "jsondata"},
            headers={"Accept": "application/json"},
            operation="macro_context",
        )
        if not isinstance(data, dict):
            return None
        try:
            series = data["dataSets"][0]["series"]
            dates = [str(v.get("id") or "") for v in data["structure"]["dimensions"]["observation"][0]["values"]]
        except (KeyError, IndexError, TypeError, AttributeError):
            return None
        if not isinstance(series, dict) or len(series) != 1:
            # The key names one series; anything else is not the series asked for.
            return None
        observations = []
        for index, cell in (next(iter(series.values())).get("observations") or {}).items():
            try:
                period = dates[int(index)]
            except (ValueError, IndexError):
                continue
            value = _finite(cell[0]) if isinstance(cell, list) and cell else None
            if value is None:
                continue
            if re.fullmatch(r"\d{4}-\d{2}", period):
                period = f"{period}-01"
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
                observations.append((period, value))
        return sorted(observations)[-count:] or None


class WorldBankVendor(VendorClient):
    """World Bank WDI: annual real GDP growth for the world economy."""

    NAME = "world_bank"
    KEY_ENV = None
    DEFAULT_RPM = 10
    TIMEOUT_SECONDS = 8.0
    URL = "https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
    SERIES = {"WB_GDP_WORLD": ("WLD", "NY.GDP.MKTP.KD.ZG")}

    def get_context_series(self, series_id: str, count: int = 8) -> Optional[list[tuple[str, float]]]:
        spec = self.SERIES.get(series_id)
        if spec is None:
            return None
        country, indicator = spec
        data = self._get_json(
            self.URL.format(country=country, indicator=indicator),
            params={"format": "json", "mrv": min(max(count, 1), 30), "per_page": 30},
            operation="macro_context",
        )
        # Errors arrive as HTTP 200 with a one-element message list.
        if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
            return None
        observations = []
        for row in data[1]:
            if not isinstance(row, dict):
                continue
            if (row.get("indicator") or {}).get("id") != indicator or row.get("countryiso3code") != country:
                continue
            year = str(row.get("date") or "")
            value = _finite(row.get("value")) if row.get("value") is not None else None
            if re.fullmatch(r"\d{4}", year) and value is not None:
                observations.append((f"{year}-01-01", value))
        return sorted(observations)[-count:] or None
