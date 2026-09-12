"""What-If — the same engine, different inputs.

A sensitivity tool, and the design constraint that makes it trustworthy is
that it does not implement any scoring. Every simulation perturbs an *input*
that `score_ticker` already accepts and then calls `score_ticker`. There is no
second aggregation, no shortcut that estimates what the verdict would become,
and therefore no way for the simulated answer to disagree with the real engine
about how a factor is weighted.

The alternative — adjusting family scores directly and re-deriving a verdict —
would be a second scoring path, which is the thing this codebase spent a
release removing. A simulator that drifts from production is worse than no
simulator: it teaches a reader a sensitivity that is not the model's.

**Nothing is stored.** The perturbed frame is a copy, the scorecard is
discarded with the request, and no snapshot, ranking or saved analysis is
touched. The result is labelled a simulation everywhere it surfaces.
"""

from __future__ import annotations

import logging
import math
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("omnisignal.whatif")

WHATIF_VERSION = "whatif-v1"


class Lever(str, Enum):
    """What can be moved. Each maps to a real `score_ticker` argument."""

    MOMENTUM = "momentum"          # scales the trailing return path
    MACRO_REGIME = "macro_regime"  # the systemic risk multiplier
    VALUATION = "valuation"        # P/E and forward P/E
    SENTIMENT = "sentiment"        # average headline tone


#: Plain-language presets, so the interface offers scenarios rather than a row
#: of unlabelled sliders. The magnitudes are stated in the label because a
#: simulation whose size is invisible is not interpretable.
PRESETS: tuple[dict[str, Any], ...] = (
    {"key": "momentum_down_20", "lever": Lever.MOMENTUM, "change": -0.20,
     "label": "Momentum weakens by 20%"},
    {"key": "momentum_up_20", "lever": Lever.MOMENTUM, "change": 0.20,
     "label": "Momentum strengthens by 20%"},
    {"key": "macro_stress", "lever": Lever.MACRO_REGIME, "change": 0.30,
     "label": "Macro regime moves to high stress"},
    {"key": "macro_calm", "lever": Lever.MACRO_REGIME, "change": -0.20,
     "label": "Macro stress eases"},
    {"key": "valuation_cheaper", "lever": Lever.VALUATION, "change": -0.15,
     "label": "Valuation improves by 15%"},
    {"key": "valuation_richer", "lever": Lever.VALUATION, "change": 0.15,
     "label": "Valuation becomes 15% richer"},
    {"key": "sentiment_negative", "lever": Lever.SENTIMENT, "change": -0.40,
     "label": "News tone turns negative"},
)

_BY_KEY = {p["key"]: p for p in PRESETS}


class Simulation(BaseModel):
    """Current versus simulated. Always labelled as a simulation."""

    simulation: bool = True
    version: str = WHATIF_VERSION
    lever: str
    change: float
    label: str

    current_signal: Optional[str] = None
    current_confidence: Optional[int] = None
    current_risk: Optional[int] = None
    current_score: Optional[float] = None

    simulated_signal: Optional[str] = None
    simulated_confidence: Optional[int] = None
    simulated_risk: Optional[int] = None
    simulated_score: Optional[float] = None

    signal_changed: bool = False
    #: Family scores that moved, so a reader can see *where* the change landed
    #: rather than only that the verdict flipped.
    family_changes: dict[str, dict[str, Optional[float]]] = Field(default_factory=dict)
    note: Optional[str] = None


def _shifted_frame(frame, change: float):
    """A copy of the price path whose *total return* over the window moves by
    `change`, signed.

    The obvious implementation — scale each daily return by (1 + change) — is
    wrong, and wrong in a way that reads as plausible. It scales magnitude
    rather than direction, so for a security that fell over the window,
    "momentum weakens by 20%" makes the fall 20% shallower and the score goes
    *up*. That was the first version's behaviour and it was caught by reading
    the output rather than by any test, because every value it produced was
    finite and ordered.

    So the target is stated as a return, not a scale factor: if the window
    return is +8% and the change is -20%, the simulated window return is -12%.
    A constant daily drift is added to reach it. That makes each daily return
    an increasing affine function of the original — `(1 + r)` becomes
    `(1 + r)·k` — so the ordering of the days is exactly preserved: the best day
    stays the best, the worst stays the worst, and the correlation with the
    original return series is 1. It is not a claim that every day keeps its
    sign; on a measured 260-bar path a 20% shift flips 4–8% of days, the ones
    whose own move was smaller than the drift. The security keeps its character
    and changes its destination, which is what the scenario asks for.

    The first price is held and the last moves, which is the natural reading of
    "it performed differently". That does move the frame's final close, so the
    caller passes the *original* price and the original valuation multiples to
    the engine: momentum factors read the frame, valuation factors read those
    arguments, and the two levers stay independent instead of one lever quietly
    moving two sleeves.
    """
    closes = frame["Close"].astype(float)
    n = len(closes)
    if n < 3:
        return frame

    first, last = float(closes.iloc[0]), float(closes.iloc[-1])
    if not math.isfinite(first) or not math.isfinite(last) or first <= 0:
        return frame

    current = last / first - 1.0
    target = current + change
    # A window return of -100% or worse is not a price path; clamped so a large
    # negative change produces a severe decline rather than an invalid series.
    target = max(-0.95, target)

    growth_now, growth_new = 1.0 + current, 1.0 + target
    if growth_now <= 0 or growth_new <= 0:
        return frame

    # One constant daily factor, applied cumulatively, so the shape survives.
    per_day = (growth_new / growth_now) ** (1.0 / (n - 1))
    factors = [per_day ** i for i in range(n)]

    out = frame.copy()
    for column in ("Open", "High", "Low", "Close"):
        if column in out.columns:
            values = frame[column].astype(float).to_numpy()
            out[column] = [v * f for v, f in zip(values, factors)]
    return out


