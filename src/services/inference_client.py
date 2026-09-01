"""
Client for the Render inference service.

## The boundary this draws

miniAladdin's research architecture is unchanged. This adds one thin edge:
the product can ask a deployed model for a prediction, and it gets back the
prediction *with its provenance attached*, or it gets back an explicit
unavailability. It never gets back a bare number.

## Failing is the normal case, not the exception

The inference service is on a free Render plan and will cold-start, time out and
occasionally be down. Every call here is wrapped, bounded by a short timeout, and
returns a structured `unavailable` result rather than raising. **No page depends
on this service.** `/quant` renders its research evidence from local artifacts
whether or not inference answers, and the company panel degrades to a disclosure.

That is a deliberate inversion of the usual dependency: the research surface is
the product, and the model is an optional annotation on it.

## What this refuses to do

It does not compute features — the point-in-time pipeline is a research concern
with a 14 GB dependency. It reads a **frozen, dated** snapshot and says so. And
it never upgrades the model's status: `research_status` and `promotion_status`
come from the service's own metadata, which comes from the artifact, which comes
from the registry's decision. Nothing in this file can promote anything.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("omnisignal.services.inference")

#: Where the model lives. Empty means "not configured", which is reported as
#: such rather than guessed at.
INFERENCE_URL = os.environ.get("QUANT_INFERENCE_URL", "").rstrip("/")

#: Short on purpose. A slow model must not become a slow page.
TIMEOUT_SECONDS = float(os.environ.get("QUANT_INFERENCE_TIMEOUT", "8"))

#: Snapshot location. Committed alongside the artifact.
SNAPSHOT_DIR = Path(os.environ.get("MODEL_ARTIFACT_DIR", "artifacts"))

#: Model metadata is immutable per deploy, so it is cached. Predictions are not.
_META_TTL_SECONDS = 300.0
_meta_cache: dict[str, Any] = {}
_snapshot_cache: dict[str, Any] = {}
_lock = threading.Lock()


def configured() -> bool:
    return bool(INFERENCE_URL)


def _unavailable(detail: str, *, remedy: Optional[str] = None,
                 status: str = "unavailable") -> dict[str, Any]:
    return {
        "status": status,
        "detail": detail,
        "remedy": remedy or "Set QUANT_INFERENCE_URL to the deployed service.",
        "research_status": "EXPERIMENTAL",
        "promotion_status": "BLOCKED",
    }


def _from_exception(error: BaseException) -> dict[str, Any]:
    """Classify a transport failure, because the causes are not equivalent.

    Every failure used to collapse into `unavailable` carrying a raw exception
    string. A free-tier cold start and a service that no longer exists then look
    identical to the reader, and they need opposite responses: one is a wait,
    the other is an outage.

    Measured 2026-09-01: the inference service takes ~43s to wake from Render's
    free-tier spin-down, against a request budget of 8s. So a timeout here is
    the *expected* first response after ~15 minutes of inactivity, and calling
    it "unavailable" describes the most routine state of the deployment as a
    fault.
    """
    import requests

    if isinstance(error, requests.exceptions.Timeout):
        return _unavailable(
            f"no response within {TIMEOUT_SECONDS:.0f}s",
            status="waking",
            remedy=(
                "The service is most likely starting. Render's free tier spins a "
                "service down after ~15 minutes of inactivity and takes roughly a "
                "minute to wake. Retry shortly; the research evidence on this page "
                "is read from committed artifacts and is unaffected."
            ),
        )
    if isinstance(error, requests.exceptions.ConnectionError):
        return _unavailable(
            f"could not connect: {type(error).__name__}",
            status="waking",
            remedy=(
                "The host refused or dropped the connection, which also happens "
                "while a spun-down service is starting. If it persists for more "
                "than a few minutes, check the service is deployed and running."
            ),
        )
    return _unavailable(f"{type(error).__name__}: {error}")


def _snapshot() -> dict[str, Any]:
    """The frozen feature snapshot, loaded once."""
    with _lock:
        if _snapshot_cache:
            return _snapshot_cache
    try:
        import pandas as pd

        meta = json.loads(
            (SNAPSHOT_DIR / "feature_snapshot.metadata.json").read_text(encoding="utf-8")
        )
        frame = pd.read_parquet(SNAPSHOT_DIR / "feature_snapshot.parquet")
        payload = {
            "meta": meta,
            "by_symbol": {
                str(row["symbol"]).upper(): {
                    f: (None if row[f] != row[f] else float(row[f]))
                    for f in meta["features"] if f in frame.columns
                }
                for _, row in frame.iterrows()
            },
        }
    except Exception as error:  # noqa: BLE001
        logger.warning("inference: feature snapshot unavailable (%s)", error)
        payload = {"meta": None, "by_symbol": {}}
    with _lock:
        _snapshot_cache.update(payload)
    return payload


def health() -> dict[str, Any]:
    if not configured():
        return _unavailable("QUANT_INFERENCE_URL is not set")
    try:
        import requests

        response = requests.get(f"{INFERENCE_URL}/health", timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return {"status": "ok", **response.json()}
    except Exception as error:  # noqa: BLE001
        return _from_exception(error)


def model_card() -> dict[str, Any]:
    """The deployed model's provenance, cached briefly."""
    if not configured():
        return _unavailable("QUANT_INFERENCE_URL is not set")

    now = time.time()
    with _lock:
        cached = _meta_cache.get("payload")
        stamped = _meta_cache.get("at", 0.0)
    if cached and now - stamped < _META_TTL_SECONDS:
        return cached

    try:
        import requests

        response = requests.get(f"{INFERENCE_URL}/model", timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = {"status": "ok", **response.json()}
    except Exception as error:  # noqa: BLE001
        return _from_exception(error)

    with _lock:
        _meta_cache.update(payload=payload, at=now)
    return payload


def predict(symbols: list[str]) -> dict[str, Any]:
    """Score symbols from the frozen snapshot.

    Symbols absent from the snapshot are reported as `not_covered` rather than
    imputed into existence — the universe is the top 250 by dollar volume on the
    snapshot date, and a name outside it has no feature vector.
    """
    if not configured():
        return _unavailable("QUANT_INFERENCE_URL is not set")

    snapshot = _snapshot()
    if not snapshot["by_symbol"]:
        return _unavailable("feature snapshot is not available on this host",
                            remedy="Run scripts.quant.export_feature_snapshot.")

    wanted = [s.upper() for s in symbols]
    covered = [s for s in wanted if s in snapshot["by_symbol"]]
    missing = [s for s in wanted if s not in snapshot["by_symbol"]]

    if not covered:
        return {
            "status": "not_covered",
            "detail": (
                f"None of {wanted} is in the snapshot universe "
                f"({len(snapshot['by_symbol'])} symbols, top 250 by dollar volume "
                f"as of {snapshot['meta']['as_of']})."
            ),
            "as_of": snapshot["meta"]["as_of"],
            "not_covered": missing,
            "research_status": "EXPERIMENTAL",
            "promotion_status": "BLOCKED",
        }

    body = {
        "items": [{"symbol": s, "features": snapshot["by_symbol"][s]} for s in covered],
        "as_of": snapshot["meta"]["as_of"],
    }
    try:
        import requests

        response = requests.post(
            f"{INFERENCE_URL}/predict", json=body, timeout=TIMEOUT_SECONDS
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as error:  # noqa: BLE001
        return _from_exception(error)

    return {
        "status": "ok",
        **payload,
        "feature_as_of": snapshot["meta"]["as_of"],
        "not_covered": missing,
        "feature_snapshot_note": snapshot["meta"]["note"],
    }
