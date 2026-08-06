"""
Observability — where time goes, and how much of it was wasted.

Built because the same question kept needing a throwaway script: *where did
the dashboard's 25 seconds go?* The provider layer already tracked whether a
vendor was alive; nothing tracked what anything cost, so every optimisation
decision so far started with hand-written instrumentation on a laptop rather
than with production truth.

Two surfaces, deliberately separate:

    metrics.registry     process-wide, percentile latency per (vendor,
                         operation) — "what is slow, in general"
    request.profiled     one request's attribution and parallelism ratio —
                         "where did *this* request's time go"

Both are cheap enough to leave on permanently; `benchmarks/observability.py`
measures the overhead rather than asserting it is small.
"""

from src.observability.metrics import (
    BUCKET_BOUNDS_MS,
    Histogram,
    MetricsRegistry,
    registry,
    timer,
)
from src.observability.request import (
    RequestProfile,
    begin,
    clear,
    current,
    profiled,
    record_in_request,
)

__all__ = [
    "BUCKET_BOUNDS_MS",
    "Histogram",
    "MetricsRegistry",
    "RequestProfile",
    "begin",
    "clear",
    "current",
    "profiled",
    "record_in_request",
    "registry",
    "timer",
]
