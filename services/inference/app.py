"""
EXP-006 inference service — research model, served read-only.

## What this serves, and what it is not

A single fitted instance of the EXP-006 `gradient_boosting` specification. It
predicts a **cross-sectional rank** for a 21-session horizon: a number in roughly
[-1, 1] saying where a name is expected to sit relative to its peers, not a
return, not a price, and not a recommendation.

**The model is not production-promoted and this service does not pretend
otherwise.** Every response carries `research_status: EXPERIMENTAL` and
`promotion_status: BLOCKED`, and `/model` names the gate it fails (net Sharpe
−0.102 at a 10 bp half-spread). The registry's production count is zero and this
service has no authority to change that — promotion happens in
`ModelRegistry.promote()`, in the research repository, not here.

## The distinction that must not be lost

EXP-006's metrics — IC +0.0290, t +2.66, gross Sharpe +0.384 — were estimated
from **eight separate walk-forward fits** and describe the *specification*. The
artifact loaded here is **one** fit of that specification over the full
pre-holdout window. It is the object you deploy; it is not the object those
numbers were measured on. `/model` reports them under
`specification_metrics`, with that caveat attached, rather than as properties of
this file.

## Deliberately absent

No training. No dataset access. No Dolt clones. No feature computation from raw
market data — callers supply an already-computed feature vector, because the
point-in-time feature pipeline is a research concern with a 14 GB dependency and
has no business on an inference host. A caller that cannot supply features
cannot get a prediction, and that is the correct failure.
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger("omnisignal.inference")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ARTIFACT_DIR = Path(os.environ.get("MODEL_ARTIFACT_DIR", "artifacts"))
ARTIFACT_NAME = os.environ.get("MODEL_ARTIFACT", "gradient_boosting@EXP-006")

#: Browser origins permitted to call this service.
#:
#: Defaults to nothing. An inference service reachable from any origin is a free
#: compute endpoint for whoever finds it, and the only browser that needs it is
#: the miniAladdin frontend — which in practice reaches it through the backend
#: anyway. Set `ALLOWED_ORIGINS` to a comma-separated list to widen it.
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()
]

#: Cap on a single batch. Not a rate limiter — just a bound so one request
#: cannot ask the box to score an unbounded matrix.
MAX_BATCH = 500

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load the artifact once, before the first request.

    A lifespan handler rather than `@app.on_event("startup")`: the latter is
    deprecated, and it does not fire under `TestClient` unless the client is
    used as a context manager — which meant the smoke test saw a permanently
    degraded service and the real cause was invisible.
    """
    _load()
    yield


