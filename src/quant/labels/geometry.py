"""
Label geometry — horizon, overlap, and everything that follows from them.

## Why this is a module and not three constants

A forward label spanning H sessions, sampled every S sessions, makes consecutive
observations share (H − S)/H of their outcome. That single ratio determines
three separate things this repository already does:

* **purge** — how much training data must be dropped either side of a fold
  boundary so no training label overlaps a validation date;
* **embargo** — how long after a fold to wait before resuming, for serial
  correlation the purge does not cover;
* **bootstrap block length** — how many consecutive observations must be
  resampled together, because an i.i.d. bootstrap on dependent draws produces
  an interval far too narrow.

Those were being derived by hand in three places, and the bootstrap block was
hardcoded as `21 // 5` in a service module where it could drift from the
experiment it described. The geometry belongs to the label, so it is computed
from the label.

## Effective sample size

The number that matters most and is quoted least. With 21-session labels at a
5-session cadence, 403 observations carry roughly 96 independent ones. Every
significance claim on this panel is really being made against 96, not 403, and
EXP-007's multiple-testing accounting is severe precisely because of it.

The estimate is deliberately conservative — n / block, floor — rather than one
of the sharper effective-sample-size corrections. An overstated independent
count is the direction that flatters a result.

## Not a research change

This derives what the experiment definitions already declare. It reads
`step_sessions`, the target name and `embargo_sessions`; it decides nothing.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional

#: `fwd_rank_21`, `fwd_ret_63` — the horizon is the trailing integer. This is
#: the existing naming convention across every label in the repository, not a
#: new one introduced here.
_HORIZON_IN_NAME = re.compile(r"_(\d+)$")


def horizon_from_target(target: str) -> Optional[int]:
    """Sessions a label looks forward, parsed from its name.

    Returns None rather than a default when the name carries no horizon. A
    guessed horizon would silently produce a wrong purge and a wrong block
    length, which is worse than refusing.
    """
    match = _HORIZON_IN_NAME.search(target or "")
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class LabelGeometry:
    """The dependence structure a label imposes on its own observations."""

    target: str
    horizon_sessions: int
    step_sessions: int
    embargo_sessions: int

    @property
    def overlapping_sessions(self) -> int:
        """Sessions two consecutive observations share."""
        return max(0, self.horizon_sessions - self.step_sessions)

    @property
    def overlap_fraction(self) -> float:
        """Share of a label's window that the next observation also covers."""
        if self.horizon_sessions <= 0:
            return 0.0
        return self.overlapping_sessions / self.horizon_sessions

    @property
    def block_length(self) -> int:
        """Consecutive observations that must be resampled together.

        Ceiling, not floor. A block shorter than the dependence leaves
        correlation inside the resample and narrows the interval — the error
        that flatters. Rounding up costs a little width and cannot mislead.
        """
        if self.step_sessions <= 0:
            return 1
        return max(1, math.ceil(self.horizon_sessions / self.step_sessions))

    @property
    def purge_sessions(self) -> int:
        """Training data that must be dropped at a fold boundary.

        A label formed on the last training date resolves `horizon` sessions
        later, which is inside the validation window unless that much is cut.
        """
        return self.horizon_sessions

    def independent_observations(self, observations: int) -> int:
        """Roughly how many of `observations` carry independent information."""
        if observations <= 0:
            return 0
        return max(1, observations // self.block_length)

    def as_dict(self, *, observations: Optional[int] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "target": self.target,
            "horizon_sessions": self.horizon_sessions,
            "step_sessions": self.step_sessions,
            "overlapping_sessions": self.overlapping_sessions,
            "overlap_fraction": round(self.overlap_fraction, 4),
            "block_length": self.block_length,
            "purge_sessions": self.purge_sessions,
            "embargo_sessions": self.embargo_sessions,
            "why": (
                f"A {self.horizon_sessions}-session label sampled every "
                f"{self.step_sessions} sessions makes consecutive observations "
                f"share {self.overlapping_sessions} of {self.horizon_sessions} "
                f"sessions ({self.overlap_fraction:.0%}). Purge drops "
                f"{self.purge_sessions} sessions at a fold boundary so no "
                f"training label resolves inside validation; the bootstrap "
                f"resamples {self.block_length} consecutive observations "
                f"together for the same reason."
            ),
        }
        if observations is not None:
            independent = self.independent_observations(observations)
            payload["observations"] = observations
            payload["independent_observations"] = independent
            payload["independence_note"] = (
                f"{observations} observations carry roughly {independent} "
                f"independent ones. Significance is being claimed against "
                f"{independent}, not {observations}."
            )
        return payload


def geometry_for(
    target: str, *, step_sessions: int, embargo_sessions: int = 0,
    horizon_sessions: Optional[int] = None,
) -> Optional[LabelGeometry]:
    """Geometry for one label, or None when the horizon cannot be established."""
    horizon = horizon_sessions if horizon_sessions is not None else horizon_from_target(target)
    if horizon is None or horizon <= 0 or step_sessions <= 0:
        return None
    return LabelGeometry(
        target=target, horizon_sessions=horizon,
        step_sessions=step_sessions, embargo_sessions=embargo_sessions,
    )
