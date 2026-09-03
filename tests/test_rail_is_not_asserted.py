"""The status rail must not state live facts it cannot see.

Whether anything is armed in production, whether the holdout is still sealed,
and how many entries the registry holds are facts only the backend knows.
Twelve workspaces stated them as static text in their own rail.

That was wrong twice. It repeated one fact twelve times, so changing it meant
changing twelve files or letting the workspaces disagree. And with the backend
unreachable every one of those pages still announced HOLDOUT SEALED and
REGISTRY 103 ENTRIES while the panels directly above them correctly reported
that nothing could be read.

A rail that keeps saying "sealed" when the app cannot reach the thing that would
tell it is the most dangerous kind of stale: it is the reassuring strip, it is
always in view, and it is the last thing a reader would think to doubt.

What a page may still pass is policy — the cost assumption in force, what a
confidence figure is not — which is static because it is a statement about how
the product works rather than about what the research currently says.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "dashboard" / "src" / "app" / "terminal"
RAIL = ROOT / "dashboard" / "src" / "components" / "system" / "SystemRail.tsx"

#: Text in a rail entry that can only be true if the backend answered.
LIVE = re.compile(
    r"\{ label: '(?:Registry|Production|Holdout)', state: '[^']+', "
    r"detail: '[^']*(?:sealed|none armed|\d+ (?:entries|models))[^']*' \}"
)


def test_no_page_hardcodes_a_live_research_fact() -> None:
    offenders: list[str] = []
    for path in sorted(PAGES.rglob("page.tsx")):
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            if LIVE.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{line_no} {line.strip()}")
    assert offenders == [], (
        "these pages state live research facts as static text; they belong in "
        "SystemRail, which reads them:\n  " + "\n  ".join(offenders)
    )


def test_the_live_rail_reports_an_unreachable_backend_as_unreadable() -> None:
    """Not "none armed", not "sealed", not a count — three honest unknowns."""
    source = RAIL.read_text()
    assert "cannot be read" in source, "the rail has no unreachable state"

    # The branch taken when the status request fails, bounded by its own
    # `return [ ... ]` rather than by the next bracket in the file — the ready
    # branch below it legitimately says "none armed" when it has been told so.
    start = source.index("if (state.status === 'unavailable')")
    branch = source[start:]
    branch = branch[: branch.index("return [")] + branch[
        branch.index("return ["): branch.index("]", branch.index("return [")) + 1
    ]

    # Comments are stripped first. The branch's own comment names the words it
    # refuses to print, and a test that reads prose rather than code would fail
    # on the explanation for the behaviour it is checking.
    code = re.sub(r"//[^\n]*", "", branch)

    for lie in ("none armed", "sealed", "entries"):
        assert lie not in code, (
            f"the unreachable branch still claims {lie!r}; an unread fact is "
            f"not a reassuring one"
        )


def test_an_unknown_holdout_is_not_called_sealed() -> None:
    source = RAIL.read_text()
    assert "state not reported" in source, (
        "an unreported holdout must say so. Untouched means sealed; unknown "
        "means unknown, and merging them is the most flattering error the rail "
        "could make."
    )
