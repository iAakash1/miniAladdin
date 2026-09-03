"""The numerical presentation system's precisions must match the measurements.

A precision is a claim about how much of a figure is signal. Rendering a Sharpe
ratio to three decimals states a difference the sample cannot resolve, and
rendering the same information coefficient to three places on one screen and
five on another makes two screens showing one number look like they disagree.

These tests read the frontend's specification table and hold it against what the
backend says those measures are, so the two cannot drift apart silently.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUANTITY = ROOT / "dashboard" / "src" / "lib" / "quantity.ts"

SPEC = re.compile(
    r"^\s{2}(\w+):\s*\{\s*digits:\s*(\d+),\s*signed:\s*(true|false),"
    r"(?:\s*unit:\s*'([^']*)',)?\s*tone:\s*(true|false)",
    re.MULTILINE,
)


def _specs() -> dict[str, dict[str, object]]:
    return {
        m.group(1): {
            "digits": int(m.group(2)),
            "signed": m.group(3) == "true",
            "unit": m.group(4),
            "tone": m.group(5) == "true",
        }
        for m in SPEC.finditer(QUANTITY.read_text())
    }


def test_the_specification_table_parses() -> None:
    """Guards the parser: a regex matching nothing would pass everything."""
    assert len(_specs()) >= 20


def test_every_engine_measure_kind_has_a_spec() -> None:
    """Each unit the risk engine reports needs a presentation rule."""
    required = {
        "ic", "ratio", "sharpe", "tstat", "probability", "share",
        "return", "magnitude", "volatility", "drawdown", "count",
    }
    assert required <= set(_specs())


def test_a_sharpe_is_not_rendered_to_more_precision_than_it_has() -> None:
    """Four hundred periods gives a Sharpe a standard error near 0.05.

    Three decimals would state a difference the sample cannot resolve.
    """
    assert _specs()["sharpe"]["digits"] <= 2


def test_an_information_coefficient_keeps_four_places_and_no_more() -> None:
    """A correlation from a few hundred dates. Six places would be noise."""
    assert _specs()["ic"]["digits"] == 4


def test_a_probability_keeps_enough_digits_to_straddle_a_threshold() -> None:
    """PBO and deflated Sharpe are read against 0.2 and 0.95."""
    assert _specs()["probability"]["digits"] >= 3


def test_counts_are_integers() -> None:
    for kind in ("count", "rank", "sessions"):
        assert _specs()[kind]["digits"] == 0


def test_direction_is_signed_only_where_the_sign_means_something() -> None:
    """A magnitude is reported positive, so a leading + would be noise; a
    return's sign is the whole content of the figure."""
    assert _specs()["magnitude"]["signed"] is False
    assert _specs()["volatility"]["signed"] is False
    assert _specs()["return"]["signed"] is True
    assert _specs()["ic"]["signed"] is True


def test_tone_is_reserved_for_figures_where_the_sign_is_good_or_bad() -> None:
    """A t-statistic of -3 is not worse than +3, and a correlation of -0.4 is
    not a bad correlation. Colouring them would be an opinion."""
    assert _specs()["tstat"]["tone"] is False
    assert _specs()["correlation"]["tone"] is False
    assert _specs()["ic"]["tone"] is True


def test_no_kind_converts_a_value() -> None:
    """A return of 0.0231 is shown as 0.0231, not as 2.31%.

    The engine's unit is the decimal. Re-scaling in the display layer is how a
    figure comes to mean two things in one product, so the unit label carries
    the interpretation instead.
    """
    source = QUANTITY.read_text()
    body = source[source.index("export function format("):]
    assert "* 100" not in body
    assert "/ 100" not in body
