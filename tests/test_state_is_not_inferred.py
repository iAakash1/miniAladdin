"""A research state must never be asserted from data that might be absent.

The pattern this forbids reads innocently:

    state={selection?.verdict?.passed ? 'candidate' : 'blocked'}

When the fetch fails, `selection` is null, the ternary takes its else branch,
and the panel states BLOCKED — a definite verdict, rendered from no data at all.
It happens to be the right answer today, which is exactly what makes it
dangerous: it would keep printing on the day it became wrong, and a surface that
cannot distinguish "the gates rejected this" from "the gates could not be read"
will eventually say the first while meaning the second.

The firewall was the sharpest case. Its payload carries a three-valued
`contract_state` precisely because a false `contract_armed` means either
"confirmed not armed" or "the contract could not be read" — a distinction the
type declaration documents in as many words — and the panel was reading the
boolean.

Absence has its own states: `unavailable`, `unknown`, `waking`. One of those is
the honest answer when the data did not arrive.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = ROOT / "dashboard" / "src" / "components"

#: `state={maybe?.thing ? 'a' : 'b'}` — a definite state from an optional chain.
INFERRED = re.compile(
    r"state=\{\s*[A-Za-z_$][\w$]*\?\.[\w$.?]+\s*\?\s*'([a-z]+)'\s*:\s*'([a-z]+)'\s*\}"
)

#: States that honestly describe missing data rather than asserting a finding.
ABSENCE = {"unavailable", "unknown", "waking"}


def _sources() -> list[Path]:
    return sorted(TERMINAL.rglob("*.tsx"))


def test_no_research_state_is_inferred_from_an_optional_chain() -> None:
    offenders: list[str] = []
    for path in _sources():
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            for match in INFERRED.finditer(line):
                # A ternary whose else branch already says "absent" is fine:
                # it is not claiming a finding, it is reporting one is missing.
                if match.group(2) in ABSENCE:
                    continue
                rel = path.relative_to(ROOT)
                offenders.append(f"{rel}:{line_no} {match.group(0)}")

    assert offenders == [], (
        "a definite research state is being asserted from possibly-absent data. "
        "Check the value for undefined first and render an absence state:\n  "
        + "\n  ".join(offenders)
    )


def test_the_firewall_reads_the_three_valued_field() -> None:
    """`contract_armed` is a boolean over three real possibilities."""
    source = (TERMINAL / "terminal" / "command" / "CommandCenter.tsx").read_text()
    assert "contract_state" in source, "the firewall must read the three-valued field"
    inferred = re.search(r"state=\{[^}]*contract_armed[^}]*\?[^}]*:", source)
    assert inferred is None, (
        "the firewall panel derives its state from contract_armed. A false there "
        "means either 'confirmed not armed' or 'could not be read', and a holdout "
        "must never be described more confidently than it is known."
    )


def test_the_holdout_is_not_called_sealed_on_a_failed_read() -> None:
    """Untouched means sealed. Unread means unread, and the two look alike."""
    source = (TERMINAL / "terminal" / "command" / "CommandCenter.tsx").read_text()
    assert "holdoutTouched === undefined" in source, (
        "an unread holdout must be distinguished from a sealed one — rendering "
        "the first as the second is the most flattering error this panel can make"
    )
