"""Fault doubles shared by the provider failure-injection tests.

A vendor adapter talks to the world through `requests.Session.request` (and,
for three library-backed vendors, `timed_call`).  Everything here replaces that
boundary with something scripted, so a test can make a vendor time out, answer
401/403/404/429/5xx, return malformed JSON, `null`, an empty body, or a payload
carrying NaN and Infinity - and then assert what the rest of the system makes
of it.

Nothing here touches the network: the session never opens a socket.
"""

from __future__ import annotations

import copy
import json
import math
from typing import Any, Callable, Optional

import requests

#: Long enough to be "configured" (the base class wants more than five
#: characters) and distinctive enough to find in any leaked string.
SECRET_KEY = "SECRETKEY-do-not-leak-0123456789"


class FakeResponse:
    """The slice of `requests.Response` the adapters read."""

    def __init__(
        self,
        status: int = 200,
        body: Any = None,
        *,
        headers: Optional[dict[str, str]] = None,
        json_error: Optional[str] = None,
        content: Optional[bytes] = None,
    ) -> None:
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self._json_error = json_error
        if content is not None:
            self.content = content
        elif json_error is not None:
            self.content = b""
        else:
            self.content = json.dumps(body, allow_nan=True).encode()
        self.text = self.content.decode("utf-8", "replace")
        self.url = f"https://vendor.invalid/path?apikey={SECRET_KEY}"

    def json(self) -> Any:
        if self._json_error is not None:
            raise ValueError(self._json_error)
        # A fresh copy per call: an adapter that mutates what it parsed must not
        # corrupt the next call's input.
        return copy.deepcopy(self._body)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            # `requests` embeds the full URL - key included - in this message.
            raise requests.exceptions.HTTPError(
                f"{self.status_code} Client Error: for url: {self.url}", response=self,
            )


class ScriptedSession:
    """A `requests.Session` stand-in that answers from a script.

    `script` is either a FakeResponse, an exception instance (raised), or a
    callable `(method, url, kwargs) -> FakeResponse | Exception`.  Every request
    is recorded in `calls`.
    """

    def __init__(self, script: Any) -> None:
        self.script = script
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def _answer(self, method: str, url: str, kwargs: dict[str, Any]) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        outcome = self.script(method, url, kwargs) if callable(self.script) else self.script
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        return self._answer(method, url, kwargs)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._answer("GET", url, kwargs)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._answer("POST", url, kwargs)


# ── the failure catalogue ────────────────────────────────────────────────────
#
# Each entry is a callable returning the scripted outcome, so every test gets a
# fresh object.  Names are the vocabulary the matrix is reported in.

def _http(status: int, headers: Optional[dict[str, str]] = None) -> Callable[[], FakeResponse]:
    return lambda: FakeResponse(status, {"message": "scripted failure"}, headers=headers)


#: A failure of the *connection*: nothing usable came back.
TRANSPORT: dict[str, Callable[[], Any]] = {
    "timeout": lambda: requests.exceptions.ReadTimeout("read timed out"),
    "connection_error": lambda: requests.exceptions.ConnectionError(
        f"HTTPSConnectionPool(host='vendor.invalid'): max retries exceeded "
        f"with url: /path?apikey={SECRET_KEY}"
    ),
    "http_401": _http(401),
    "http_403": _http(403),
    "http_404": _http(404),
    "http_418": _http(418),
    "http_429": _http(429),
    "http_429_long_retry_after": _http(429, {"Retry-After": "120"}),
    "http_500": _http(500),
    "http_502": _http(502),
    "http_503": _http(503),
    "http_504": _http(504),
}

#: HTTP 200 whose body is not a usable answer.
UNPARSEABLE: dict[str, Callable[[], Any]] = {
    "malformed_json": lambda: FakeResponse(200, json_error="Expecting value: line 1 column 1 (char 0)"),
    "empty_body": lambda: FakeResponse(200, json_error="Expecting value: line 1 column 1 (char 0)", content=b""),
    "truncated_json": lambda: FakeResponse(200, json_error="Unterminated string starting at: line 1 column 9"),
}

#: HTTP 200 whose body parses, into something that is not any vendor's answer.
WRONG_SHAPE: dict[str, Callable[[], Any]] = {
    "null_body": lambda: FakeResponse(200, None),
    "string_body": lambda: FakeResponse(200, "Service temporarily unavailable"),
    "number_body": lambda: FakeResponse(200, 0),
    "bool_body": lambda: FakeResponse(200, False),
}

#: HTTP 200 whose body is the vendor saying "nothing here" in the legitimate
#: way.  Not a fault, but it must never be dressed up as data.
EMPTY_ANSWER: dict[str, Callable[[], Any]] = {
    "empty_object": lambda: FakeResponse(200, {}),
    "empty_list": lambda: FakeResponse(200, []),
}

#: HTTP 200 carrying the vendor's own error envelope.  Several vendors report
#: rate limits and bad keys this way instead of with a status code.
ERROR_ENVELOPE: dict[str, Callable[[], Any]] = {
    "status_error_rate_limit": lambda: FakeResponse(
        200, {"status": "error", "code": 429, "message": "You have run out of API credits for the current minute."},
    ),
    "status_error_bad_key": lambda: FakeResponse(
        200, {"status": "error", "code": 401, "message": "apikey parameter is incorrect or not specified."},
    ),
    "error_message_key": lambda: FakeResponse(200, {"Error Message": "Invalid API KEY. Please retry or visit our documentation."}),
    "note_key": lambda: FakeResponse(
        200, {"Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."},
    ),
    "polygon_error": lambda: FakeResponse(200, {"status": "ERROR", "error": "Unknown API Key"}),
}


# ── payload mutation ─────────────────────────────────────────────────────────

NON_FINITE = (float("nan"), float("inf"), float("-inf"))


def numeric_paths(node: Any, prefix: tuple = ()) -> list[tuple]:
    """Every path in `node` that leads to a number (bools excluded)."""
    found: list[tuple] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.extend(numeric_paths(value, prefix + (key,)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(numeric_paths(value, prefix + (index,)))
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        found.append(prefix)
    return found


def with_value(payload: Any, path: tuple, value: Any) -> Any:
    """A deep copy of `payload` with the leaf at `path` replaced."""
    clone = copy.deepcopy(payload)
    cursor = clone
    for step in path[:-1]:
        cursor = cursor[step]
    cursor[path[-1]] = value
    return clone


def contains_non_finite(node: Any) -> bool:
    """Whether a model/dict/list holds NaN or +/-Infinity anywhere inside it."""
    if hasattr(node, "model_dump"):
        node = node.model_dump()
    if isinstance(node, float):
        return not math.isfinite(node)
    if isinstance(node, dict):
        return any(contains_non_finite(v) for v in node.values())
    if isinstance(node, (list, tuple, set)):
        return any(contains_non_finite(v) for v in node)
    return False


def is_empty_container(value: Any) -> bool:
    return isinstance(value, (list, dict, tuple, set)) and not value


def is_empty_value(value: Any) -> bool:
    """None, an empty container, or a model that holds nothing at all.

    A `KnowledgeBundle` with no nodes, edges, claims, events or findings is an
    honest "nothing found". A bundle with a node in it is a claim about the
    world and must have come from something the vendor actually said.
    """
    if value is None or is_empty_container(value):
        return True
    if hasattr(value, "model_dump"):
        return all(not v for v in value.model_dump().values())
    return False
