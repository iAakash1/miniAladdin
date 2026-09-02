"""The handbook is generated, so it cannot drift from the engine.

A methodology page maintained by hand is wrong the first time a convention
changes, and a wrong methodology page is worse than none — it is a confident
statement about how a number was computed that is no longer true.
"""

from __future__ import annotations

from src.quant.risk.engine import METHODOLOGY, MIN_OBSERVATIONS, RETURN_ONLY_METRICS
from src.services.methodology_service import NOTES, handbook


def test_every_reported_measure_appears() -> None:
    names = {e["name"] for e in handbook()["entries"]}
    assert names == set(METHODOLOGY)


def test_units_are_read_from_the_engine_not_restated() -> None:
    for entry in handbook()["entries"]:
        unit, annualisation, inputs = METHODOLOGY[entry["name"]]
        assert entry["unit"] == unit.value
        assert entry["annualisation"] == annualisation.value
        assert entry["inputs"] == list(inputs)


def test_applicability_matches_the_engine_rule() -> None:
    for entry in handbook()["entries"]:
        assert entry["return_units_required"] == (entry["name"] in RETURN_ONLY_METRICS)


def test_the_observation_floor_is_the_engine_constant() -> None:
    book = handbook()
    assert book["minimum_observations"] == MIN_OBSERVATIONS
    assert all(e["minimum_observations"] == MIN_OBSERVATIONS for e in book["entries"])


def test_every_measure_states_what_makes_it_fail() -> None:
    """The field that matters. Assumptions only help a reader told what breaks them."""
    missing = [e["name"] for e in handbook()["entries"] if not e["fails_when"]]
    assert missing == [], f"undocumented failure conditions: {missing}"


def test_every_measure_states_its_purpose() -> None:
    missing = [e["name"] for e in handbook()["entries"] if not e["purpose"]]
    assert missing == []


def test_authored_prose_is_flagged_as_authored() -> None:
    """A reader must be able to tell derived fields from written ones."""
    for entry in handbook()["entries"]:
        assert entry["documented"] is (entry["name"] in NOTES)


def test_notes_do_not_describe_measures_the_engine_does_not_report() -> None:
    """Prose for a removed metric is how a handbook starts lying."""
    orphans = set(NOTES) - set(METHODOLOGY)
    assert orphans == set(), f"notes for unreported measures: {sorted(orphans)}"
