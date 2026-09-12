"""Why something is not here, in one vocabulary.

Three surfaces were each inventing their own failure presentation. The
performance page turned a legitimately absent artifact into "Request failed:
404". The covariance page collapsed six distinct causes — no book, too few
positions, too little overlapping history, a singular matrix, a missing
artifact, an unreachable provider — into one `None` and then into a 500 when
anything unexpected happened. Paper trading reported missing credentials as
though the feature were broken.

All three are the same shape of problem: the backend knows exactly why, and
the reader is shown a status code instead.

So this module owns the vocabulary. A caller returns a `State` and a reason a
person can act on; the interface renders it. Two rules make it worth having:

**A status code is not a reason.** 404 says "not here" and nothing about
whether that is a bug, a deployment that never stored the file, or a model
this experiment never ran. Those need different responses from the reader and
only one of them is worth reporting.

**The detail a reader sees is never the exception.** Raw exception text leaks
paths, vendor internals and occasionally credentials. The detail goes to the
log; the reader gets the fact.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class State(str, Enum):
    """What a surface can be, beyond "it worked"."""

    AVAILABLE = "AVAILABLE"
    EMPTY = "EMPTY"                                  # asked, answered, nothing there
    PARTIAL = "PARTIAL"                              # some inputs missing
    STALE = "STALE"                                  # real, but past its window
    NOT_CONFIGURED = "NOT_CONFIGURED"                # this deployment has no credential
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"          # not enough to compute honestly
    UNSUPPORTED = "UNSUPPORTED"                      # not a thing this build does
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"  # an upstream is down
    PERMISSION_DENIED = "PERMISSION_DENIED"
    ERROR = "ERROR"                                  # a genuine fault, logged


#: States that mean "this is working as designed, there is simply nothing to
#: show". An interface should explain these calmly; none of them is a defect.
EXPECTED: frozenset[State] = frozenset({
    State.EMPTY, State.NOT_CONFIGURED, State.INSUFFICIENT_DATA, State.UNSUPPORTED,
})


class Availability(BaseModel):
    """A typed 'not here, and here is why'."""

    status: State
    #: A sentence for a person. Never an exception, never a path, never a key.
    message: str
    #: A stable machine-readable cause, so an interface can special-case one
    #: without matching on prose that will be reworded.
    reason: Optional[str] = None
    #: What would make this available. Omitted when nothing would.
    remedy: Optional[str] = None
    #: Extra facts safe to show — counts, thresholds, names. No secrets.
    detail: dict[str, Any] = Field(default_factory=dict)

    @property
    def expected(self) -> bool:
        return self.status in EXPECTED

    def payload(self, **extra: Any) -> dict[str, Any]:
        """The response body. Always HTTP 200.

        200 because the request was understood and answered truthfully: the
        answer is that the thing is not available and this is why. A 404 here
        would tell a client the *route* was wrong, and a 500 would tell it we
        failed — neither is what happened, and both send a reader chasing the
        wrong problem.
        """
        body = {
            "status": self.status.value,
            "message": self.message,
            "reason": self.reason,
            "remedy": self.remedy,
            "detail": self.detail,
        }
        body.update(extra)
        return body


def available(**extra: Any) -> dict[str, Any]:
    return {"status": State.AVAILABLE.value, **extra}


def empty(message: str, *, reason: Optional[str] = None, **detail: Any) -> Availability:
    return Availability(status=State.EMPTY, message=message, reason=reason, detail=detail)


def not_configured(message: str, *, remedy: Optional[str] = None, reason: Optional[str] = None) -> Availability:
    return Availability(
        status=State.NOT_CONFIGURED, message=message, remedy=remedy, reason=reason,
    )


def insufficient(message: str, *, reason: Optional[str] = None, **detail: Any) -> Availability:
    return Availability(
        status=State.INSUFFICIENT_DATA, message=message, reason=reason, detail=detail,
    )


def unsupported(message: str, *, reason: Optional[str] = None) -> Availability:
    return Availability(status=State.UNSUPPORTED, message=message, reason=reason)


def dependency_unavailable(message: str, *, reason: Optional[str] = None) -> Availability:
    return Availability(
        status=State.DEPENDENCY_UNAVAILABLE, message=message, reason=reason,
    )


def error(message: str, *, reason: Optional[str] = None) -> Availability:
    """A genuine fault.

    The message is what the reader sees, so it must already be safe. Callers
    log the exception; they do not pass it here.
    """
    return Availability(status=State.ERROR, message=message, reason=reason)
