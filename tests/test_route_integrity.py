"""Navigation must not point at anything that does not exist.

A dead nav entry is the class of debt the redesigned shell exists to remove,
and it is invisible until someone clicks it. This parses the workbench
navigation and asserts every route resolves to a real page, every shortcut is
unique, and the two-key `g` map agrees with the navigation it claims to mirror.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "dashboard" / "src" / "components" / "system" / "Workbench.tsx"
APP = ROOT / "dashboard" / "src" / "app"

#: One nav item: href, label and shortcut, in the order the file writes them.
ITEM = re.compile(
    r"\{\s*href:\s*'([^']+)',\s*label:\s*'([^']+)',\s*key:\s*'([a-z])'\s*\}"
)
#: The `g`-prefixed jump table. The trailing segment is optional because the
#: market surface is `/terminal` itself, with nothing after it.
GOTO = re.compile(r"\b([a-z]):\s*'(/terminal(?:/[a-z-]+)?)'")


def _source() -> str:
    return WORKBENCH.read_text()


def _items() -> list[tuple[str, str, str]]:
    return ITEM.findall(_source())


def _goto() -> dict[str, str]:
    # Only the block between GOTO's declaration and its closing brace, so a
    # route mentioned elsewhere in the file is not mistaken for a mapping.
    src = _source()
    start = src.index("const GOTO")
    end = src.index("}", src.index("{", start))
    return dict(GOTO.findall(src[start:end]))


def test_the_navigation_parses() -> None:
    """Guards the parser: a regex that matches nothing would pass everything."""
    assert len(_items()) >= 15


def test_every_navigation_route_resolves_to_a_page() -> None:
    dead = [
        (label, href)
        for href, label, _ in _items()
        if not (APP / href.lstrip("/") / "page.tsx").is_file()
    ]
    assert dead == [], f"navigation entries with no page: {dead}"


def test_every_shortcut_is_unique() -> None:
    keys = [key for _, _, key in _items()]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    assert duplicates == [], f"shortcut collisions: {duplicates}"


def test_the_goto_map_matches_the_navigation() -> None:
    """The `g` map and the rail are two views of one thing and must agree."""
    goto = _goto()
    nav = {key: href for href, _, key in _items() if href.startswith("/terminal/")}
    for key, href in nav.items():
        assert key in goto, f"nav offers 'g {key}' but the map has no entry"
        assert goto[key] == href, f"'g {key}' goes to {goto[key]}, nav shows {href}"


def test_every_goto_target_resolves() -> None:
    dead = [
        (key, href)
        for key, href in _goto().items()
        if not (APP / href.lstrip("/") / "page.tsx").is_file()
    ]
    assert dead == [], f"keyboard shortcuts pointing at no page: {dead}"


def test_the_shortcut_sheet_documents_only_wired_keys() -> None:
    """A help sheet naming a key nothing handles is worse than no help sheet."""
    sheet = (ROOT / "dashboard" / "src" / "components" / "system" / "Shortcuts.tsx").read_text()
    documented = set(re.findall(r"combo:\s*'g ([a-z])'", sheet))
    wired = set(_goto())
    undocumented_but_wired = wired - documented
    documented_but_dead = documented - wired
    assert documented_but_dead == set(), f"documented but not wired: {sorted(documented_but_dead)}"
    assert undocumented_but_wired == set(), f"wired but undocumented: {sorted(undocumented_but_wired)}"
