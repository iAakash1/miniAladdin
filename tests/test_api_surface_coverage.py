"""Every endpoint is exposed in the UI, or declared internal on purpose.

The redesign began from a measurement: of 43 endpoints, eleven were called by
no component. They were not stubs — among them were the feature registry, the
dataset contracts and the model registry, which is to say the evidence for the
product's central claim was being computed and thrown away.

That was found by hand once. This test makes it impossible to reintroduce
silently: an endpoint added without a caller and without a deliberate entry in
INTERNAL fails here.

INTERNAL is not a way to quiet the test. Each entry names why the endpoint has
no user-facing surface, and an entry that stops being true is a lie this file
will keep telling, so they are kept short and checkable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api" / "index.py"
FRONTEND = ROOT / "dashboard" / "src"

#: Endpoints with no UI surface, and the reason each one has none.
INTERNAL: dict[str, str] = {
    "/api/health": "liveness probe for the platform, not for a person",
    "/api/metrics": "latency percentiles scraped by the host, not read in the product",
    "/api/graph/expand": "called by the graph explorer through a query builder, not by path",
    "/api/graph/path": "same",
    "/api/quant/features": "an alias of /api/ml/features; the UI calls the ml route",
    "/api/quant/datasets": "an alias of /api/ml/datasets; the UI calls the ml route",
    "/api/ml/capabilities": "mirrors /api/providers/capabilities, which is the one surfaced",
    "/api/research/providers/health": "duplicate of /api/providers/health",
    "/api/factors/universes": "populates a control inside the factor workspace, not a page",
    "/api/company/{ticker}/media": "called from the security workspace by composed path",
    "/api/memo/{ticker}": "server-generated analyst prose; the notebook is deliberately author-written instead, so this stays unwired",
    "/api/knowledge/{ticker}": "read through lib/knowledge, which composes the path",
    "/api/screen": "read through lib/intelligence/providers, which composes the path",
    "/api/quotes": "read through lib/watchlists, which composes the path",
}

ENDPOINT = re.compile(r'@app\.(?:get|post)\("([^"]+)"')


def _endpoints() -> list[str]:
    return sorted(set(ENDPOINT.findall(API.read_text())))


def _frontend_text() -> str:
    parts = []
    for path in FRONTEND.rglob("*"):
        if path.suffix in {".ts", ".tsx"} and path.is_file():
            parts.append(path.read_text())
    return "\n".join(parts)


def _is_referenced(endpoint: str, haystack: str) -> bool:
    """A path is referenced if its literal prefix appears anywhere in the UI.

    Templated segments are stripped: the UI builds those by interpolation, so
    the constant prefix is the only part that can appear literally.

    This is deliberately generous. It cannot distinguish a direct call from a
    sibling path sharing a prefix, so it can say an endpoint is reachable when
    only its neighbour is. That direction is the safe one: the test exists to
    catch endpoints with NO surface, and a false "reachable" is caught by
    reading, while a false "orphan" would train people to ignore the failure.
    """
    prefix = endpoint.split("{")[0].rstrip("/")
    return prefix in haystack


def test_the_api_surface_is_not_empty() -> None:
    """Guards the parser: a regex that matches nothing would pass everything."""
    assert len(_endpoints()) > 30


def test_every_endpoint_is_exposed_or_declared_internal() -> None:
    haystack = _frontend_text()
    orphans = [
        e for e in _endpoints()
        if e not in INTERNAL and not _is_referenced(e, haystack)
    ]
    assert orphans == [], (
        "endpoints with no UI surface and no INTERNAL entry:\n  "
        + "\n  ".join(orphans)
        + "\n\nEither surface them in a workspace or record why they have no surface."
    )


def test_internal_entries_describe_real_endpoints() -> None:
    """A reason attached to a route that no longer exists is stale documentation."""
    known = set(_endpoints())
    stale = sorted(set(INTERNAL) - known)
    assert stale == [], f"INTERNAL names endpoints that do not exist: {stale}"


def test_internal_entries_carry_a_reason() -> None:
    empty = sorted(k for k, v in INTERNAL.items() if not v.strip())
    assert empty == [], f"INTERNAL entries without a reason: {empty}"


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/ml/features",
        "/api/ml/datasets",
        "/api/ml/registry",
        "/api/quant/methodology",
        "/api/quant/experiments",
        "/api/quant/selection/{experiment_id}",
        "/api/quant/portfolio",
        "/api/quant/status",
        "/api/ml/provenance/{label}/{model_id}",
        "/api/providers/capabilities",
        "/api/providers/health",
        "/api/quant/covariance",
        "/api/quant/latest",
        "/api/dashboard",
        "/api/graph/workspace",
        "/api/backtest/{ticker}",
    ],
)
def test_the_endpoints_the_redesign_surfaced_stay_surfaced(endpoint: str) -> None:
    """These were orphans. A regression that re-orphans one fails here by name."""
    assert _is_referenced(endpoint, _frontend_text()), f"{endpoint} lost its UI surface"
