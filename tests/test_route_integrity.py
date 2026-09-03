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

#: One nav item: href, label and shortcut. `glyph` sits between label and key
#: and is skipped rather than captured — the check is about destinations, and
#: pinning the exact field order would fail on every cosmetic edit.
ITEM = re.compile(
    r"\{\s*href:\s*'([^']+)',\s*label:\s*'([^']+)',"
    r"(?:\s*glyph:\s*'[^']*',)?\s*key:\s*'([a-z])'\s*\}"
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


def _palette() -> dict[str, tuple[str, str]]:
    """The command palette's navigation entries, keyed by shortcut hint.

    Returns {'s': ('Go to Securities', '/terminal/security'), ...}.
    """
    source = (ROOT / "dashboard" / "src" / "components" / "system" / "Palette.tsx").read_text()
    entries = re.findall(r"go\('([^']+)',\s*'([^']+)',\s*'g ([a-z])'\)", source)
    return {key: (label, href) for label, href, key in entries}


def test_the_palette_and_the_navigation_agree() -> None:
    """One command, one destination.

    The palette shipped `Go to Securities → /terminal/analyze` while the sidebar
    sent the same `g s` to `/terminal/security`. Both were live routes, so
    nothing failed; the reader simply arrived somewhere else depending on how
    they asked, and one of the two destinations still ran the old shell.

    Two ways to reach one workspace must agree on where it is.
    """
    nav = _goto()
    disagreements = [
        (key, href, nav[key])
        for key, (_, href) in _palette().items()
        if key in nav and nav[key] != href
    ]
    assert disagreements == [], (
        "palette and navigation disagree on where a shortcut goes "
        f"(key, palette, nav): {disagreements}"
    )


def test_every_palette_destination_resolves() -> None:
    dead = [
        (key, href)
        for key, (_, href) in _palette().items()
        if not (APP / href.lstrip("/") / "page.tsx").is_file()
    ]
    assert dead == [], f"palette entries pointing at no page: {dead}"


def test_the_palette_names_a_shortcut_that_exists() -> None:
    """A hint promising `g s` when nothing handles `g s` teaches a wrong key."""
    nav = _goto()
    unwired = sorted(key for key in _palette() if key not in nav)
    assert unwired == [], f"palette hints for unwired shortcuts: {unwired}"


def test_a_workspace_does_not_print_the_same_number_twice() -> None:
    """The masthead and the strip beneath it must not repeat a figure.

    Twenty workspaces carried the same labels in both — five of them repeated
    every single number, forty pixels apart. Two rows saying the same thing
    teach a reader to skip one of them, and then to skip both, which costs the
    strip the one job it has.

    The masthead states the object's headline facts. The strip is for what the
    masthead does not say.
    """
    import re

    ui = ROOT / "dashboard" / "src" / "components" / "terminal"
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
