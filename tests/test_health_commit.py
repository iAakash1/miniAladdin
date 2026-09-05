"""The health endpoint must report the code in memory, not the checkout.

A server started before a commit reported that commit anyway, because the
value was resolved by shelling out to `git rev-parse` on every request. That
is the most misleading answer this endpoint can give: it is exactly what
someone checks to find out whether a deployment picked up a change, and a
long-lived process on old code answered yes.
"""

import subprocess
from unittest.mock import patch

import api.index as api


def test_the_commit_is_frozen_at_import_not_read_per_request():
    """Moving the checkout's HEAD must not move a running process's answer."""
    with patch.object(subprocess, "run") as run:
        first = api._build_commit()
        second = api._build_commit()
    assert first == second
    assert run.call_count == 0, (
        "the health commit shells out to git per request, so it reports the "
        "working tree rather than the code this process loaded"
    )


def test_a_host_injected_revision_wins_over_the_checkout():
    for name in ("RENDER_GIT_COMMIT", "VERCEL_GIT_COMMIT_SHA", "GIT_COMMIT", "SOURCE_VERSION"):
        with patch.dict("os.environ", {name: "a" * 40}, clear=False):
            assert api._resolve_build_commit() == "a" * 12


def test_an_unresolvable_revision_is_unknown_rather_than_an_error():
    """Health must never fail — an endpoint that can 500 is not a health check."""
    with patch.dict("os.environ", {}, clear=True), \
         patch.object(subprocess, "run", side_effect=OSError("no git")):
        assert api._resolve_build_commit() == "unknown"


def test_health_reports_the_frozen_value():
    payload = api.health()
    assert payload["commit"] == api._BUILD_COMMIT