app = FastAPI(
    title="miniAladdin quant inference",
    description=(
        "EXP-006 research model. EXPERIMENTAL — not production-promoted, "
        "not investment advice."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

_state: dict[str, Any] = {"model": None, "imputer": None, "features": [], "meta": {}, "error": None}


def _load() -> None:
    """Load once, at startup. A request must never trigger a disk read."""
    import joblib

    began = time.perf_counter()
    bundle_path = ARTIFACT_DIR / f"{ARTIFACT_NAME}.joblib"
    meta_path = ARTIFACT_DIR / f"{ARTIFACT_NAME}.metadata.json"
    try:
        bundle = joblib.load(bundle_path)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001 — reported, never faked
        _state["error"] = f"{type(error).__name__}: {error}"
        logger.error("inference: artifact load FAILED — %s", _state["error"])
        return

    _state.update(
        model=bundle["model"],
        imputer=bundle["imputer"],
        features=list(bundle["features"]),
        meta=meta,
        error=None,
    )
    logger.info(
        "inference: loaded %s (%d features) in %.2fs — status %s / promotion %s",
        ARTIFACT_NAME, len(_state["features"]), time.perf_counter() - began,
        meta.get("research_status"), meta.get("promotion_status"),
    )


# ── contracts ────────────────────────────────────────────────────────────────


class PredictItem(BaseModel):
    symbol: str = Field(..., max_length=16)
    #: Feature name -> value. Missing features are imputed with the training
    #: medians the artifact carries; unknown names are ignored and reported.
    features: dict[str, float]


class PredictRequest(BaseModel):
    items: list[PredictItem] = Field(..., min_length=1, max_length=MAX_BATCH)
    as_of: Optional[str] = None


# ── endpoints ────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness plus whether the model is actually usable.

    `ok` is false when the artifact failed to load. A service that reports
    healthy while unable to predict is worse than one that is down, because the
    caller's fallback never engages.
    """
    if _state["model"] is None and _state["error"] is None:
        _load()          # cold path: a caller reached us before lifespan ran
    loaded = _state["model"] is not None
    return {
        "ok": loaded,
        "status": "ready" if loaded else "degraded",
        "model_loaded": loaded,
        "error": _state["error"],
        "artifact": ARTIFACT_NAME,
        "features": len(_state["features"]),
    }


@app.get("/model")
def model_card() -> dict[str, Any]:
    """Full provenance. Everything a caller needs to judge the prediction."""
    if _state["model"] is None:
        raise HTTPException(status_code=503, detail=f"model not loaded: {_state['error']}")
    meta = _state["meta"]
    return {
        "model_id": meta.get("model_id"),
        "model_version": meta.get("model_version"),
        "registry_key": meta.get("registry_key"),
        "experiment_id": meta.get("experiment_id"),
        "experiment_fingerprint": meta.get("experiment_fingerprint"),
        "target": meta.get("target"),
        "horizon_sessions": meta.get("horizon_sessions"),
        "prediction_units": (
            "cross-sectional rank in [-1, 1] over the 21-session forward horizon; "
            "NOT a return, NOT a price, NOT a recommendation"
        ),
        "features": meta.get("features"),
        "feature_count": meta.get("feature_count"),
        "feature_families": meta.get("feature_families"),
        "preprocessing": meta.get("preprocessing"),
        "dataset_version": meta.get("dataset_version"),
        "dataset_content_hash": meta.get("dataset_content_hash"),
        "git_commit": meta.get("git_commit"),
        "seed": meta.get("seed"),
        "hyperparameters": meta.get("hyperparameters"),
        "training_cutoff": (meta.get("fit_scope") or {}).get("training_cutoff"),
        "fit_scope": meta.get("fit_scope"),
        "specification_metrics": meta.get("specification_metrics"),
        "research_status": meta.get("research_status"),
        "promotion_status": meta.get("promotion_status"),
        "promotion_blocked_by": meta.get("promotion_blocked_by"),
        "holdout": meta.get("holdout"),
        "usage": meta.get("usage"),
        "artifact_sha256": meta.get("sha256"),
        "built_at": meta.get("built_at"),
    }


@app.post("/predict")
def predict(request: PredictRequest) -> dict[str, Any]:
    """Score a batch of pre-computed feature vectors.

    The response repeats the model's identity and status on every call. A
    prediction that travels without its provenance eventually gets quoted
    without it.
    """
    if _state["model"] is None:
        raise HTTPException(status_code=503, detail=f"model not loaded: {_state['error']}")

    features: list[str] = _state["features"]
    known = set(features)
    began = time.perf_counter()

    matrix = np.full((len(request.items), len(features)), np.nan, dtype=float)
    unknown: set[str] = set()
    supplied: list[int] = []
    for row, item in enumerate(request.items):
        unknown |= set(item.features) - known
        present = 0
        for column, name in enumerate(features):
            value = item.features.get(name)
            if value is not None and np.isfinite(value):
                matrix[row, column] = float(value)
                present += 1
        supplied.append(present)

    ready = _state["imputer"].transform(matrix)
    scores = np.asarray(_state["model"].predict(ready), dtype=float)

    meta = _state["meta"]
    predictions = [
        {
            "symbol": item.symbol.upper(),
            "prediction": None if not np.isfinite(scores[i]) else round(float(scores[i]), 6),
            "features_supplied": supplied[i],
            "features_expected": len(features),
            "features_imputed": len(features) - supplied[i],
        }
        for i, item in enumerate(request.items)
    ]

    return {
        "predictions": predictions,
        "as_of": request.as_of,
        "target": meta.get("target"),
        "horizon_sessions": meta.get("horizon_sessions"),
        "prediction_units": (
            "cross-sectional rank in [-1, 1]; higher means expected to rank above "
            "peers over the next 21 sessions. NOT a return and NOT a recommendation."
        ),
        "model_id": meta.get("model_id"),
        "model_version": meta.get("model_version"),
        "experiment_id": meta.get("experiment_id"),
        "research_status": meta.get("research_status"),
        "promotion_status": meta.get("promotion_status"),
        "disclaimer": meta.get("usage"),
        "unknown_features_ignored": sorted(unknown)[:20],
        "elapsed_ms": round((time.perf_counter() - began) * 1000, 2),
    }
