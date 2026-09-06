"""Who may operate the paper trading account.

This exists because authentication alone does not make the paper workspace
safe. There is exactly **one** Alpaca paper account behind this API, shared by
every caller the server accepts. Requiring a Clerk session would stop
anonymous access and would still leave every signed-in user reading and
mutating the same positions, the same orders and the same balance — one
person's cancel would delete another person's order, and each would see it as
their own account.

So the account is treated as what it is: a single demonstration account with
named operators, not a per-user book. `PAPER_TRADING_OWNERS` holds a
comma-separated list of Clerk user ids permitted to use it.

**It fails closed.** With no owners configured, nobody is authorised, and the
routes answer 403 with the reason. That is deliberate: the alternative — an
empty list meaning "everyone" — is exactly the flaw this module was written to
close, and a deployment that forgets to set the variable would silently
reopen it. A paper workspace that says "not enabled for this deployment" is
honest; one that hands a stranger the controls is not.

Nothing here touches the broker's own guarantee. `alpaca_paper` hardcodes
`https://paper-api.alpaca.markets` and refuses any other host, and that stays
exactly as it is. This is a second, independent control: the broker decides
*which venue*, this decides *who*.
"""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException

from src.services.clerk_auth import require_clerk_user

#: Environment variable holding the permitted Clerk user ids.
OWNERS_ENV = "PAPER_TRADING_OWNERS"


def configured_owners() -> frozenset[str]:
    """Clerk user ids allowed to operate the demo paper account."""
    raw = os.getenv(OWNERS_ENV, "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def paper_access_state() -> dict[str, object]:
    """Whether *anyone* may trade here — without naming who.

    Reported by `/api/paper/status` so the interface can distinguish "this
    deployment has no paper operator" from "you are not one of them". The
    owner ids themselves are never returned: they are account identifiers and
    the client has no use for someone else's.
    """
    owners = configured_owners()
    return {
        "authorization": "clerk-session + explicit owner allowlist",
        "enabled": bool(owners),
        "reason": (
            None if owners
            else f"No paper trading owner is configured ({OWNERS_ENV} is unset), "
                 "so the shared demo account is closed to everyone."
        ),
    }


def require_paper_trader(user_id: str = Depends(require_clerk_user)) -> str:
    """A Clerk user explicitly permitted to operate the demo paper account.

    401 for an anonymous caller — supplied by `require_clerk_user`.
    403 for a signed-in caller who is not an owner, and for every caller when
    no owner is configured.
    """
    owners = configured_owners()
    if not owners:
        raise HTTPException(
            status_code=403,
            detail=(
                "Paper trading is not enabled on this deployment. A single "
                "shared paper account cannot be given to every signed-in user, "
                f"so it stays closed until {OWNERS_ENV} names its operators."
            ),
        )
    if user_id not in owners:
        raise HTTPException(
            status_code=403,
            detail=(
                "This account is not an operator of the demonstration paper "
                "account. There is one paper account on this deployment and it "
                "is not per-user."
            ),
        )
    return user_id
