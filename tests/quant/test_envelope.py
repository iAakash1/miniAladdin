"""
The envelope's job is to make a number's status underivable from wishful thinking.

`status` is computed from the timestamp and the declared policy. Nothing can
pass it in, which is the whole design: the recurring failure in this product has
been a caller labelling data it did not measure — unknown rendered as sealed,
unavailable rendered as zero, stale rendered as live.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.services.envelope import (
    POLICIES, DataEnvelope, FreshnessPolicy, Status, envelope_dict,
)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def test_freshness_is_derived_from_the_timestamp():
    policy = FreshnessPolicy("t", timedelta(minutes=15), "why")
    assert policy.status_for(NOW - timedelta(minutes=5), NOW) is Status.LIVE
    assert policy.status_for(NOW - timedelta(minutes=30), NOW) is Status.STALE


def test_a_missing_timestamp_is_unknown_not_live():
    assert FreshnessPolicy("t", timedelta(minutes=15), "w").status_for(None, NOW) is Status.UNKNOWN


def test_a_recorded_artifact_never_goes_stale():
    """Age is provenance for an artifact, not decay.

    EXP-006 does not become less true in September, and a UI that marks it
    stale is wrong about what it is looking at.
    """
    policy = POLICIES["experiment"]
    assert policy.ttl is None
    assert policy.status_for(NOW - timedelta(days=400), NOW) is Status.RECORDED


def test_a_null_value_can_never_be_live():
    """The bug this product keeps producing, blocked at the type."""
    env = DataEnvelope(None, "provider", as_of=datetime.now(timezone.utc), policy="quote")
    assert env.status is Status.UNKNOWN
    assert env.trustworthy is False


def test_the_three_non_measurement_states_stay_distinct():
    """`waking` and `unavailable` justify different responses.

    One means retry; the other means stop waiting. Collapsing them is how a
    routine cold start reads as an outage.
    """
    assert DataEnvelope.waking("s", "d").status is Status.WAKING
    assert DataEnvelope.unavailable("s", "d").status is Status.UNAVAILABLE
    assert DataEnvelope.unknown("s", "d").status is Status.UNKNOWN
    for ctor in (DataEnvelope.waking, DataEnvelope.unavailable, DataEnvelope.unknown):
        env = ctor("s", "d")
        assert env.value is None
        assert env.trustworthy is False


def test_only_live_and_recorded_are_trustworthy():
    assert DataEnvelope(1.0, "s", as_of=datetime.now(timezone.utc), policy="quote").trustworthy
    assert DataEnvelope.recorded(1.0, "artifact").trustworthy
    stale = DataEnvelope(1.0, "s", as_of=NOW - timedelta(days=9), policy="quote")
    assert stale.status is Status.STALE
    assert stale.trustworthy is False


def test_serialisation_carries_the_policy_and_its_reason():
    """A consumer can render *why* a window is what it is, not just its length."""
    payload = DataEnvelope.recorded(
        0.4983, "experiments/EXP-007/search.json",
        method="annualised, 8 expanding folds", unit="Sharpe",
    ).as_dict()
    assert payload["status"] == "recorded"
    assert payload["method"] == "annualised, 8 expanding folds"
    assert payload["freshness"]["ttl_seconds"] is None
    assert "provenance" in payload["freshness"]["why"]


def test_every_declared_policy_explains_itself():
    for name, policy in POLICIES.items():
        assert policy.name == name
        assert len(policy.why) > 40, f"{name} needs a real reason, not a label"


def test_envelope_dict_groups_by_field_name():
    out = envelope_dict(
        net_sharpe=DataEnvelope.recorded(0.11, "artifact"),
        pbo=DataEnvelope.unavailable("artifact", "not computed"),
    )
    assert out["net_sharpe"]["status"] == "recorded"
    assert out["pbo"]["status"] == "unavailable"
    assert out["pbo"]["value"] is None


def test_an_unknown_policy_name_fails_loudly():
    """A typo must not silently pick a default freshness window."""
    with pytest.raises(KeyError):
        DataEnvelope(1.0, "s", as_of=NOW, policy="typo").status
