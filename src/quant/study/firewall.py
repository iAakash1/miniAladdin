"""
Holdout firewall — a runtime guard, not a convention.

## Why the CLI guard was not enough

`src/quant/study/holdout.py` refuses to *run the holdout experiment* unless the
contract is armed. That protects one entry point. It does nothing about the
ordinary way a holdout actually gets spent, which is not a deliberate run of the
holdout script — it is a researcher building a panel that happens to extend past
the cutoff, fitting something on it, and looking at the number before realising
what they just did. By then the holdout is gone: the result cannot be un-known,
and every later decision is conditioned on it whether anyone intends that or not.

So the guard belongs at the point where holdout ROWS meet code, not at the point
where someone types a command. `assert_clear` is called by the walk-forward plan
builder, by the model-fitting stage and by the metric stage. Each call names its
context, so the refusal says which stage reached and how far in.

## Arming

The firewall lifts only when `docs/HOLDOUT_CONTRACT.md` says `| Armed | **YES**`,
which is a human editing a tracked file — the same condition the preflight reads,
deliberately, so there is exactly one place the answer lives. There is no
environment variable and no keyword argument that opens it, because both are
things a script can set by accident.

`FIREWALL.override()` exists for the holdout runner itself and for tests. It is a
context manager with a mandatory reason, it logs at WARNING, and it is the only
sanctioned path — which is what makes an unsanctioned one visible in review.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date as Date
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

import pandas as pd

logger = logging.getLogger("omnisignal.quant.study.firewall")

CONTRACT_PATH = Path("docs/HOLDOUT_CONTRACT.md")

#: The armed marker, matched exactly as the preflight matches it.
ARMED_MARKERS: tuple[str, ...] = ("| Armed | **YES**", "| Armed | YES")


class HoldoutBreach(RuntimeError):
    """Raised when holdout-dated rows reach a stage that must not see them.

    Deliberately not a subclass of ValueError: a breach is never something a
    caller should be catching and continuing past.
    """


@dataclass
class HoldoutWindow:
    """The reserved period. `None` start means no holdout is in force."""

    start: Optional[Date] = None
    end: Optional[Date] = None

    @property
    def active(self) -> bool:
        return self.start is not None and self.end is not None

    def contains(self, values: pd.Series) -> pd.Series:
        if not self.active:
            return pd.Series(False, index=values.index)
        dates = pd.to_datetime(values).dt.date
        return (dates >= self.start) & (dates <= self.end)

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "active": self.active,
        }


@dataclass
class HoldoutFirewall:
    """Process-wide guard. One instance, imported as `FIREWALL`."""

    window: HoldoutWindow = field(default_factory=HoldoutWindow)
    contract_path: Path = CONTRACT_PATH
    _override_reason: Optional[str] = None
    breaches_prevented: int = 0
    checks: int = 0

    # ── state ────────────────────────────────────────────────────────────

    def arm_window(self, start: Optional[Date], end: Optional[Date]) -> None:
        """Declare the reserved period. Called by the walk-forward planner."""
        self.window = HoldoutWindow(start=start, end=end)
        if self.window.active:
            logger.info("firewall: holdout %s..%s is LOCKED", start, end)

    def contract_readable(self) -> bool:
        """Whether the contract could actually be read.

        Separate from `contract_armed` because the two answer different
        questions and only one of them is a fact about the contract. An
        unreadable contract makes `contract_armed` return False — which is the
        correct *behaviour*, since the firewall must stay engaged — but it is
        not evidence that a human declined to arm it. Reporting those two states
        identically would let "we could not read the file" render as "confirmed
        not armed", and a holdout is exactly the thing that must never be
        described more confidently than it is known.
        """
        try:
            self.contract_path.read_text(encoding="utf-8")
        except OSError:
            return False
        return True

    def contract_armed(self) -> bool:
        """Whether a human has armed the contract. The only lift condition.

        Unreadable means not armed. That is the safe direction and it does not
        change: the firewall stays engaged. `contract_readable` records whether
        this answer was measured or defaulted.
        """
        try:
            text = self.contract_path.read_text(encoding="utf-8")
        except OSError:
            return False
        return any(marker in text for marker in ARMED_MARKERS)

    @property
    def engaged(self) -> bool:
        """The firewall blocks unless overridden or the contract is armed."""
        return self._override_reason is None and not self.contract_armed()

    @contextmanager
    def override(self, reason: str) -> Iterator[None]:
        """The one sanctioned lift. Requires a reason and logs loudly."""
        if not reason or not reason.strip():
            raise ValueError(
                "an override needs a reason; an unexplained lift of the holdout "
                "firewall is indistinguishable from an accident"
            )
        previous = self._override_reason
        self._override_reason = reason
        logger.warning("firewall: OVERRIDDEN — %s", reason)
        try:
            yield
        finally:
            self._override_reason = previous
            logger.warning("firewall: override released (%s)", reason)

    # ── the guard ────────────────────────────────────────────────────────

    def assert_clear(
        self,
        frame: pd.DataFrame,
        *,
        context: str,
        date_column: str = "date",
    ) -> None:
        """Refuse a frame containing holdout-dated rows.

        A no-op when no holdout is declared or the column is absent — this must
        not become a reason to avoid calling it.
        """
        self.checks += 1
        if not self.window.active or frame is None or frame.empty:
            return
        if date_column not in frame.columns:
            return

        hits = self.window.contains(frame[date_column])
        count = int(hits.sum())
        if count == 0:
            return

        if not self.engaged:
            logger.warning(
                "firewall: %s touched %d holdout rows under an active override (%s)",
                context, count, self._override_reason or "contract armed",
            )
            return

        self.breaches_prevented += 1
        offending = pd.to_datetime(frame.loc[hits, date_column])
        raise HoldoutBreach(
            f"{context} reached {count} row(s) inside the LOCKED holdout "
            f"({self.window.start} .. {self.window.end}); first {offending.min().date()}, "
            f"last {offending.max().date()}. The holdout is single-use: computing "
            "anything on it — a metric, a fit, a normalisation constant, a universe "
            "membership — spends it. If this is the pre-registered holdout run, arm "
            f"{self.contract_path} and go through src.quant.study.holdout."
        )

    def assert_dates_clear(self, dates: Sequence[Date], *, context: str) -> None:
        """The same guard for a bare sequence of dates."""
        if not self.window.active or not len(dates):
            return
        self.assert_clear(pd.DataFrame({"date": list(dates)}), context=context)

    def status(self) -> dict[str, Any]:
        readable = self.contract_readable()
        armed = self.contract_armed()
        return {
            "window": self.window.as_dict(),
            "contract_path": str(self.contract_path),
            "contract_armed": armed,
            #: False here means `contract_armed` was defaulted, not measured.
            #: The firewall is engaged either way; the reader is told which.
            "contract_readable": readable,
            "contract_state": (
                "ARMED" if armed else "NOT_ARMED" if readable else "UNKNOWN"
            ),
            "engaged": self.engaged,
            "override_reason": self._override_reason,
            "checks": self.checks,
            "breaches_prevented": self.breaches_prevented,
        }


#: The process-wide instance. Import this, never construct another.
FIREWALL = HoldoutFirewall()


def reset_for_tests() -> None:
    """Return the singleton to a clean state. Test-only."""
    FIREWALL.window = HoldoutWindow()
    FIREWALL._override_reason = None
    FIREWALL.breaches_prevented = 0
    FIREWALL.checks = 0
    FIREWALL.contract_path = CONTRACT_PATH


def _env_override_is_refused() -> None:
    """Fail loudly if someone tries to open the firewall by environment.

    There is deliberately no environment switch. This exists so that setting one
    in the hope that it works produces an error rather than silence.
    """
    for name in ("QUANT_DISABLE_HOLDOUT_FIREWALL", "QUANT_ALLOW_HOLDOUT"):
        if os.environ.get(name):
            raise RuntimeError(
                f"{name} is set, but the holdout firewall has no environment "
                "override by design. Arm docs/HOLDOUT_CONTRACT.md instead — "
                "opening a single-use holdout should require editing a tracked "
                "file, not exporting a variable."
            )


_env_override_is_refused()
