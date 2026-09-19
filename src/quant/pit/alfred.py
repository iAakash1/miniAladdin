"""Small ALFRED vintage downloader for the Treasury series already used by the model."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.quant.pit.sec_foundation import atomic_json, sha256_file

SERIES = ("DGS3MO", "DGS2", "DGS10")
API = "https://api.stlouisfed.org/fred/series/observations"


def download_alfred(raw_dir: Path, manifest_path: Path, *, api_key: str | None = None,
                    realtime_start: str = "2011-01-01", realtime_end: str = "2025-05-09") -> dict[str, Any]:
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        return {"status": "BLOCKED_EXTERNAL_FRED_KEY", "series": list(SERIES)}
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for series_id in SERIES:
        query = urllib.parse.urlencode({
            "series_id": series_id, "api_key": key, "file_type": "json",
            "realtime_start": realtime_start, "realtime_end": realtime_end,
            "output_type": 4,
        })
        with urllib.request.urlopen(f"{API}?{query}", timeout=120) as response:
            payload = json.loads(response.read())
        observations = pd.DataFrame(payload.get("observations", []))
        observations = observations.rename(columns={"date": "observation_date"})
        observations["series_id"] = series_id
        observations["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        observations["value"] = pd.to_numeric(observations["value"], errors="coerce")
        path = raw_dir / f"{series_id}.parquet"
        temporary = path.with_suffix(".parquet.tmp")
        observations[["series_id", "observation_date", "realtime_start", "realtime_end", "value", "retrieved_at"]].to_parquet(temporary, compression="zstd", index=False)
        os.replace(temporary, path)
        records.append({"series_id": series_id, "rows": len(observations), "sha256": sha256_file(path)})
    manifest = {"status": "BUILT", "source": "ALFRED/FRED API", "series": records,
                "realtime_window": [realtime_start, realtime_end]}
    atomic_json(Path(manifest_path), manifest)
    return manifest
