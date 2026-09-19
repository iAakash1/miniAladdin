"""Independent verification of the SEC Financial Statement Data Set archives on disk.

The download manifest is a claim, not evidence.  This audit re-derives every fact it can from the
files themselves: presence, filename and quarter continuity, size and SHA-256 against the manifest,
ZIP readability, member CRCs, required members, and the acceptance-time range inside each archive.
The SEC publishes no checksums for these archives, so the SHA-256 recorded at download time is
self-recorded provenance; the only independent source check available is the HTTP Content-Length.
"""

from __future__ import annotations

import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from src.quant.pit.sec_foundation import (
    REQUIRED_MEMBERS, _parse_accepted, _request, archive_specs, sha256_file, DEFAULT_USER_AGENT,
)

QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def expected_quarters(start: tuple[int, int] = (2011, 1), end: tuple[int, int] = (2025, 2)) -> list[str]:
    return [spec["filename"] for spec in archive_specs(start[0], end[0], end[1]) if (spec["year"], spec["quarter"]) >= start]


def quarter_continuity(filenames: list[str]) -> dict[str, Any]:
    """Every quarter between the first and the last present, none missing, none duplicated."""
    keys = sorted((int(name[:4]), int(name[5])) for name in filenames)
    missing = []
    for (y0, q0), (y1, q1) in zip(keys, keys[1:]):
        step = (y1 * 4 + q1) - (y0 * 4 + q0)
        for gap in range(1, step):
            index = y0 * 4 + (q0 - 1) + gap
            missing.append(f"{index // 4}q{index % 4 + 1}.zip")
    return {"first": f"{keys[0][0]}q{keys[0][1]}" if keys else None, "last": f"{keys[-1][0]}q{keys[-1][1]}" if keys else None,
            "count": len(keys), "duplicates": len(keys) - len(set(keys)), "missing": missing, "continuous": not missing and len(keys) == len(set(keys))}


def audit_archive(path: Path, recorded: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Audit one archive.  Reads every member once (CRC) and the `sub` table for acceptance times."""
    started = time.perf_counter()
    row: dict[str, Any] = {"filename": path.name, "exists": path.exists(), "problems": []}
    if not path.exists():
        row["problems"].append("MISSING")
        return row
    row["bytes"] = path.stat().st_size
    row["sha256"] = sha256_file(path)
    if recorded is None:
        row["problems"].append("NOT_IN_MANIFEST")
    else:
        if recorded.get("bytes") != row["bytes"]:
            row["problems"].append("SIZE_DIFFERS_FROM_MANIFEST")
        if recorded.get("sha256") != row["sha256"]:
            row["problems"].append("SHA256_DIFFERS_FROM_MANIFEST")
    try:
        with zipfile.ZipFile(path) as archive:
            names = {Path(n).name.lower(): n for n in archive.namelist()}
            missing = sorted(REQUIRED_MEMBERS - set(names))
            row["members"] = sorted(names)
            if missing:
                row["problems"].append(f"MISSING_MEMBERS:{','.join(missing)}")
            bad = archive.testzip()  # reads every member and checks its CRC-32
            row["crc_ok"] = bad is None
            if bad is not None:
                row["problems"].append(f"CRC_FAILURE:{bad}")
            if not missing:
                with archive.open(names["sub.txt"]) as handle:
                    sub = pd.read_csv(handle, sep="\t", dtype=str, usecols=["adsh", "cik", "accepted", "form"], low_memory=False)
                accepted = _parse_accepted(sub["accepted"])
                row["sub_rows"] = int(len(sub))
                row["ciks"] = int(sub["cik"].nunique())
                row["accepted_min"] = str(accepted.min())
                row["accepted_max"] = str(accepted.max())
                row["accepted_unparsed"] = int(accepted.isna().sum())
                row["adsh_duplicates"] = int(sub["adsh"].duplicated().sum())
                year, quarter = int(path.stem[:4]), int(path.stem[5])
                lo = pd.Timestamp(year, 3 * quarter - 2, 1)
                hi = pd.Timestamp(year, *QUARTER_END[quarter]) + pd.Timedelta(days=1)
                inside = accepted.between(lo, hi + pd.Timedelta(days=1), inclusive="left")
                row["accepted_outside_quarter_share"] = float((~inside & accepted.notna()).mean())
                info = archive.getinfo(names["num.txt"])
                row["num_uncompressed_bytes"] = info.file_size
    except zipfile.BadZipFile as error:
        row["problems"].append(f"BAD_ZIP:{error}")
    row["seconds"] = round(time.perf_counter() - started, 1)
    return row


def source_sizes(filenames: list[str], *, user_agent: str = DEFAULT_USER_AGENT, pause: float = 0.12,
                 fetch: Optional[Callable[[str], Optional[int]]] = None) -> dict[str, Optional[int]]:
    """Content-Length from the official host (HEAD, <= ~8 requests/s).  None where unreachable."""
    def head(url: str) -> Optional[int]:
        try:
            with _request(url, method="HEAD", user_agent=user_agent) as response:
                return int(response.headers.get("Content-Length", 0)) or None
        except Exception:
            return None

    fetch = fetch or head
    specs = {spec["filename"]: spec["url"] for spec in archive_specs()}
    out = {}
    for name in filenames:
        out[name] = fetch(specs[name])
        time.sleep(pause)
    return out


def verify_archives(raw_dir: Path, manifest_path: Path, *, check_source: bool = True,
                    progress: Optional[Callable[[str], None]] = print) -> dict[str, Any]:
    raw_dir, manifest_path = Path(raw_dir), Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    recorded = {row["filename"]: row for row in manifest["archives"]}
    expected = expected_quarters()
    present = sorted(p.name for p in raw_dir.glob("????q?.zip"))
    unexpected = sorted(set(present) - set(expected))
    rows = []
    for index, name in enumerate(expected, 1):
        row = audit_archive(raw_dir / name, recorded.get(name))
        rows.append(row)
        if progress:
            progress(f"verify {index}/{len(expected)} {name}: {'OK' if not row['problems'] else row['problems']} ({row.get('seconds', 0)} s)")
    remote = source_sizes(expected) if check_source else {}
    for row in rows:
        size = remote.get(row["filename"])
        row["source_content_length"] = size
        row["source_size_check"] = "NOT_CHECKED" if not check_source else ("UNREACHABLE" if size is None else ("MATCH" if size == row.get("bytes") else "DIFFERS"))
    continuity = quarter_continuity(present)
    problems = [{"filename": r["filename"], "problems": r["problems"]} for r in rows if r["problems"]]
    source_differs = [r["filename"] for r in rows if r["source_size_check"] == "DIFFERS"]
    ok = not problems and not unexpected and continuity["continuous"] and len(rows) == len(expected)
    return {
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "PASS" if ok else "FAIL",
        "expected_archives": len(expected), "present_archives": len(present), "unexpected_files": unexpected,
        "continuity": continuity,
        "total_bytes": sum(r.get("bytes", 0) for r in rows),
        "problems": problems,
        "source_size_differs": source_differs,
        "source_check": "HTTP Content-Length against the official host; the SEC publishes no checksums" if check_source else "skipped",
        "sub_rows_total": sum(r.get("sub_rows", 0) for r in rows),
        "archives": rows,
    }
