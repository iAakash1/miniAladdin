"""The data contracts every agent speaks.

The point of this layer is traceability: a sentence a reader is shown should
be reducible to the numbers it came from, and those numbers to the vendor
responses they came from. That is only enforceable if agents emit structured
claims carrying evidence handles, rather than prose that happens to mention
figures.

Three shapes do the work.

`EvidenceRecord` is one measured value with its provenance and its units. The
unit and period fields are not decoration: TTM revenue and fiscal-year revenue
are different measurements, and an agent that compares them without noticing
produces a confident, wrong claim that nothing downstream can detect.

`Claim` is one statement an agent is prepared to defend, with the evidence ids
that support it. A claim with no evidence ids fails validation by
construction — that is the mechanism which stops a generated sentence from
introducing a number nobody measured.

`AgentResult` is what one agent returns, including its failures. An agent that
could not reach its data reports that rather than returning an empty success,
because "no negative news" and "the news provider was down" look identical
once the list is empty and only one of them is a finding.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

#: Bumped when a field in this module changes meaning. Recorded on every
#: pipeline result so a stored run can be read back under the contract it was
#: produced with rather than the one in force when it is read.
AGENT_SCHEMA_VERSION = "agents-v1"


class AgentStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"        # ran, but some inputs were missing
    UNAVAILABLE = "unavailable"  # could not run at all
    ERROR = "error"


class ValidationStatus(str, Enum):
    """How well a claim is supported. Defined once, here, because a status
    that means one thing in the validator and another in the interface is
    worse than having no status."""

    VERIFIED = "VERIFIED"        # evidence present, fresh, and it matches
    PARTIAL = "PARTIAL"          # supported, but some evidence is incomplete
    CONFLICTED = "CONFLICTED"    # sources disagree materially
    STALE = "STALE"              # supported only by evidence past its window
    UNSUPPORTED = "UNSUPPORTED"  # no evidence, or it does not say this


class Period(BaseModel):
    """What span a measurement covers.

    Carried explicitly so that comparing across periods has to be a decision
    rather than an accident. `basis` distinguishes TTM from a fiscal year from
    an instant; two values with different bases are not comparable and the
    validator refuses to treat them as though they were.
    """

    basis: str = "instant"       # "instant" | "ttm" | "fiscal_year" | "quarter" | "window"
    start: Optional[str] = None
    end: Optional[str] = None
    label: Optional[str] = None


class EvidenceRecord(BaseModel):
    """One measured value, with everything needed to check it later."""

    evidence_id: str
    agent: str
    provider: str
    capability: str
    field: str

    value: Optional[Any] = None
    unit: Optional[str] = None          # "usd" | "fraction" | "percent" | "ratio" | "count" | "days"
    currency: Optional[str] = None
    period: Period = Field(default_factory=Period)

    #: When the world was in this state, as distinct from when we asked.
    #: Conflating them is how a cached figure gets presented as current.
    observed_at: Optional[str] = None
    fetched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    stale: bool = False

    #: Provider-reported condition: "live" | "cached" | "stale" | "unavailable".
    quality: str = "live"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    """One statement, and the evidence it rests on."""

    claim_id: str
    agent: str
    claim_type: str              # "measurement" | "comparison" | "state" | "event"
    statement: str
    evidence_ids: list[str] = Field(default_factory=list)

    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    period: Optional[Period] = None
    as_of: Optional[str] = None

    validation_status: ValidationStatus = ValidationStatus.PARTIAL
    #: Filled by the validator when a claim is not VERIFIED.
    validation_note: Optional[str] = None


class AgentResult(BaseModel):
    """What one agent produced, including what it could not."""

    agent: str
    status: AgentStatus = AgentStatus.OK
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)

    #: Inputs the agent wanted and did not get. Recorded rather than omitted,
    #: because a factor that is missing and a factor that scored neutral look
    #: identical in a decomposition otherwise.
    missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0


class ValidationFinding(BaseModel):
    claim_id: str
    status: ValidationStatus
    rule: str
    detail: str


class ValidationReport(BaseModel):
    """The deterministic verdict on a pipeline's claims."""

    status: ValidationStatus = ValidationStatus.VERIFIED
    findings: list[ValidationFinding] = Field(default_factory=list)
    verified: int = 0
    partial: int = 0
    conflicted: int = 0
    stale: int = 0
    unsupported: int = 0

    #: True when the narrative may be shown as generated. False sends the
    #: caller to the deterministic fallback — an explanation that failed
    #: validation is withheld, not annotated and shown anyway.
    narrative_admissible: bool = True
    rejected_reason: Optional[str] = None

    def counts(self) -> dict[str, int]:
        return {
            "verified": self.verified, "partial": self.partial,
            "conflicted": self.conflicted, "stale": self.stale,
            "unsupported": self.unsupported,
        }


class EvidenceContext(BaseModel):
    """Everything fetched once and shared by every agent.

    The alternative — each agent fetching what it needs — costs the same data
    several times over and, worse, lets two agents reason about different
    snapshots of the same security. A contradiction produced that way is
    indistinguishable from a real one.
    """

    model_config = {"arbitrary_types_allowed": True}

    symbol: str
    company_name: str = ""
    as_of: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    price_frame: Optional[Any] = None       # pandas DataFrame
    benchmark_frame: Optional[Any] = None
    series_result: Optional[Any] = None
    fundamentals: Optional[Any] = None
    analyst_targets: Optional[Any] = None
    headlines: list[Any] = Field(default_factory=list)
    macro_multiplier: Optional[float] = None
    macro_stats: dict[str, Any] = Field(default_factory=dict)
    quality_inputs: dict[str, Any] = Field(default_factory=dict)
    scorecard: Optional[Any] = None

    #: Provider-level evidence from the fabric, kept so an agent claim can be
    #: traced past our own layer to the vendor exchange behind it.
    provider_evidence: list[Any] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    """One complete run: evidence, agents, validation, decision, narrative."""

    symbol: str
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_schema_version: str = AGENT_SCHEMA_VERSION
    scoring_version: Optional[str] = None
    prompt_version: Optional[str] = None

    agents: list[AgentResult] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    validation: ValidationReport = Field(default_factory=ValidationReport)

    #: The engine's, carried verbatim. No agent and no model writes this.
    model_signal: Optional[str] = None
    confidence: Optional[int] = None
    risk_score: Optional[int] = None
    data_completeness: Optional[float] = None

    narrative: Optional[dict[str, Any]] = None
    narrative_source: str = "none"   # "model" | "deterministic" | "none"
    critic: Optional[dict[str, Any]] = None
