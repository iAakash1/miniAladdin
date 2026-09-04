"""Alpaca paper trading. Paper only — enforced, not requested.

This module can only ever reach `paper-api.alpaca.markets`. That is not a
default, a preference or a configuration flag: the host is a constant, and the
one function that could have made it configurable instead refuses to run when
the environment asks for anything else.

The reason is asymmetric risk. A market-data provider misconfigured against
the wrong host returns wrong numbers, which is bad and visible. A broker
client misconfigured against the wrong host spends real money, which is
irreversible and — with the same code path, the same credentials shape and
the same response schema — completely invisible until it has happened. So the
live endpoint is not reachable from here at all, and an environment that
looks like it is trying to reach it is treated as broken rather than obeyed.

Alpaca issues separate credentials for paper and live, so a paper key cannot
trade real money even if this file were wrong. That is a second line, not the
first one, and it is not a reason to be careless with the first.

Nothing here returns a credential to a caller, logs one, or puts one in a URL.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# The only host this module will talk to. Not a default — a constant.
PAPER_HOST = "https://paper-api.alpaca.markets"

# Alpaca's own documented names come first; the unprefixed pair is accepted
# because it is what most deployments actually set.
KEY_ID_ENVS = ("APCA_API_KEY_ID", "ALPACA_API_KEY_ID")
SECRET_ENVS = ("APCA_API_SECRET_KEY", "ALPACA_API_SECRET_KEY")

# If a deployment sets a base URL, it is checked rather than used.
BASE_URL_ENVS = ("APCA_API_BASE_URL", "ALPACA_API_BASE_URL")


class BrokerMisconfigured(RuntimeError):
    """The environment asks for something this module will not do."""


class BrokerUnavailable(RuntimeError):
    """The broker could not be reached, or answered with an error."""


@dataclass(frozen=True)
class BrokerStatus:
    """What the interface is allowed to say about the connection.

    Deliberately carries no credential, no host secret and no key fragment —
    this crosses the API boundary to the browser.
    """
    configured: bool
    reason: Optional[str] = None
    environment: str = "paper"


def _first_env(names: tuple[str, ...]) -> str:
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return ""


def _assert_paper_environment() -> None:
    """Refuse to run in an environment pointed anywhere but paper.

    A deployment that sets APCA_API_BASE_URL to the live host has told us
    plainly what it intends. The safe response is to stop, not to quietly use
    the paper host anyway and let someone believe live trading is configured
    and working.
    """
    configured = _first_env(BASE_URL_ENVS)
    if not configured:
        return
    if configured.rstrip("/") != PAPER_HOST:
        raise BrokerMisconfigured(
            "This build executes paper orders only, and the configured broker "
            f"base URL is not the paper endpoint. Set it to {PAPER_HOST} or "
            "remove it entirely."
        )


def status() -> BrokerStatus:
    """Whether paper trading can be used, and if not, why — in words that are
    safe to render in a browser."""
    try:
        _assert_paper_environment()
    except BrokerMisconfigured as e:
        return BrokerStatus(configured=False, reason=str(e))

    if not _first_env(KEY_ID_ENVS) or not _first_env(SECRET_ENVS):
        return BrokerStatus(
            configured=False,
            reason="Alpaca paper credentials are not configured.",
        )
    return BrokerStatus(configured=True)


class AlpacaPaper:
    """A thin client over the paper trading API.

    Thin on purpose. Every method returns what the broker said, and none of
    them computes a fill, an average price, a P&L or an order state locally.
    A number this product shows about an account is a number the broker
    reported, or it is absent.
    """

    TIMEOUT_SECONDS = 8.0

    def __init__(self, session: Optional[requests.Session] = None):
        _assert_paper_environment()
        self._key = _first_env(KEY_ID_ENVS)
        self._secret = _first_env(SECRET_ENVS)
        if not self._key or not self._secret:
            raise BrokerMisconfigured("Alpaca paper credentials are not configured.")
        self._session = session or requests.Session()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._key,
            "APCA-API-SECRET-KEY": self._secret,
            "accept": "application/json",
        }

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        url = f"{PAPER_HOST}{path}"
        try:
            r = self._session.request(
                method, url, headers=self._headers,
                timeout=self.TIMEOUT_SECONDS, **kw,
            )
        except requests.RequestException as e:
            # The exception text can carry the URL but never a header, so this
            # is safe to surface. Credentials live in headers only.
            raise BrokerUnavailable(f"the broker did not respond ({type(e).__name__})") from e

        if r.status_code >= 400:
            detail = ""
            try:
                body = r.json()
                detail = str(body.get("message") or body)[:300]
            except ValueError:
                detail = r.text[:300]
            logger.warning("alpaca paper %s %s -> %s", method, path, r.status_code)
            raise BrokerUnavailable(f"the broker returned {r.status_code}: {detail}")

        return r.json() if r.content else None

    # ── read ─────────────────────────────────────────────────────────────────

    def account(self) -> dict[str, Any]:
        return self._request("GET", "/v2/account")

    def positions(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v2/positions") or []

    def orders(self, status_filter: str = "all", limit: int = 50) -> list[dict[str, Any]]:
        return self._request(
            "GET", "/v2/orders",
            params={"status": status_filter, "limit": limit, "direction": "desc"},
        ) or []

    def asset(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/assets/{symbol.upper()}")

    # ── write ────────────────────────────────────────────────────────────────

    def submit_order(
        self, *, symbol: str, qty: float, side: str,
        order_type: str = "market", time_in_force: str = "day",
        limit_price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Place a paper order and return exactly what the broker replied.

        No fill is simulated and no status is inferred. If the broker says
        `accepted`, this says accepted — the interface does not upgrade that
        to `filled` because a market order "probably" filled.
        """
        body: dict[str, Any] = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if limit_price is not None:
            body["limit_price"] = str(limit_price)
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", "/v2/orders", json=body)

    def cancel_order(self, order_id: str) -> None:
        self._request("DELETE", f"/v2/orders/{order_id}")
