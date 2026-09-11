"""What an agent is, and what it is allowed to do.

An agent here is a specialised component with an objective, a declared set of
inputs, a typed output and defined failure semantics. Most of them contain no
language model at all, which is deliberate: computing a 21-day return is
arithmetic, and routing arithmetic through a model would make a
deterministic, checkable number into a generated, uncheckable one.

The one hard rule every agent obeys: **an agent produces evidence and claims,
never a verdict.** The BUY/HOLD/SELL decision belongs to the scoring engine.
An agent that returned its own recommendation would be a second decision
authority, and the product already spent a release removing one of those.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Protocol

from src.agents.schemas import (
    AgentResult, AgentStatus, Claim, EvidenceContext, EvidenceRecord, Period,
)

logger = logging.getLogger("omnisignal.agents")


class Agent(Protocol):
    name: str

    def run(self, context: EvidenceContext) -> AgentResult: ...


class BaseAgent:
    """Shared plumbing: id minting, timing, and never raising.

    An agent that raises takes the pipeline down with it. Every one of them
    reports failure as a status instead, so one unavailable vendor costs the
    reader one section rather than the whole analysis.
    """

    name: str = "agent"

    def __init__(self) -> None:
        self._evidence_seq = 0
        self._claim_seq = 0

    # ── id minting ───────────────────────────────────────────────────────────

    def evidence_id(self) -> str:
        self._evidence_seq += 1
        return f"{self.name[:3].upper()}-E{self._evidence_seq}"

    def claim_id(self) -> str:
        self._claim_seq += 1
        return f"{self.name[:3].upper()}-C{self._claim_seq}"

    # ── helpers ──────────────────────────────────────────────────────────────

    def record(
        self,
        *,
        provider: str,
        capability: str,
        field: str,
        value,
        unit: Optional[str] = None,
        currency: Optional[str] = None,
        period: Optional[Period] = None,
        observed_at: Optional[str] = None,
        stale: bool = False,
        quality: str = "live",
        **metadata,
    ) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=self.evidence_id(), agent=self.name, provider=provider,
            capability=capability, field=field, value=value, unit=unit,
            currency=currency, period=period or Period(), observed_at=observed_at,
            stale=stale, quality=quality, metadata=metadata,
        )

    def claim(
        self,
        statement: str,
        evidence: list[EvidenceRecord],
        *,
        claim_type: str = "measurement",
        numeric_value: Optional[float] = None,
        unit: Optional[str] = None,
        period: Optional[Period] = None,
        as_of: Optional[str] = None,
    ) -> Claim:
        return Claim(
            claim_id=self.claim_id(), agent=self.name, claim_type=claim_type,
            statement=statement, evidence_ids=[e.evidence_id for e in evidence],
            numeric_value=numeric_value, unit=unit, period=period, as_of=as_of,
        )

    # ── entry point ──────────────────────────────────────────────────────────

    def run(self, context: EvidenceContext) -> AgentResult:
        started = time.perf_counter()
        self._evidence_seq = self._claim_seq = 0
        try:
            result = self.gather(context)
        except Exception as exc:  # noqa: BLE001 — one agent never fails the run
            logger.exception("%s agent raised", self.name)
            result = AgentResult(
                agent=self.name, status=AgentStatus.ERROR,
                warnings=[f"{type(exc).__name__} while gathering evidence"],
            )
        result.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return result

    def gather(self, context: EvidenceContext) -> AgentResult:  # pragma: no cover
        raise NotImplementedError
