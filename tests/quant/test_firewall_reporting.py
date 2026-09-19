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


# ── holdout_state: the unambiguous reading of NOT_ARMED + engaged ────────────
#
# EXP-010A's manifest recorded contract_armed=false, contract_state=NOT_ARMED,
# engaged=true, window.active=true. That is the SAFE state (holdout closed, firewall
# blocking) but it reads backwards to anyone who takes "armed" to mean "protected".

from datetime import date  # noqa: E402

from src.quant.study.firewall import HoldoutBreach, reset_for_tests  # noqa: E402


@pytest.fixture()
def declared_window():
    reset_for_tests()
    FIREWALL.arm_window(date(2025, 8, 26), date(2026, 8, 28))
    yield
    reset_for_tests()


def test_not_armed_with_a_declared_window_is_reported_as_sealed(declared_window, contract_path):
    contract_path(Path("docs/HOLDOUT_CONTRACT.md"))
    status = FIREWALL.status()
    assert status["contract_state"] == "NOT_ARMED"       # the detail is unchanged ...
    assert status["engaged"] is True
    assert status["holdout_state"] == "SEALED"           # ... and the summary is unambiguous
    assert status["holdout_access"] == "BLOCKED"
    assert "closed" in status["reading_note"]


def test_a_sealed_holdout_actually_refuses_holdout_rows(declared_window, contract_path):
    import pandas as pd

    contract_path(Path("docs/HOLDOUT_CONTRACT.md"))
    assert FIREWALL.holdout_state() == "SEALED"
    with pytest.raises(HoldoutBreach):
        FIREWALL.assert_clear(pd.DataFrame({"date": [date(2025, 9, 2)]}), context="test")


def test_an_unreadable_contract_is_sealed_but_flagged(declared_window, contract_path, tmp_path):
    contract_path(tmp_path / "absent.md")
    assert FIREWALL.holdout_state() == "SEALED_CONTRACT_UNREADABLE"
    assert FIREWALL.status()["holdout_access"] == "BLOCKED"


def test_no_declared_window_is_never_described_as_sealed(contract_path):
    reset_for_tests()
    contract_path(Path("docs/HOLDOUT_CONTRACT.md"))
    status = FIREWALL.status()
    assert status["holdout_state"] == "NO_WINDOW_DECLARED"
    assert status["holdout_access"] != "BLOCKED"


def test_an_armed_contract_and_an_override_are_reported_as_unsealed(declared_window, contract_path, tmp_path):
    from src.quant.study.firewall import ARMED_MARKERS

    armed = tmp_path / "armed.md"
    armed.write_text(f"# c\n\n{ARMED_MARKERS[0]}\n")
    contract_path(armed)
    assert FIREWALL.holdout_state() == "UNSEALED_CONTRACT_ARMED"
    contract_path(Path("docs/HOLDOUT_CONTRACT.md"))
    with FIREWALL.override("test only"):
        assert FIREWALL.holdout_state() == "UNSEALED_OVERRIDE"
    assert FIREWALL.holdout_state() == "SEALED"
