"""
The canonical shape of a served number.

## Why this exists

Every panel in this product had to decide for itself what context a value
needs — whether to carry a source, an as-of date, a methodology — and the
honest ones were the exception. The result was numbers that could not be
questioned: a Sharpe with no cost assumption, a VaR with no estimator, a count
that might be a measurement or a default.

An envelope makes the context part of the value rather than something a caller
remembers to attach.

## What was taken, and from where

**OpenBB's standard models.** Their platform defines a `Data` class per domain
concept and has providers *extend* it, so a consumer codes against one contract
and providers stay swappable. `DataEnvelope` is the same move at a smaller
scale: one shape for every served value, with the domain payload inside it.

**Fincept's `TopicPolicy`.** Their DataHub declares a TTL and minimum refresh
interval per topic, so freshness is a property of the data rather than a
convention in each screen. `FreshnessPolicy` is that idea: a datum declares how
long it stays fresh, and `status` is *derived* rather than asserted.

Neither project's code is used here. Both are AGPL-3.0; these are architectural
ideas, implemented independently.

## The rule that matters

`status` is computed from timestamps and the policy — never passed in. A caller
cannot label stale data live, because a caller does not get to label anything.
Absent inputs yield `UNKNOWN`, never `LIVE` and never a zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional


class Status(str, Enum):
    """What a consumer may claim about this value.

    Ordered by how much trust each one licenses. The distinction between
    `UNAVAILABLE` and `UNKNOWN` is the one that keeps getting collapsed in
    practice and is the reason this is an enum rather than a bool: "we asked and
    got nothing" and "we never asked" justify different responses, and rendering
    either as a zero is what turns a gap in the data into a claim about the
    world.
    """

    LIVE = "live"              #: Measured within the policy's freshness window.
    STALE = "stale"            #: Real, and older than the policy allows.
    RECORDED = "recorded"      #: A historical artifact. Age is expected, not a fault.
    WAKING = "waking"          #: The source exists and is starting. Retry works.
    UNAVAILABLE = "unavailable"  #: Asked, and the source could not answer.
    UNKNOWN = "unknown"        #: Not asked, or the answer cannot be interpreted.


#: Statuses a consumer may render as a usable number.
TRUSTWORTHY = frozenset({Status.LIVE, Status.RECORDED})


@dataclass(frozen=True)
class FreshnessPolicy:
    """How long a value of this kind stays fresh, declared per domain.

    Adapted from Fincept's per-topic TTL. The point is that freshness belongs to
    the *data*, not to whichever screen is drawing it — otherwise two panels
    showing the same series disagree about whether it is current, and both are
    guessing.

    `RECORDED` sources set `ttl=None`: an experiment artifact from August is not
    stale, it is dated, and a UI that nags about its age is wrong about what it
    is looking at.
    """

    name: str
    ttl: Optional[timedelta]
    why: str

    def status_for(self, as_of: Optional[datetime], now: Optional[datetime] = None) -> Status:
        # A ttl-less policy is checked FIRST, before the timestamp.
        #
        # `status` answers "may I trust this as current?". For recorded data
        # that question does not apply — currency is not a property an artifact
        # has — so a missing `as_of` is a gap in the provenance, not a reason to
        # distrust the value. Reporting UNKNOWN here would conflate "I do not
        # know this artifact's vintage" with "I do not know whether this number
        # is usable", and only the first is true.
        #
        # For a policy where freshness DOES matter, a missing timestamp is
        # genuinely disqualifying and still returns UNKNOWN below.
        if self.ttl is None:
            return Status.RECORDED
        if as_of is None:
            return Status.UNKNOWN
        now = now or datetime.now(timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        return Status.LIVE if (now - as_of) <= self.ttl else Status.STALE


#: The declared policies. One place, so two surfaces cannot disagree.
POLICIES: dict[str, FreshnessPolicy] = {
    "quote": FreshnessPolicy(
        "quote", timedelta(minutes=15),
        "Intraday prices move continuously; a quarter hour is the outside edge "
        "of what may be shown without a stale marker.",
    ),
    "macro": FreshnessPolicy(
        "macro", timedelta(days=2),
        "Macro series publish on cadences from daily to monthly. Two days "
        "tolerates a weekend without calling a Friday print stale.",
    ),
    "news": FreshnessPolicy(
        "news", timedelta(hours=1),
        "A feed that has not moved in an hour is more likely broken than quiet.",
    ),
    "experiment": FreshnessPolicy(
        "experiment", None,
        "A recorded research artifact. Its age is provenance, not decay — "
        "EXP-006 does not become less true in September.",
    ),
    "registry": FreshnessPolicy(
        "registry", None,
        "The promotion ledger. Append-only and authoritative regardless of age.",
    ),
    "inference": FreshnessPolicy(
        "inference", timedelta(minutes=5),
        "Model metadata is immutable per deploy but the service is not: a "
        "five-minute window surfaces a restart without hammering it.",
    ),
}


@dataclass(frozen=True)
class DataEnvelope:
    """One served value with everything needed to question it."""

    value: Any
    source: str
    #: When the data describes the world. Distinct from `retrieved_at`: a fresh
    #: fetch of a stale series is a thing that happens constantly, and conflating
    #: the two is how a dead feed looks healthy.
    as_of: Optional[datetime] = None
    retrieved_at: Optional[datetime] = None
    policy: str = "experiment"
    method: Optional[str] = None
    unit: Optional[str] = None
    detail: Optional[str] = None
    _status_override: Optional[Status] = field(default=None, repr=False)

    @property
    def status(self) -> Status:
        """Derived, never asserted."""
        if self._status_override is not None:
            return self._status_override
        if self.value is None:
            return Status.UNKNOWN
        return POLICIES[self.policy].status_for(self.as_of)

    @property
    def trustworthy(self) -> bool:
        return self.status in TRUSTWORTHY

    def as_dict(self) -> dict[str, Any]:
        policy = POLICIES[self.policy]
        return {
            "value": self.value,
            "status": self.status.value,
            "source": self.source,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "method": self.method,
            "unit": self.unit,
            "detail": self.detail,
            "freshness": {
                "policy": policy.name,
                "ttl_seconds": policy.ttl.total_seconds() if policy.ttl else None,
                "why": policy.why,
            },
        }

    # ── constructors for the states that are not a measurement ───────────

    @classmethod
    def unavailable(cls, source: str, detail: str, *, policy: str = "experiment") -> "DataEnvelope":
        """Asked, and the source could not answer. Value stays None."""
        return cls(value=None, source=source, policy=policy, detail=detail,
                   _status_override=Status.UNAVAILABLE)

    @classmethod
    def waking(cls, source: str, detail: str, *, policy: str = "experiment") -> "DataEnvelope":
        """The source is starting. Distinct from unavailable: retrying works."""
        return cls(value=None, source=source, policy=policy, detail=detail,
                   _status_override=Status.WAKING)

    @classmethod
    def unknown(cls, source: str, detail: str, *, policy: str = "experiment") -> "DataEnvelope":
        """Never asked, or the answer cannot be interpreted."""
        return cls(value=None, source=source, policy=policy, detail=detail,
                   _status_override=Status.UNKNOWN)

    @classmethod
    def recorded(cls, value: Any, source: str, *, as_of: Optional[datetime] = None,
                 method: Optional[str] = None, unit: Optional[str] = None,
                 policy: str = "experiment") -> "DataEnvelope":
        """A value read from a committed artifact."""
        return cls(value=value, source=source, as_of=as_of, method=method,
                   unit=unit, policy=policy,
                   retrieved_at=datetime.now(timezone.utc))


def envelope_dict(**named: DataEnvelope) -> dict[str, Any]:
    """Serialise a group of envelopes by field name."""
    return {name: env.as_dict() for name, env in named.items()}
