"""
Live training progress — real measurements, never a synthetic bar.

## Why this is its own module

A progress display that estimates rather than reports is worse than none: it
teaches the reader to trust a number that is not measured. `src/services/
factor_lab_service.py` already made this argument for the panel build —

    That also makes the loader honest for the first time: the stages it shows
    are reported by the process doing the work rather than estimated from a
    timer.

— and the same standard applies here. Every field below is sampled at the
moment it is printed: elapsed time from a monotonic clock, RSS from the
process, fold and model counts from the loop itself. The ETA is the only
derived quantity and it is labelled as a projection from observed throughput,
not a promise.

## Resource sampling without a dependency

`psutil` would be the obvious choice and is not added for this. Resident memory
comes from `resource.getrusage`, which is in the standard library, and CPU
utilisation from `os.times()` deltas against wall time. Both are approximations
of what Activity Monitor shows, and saying so here is cheaper than a dependency.
"""

from __future__ import annotations

import os
import resource
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional


def _rss_gb() -> float:
    """Peak resident set size in GB.

    `ru_maxrss` is bytes on macOS and kilobytes on Linux — the platform check
    is not defensive noise, it is a factor of 1024.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024**3 if sys.platform == "darwin" else 1024**2
    return usage / divisor


@dataclass
class TrainingProgress:
    """Thread-safe counters plus a one-line live display."""

    total_units: int
    label: str = "training"
    stream: Any = None
    quiet: bool = False

    completed: int = 0
    started_at: float = field(default_factory=time.perf_counter)
    _cpu_start: tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_line_length: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.stream = self.stream or sys.stdout
        times = os.times()
        self._cpu_start = (times.user, times.system)

    # ── measurement ──────────────────────────────────────────────────────

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.started_at

    def cpu_utilisation(self) -> float:
        """Approximate mean cores busy since start, over wall clock.

        Includes child processes so a joblib fan-out is counted. Two honest
        caveats, both observed rather than theorised:

        1. `os.times().children_*` only accumulates when a child is **reaped**,
           so a pool that exits mid-interval dumps its entire CPU history into
           one sample. A second label reusing the counter showed "139 cores" on
           a 12-core machine for exactly this reason.
        2. The result is therefore clamped to the logical CPU count. The clamp
           is a display bound, not a correction — it stops the number being
           absurd without pretending the accounting is exact, which is why this
           is labelled approximate everywhere it appears.
        """
        times = os.times()
        cpu = (times.user + times.children_user) - self._cpu_start[0]
        cpu += (times.system + times.children_system) - self._cpu_start[1]
        ceiling = float(os.cpu_count() or 1)
        return max(0.0, min(cpu / max(self.elapsed, 1e-9), ceiling))

    def eta_seconds(self) -> Optional[float]:
        """Projection from observed throughput. Not a promise, and labelled so."""
        if self.completed <= 0:
            return None
        rate = self.completed / max(self.elapsed, 1e-9)
        return (self.total_units - self.completed) / rate if rate > 0 else None

    # ── reporting ────────────────────────────────────────────────────────

    def advance(self, detail: str = "", **metrics: Any) -> None:
        with self._lock:
            self.completed += 1
            snapshot = {
                "unit": self.completed,
                "detail": detail,
                "elapsed_s": round(self.elapsed, 2),
                "rss_gb": round(_rss_gb(), 2),
                "cpu_cores": round(self.cpu_utilisation(), 2),
                **{k: v for k, v in metrics.items() if v is not None},
            }
            self.history.append(snapshot)
            self._render(detail, metrics)

    def _render(self, detail: str, metrics: dict[str, Any]) -> None:
        if self.quiet:
            return
        eta = self.eta_seconds()
        parts = [
            f"[{self.completed:>3}/{self.total_units}]",
            f"{self.label}",
            detail[:46].ljust(46) if detail else "",
        ]
        for name, value in metrics.items():
            if isinstance(value, float):
                parts.append(f"{name}={value:+.4f}")
            elif value is not None:
                parts.append(f"{name}={value}")
        parts.append(f"| ~{self.cpu_utilisation():.1f}c {_rss_gb():.1f}GB")
        parts.append(f"{self.elapsed:.0f}s")
        if eta is not None:
            parts.append(f"eta~{eta:.0f}s")

        line = " ".join(str(p) for p in parts if p != "")
        # Overwrite in place on a TTY; append cleanly when piped to a log, where
        # carriage returns would produce one unreadable line.
        if self.stream.isatty():
            padding = max(0, self._last_line_length - len(line))
            self.stream.write("\r" + line + " " * padding)
            self._last_line_length = len(line)
        else:
            self.stream.write(line + "\n")
        self.stream.flush()

    def finish(self, summary: str = "") -> dict[str, Any]:
        if not self.quiet:
            if self.stream.isatty():
                self.stream.write("\n")
            self.stream.flush()
        report = {
            "label": self.label,
            "units": self.completed,
            "total_units": self.total_units,
            "elapsed_s": round(self.elapsed, 2),
            "units_per_second": round(self.completed / max(self.elapsed, 1e-9), 3),
            "peak_rss_gb": round(_rss_gb(), 2),
            "mean_cpu_cores_approx": round(self.cpu_utilisation(), 2),
            "cpu_note": (
                "Approximate: children_* accumulates only on reap, so a pool exiting "
                "mid-interval inflates one sample. Clamped to logical CPU count."
            ),
            "summary": summary,
        }
        if not self.quiet:
            print(
                f"  -> {self.label}: {self.completed}/{self.total_units} in "
                f"{report['elapsed_s']}s  "
                f"({report['units_per_second']}/s, ~{report['mean_cpu_cores_approx']} cores, "
                f"peak {report['peak_rss_gb']} GB)  {summary}",
                file=self.stream,
            )
        return report


def machine_profile() -> dict[str, Any]:
    """What the run had available. Recorded with every experiment."""
    import platform

    profile: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpus": os.cpu_count(),
        "python": platform.python_version(),
    }
    if sys.platform == "darwin":
        import subprocess

        for key, name in (
            ("hw.physicalcpu", "physical_cpus"),
            ("hw.memsize", "memory_bytes"),
            ("machdep.cpu.brand_string", "cpu_brand"),
        ):
            try:
                value = subprocess.run(
                    ["sysctl", "-n", key], capture_output=True, text=True, timeout=5
                ).stdout.strip()
                profile[name] = int(value) if value.isdigit() else value or None
            except (OSError, subprocess.SubprocessError, ValueError):
                profile[name] = None
    return profile
