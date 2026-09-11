"""Evidence-grounded finance agents.

Specialist components that gather evidence and make traceable claims about a
security. None of them decides anything: the BUY/HOLD/SELL verdict is the
scoring engine's, and it is attached to a pipeline result after validation
rather than produced by it.
"""

from src.agents.orchestrator import analyse, attach_scorecard, build_context, run_agents
from src.agents.schemas import (
    AGENT_SCHEMA_VERSION, AgentResult, AgentStatus, Claim, EvidenceContext,
    EvidenceRecord, PipelineResult, ValidationReport, ValidationStatus,
)
from src.agents.validation_agent import ValidationAgent

__all__ = [
    "AGENT_SCHEMA_VERSION", "AgentResult", "AgentStatus", "Claim", "EvidenceContext",
    "EvidenceRecord", "PipelineResult", "ValidationAgent", "ValidationReport",
    "ValidationStatus", "analyse", "attach_scorecard", "build_context", "run_agents",
]