def _families(card) -> dict[str, Optional[float]]:
    return {
        name: getattr(card, f"{name}_score", None)
        for name in ("momentum", "fundamental", "quality", "news", "reversal")
    }


def simulate(
    context: Any,
    *,
    lever: Lever,
    change: float,
    label: Optional[str] = None,
) -> Optional[Simulation]:
    """Re-score one security under a perturbed input. Never mutates anything.

    Returns None when there is no baseline to compare against — a security the
    engine could not score has no sensitivity to report, and inventing one
    would be the simulator making a claim of its own.
    """
    from src.scoring.engine import score_ticker

    baseline = getattr(context, "scorecard", None)
    frame = getattr(context, "price_frame", None)
    if baseline is None or frame is None:
        return None

    # The *same* builder production scoring uses, so the "current" column is
    # the scorecard on the page beside it rather than a near-miss reconstruction.
    from src.agents.orchestrator import scoring_inputs

    kwargs = scoring_inputs(context)
    if kwargs is None:
        return None
    srm = kwargs["srm"]
    sentiment = kwargs["sentiment_avg"]

    simulated_frame = frame
    note: Optional[str] = None

    if lever is Lever.MOMENTUM:
        simulated_frame = _shifted_frame(frame, change)
        window_now = float(frame["Close"].iloc[-1]) / float(frame["Close"].iloc[0]) - 1.0
        note = (
            f"The window return moves from {window_now:+.1%} to "
            f"{max(-0.95, window_now + change):+.1%}. `price` and the valuation "
            "multiples are passed unchanged, so this lever moves momentum only."
        )
    elif lever is Lever.MACRO_REGIME:
        from src.scoring.engine import momentum_gate

        # Clamped to the engine's own multiplier range rather than to an
        # arbitrary one, so a simulation cannot ask for a regime the production
        # model has no meaning for.
        kwargs["srm"] = max(0.5, min(1.6, srm + change))
        before, after = momentum_gate(None, srm), momentum_gate(None, kwargs["srm"])
        note = f"Systemic risk multiplier moved from {srm:.2f} to {kwargs['srm']:.2f}."

        # The macro gate is doubly one-sided, and both halves have to be
        # explained or the reader sees a moved dial next to an unmoved score and
        # concludes the simulator is broken. It only ever subtracts, and it only
        # subtracts from *bullish* momentum — stress withdrawing credit from an
        # already-bearish reading would make stress a bullish input.
        momentum_now = getattr(baseline, "momentum_score", None)
        bullish = isinstance(momentum_now, (int, float)) and momentum_now > 0
        if abs(before - after) < 1e-9:
            note += (
                " The signal is unchanged because the macro gate only ever subtracts:"
                " a calmer regime removes a haircut that was not being applied at this"
                " level. Risk still moves, because risk reads the regime directly."
            )
        elif not bullish:
            note += (
                f" Momentum gate {before:.2f} -> {after:.2f}, but the gate applies to"
                " bullish momentum only and this security's momentum reading is not"
                " positive, so there is no upside credit for stress to withdraw. Risk"
                " still moves, because risk reads the regime directly."
            )
        else:
            note += f" Momentum gate {before:.2f} -> {after:.2f}."

    elif lever is Lever.VALUATION:
        for field in ("pe_ratio", "forward_pe"):
            value = kwargs.get(field)
            if value is not None and math.isfinite(value) and value > 0:
                kwargs[field] = value * (1.0 + change)
        note = "A lower multiple is a cheaper valuation, which the fundamental sleeve reads as support."
        if kwargs.get("pe_ratio") is None and kwargs.get("forward_pe") is None:
            note = "No valuation multiple was available, so this lever had nothing to move."
    elif lever is Lever.SENTIMENT:
        if sentiment is None:
            note = "No scored headlines were available, so this lever had nothing to move."
        else:
            kwargs["sentiment_avg"] = max(-1.0, min(1.0, sentiment + change))
            note = f"Average headline tone moved from {sentiment:+.2f} to {kwargs['sentiment_avg']:+.2f}."

    try:
        simulated = score_ticker(simulated_frame, **kwargs)
    except Exception:  # noqa: BLE001 — a simulation fault is not a product fault
        logger.exception("what-if simulation failed")
        return None
    if simulated is None:
        return None

    before, after = _families(baseline), _families(simulated)
    moved = {
        name: {"current": before[name], "simulated": after[name]}
        for name in before
        if before[name] is not None and after[name] is not None
        and abs(before[name] - after[name]) > 1e-6
    }

    return Simulation(
        lever=lever.value,
        change=change,
        label=label or f"{lever.value} {change:+.0%}",
        current_signal=baseline.verdict,
        current_confidence=baseline.confidence,
        current_risk=baseline.risk_score,
        current_score=baseline.raw_score,
        simulated_signal=simulated.verdict,
        simulated_confidence=simulated.confidence,
        simulated_risk=simulated.risk_score,
        simulated_score=simulated.raw_score,
        signal_changed=baseline.verdict != simulated.verdict,
        family_changes=moved,
        note=note,
    )


def preset(key: str) -> Optional[dict[str, Any]]:
    return _BY_KEY.get(key)


def presets_payload() -> list[dict[str, Any]]:
    return [
        {"key": p["key"], "label": p["label"], "lever": p["lever"].value, "change": p["change"]}
        for p in PRESETS
    ]
