"""Who may do what.

Authentication answers "which account is this". Authorization answers "may
that account do this", and the two are not the same question — a signed-in
stranger is still a stranger. This module owns the second question for the
whole backend.

Three dimensions are kept deliberately separate, because collapsing any pair
of them is a security bug waiting for a product decision to trigger it:

    ROLE          USER | ADMIN          what you may do
    EXPERIENCE    BEGINNER | ADVANCED   how the interface is drawn
    ENTITLEMENT   FREE | PRO            what you have paid for

An ADVANCED user is not an administrator. A PRO subscriber is not an
administrator. A BEGINNER is not a free-tier user. Each of those is a
separate lookup and they never imply one another.

**Role elevation is not an API.** Nothing a client can call writes `admin`.
A role is granted either by a direct service-role update to `profiles.role`
or by naming the Clerk user id in `ADMIN_CLERK_USER_IDS`, which exists so the
first administrator can be created on a fresh deployment that has no
administrator to grant one. Both are operational acts performed by someone
with deployment access.

**It fails to the floor.** Every unknown — no database, no profile row, an
unrecognised role string, a failed query — resolves to USER, never ADMIN.
The failure mode of this module is "you can do less than you should", which
is recoverable; the opposite is not.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Callable, Optional

from fastapi import Depends, HTTPException

from src.services.clerk_auth import require_clerk_user

logger = logging.getLogger("omnisignal.authz")

#: Comma-separated Clerk user ids granted ADMIN without a database row.
#: The bootstrap path: a fresh deployment has no administrator, so there is
#: nobody who could promote one.
ADMIN_IDS_ENV = "ADMIN_CLERK_USER_IDS"


class Role(str, Enum):
    USER = "user"
    ADMIN = "admin"


class Permission(str, Enum):
    """What the backend actually gates on.

    Named for the capability rather than the route, so that adding a second
    endpoint to an existing capability does not require a new permission and
    a second place to forget to check it.
    """

    # Everyone signed in
    ANALYZE = "analyze"
    USE_BEGINNER = "use_beginner"
    USE_ADVANCED = "use_advanced"
    USE_EXPLORE = "use_explore"
    MANAGE_OWN_WATCHLISTS = "manage_own_watchlists"
    MANAGE_OWN_PORTFOLIO = "manage_own_portfolio"
    VIEW_OWN_HISTORY = "view_own_history"

    # Operators only
    VIEW_ADMIN_DIAGNOSTICS = "view_admin_diagnostics"
    VIEW_AGENT_EVALUATION = "view_agent_evaluation"
    MANAGE_SYSTEM = "manage_system"


#: Everything an ordinary signed-in account may do. Note what is *not* here:
#: no permission to read another user's data, because no such permission
#: exists — per-user scoping is enforced in the repositories by filtering on
#: the Clerk-verified id, not by a permission anyone could be granted.
_USER_PERMISSIONS: frozenset[Permission] = frozenset({
    Permission.ANALYZE,
    Permission.USE_BEGINNER,
    Permission.USE_ADVANCED,
    Permission.USE_EXPLORE,
    Permission.MANAGE_OWN_WATCHLISTS,
    Permission.MANAGE_OWN_PORTFOLIO,
    Permission.VIEW_OWN_HISTORY,
})

#: Operator capabilities, additive over the user set. An administrator is a
#: user who can also see how the machine is running — not a user with
#: different financial permissions, because there are none.
_ADMIN_ONLY: frozenset[Permission] = frozenset({
    Permission.VIEW_ADMIN_DIAGNOSTICS,
    Permission.VIEW_AGENT_EVALUATION,
    Permission.MANAGE_SYSTEM,
})

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.USER: _USER_PERMISSIONS,
    Role.ADMIN: _USER_PERMISSIONS | _ADMIN_ONLY,
}


def bootstrap_admin_ids() -> frozenset[str]:
    """Clerk user ids promoted by deployment configuration."""
    raw = os.getenv(ADMIN_IDS_ENV, "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def resolve_role(clerk_user_id: str) -> Role:
    """The caller's role, resolved from configuration then the database.

    Configuration wins. If an operator has named an id in the bootstrap
    variable, that id is an administrator even when the database is
    unreachable — which is exactly when an operator most needs to get in.

    Every other path, including an unreadable database or a role string this
    build does not recognise, resolves to USER.
    """
    if not clerk_user_id:
        return Role.USER
    if clerk_user_id in bootstrap_admin_ids():
        return Role.ADMIN

    from src.services import database
    from src.services.database.repositories import ProfilesRepository

    client = database.get_client()
    if client is None:
        return Role.USER
    try:
        stored = ProfilesRepository(client).role_of(clerk_user_id)
    except Exception:  # noqa: BLE001 — a database fault must not grant access
        logger.exception("role lookup failed for a caller; treating as %s", Role.USER.value)
        return Role.USER
    try:
        return Role(stored)
    except ValueError:
        # A value the constraint should have refused. Treated as the floor
        # rather than trusted, because an unrecognised role is a corrupted
        # one and corruption must not read as elevation.
        logger.warning("unrecognised role %r in profiles; treating as %s", stored, Role.USER.value)
        return Role.USER


def permissions_for(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, _USER_PERMISSIONS)


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in permissions_for(role)


def require_permission(permission: Permission) -> Callable[..., str]:
    """A FastAPI dependency that admits only callers holding `permission`.

    Returns the Clerk user id so a route can depend on this alone rather than
    stacking it on top of `require_clerk_user` and using two parameters.

    401 for an anonymous caller, supplied by `require_clerk_user`.
    403 for a signed-in caller whose role does not carry the permission — a
    different answer because it is a different problem, and telling them
    apart is the difference between "sign in" and "ask an operator".
    """

    def _dependency(user_id: str = Depends(require_clerk_user)) -> str:
        role = resolve_role(user_id)
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"This account does not have the {permission.value} capability. "
                    "It is granted by role, and roles are assigned operationally."
                ),
            )
        return user_id

    return _dependency


def capabilities_for(clerk_user_id: str, experience_mode: Optional[str] = None) -> dict:
    """The self-description a client may safely read about itself.

    Deliberately excludes the token, Clerk private metadata, the bootstrap
    list and anything else about *other* accounts. What a client learns here
    it already possesses; the backend still re-checks every permission on
    every request, because this response is a convenience for drawing
    navigation and is not a security boundary.
    """
    role = resolve_role(clerk_user_id)
    return {
        "role": role.value,
        "permissions": sorted(p.value for p in permissions_for(role)),
        "experience_mode": experience_mode,
    }
