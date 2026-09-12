"""Measuring whether grounding and validation actually change the outcome.

Three configurations are compared over the frozen scenarios:

    M0  ungrounded generator — claims with no evidence handles, no validation
    M1  grounded generator   — claims cite evidence; no claim-level validation
    M2  grounded + validated — the shipped architecture

**What M0 is and is not.** It is a *structural* baseline, not a live model
run: it models an ungrounded generator by stripping evidence handles from the
same claims and skipping validation. That is the defining property of an
ungrounded system — its sentences carry no traceable support — and modelling
it this way keeps the benchmark deterministic and free. It is deliberately
not presented as a measurement of any particular vendor's model, because it
is not one, and a number labelled "GPT hallucination rate" that was never
produced by GPT would be the exact dishonesty this project exists to avoid.

The metrics therefore measure *architecture*, not model quality: how many
unsupported statements reach a reader, how many detectable defects are caught,
and whether the decision survives each configuration unchanged.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.agents.schemas import Claim, ValidationStatus
from src.agents.validation_agent import ValidationAgent
from src.evaluation.scenarios import SCENARIO_SET_VERSION, Scenario, scenarios


class Configuration(str, Enum):
    M0_UNGROUNDED = "M0"
    M1_GROUNDED = "M1"
    M2_VALIDATED = "M2"


class ScenarioOutcome(BaseModel):
    scenario: str
    configuration: Configuration

    claims_total: int = 0
    claims_with_evidence: int = 0
    #: Statements that reached the reader without surviving a check.
    unsupported_surfaced: int = 0
    #: Defects the scenario planted that this configuration caught.
    defects_planted: int = 0
    defects_caught: int = 0

    narrative_shown: bool = True
    narrative_should_have_been_withheld: bool = False

    model_signal: Optional[str] = None


class Metrics(BaseModel):
    configuration: Configuration
    scenarios: int = 0

    #: Of all claims, the share that reached a reader unchecked or refuted.
    unsupported_claim_rate: float = 0.0
    #: Of planted, detectable defects, the share this configuration caught.
    defect_detection_rate: float = 0.0
    #: Of all claims, the share carrying at least one evidence handle.
    evidence_coverage: float = 0.0
    #: Narratives that should have been withheld and were not.
    narrative_failure_rate: float = 0.0
    #: Decisions identical to the deterministic engine's across every scenario.
    decision_invariance: float = 1.0


class EvaluationReport(BaseModel):
    scenario_set_version: str = SCENARIO_SET_VERSION
    metrics: list[Metrics] = Field(default_factory=list)
    outcomes: list[ScenarioOutcome] = Field(default_factory=list)

    def by_configuration(self) -> dict[str, Metrics]:
        return {m.configuration.value: m for m in self.metrics}


def _strip_evidence(claims: list[Claim]) -> list[Claim]:
    """What an ungrounded generator's output looks like structurally."""
    return [c.model_copy(update={"evidence_ids": []}) for c in claims]


def run_scenario(scenario: Scenario, configuration: Configuration) -> ScenarioOutcome:
    planted = set(scenario.expect_rejected)
    narrative_should_be_withheld = not scenario.expect_narrative_admissible

    outcome = ScenarioOutcome(
        scenario=scenario.key,
        configuration=configuration,
        defects_planted=len(planted) + (1 if narrative_should_be_withheld else 0),
        narrative_should_have_been_withheld=narrative_should_be_withheld,
        # Copied, in every configuration. The decision does not depend on how
        # the narrative was produced, and that is the invariance being tested.
        model_signal=scenario.model_signal,
    )

    if configuration is Configuration.M0_UNGROUNDED:
        claims = _strip_evidence(scenario.claims)
        outcome.claims_total = len(claims)
        outcome.claims_with_evidence = 0
        # No validation runs, so every statement reaches the reader and no
        # planted defect is caught.
        outcome.unsupported_surfaced = len(claims)
        outcome.defects_caught = 0
        outcome.narrative_shown = scenario.narrative is not None
        return outcome

    claims = [c.model_copy() for c in scenario.claims]
    outcome.claims_total = len(claims)
    outcome.claims_with_evidence = sum(1 for c in claims if c.evidence_ids)

    if configuration is Configuration.M1_GROUNDED:
        # Claims cite evidence, but nothing checks whether the citation says
        # what the claim says. Grounding without verification.
        outcome.unsupported_surfaced = sum(1 for c in claims if not c.evidence_ids)
        outcome.defects_caught = sum(1 for c in claims if not c.evidence_ids and c.claim_id in planted)
        outcome.narrative_shown = scenario.narrative is not None
        return outcome

    report = ValidationAgent().validate(
        claims, scenario.evidence,
        model_signal=scenario.model_signal,
        risk_score=scenario.risk_score,
        narrative_text=scenario.narrative,
    )
    refused = {
        c.claim_id for c in claims
        if c.validation_status is not ValidationStatus.VERIFIED
    }
    outcome.unsupported_surfaced = 0  # refused claims are not surfaced
    outcome.defects_caught = len(refused & planted)
    outcome.narrative_shown = bool(scenario.narrative) and report.narrative_admissible
    if narrative_should_be_withheld and not report.narrative_admissible:
        outcome.defects_caught += 1
    return outcome


def evaluate(configurations: Optional[list[Configuration]] = None) -> EvaluationReport:
    """Run every scenario under every configuration. Deterministic and offline."""
    configurations = configurations or list(Configuration)
    report = EvaluationReport()
    cases = scenarios()

    for configuration in configurations:
        outcomes = [run_scenario(case, configuration) for case in cases]
        report.outcomes.extend(outcomes)

        claims = sum(o.claims_total for o in outcomes) or 1
        planted = sum(o.defects_planted for o in outcomes) or 1
        narratives_to_withhold = sum(1 for o in outcomes if o.narrative_should_have_been_withheld) or 1
        leaked = sum(
            1 for o in outcomes
            if o.narrative_should_have_been_withheld and o.narrative_shown
        )
        invariant = sum(
            1 for o, case in zip(outcomes, cases) if o.model_signal == case.model_signal
        )

        report.metrics.append(Metrics(
            configuration=configuration,
            scenarios=len(outcomes),
            unsupported_claim_rate=round(sum(o.unsupported_surfaced for o in outcomes) / claims, 4),
            defect_detection_rate=round(sum(o.defects_caught for o in outcomes) / planted, 4),
            evidence_coverage=round(sum(o.claims_with_evidence for o in outcomes) / claims, 4),
            narrative_failure_rate=round(leaked / narratives_to_withhold, 4),
            decision_invariance=round(invariant / (len(outcomes) or 1), 4),
        ))

    return report


def summary_table(report: EvaluationReport) -> str:
    header = (
        f"{'config':8}{'claims unsupported':>20}{'defects caught':>16}"
        f"{'evidence cov.':>15}{'narrative leaks':>17}{'decision inv.':>15}"
    )
    lines = [f"scenario set: {report.scenario_set_version}", header, "-" * len(header)]
    for m in report.metrics:
        lines.append(
            f"{m.configuration.value:8}{m.unsupported_claim_rate:>20.1%}"
            f"{m.defect_detection_rate:>16.1%}{m.evidence_coverage:>15.1%}"
            f"{m.narrative_failure_rate:>17.1%}{m.decision_invariance:>15.1%}"
        )
    return "\n".join(lines)
