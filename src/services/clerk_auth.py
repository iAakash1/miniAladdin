"""
Clerk session-token verification for the FastAPI backend.

The frontend attaches the Clerk session JWT (RS256) as a Bearer token; this
module verifies it against Clerk's public JWKS. No Clerk SDK, no network
round-trip per request — the JWKS is fetched once and cached by PyJWKClient.

Configuration (both optional — without them the API simply has no
authenticated persistence, and everything else keeps working):

    CLERK_JWKS_URL  e.g. https://<instance>.clerk.accounts.dev/.well-known/jwks.json
    CLERK_ISSUER    e.g. https://<instance>.clerk.accounts.dev
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import jwt
from fastapi import Header, HTTPException, Request
from jwt import PyJWKClient

logger = logging.getLogger("omnisignal.auth")

_jwks_client: Optional[PyJWKClient] = None


def is_configured() -> bool:
    return bool(os.getenv("CLERK_JWKS_URL"))


def _get_jwks_client() -> Optional[PyJWKClient]:
    global _jwks_client
    url = os.getenv("CLERK_JWKS_URL", "").strip()
    if not url:
        return None
    if _jwks_client is None:
        _jwks_client = PyJWKClient(url, cache_keys=True, lifespan=3600)
    return _jwks_client


def _reset_for_testing() -> None:
    global _jwks_client
    _jwks_client = None


def verify_token(token: str) -> Optional[str]:
    """Return the Clerk user id (`sub`) for a valid session token, else None."""
    client = _get_jwks_client()
    if client is None or not token:
        return None
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            # Clerk session tokens carry no `aud`; identity is established by
            # signature + issuer + expiry.
            options={"verify_aud": False},
            issuer=os.getenv("CLERK_ISSUER") or None,
            leeway=10,
        )
    except jwt.PyJWTError as exc:
        logger.info("rejected bearer token: %s", exc)
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) and sub else None


def _token_from_header(authorization: str) -> str:
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def require_clerk_user(request: Request, authorization: str = Header(default="")) -> str:
    """FastAPI dependency: a valid Clerk user or an explicit HTTP error."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="Authentication is not configured on this server.")
    user_id = verify_token(_token_from_header(authorization))
    if not user_id:
        raise HTTPException(status_code=401, detail="A valid Clerk session token is required.")
    request.state.clerk_user = user_id  # read by the request-logging middleware
    return user_id


def optional_clerk_user(request: Request, authorization: str = Header(default="")) -> Optional[str]:
    """FastAPI dependency: the Clerk user if a valid token is present, else None."""
    if not is_configured():
        return None
    user_id = verify_token(_token_from_header(authorization))
    if user_id:
        request.state.clerk_user = user_id
    return user_id
