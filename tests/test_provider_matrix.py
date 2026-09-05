"""The provider field matrix must match the map it claims to describe.

A hand-maintained matrix goes stale in silence, which is the failure this
whole audit exists to catch. The document is generated; this asserts it is
still in step with the code, so a mapping added without regenerating fails
here rather than misleading a reader later.
"""

import pathlib
import subprocess
import sys

from src.providers import statements

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "PROVIDER_FIELD_MATRIX.md"


def test_the_matrix_is_current():
    """Regenerate into a scratch copy and compare."""
    before = DOC.read_text()
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_provider_matrix.py")],
        check=True, capture_output=True, cwd=ROOT,
    )
    after = DOC.read_text()
    assert before == after, (
        "docs/PROVIDER_FIELD_MATRIX.md is out of date — run "
        "`python scripts/generate_provider_matrix.py` and commit the result"
    )


def test_every_mapped_key_appears_exactly_once():
    doc = DOC.read_text()
    for table in statements.VENDOR_KEYS.values():
        for key in table:
            assert doc.count(f"`{key}`") == 1, f"{key} is missing or duplicated"


def test_a_rescaled_field_declares_its_factor():
    """The million-fold rescale is the single most dangerous row in the table."""
    doc = DOC.read_text()
    for key, spec in statements.FINNHUB.items():
        if spec.scale != 1.0:
            line = next(l for l in doc.splitlines() if f"`{key}`" in l)
            assert "×1,000,000" in line, f"{key} does not declare its scale"


def test_an_unstated_period_is_labelled_rather_than_left_blank():
    doc = DOC.read_text()
    unstated = [k for table in statements.VENDOR_KEYS.values()
                for k, s in table.items() if not s.period]
    assert unstated, "the fixture assumes at least one vendor states no period"
    for key in unstated:
        line = next(l for l in doc.splitlines() if f"`{key}`" in l)
        assert "not stated" in line, f"{key} renders an empty period as blank"
