"""Measured compute provenance; absent GPU values remain absent."""

from __future__ import annotations

import platform
import resource
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComputeProbe:
    began: float = field(default_factory=time.perf_counter)
    fit_seconds: float = 0.0
    prediction_seconds: float = 0.0

    def finish(self) -> dict[str, Any]:
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports KiB.
        peak_mb = peak / (1024 * 1024) if platform.system() == "Darwin" else peak / 1024
        return {
            "wall_seconds": round(time.perf_counter() - self.began, 6),
            "fit_seconds": round(self.fit_seconds, 6),
            "prediction_seconds": round(self.prediction_seconds, 6),
            "cpu": platform.processor() or platform.machine(),
            "peak_rss_mb": round(float(peak_mb), 2),
            "gpu": None,
            "vram_peak_mb": None,
            "platform": platform.platform(),
            "python": platform.python_version(),
        }
