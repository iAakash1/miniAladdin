"""Which deployment this process is: production, or somebody's laptop.

This existed inline in `/api/health` and had gone stale. It reported
"production" from `RAILWAY_ENVIRONMENT` long after the service moved to
Render, whose marker is `RENDER` / `RENDER_GIT_COMMIT` — so the live
deployment described itself as development, and anything gated on that
description was gated wrongly.

The fix is not to add this year's host to the list and wait for the same bug.
`APP_ENV` is the deliberate switch: when it is set it decides, because a
deployment should be able to state what it is without the code having to
recognise its landlord. The host markers stay underneath it as a fallback so
an existing deployment that sets none of this does not silently downgrade.
"""

from __future__ import annotations

import os

#: The explicit switch. Set it and nothing else is consulted.
APP_ENV = "APP_ENV"

#: Host-injected markers, consulted only when APP_ENV says nothing. Render
#: first because that is where this service runs; Railway retained so an
#: older deployment does not regress.
_HOST_MARKERS = ("RENDER", "RENDER_GIT_COMMIT", "RAILWAY_ENVIRONMENT")


def is_production() -> bool:
    """True when this process is serving a real deployment."""
    explicit = os.getenv(APP_ENV, "").strip().lower()
    if explicit:
        return explicit == "production"
    if any(os.getenv(name) for name in _HOST_MARKERS):
        return True
    return os.getenv("ENV", "").strip().lower() == "production"


def environment_name() -> str:
    """The word `/api/health` reports."""
    return "production" if is_production() else "development"
