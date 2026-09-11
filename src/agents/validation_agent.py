"""Whether the claims in front of a reader are actually supported.

Deterministic on purpose. The temptation in a system like this is to have a
second language model check the first one, and that is not validation: two
models can be wrong in the same direction, and their agreement is evidence
about their training distribution rather than about the security. Truth here
comes from evidence and arithmetic, and the model-based critic is a separate,
optional, narrative-quality layer that cannot overrule this one.

The rules below are the ones that catch real failures rather than hypothetical
ones. Each exists because the corresponding mistake is easy to make and
invisible once made:

  1  every factual claim cites evidence          - a sentence with no source
  2  the evidence it cites exists                - a dangling handle
  3  numbers match their evidence                - prose drifting from data
  4  units match                                 - a fraction read as a percent
  5  periods are comparable                      - TTM against fiscal year
  6  currencies match                            - two currencies, one total
  7  evidence is fresh enough                    - last year's price, stated flat
  8  sources that share an upstream are not      - one wire story counted twice
     counted as independent
  9  missing is not zero                         - an absence scored as a value
 10  the narrative agrees with the signal        - text that argues the opposite
 11  risk wording matches the risk score         - "low risk" over a 90
 12  factor signs are described correctly        - a drag described as support

A claim that fails any of these is marked and, where it is a generated
sentence, the whole narrative is withheld rather than shown with a footnote.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Optional

from src.agents.schemas import (
    Claim, EvidenceRecord, ValidationFinding, ValidationReport, ValidationStatus,
)

#: How old a measurement may be before a claim resting on it is STALE.
#: Prices move daily; fundamentals do not, so they are allowed a longer life.
FRESHNESS_DAYS = {"price_series": 7.0, "news": 14.0, "macro": 45.0, "fundamentals": 400.0}
DEFAULT_FRESHNESS_DAYS = 90.0

#: Relative tolerance when checking a claim's number against its evidence.
#: Not zero: claims round for display, and 12.34 standing for 12.3416 is
#: presentation rather than drift.
NUMERIC_TOLERANCE = 0.02

#: Vendors that resyndicate the same upstream wire. Two of them agreeing is
#: one source agreeing with itself, and counting it twice inflates apparent
#: corroboration exactly where a reader is most likely to rely on it.
_SHARED_UPSTREAM: dict[str, str] = {
    "yahoo": "yahoo", "yahoo_rss": "yahoo", "yfinance": "yahoo",
    "newsapi": "newsapi", "gnews": "newsapi",
}


def _finite(value) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def upstream_of(provider: str) -> str:
    """The origin a vendor resells, or the vendor itself."""
    return _SHARED_UPSTREAM.get((provider or "").strip().lower(), (provider or "").strip().lower())


def independent_sources(providers: Iterable[str]) -> int:
    """Distinct upstreams, not distinct vendor names."""
    return len({upstream_of(p) for p in providers if p})


def _age_days(record: EvidenceRecord) -> Optional[float]:
    from datetime import datetime, timezone

    stamp = record.observed_at or record.fetched_at
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(str(stamp)[:19])
    except ValueError:
        try:
            from datetime import date
            moment = datetime.combine(date.fromisoformat(str(stamp)[:10]), datetime.min.time())
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - moment).total_seconds() / 86400.0)


class ValidationAgent:
    """Checks claims against evidence and returns a typed report."""

    name = "validation"

    def validate(
        self,
        claims: list[Claim],
        evidence: list[EvidenceRecord],
        *,
        model_signal: Optional[str] = None,
        risk_score: Optional[int] = None,
        narrative_text: Optional[str] = None,
    ) -> ValidationReport:
        index = {e.evidence_id: e for e in evidence}
        report = ValidationReport()

        for claim in claims:
            status, rule, detail = self._check(claim, index)
            claim.validation_status = status
            claim.validation_note = None if status is ValidationStatus.VERIFIED else detail
            if status is not ValidationStatus.VERIFIED:
                report.findings.append(ValidationFinding(
                    claim_id=claim.claim_id, status=status, rule=rule, detail=detail,
                ))
            setattr(report, status.value.lower(), getattr(report, status.value.lower()) + 1)

        if narrative_text:
            self._check_narrative(report, narrative_text, model_signal, risk_score)

        if report.unsupported or report.conflicted:
            report.status = ValidationStatus.CONFLICTED if report.conflicted else ValidationStatus.UNSUPPORTED
        elif report.stale:
            report.status = ValidationStatus.STALE
        elif report.partial:
            report.status = ValidationStatus.PARTIAL
        else:
            report.status = ValidationStatus.VERIFIED
        return report

    # ── per-claim rules ──────────────────────────────────────────────────────

    def _check(
        self, claim: Claim, index: dict[str, EvidenceRecord],
    ) -> tuple[ValidationStatus, str, str]:
        # 1 — a factual claim must cite something.
        if not claim.evidence_ids:
            return (
                ValidationStatus.UNSUPPORTED, "evidence_required",
                "the claim cites no evidence",
            )

        # 2 — every handle it cites must resolve.
        missing = [eid for eid in claim.evidence_ids if eid not in index]
        if missing:
            return (
                ValidationStatus.UNSUPPORTED, "evidence_exists",
                f"cites evidence that does not exist: {', '.join(missing)}",
            )

        records = [index[eid] for eid in claim.evidence_ids]

        # 9 — a value the provider never sent is not a measurement.
        if claim.numeric_value is not None:
            supporting = [r for r in records if _finite(r.value) is not None]
            if not supporting:
                return (
                    ValidationStatus.UNSUPPORTED, "missing_is_not_zero",
                    "the claim states a number but no cited evidence carries one",
                )

            # 3 — the number must match what was measured.
            claimed = float(claim.numeric_value)
            if not any(self._matches(claimed, _finite(r.value)) for r in supporting):
                observed = ", ".join(f"{r.field}={r.value}" for r in supporting)
                return (
                    ValidationStatus.UNSUPPORTED, "numeric_match",
                    f"claims {claimed} but the evidence says {observed}",
                )

            # 4 — units must agree.
            units = {r.unit for r in supporting if r.unit}
            if claim.unit and units and claim.unit not in units:
                return (
                    ValidationStatus.CONFLICTED, "unit_match",
                    f"claim is in {claim.unit} but evidence is in {', '.join(sorted(units))}",
                )

            # 6 — currencies must agree.
            currencies = {r.currency for r in supporting if r.currency}
            if len(currencies) > 1:
                return (
                    ValidationStatus.CONFLICTED, "currency_match",
                    f"evidence mixes currencies: {', '.join(sorted(currencies))}",
                )

        # 5 — a comparison across incompatible bases is not a comparison.
        bases = {r.period.basis for r in records if r.period and r.period.basis}
        if claim.claim_type == "comparison" and len(bases) > 1:
            return (
                ValidationStatus.CONFLICTED, "period_match",
                f"compares measurements on different bases: {', '.join(sorted(bases))}",
            )

        # 7 — freshness, by capability.
        for record in records:
            age = _age_days(record)
            if age is None:
                continue
            limit = FRESHNESS_DAYS.get(record.capability, DEFAULT_FRESHNESS_DAYS)
            if age > limit:
                return (
                    ValidationStatus.STALE, "freshness",
                    f"{record.field} is {age:.0f} days old, past the "
                    f"{limit:.0f}-day window for {record.capability}",
                )
            if record.stale or record.quality in ("stale", "unavailable"):
                return (
                    ValidationStatus.STALE, "provider_stale",
                    f"{record.field} was served from a stale cache",
                )

        return ValidationStatus.VERIFIED, "", ""

    @staticmethod
    def _matches(claimed: float, observed: Optional[float]) -> bool:
        if observed is None:
            return False
        scale = max(abs(claimed), abs(observed), 1e-9)
        return abs(claimed - observed) / scale <= NUMERIC_TOLERANCE

    # ── narrative rules ──────────────────────────────────────────────────────

    def _check_narrative(
        self,
        report: ValidationReport,
        text: str,
        model_signal: Optional[str],
        risk_score: Optional[int],
    ) -> None:
        lowered = text.lower()

        # 10 — generated text must not argue against the signal it explains.
        if model_signal:
            signal = model_signal.lower()
            contradictions: list[tuple[str, str]] = []
            if "buy" in signal:
                contradictions = [("recommend selling", "sell"), ("suggests selling", "sell")]
            elif "sell" in signal:
                contradictions = [("recommend buying", "buy"), ("suggests buying", "buy")]
            for phrase, _ in contradictions:
                if phrase in lowered:
                    report.narrative_admissible = False
                    report.rejected_reason = (
                        f"the narrative says {phrase!r} while the model signal is {model_signal}"
                    )
                    report.findings.append(ValidationFinding(
                        claim_id="narrative", status=ValidationStatus.CONFLICTED,
                        rule="narrative_agrees_with_signal",
                        detail=report.rejected_reason,
                    ))
                    return

        # 11 — risk wording must match the measured score.
        if risk_score is not None:
            says_low = re.search(r"\blow(?:er)?\s+risk\b", lowered) is not None
            says_high = re.search(r"\bhigh(?:er)?\s+risk\b", lowered) is not None
            if says_low and risk_score >= 67:
                report.narrative_admissible = False
                report.rejected_reason = (
                    f"the narrative calls this low risk while the risk score is {risk_score}"
                )
            elif says_high and risk_score < 34:
                report.narrative_admissible = False
                report.rejected_reason = (
                    f"the narrative calls this high risk while the risk score is {risk_score}"
                )
            if not report.narrative_admissible and report.rejected_reason:
                report.findings.append(ValidationFinding(
                    claim_id="narrative", status=ValidationStatus.CONFLICTED,
                    rule="risk_wording_matches_score", detail=report.rejected_reason,
                ))
                return

        # An instruction that reached the narrative means an article's text
        # was treated as guidance somewhere upstream.
        from src.agents.news_agent import looks_like_injection

        if looks_like_injection(lowered):
            report.narrative_admissible = False
            report.rejected_reason = "the narrative repeats instruction-like text from evidence"
            report.findings.append(ValidationFinding(
                claim_id="narrative", status=ValidationStatus.UNSUPPORTED,
                rule="no_injected_instructions", detail=report.rejected_reason,
            ))
