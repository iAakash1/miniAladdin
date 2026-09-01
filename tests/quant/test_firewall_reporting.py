"""
The firewall must never be described more confidently than it is known.

`contract_armed` returns False when the contract cannot be read. That is the
correct *behaviour* — the firewall stays engaged and the holdout stays blocked —
but it is not evidence that a human declined to arm it. Reporting the two states
identically would let "we could not read the file" render as "confirmed not
armed" on a page whose whole job is to say what is and is not established.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.quant.study.firewall import FIREWALL


@pytest.fixture()
def contract_path():
    original = FIREWALL.contract_path
    yield lambda p: setattr(FIREWALL, "contract_path", p)
    FIREWALL.contract_path = original


def test_a_readable_unarmed_contract_reports_not_armed(contract_path):
    contract_path(Path("docs/HOLDOUT_CONTRACT.md"))
    status = FIREWALL.status()
    assert status["contract_readable"] is True
    assert status["contract_armed"] is False
    assert status["contract_state"] == "NOT_ARMED"
    assert status["engaged"] is True


def test_an_unreadable_contract_reports_unknown_not_not_armed(contract_path, tmp_path):
    contract_path(tmp_path / "absent.md")
    status = FIREWALL.status()
    assert status["contract_readable"] is False
    assert status["contract_state"] == "UNKNOWN", (
        "an unreadable contract is unknown, never a confirmed negative"
    )


def test_an_unreadable_contract_still_blocks(contract_path, tmp_path):
    """The safety behaviour must not change. This is the important assertion.

    Distinguishing UNKNOWN from NOT_ARMED is a reporting change. If it ever
    became a behavioural one — if an unknown contract stopped engaging the
    firewall — that would turn a clearer message into an open holdout.
    """
    contract_path(tmp_path / "absent.md")
    assert FIREWALL.contract_armed() is False
    assert FIREWALL.engaged is True


def test_an_armed_contract_reports_armed(contract_path, tmp_path):
    from src.quant.study.firewall import ARMED_MARKERS

    armed = tmp_path / "armed.md"
    armed.write_text(f"# Contract\n\n{next(iter(ARMED_MARKERS))}\n", encoding="utf-8")
    contract_path(armed)
    status = FIREWALL.status()
    assert status["contract_armed"] is True
    assert status["contract_state"] == "ARMED"
    assert status["engaged"] is False, "an armed contract is the one lift condition"
