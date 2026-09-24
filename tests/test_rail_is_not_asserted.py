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
#: The always-visible strip that now carries the live facts.
RAIL = ROOT / "dashboard" / "src" / "components" / "shell" / "StatusBar.tsx"

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


def _not_current(source: str) -> str:
    """The one function every live fact passes through before it is shown."""
    start = source.index("function notCurrent")
    return source[start: source.index("\n}\n", start)]


def test_the_live_rail_reports_an_unreachable_backend_as_unreadable() -> None:
    """Nothing ever read means no value at all — not a reassuring one."""
    source = RAIL.read_text()
    body = _not_current(source)
    assert "'status unavailable'" in body, "the strip has no unreachable state"
    # The never-read branch is the function's last return; it names no fact.
    tail = body[body.rindex("return"):]
    for lie in ("none armed", "sealed", "entries", "promoted"):
        assert lie not in tail, (
            f"the unreachable branch still claims {lie!r}; an unread fact is "
            f"not a reassuring one"
        )
    # Every live fact on the strip — providers, macro, governance — goes through it.
    assert source.count("notCurrent(") == 3, "a live fact bypasses the unreadable check"


def test_a_remembered_reading_is_labelled_and_timed() -> None:
    """A stale value may be shown. It may not be shown as a current one."""
    source = RAIL.read_text()
    assert "failed(prev" in source, "a failed refresh overwrites or keeps the old value unlabelled"
    body = _not_current(source)
    start = body.index("read.state === 'last-observed'")
    branch = body[start: body.index("\n  }", start)]
    # The remembered value is introduced as such, with the time it was read,
    # and in the muted tone rather than a tone that claims the present.
    assert "last seen" in branch and "clock(read.at)" in branch, (
        "a remembered reading is not labelled with when it was seen"
    )
    assert "tone: 'muted'" in branch, "a remembered reading renders in a current tone"
    for current in ("'pos'", "'info'", "'live'"):
        assert current not in branch, (
            f"a remembered reading renders as {current}, which claims the value describes now"
        )


def test_an_unknown_holdout_is_not_called_sealed() -> None:
    source = RAIL.read_text()
    assert "state not reported" in source, (
        "an unreported holdout must say so. Untouched means sealed; unknown "
        "means unknown, and merging them is the most flattering error the rail "
        "could make."
    )
