"""Cheap process-memory diagnostics for health checks and request logging.

Linux reads are file-backed kernel counters.  No profiler dependency is
required, and no host paths or environment values are returned to callers.
"""

from __future__ import annotations

import os
import resource
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping


_CGROUP_LIMIT_PATHS = (
    Path("/sys/fs/cgroup/memory.max"),
    Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
)
_LIMIT_ENV_NAMES = ("MEMORY_LIMIT_MB", "RENDER_MEMORY_LIMIT_MB")
_UNLIMITED_CGROUP_BYTES = 1 << 60


@dataclass(frozen=True)
class MemorySnapshot:
    rss_mb: float | None
    peak_rss_mb: float | None
    memory_limit_mb: float | None
    memory_utilization_percent: float | None
    rss_source: str

    def as_dict(self) -> dict[str, float | str | None]:
        return asdict(self)


def _mb(value: int | float) -> float:
    return round(float(value) / (1024 * 1024), 2)


def _linux_status() -> tuple[float | None, float | None]:
    try:
        rows = Path("/proc/self/status").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, None
    values: dict[str, float] = {}
    for row in rows:
        if row.startswith(("VmRSS:", "VmHWM:")):
            name, raw, _unit = row.split(maxsplit=2)
            values[name.rstrip(":")] = round(float(raw) / 1024, 2)
    return values.get("VmRSS"), values.get("VmHWM")


def _resource_peak_mb() -> float | None:
    try:
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (OSError, ValueError):
        return None
    # Linux reports KiB; macOS reports bytes.
    return round(value / (1024 * 1024) if sys.platform == "darwin" else value / 1024, 2)


def memory_limit_mb(
    *,
    environ: Mapping[str, str] | None = None,
    cgroup_paths: tuple[Path, ...] = _CGROUP_LIMIT_PATHS,
) -> float | None:
    """Return an explicit/cgroup limit, never an inferred service-plan size."""
    environment = os.environ if environ is None else environ
    for name in _LIMIT_ENV_NAMES:
        raw = environment.get(name, "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 0:
            return round(value, 2)

    for path in cgroup_paths:
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if raw == "max":
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if 0 < value < _UNLIMITED_CGROUP_BYTES:
            return _mb(value)
    return None


def snapshot() -> MemorySnapshot:
    rss, peak = _linux_status()
    source = "proc_status"
    if peak is None:
        peak = _resource_peak_mb()
    if rss is None:
        # Portable fallback. On non-Linux this is a peak, not a fabricated
        # current reading, so the source makes the limitation explicit.
        rss = peak
        source = "resource_peak_fallback"
    limit = memory_limit_mb()
    utilization = (
        round(100.0 * rss / limit, 2)
        if rss is not None and limit is not None and limit > 0 else None
    )
    return MemorySnapshot(rss, peak, limit, utilization, source)


def configured_worker_count(environ: Mapping[str, str] | None = None) -> int | None:
    environment = os.environ if environ is None else environ
    for name in ("WEB_CONCURRENCY", "RENDER_WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"):
        raw = environment.get(name, "").strip()
        try:
            value = int(raw)
        except ValueError:
            continue
        if value > 0:
            return value
    return None


def pressure_level(utilization_percent: float | None) -> str | None:
    if utilization_percent is None or utilization_percent < 70:
        return None
    if utilization_percent >= 95:
        return "critical"
    if utilization_percent >= 85:
        return "high"
    return "elevated"
