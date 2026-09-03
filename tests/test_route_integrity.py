"""Navigation resolves, and every surface agrees on where things are.

The sidebar, the command palette, the keyboard chords and the shortcut sheet
were four independent lists of the same destinations, and they drifted exactly
as four hand-maintained copies of anything drift. "Go to Securities" in the
palette pointed at /terminal/analyze while the same label under the same `g s`
in the sidebar pointed at /terminal/security. Both routes were live, so nothing
failed — the reader simply arrived somewhere else depending on how they asked,
and one of the two destinations was still running the old shell.

They now derive from one registry. These tests hold that: the registry is
internally coherent, every route in it exists, and no surface reintroduces a
hand-written destination beside it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
APP = SRC / "app"
REGISTRY = SRC / "lib" / "destinations.ts"
WORKBENCH = SRC / "components" / "system" / "Workbench.tsx"
PALETTE = SRC / "components" / "system" / "Palette.tsx"
SHEET = SRC / "components" / "system" / "Shortcuts.tsx"

ITEM = re.compile(
    r"\{ href: '([^']+)', label: '([^']+)', glyph: '([^']*)', "
    r"key: '([a-z])', answers: '([^']*)' \}"
)


def _destinations() -> list[tuple[str, str, str, str, str]]:
    return ITEM.findall(REGISTRY.read_text())


def test_the_registry_parses() -> None:
    found = _destinations()
    assert len(found) >= 20, f"only {len(found)} destinations parsed; the shape changed"


def test_every_route_in_the_registry_exists() -> None:
    dead = [
        (label, href)
        for href, label, _glyph, _key, _answers in _destinations()
        if not (APP / href.lstrip("/") / "page.tsx").is_file()
    ]
    assert dead == [], f"destinations pointing at no page: {dead}"


def test_every_chord_is_unique() -> None:
    keys = [key for _h, _l, _g, key, _a in _destinations()]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    assert duplicates == [], f"a chord letter reaching two workspaces: {duplicates}"


def test_every_destination_says_what_it_answers() -> None:
    """A palette listing twenty-four names is a list you must already know."""
    silent = [label for _h, label, _g, _k, answers in _destinations() if not answers.strip()]
    assert silent == [], f"destinations with nothing to choose on: {silent}"


def test_labels_are_unique() -> None:
    labels = [label for _h, label, _g, _k, _a in _destinations()]
    duplicates = sorted({l for l in labels if labels.count(l) > 1})
    assert duplicates == [], f"two destinations share a name: {duplicates}"


def test_the_navigation_derives_from_the_registry() -> None:
    """Not a copy of it, and not a second list beside it."""
    source = WORKBENCH.read_text()
    assert "from '@/lib/destinations'" in source, "the workbench does not read the registry"
    assert "export const WORKBENCH = DESTINATIONS" in source, (
        "the workbench builds its own navigation list instead of using the registry"
    )
    # A literal destination here is a copy waiting to drift.
    assert not re.search(r"\{ href: '/terminal/[^']+', label:", source), (
        "the workbench declares a destination inline; it must come from the registry"
    )


def test_the_palette_derives_from_the_registry() -> None:
    source = PALETTE.read_text()
    assert "ALL_DESTINATIONS" in source, "the palette does not read the registry"
    hand_written = re.findall(r"go\('Go to [^']+', '([^']+)'", source)
    assert hand_written == [], (
        f"the palette hand-writes destinations, which is exactly how it came to "
        f"disagree with the sidebar: {hand_written}"
    )


def test_the_shortcut_sheet_documents_exactly_the_wired_chords() -> None:
    """A sheet naming a key nothing handles teaches the wrong key."""
    documented = set(re.findall(r"combo:\s*'g ([a-z])'", SHEET.read_text()))
    wired = {key for _h, _l, _g, key, _a in _destinations()}
    assert documented - wired == set(), f"documented but not wired: {sorted(documented - wired)}"
    assert wired - documented == set(), f"wired but undocumented: {sorted(wired - documented)}"


def test_a_workspace_does_not_print_the_same_number_twice() -> None:
    """The masthead and the strip beneath it must not repeat a figure.

    Twenty workspaces carried the same labels in both — five of them repeated
    every single number, forty pixels apart. Two rows saying the same thing
    teach a reader to skip one of them, and then to skip both.
    """
    ui = SRC / "components" / "terminal"
    offenders: list[str] = []

    for path in sorted(ui.rglob("*.tsx")):
        text = path.read_text()
        if "<ObjectHeader" not in text or "<Strip" not in text:
            continue
        facts = re.search(r"facts=\{\[(.*?)\]\}", text, re.S)
        strip = re.search(r"<Strip metrics=\{\[(.*?)\]\}", text, re.S)
        if not facts or not strip:
            continue
        labels = lambda blob: {m.group(1) for m in re.finditer(r"label: '([^']+)'", blob)}
        repeated = sorted(labels(facts.group(1)) & labels(strip.group(1)))
        if repeated:
            offenders.append(f"{path.relative_to(ROOT)}: {', '.join(repeated)}")

    assert offenders == [], (
        "these workspaces print the same figure in the masthead and the strip:\n  "
        + "\n  ".join(offenders)
    )
