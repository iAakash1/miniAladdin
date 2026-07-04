"""
Analyst consensus snapshot store (plan item 10).

Persist-only for now — NOT scored. Revision momentum, dispersion and
consensus drift (docs/QUANT-REVIEW.md §8) all derive from this history,
and the history cannot be bought later; recording starts today.

Append-only JSONL per ticker, one row per UTC day, under
research_vault/analyst_snapshots/ (gitignored pipeline output). On
Railway's ephemeral filesystem this is best-effort until a volume is
attached — documented, not hidden.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

STORE_DIR = Path(__file__).parent.parent.parent / "research_vault" / "analyst_snapshots"
_lock = threading.Lock()
_recorded_today: set[str] = set()  # process-local fast path


def _path(ticker: str) -> Path:
    return STORE_DIR / f"{ticker.upper()}.jsonl"


def record_snapshot(
    ticker: str,
    price: Optional[float],
    analyst_target: Optional[float],
    pe_ratio: Optional[float],
    forward_pe: Optional[float],
    eps: Optional[float],
) -> bool:
    """One row per ticker per UTC day. Returns True when a row was written.
    Never raises — persistence must not affect the request path."""
    ticker = ticker.upper()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fast_key = f"{ticker}:{today}"
    if fast_key in _recorded_today:
        return False
    try:
        with _lock:
            STORE_DIR.mkdir(parents=True, exist_ok=True)
            path = _path(ticker)
            if path.exists():
                last_line = ""
                with path.open("rb") as handle:
                    try:
                        handle.seek(-min(400, path.stat().st_size), 2)
                    except OSError:
                        handle.seek(0)
                    last_line = handle.read().decode(errors="ignore").strip().splitlines()[-1] if path.stat().st_size else ""
                if last_line and f'"date": "{today}"' in last_line:
                    _recorded_today.add(fast_key)
                    return False
            row: dict[str, Any] = {
                "date": today,
                "ts": datetime.now(timezone.utc).isoformat(),
                "price": price,
                "analyst_target": analyst_target,
                "pe_ratio": pe_ratio,
                "forward_pe": forward_pe,
                "eps": eps,
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
        _recorded_today.add(fast_key)
        return True
    except Exception:  # noqa: BLE001 — never let persistence break research
        logger.exception("analyst snapshot write failed for %s", ticker)
        return False


def load_snapshots(ticker: str, limit: int = 400) -> list[dict[str, Any]]:
    """Read history (oldest→newest). For the future revision-momentum factor."""
    try:
        path = _path(ticker)
        if not path.exists():
            return []
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return rows[-limit:]
    except Exception:  # noqa: BLE001
        logger.exception("analyst snapshot read failed for %s", ticker)
        return []


def reset_for_tests(directory: Optional[Path] = None) -> None:
    global STORE_DIR
    if directory is not None:
        STORE_DIR = directory
    _recorded_today.clear()
