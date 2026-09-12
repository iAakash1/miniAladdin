"""The evaluation harness, and what it is honestly allowed to claim.

The result this benchmark exists to produce is an architectural one: grounding
claims in evidence and then *checking* those claims changes how many
unsupported statements reach a reader. The tests below pin that result and,
just as importantly, pin its limits — M0 is a structural baseline rather than
a measurement of any vendor's model, and the harness must not drift into
implying otherwise.

Determinism matters here more than in most test files. A benchmark whose
inputs move between runs measures the market as much as the system, so the
scenarios are frozen and these tests assert that running twice gives the same
numbers.
"""

import pytest

from src.agents.schemas import ValidationStatus
from src.agents.validation_agent import ValidationAgent
from src.evaluation import Configuration, evaluate, scenarios, summary_table
from src.evaluation.harness import run_scenario
from src.evaluation.scenarios import by_key


# ── the scenarios themselves ─────────────────────────────────────────────────

def test_the_scenario_set_covers_the_failures_that_matter():
    keys = {s.key for s in scenarios()}
    for required in (
        "healthy", "unsupported_number", "number_drift", "period_mismatch",
        "stale_price", "unit_confusion", "currency_mix", "missing_macro",
        "narrative_contradicts_signal", "narrative_misstates_risk",
        "prompt_injection", "dangling_citation",
    ):
        assert required in keys, required


def test_a_healthy_scenario_plants_no_defect():
    """Without a control, a validator that refuses everything scores perfectly."""
    healthy = by_key()["healthy"]
    assert healthy.expect_rejected == []
    assert healthy.expect_narrative_admissible is True


def test_the_validator_accepts_the_healthy_control():
    healthy = by_key()["healthy"]
    report = ValidationAgent().validate(
        [c.model_copy() for c in healthy.claims], healthy.evidence,
        model_signal=healthy.model_signal, risk_score=healthy.risk_score,
        narrative_text=healthy.narrative,
    )
    assert report.status is ValidationStatus.VERIFIED
    assert report.narrative_admissible is True


@pytest.mark.parametrize("case", [s for s in scenarios() if s.expect_rejected])
def test_every_planted_claim_defect_is_caught(case):
    report = ValidationAgent().validate(
        [c.model_copy() for c in case.claims], case.evidence,
        model_signal=case.model_signal, risk_score=case.risk_score,
    )
    refused = {f.claim_id for f in report.findings}
    assert set(case.expect_rejected) <= refused, (case.key, report.findings)


@pytest.mark.parametrize(
    "case", [s for s in scenarios() if not s.expect_narrative_admissible]
)
def test_every_planted_narrative_defect_is_caught(case):
    report = ValidationAgent().validate(
        [c.model_copy() for c in case.claims], case.evidence,
        model_signal=case.model_signal, risk_score=case.risk_score,
        narrative_text=case.narrative,
    )
    assert report.narrative_admissible is False, case.key
    assert report.rejected_reason


# ── the architectural result ─────────────────────────────────────────────────

def test_validation_strictly_improves_on_grounding_alone():
    """The claim the project makes, stated as an ordering.

    Grounding alone gets citations onto claims. It does not check that the
    citation says what the claim says, which is why M1 still leaks.
    """
    m = evaluate().by_configuration()
    assert m["M2"].unsupported_claim_rate < m["M1"].unsupported_claim_rate
    assert m["M1"].unsupported_claim_rate < m["M0"].unsupported_claim_rate
    assert m["M2"].defect_detection_rate > m["M1"].defect_detection_rate


def test_the_validated_configuration_catches_every_planted_defect():
    assert evaluate().by_configuration()["M2"].defect_detection_rate == 1.0


def test_only_the_validated_configuration_withholds_a_bad_narrative():
    m = evaluate().by_configuration()
    assert m["M2"].narrative_failure_rate == 0.0
    assert m["M0"].narrative_failure_rate == 1.0
    assert m["M1"].narrative_failure_rate == 1.0


def test_an_ungrounded_configuration_has_no_evidence_coverage():
    assert evaluate().by_configuration()["M0"].evidence_coverage == 0.0


def test_the_decision_is_identical_under_every_configuration():
    """The invariance that makes the comparison meaningful.

    If the architectures produced different verdicts, the metrics above would
    be comparing two products rather than two ways of explaining one.
    """
    report = evaluate()
    for metrics in report.metrics:
        assert metrics.decision_invariance == 1.0

    by_scenario: dict[str, set] = {}
    for outcome in report.outcomes:
        by_scenario.setdefault(outcome.scenario, set()).add(outcome.model_signal)
    for scenario, signals in by_scenario.items():
        assert len(signals) == 1, (scenario, signals)


# ── honesty about what this measures ─────────────────────────────────────────

def test_the_baseline_is_documented_as_structural_not_a_vendor_measurement():
    """A number labelled with a vendor's name that the vendor never produced
    would be exactly the dishonesty this project exists to avoid."""
    import src.evaluation.harness as harness

    # Whitespace-normalised: the assertion is about what the docstring says,
    # not about where its lines happen to wrap.
    import re

    doc = re.sub(r"\s+", " ", (harness.__doc__ or "").lower())
    assert "structural" in doc
    assert "not a live model run" in doc or "not a measurement" in doc

    source = harness.__file__
    with open(source) as fh:
        body = fh.read().lower()
    for vendor in ("gpt-4", "claude-3", "llama-", "mistral-"):
        assert vendor not in body, f"harness names a model it never ran: {vendor}"


def test_the_benchmark_is_reproducible():
    first, second = evaluate(), evaluate()
    assert [m.model_dump() for m in first.metrics] == [m.model_dump() for m in second.metrics]


def test_the_report_is_versioned():
    from src.evaluation.scenarios import SCENARIO_SET_VERSION

    assert evaluate().scenario_set_version == SCENARIO_SET_VERSION


def test_the_summary_renders_every_configuration():
    text = summary_table(evaluate())
    for configuration in Configuration:
        assert configuration.value in text


def test_the_harness_runs_offline():
    """No provider, no model, no clock dependency beyond frozen ages."""
    import socket

    original = socket.socket

    class _Refused(original):  # type: ignore[misc, valid-type]
        def connect(self, *a, **k):
            raise AssertionError("the harness attempted a network connection")

    socket.socket = _Refused  # type: ignore[assignment]
    try:
        evaluate()
    finally:
        socket.socket = original  # type: ignore[assignment]
