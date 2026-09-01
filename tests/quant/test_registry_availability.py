"""
An absent model register is UNKNOWN, never zero.

This is a production incident captured as a test. `data/research/models/
registry.json` was excluded from git by a rule written to keep 216 MB of derived
partitions out of the repository, so it never reached the Render image. The
deployed backend loaded an empty register, found no entries, and served:

    deployment_status: NO_MODEL
    message: "No production-grade predictive model currently validated."
    total_entries: 0

Every one of those happened to match reality — there genuinely is no production
model — and not one of them was derived from it. The API was asserting a
research conclusion from a file it could not see, and it would have kept saying
NO_MODEL after a real promotion, because the register that records promotions
was not in the image.
"""

from __future__ import annotations

import json

from src.quant.models.registry import ModelRegistry
from src.services import quant_service


def test_a_present_register_is_reported_as_read():
    registry = ModelRegistry("data/research/models")
    assert registry.source_present is True
    assert len(registry.all()) > 0, (
        "the register ships with the repository; if this fails it was excluded again"
    )

    status = quant_service.production_status()
    assert status["registry_available"] is True
    assert status["deployment_status"] == "NO_MODEL"
    assert isinstance(status["total_entries"], int)


def test_an_absent_register_reports_unknown_not_no_model(tmp_path):
    registry = ModelRegistry(tmp_path / "absent")
    assert registry.source_present is False
    assert registry.all() == []

    status = quant_service.production_status(tmp_path / "absent")
    assert status["deployment_status"] == "UNKNOWN", (
        "NO_MODEL is a claim about research and cannot be made from a missing file"
    )
    assert status["registry_available"] is False
    # Counts must be null, not zero. A zero here is the whole bug.
    for field in ("production", "candidates", "validated", "total_entries", "retired"):
        assert status[field] is None, f"{field} must be null when the register is absent"
    assert status["serving_predictions"] is False


def test_an_unreadable_register_also_reports_unknown(tmp_path):
    """Corrupt is unknown too — and must not be reported as nothing validated."""
    root = tmp_path / "corrupt"
    root.mkdir()
    (root / "registry.json").write_text("{ not json", encoding="utf-8")

    status = quant_service.production_status(root)
    assert status["deployment_status"] == "UNKNOWN"
    assert status["registry_available"] is False
    assert status["production"] is None
    assert status["serving_predictions"] is False


def test_an_empty_but_present_register_is_no_model_not_unknown(tmp_path):
    """The distinction runs both ways.

    A register that exists and records nothing genuinely supports the claim that
    nothing is validated. Reporting UNKNOWN there would be its own inaccuracy.
    """
    root = tmp_path / "empty"
    root.mkdir()
    (root / "registry.json").write_text(
        json.dumps({"schema_version": 1, "entries": []}), encoding="utf-8"
    )

    status = quant_service.production_status(root)
    assert status["deployment_status"] == "NO_MODEL"
    assert status["registry_available"] is True
    assert status["total_entries"] == 0
