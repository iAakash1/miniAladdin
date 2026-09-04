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


def test_a_count_is_never_rendered_signed() -> None:
    """`digits: 0` alone falls through to the signed, toned default.

    The default kind is `ratio`, which is signed and coloured by sign. A count
    rendered through it comes out as "+0 candidates" and "+34 retired" — a
    plus sign on a population, which reads as a change rather than a total, and
    a green tint on a retirement count.

    Every integer count must name `kind: 'count'`. Two hundred and twenty-seven
    call sites did not.
    """
    import re

    ui = ROOT / "dashboard" / "src" / "components"
    offenders: list[str] = []

    # A metric literal carrying digits: 0 with no kind, sign or tone.
    metric = re.compile(r"\{[^{}]*\bdigits: 0\b[^{}]*\}")
    # A <Value> with digits={0} and nothing else to steer it.
    element = re.compile(r"<Value\b[^>]*digits=\{0\}[^>]*/>")

    # `format(value, 'currency', { digits: 0 })` names its kind positionally,
    # outside the braces this scans. That is steered, not a fall-through — the
    # detector previously read only inside the literal and reported it as an
    # unsteered count. Widened rather than relaxed: a bare `{ digits: 0 }` with
    # no kind in either position is still caught.
    positional_kind = re.compile(r"\bformat\(\s*[^,]+,\s*['\"][a-z_]+['\"]")

    for path in sorted(ui.rglob("*.tsx")):
        text = path.read_text()
        for line_no, line in enumerate(text.splitlines(), 1):
            for pattern in (metric, element):
                for match in pattern.finditer(line):
                    hit = match.group(0)
                    if "kind" in hit or "signed" in hit or "tone" in hit:
                        continue
                    if positional_kind.search(line):
                        continue
                    offenders.append(f"{path.relative_to(ROOT)}:{line_no} {hit[:80]}")

    assert offenders == [], (
        "counts rendered through the signed default — add kind: 'count':\n  "
        + "\n  ".join(offenders[:20])
        + (f"\n  ...and {len(offenders) - 20} more" if len(offenders) > 20 else "")
    )


def test_one_payload_carries_two_scales_and_the_ui_must_not_conflate_them() -> None:
    """Ratios arrive as percentages; ownership arrives as fractions.

    Verified against a live payload during the Phase 13 sweep:

        gross_margin_ttm            48.65     a percentage
        net_margin_ttm              27.62     a percentage
        held_percent_institutions    0.66374  a fraction
        held_percent_insiders        0.01648  a fraction

    Both live in one research response, both have "percent" or "margin" in
    their names, and they are on scales a hundred apart. A renderer that
    multiplies fractions would report Apple's margin as 4,865%; one that does
    not would report institutional ownership as 0.66%.

    The product's answer is that `percent` never multiplies and `share` never
    multiplies either — the scaling decision belongs to the one place that
    knows which it is holding. This asserts the fundamentals panel keeps
    ownership on the `share` kind and margins on `percent`, because the day
    those swap is the day both are wrong and neither looks it.
    """
    import re

    panel = (ROOT / "dashboard" / "src" / "components" / "terminal"
             / "security" / "Fundamentals2.tsx").read_text()

    def kind_for(label: str) -> str | None:
        m = re.search(rf"label: '{re.escape(label)}'[^}}]*?kind: '([a-z]+)'", panel)
        return m.group(1) if m else None

    for label in ("Gross margin", "Operating margin", "Net margin"):
        assert kind_for(label) == "percent", (
            f"{label} is not on the percent kind; a fraction scale would be off by 100x"
        )

    for label in ("Held by institutions", "Held by insiders", "Short interest of float"):
        assert kind_for(label) == "share", (
            f"{label} is not on the share kind; the percent kind would report a "
            f"fraction as a percentage"
        )
