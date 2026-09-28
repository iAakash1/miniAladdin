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
