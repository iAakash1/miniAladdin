"""Every measure the risk workspace links to must exist in the handbook.

The risk report names a measure at a confidence level — `var_historical_95` —
while the methodology table keys some entries without one. A link built by
guessing at that transformation lands on nothing, silently, for exactly the
measures a reader most wants explained.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.services.methodology_service import handbook

ROOT = Path(__file__).resolve().parents[2]
RISK_VIEW = ROOT / "dashboard" / "src" / "components" / "terminal" / "risk" / "RiskWorkbench.tsx"

MAP = re.compile(r"^\s{2}([a-z_0-9]+):\s*'([a-z_0-9]+)',$", re.MULTILINE)


def _links() -> dict[str, str]:
    src = RISK_VIEW.read_text()
    start = src.index("const HANDBOOK_KEY")
    end = src.index("}", src.index("{", start))
    return dict(MAP.findall(src[start:end]))


def test_the_link_table_parses() -> None:
    assert len(_links()) >= 15


def test_every_link_target_exists_in_the_handbook() -> None:
    known = {e["name"] for e in handbook()["entries"]}
    missing = sorted({target for target in _links().values() if target not in known})
    assert missing == [], f"risk links to measures the handbook does not define: {missing}"


def test_linked_measures_carry_failure_conditions() -> None:
    """A link is a promise that the destination explains something."""
    entries = {e["name"]: e for e in handbook()["entries"]}
    undocumented = sorted(
        target for target in _links().values()
        if target in entries and not entries[target]["fails_when"]
    )
    assert undocumented == [], f"linked but with no failure conditions: {undocumented}"
