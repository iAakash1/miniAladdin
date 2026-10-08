"""
VendorClient — the base every vendor adapter builds on.

Provides, per vendor:
  * key management (adapter is `available` only when its env key exists;
    keyless vendors like yfinance/Yahoo RSS are always available)
  * token-bucket rate limiting (defaults per free tier, override with
    PROVIDER_<NAME>_RPM)
  * hard timeout per request
  * bounded retries with exponential backoff on transient failures
  * health statistics: totals, success %, consecutive failures, avg/max
    latency, last error — feeding the orchestrator's routing decisions
  * cooldown circuit: after N consecutive failures the vendor is skipped
    by fallback chains until the cooldown elapses
"""

from __future__ import annotations

import functools
import inspect
import logging
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Any, Optional

import requests

from src.observability import metrics as _metrics

logger = logging.getLogger(__name__)

TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class FailureClass(str, Enum):
    """Stable operator-facing reason for a provider failure."""

    RATE_LIMITED = "rate_limited"
    AUTH_FAILURE = "auth_failure"
    NOT_ENTITLED = "not_entitled"
    TIMEOUT = "timeout"
    UPSTREAM = "upstream_failure"
    PARSE = "parse_failure"
    LOCAL_LIMITER = "local_limiter"
    UNAVAILABLE = "unavailable"

# Query parameters that carry credentials. Several vendors only accept auth in
# the query string, so these values reach `requests`, which then embeds the
# full URL in the text of any HTTPError it raises. That string is recorded as
# the vendor's error, travels into `Evidence.error`, and from there into the
# provenance payload the API returns — so an ordinary 403 from one vendor was
# enough to publish that vendor's API key to the browser. Redaction happens at
# the point the message is built rather than at the point it is displayed,
# because there is no way to know every place an error string will end up.
_SECRET_PARAMS = (
    "apikey", "api_key", "apiKey", "token", "access_key", "access_token",
    "key", "auth", "client_id", "client_secret", "UserID",
)
_SECRET_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(p) for p in _SECRET_PARAMS) + r")=[^&\s\"']+"
)


def redact(text: str) -> str:
    """Replace credential query values with a marker.

    Deliberately operates on the message rather than on the URL: by the time
    `requests` has raised, the key is already inside a formatted string, and
    reconstructing the URL to re-encode it would be both fragile and easy to
    forget at the next call site.
    """
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}=<redacted>", text or "")


def scrub_non_finite(payload: Any) -> Any:
    """Replace NaN and +/-Infinity in a parsed JSON payload with None.

    Python's `json` accepts the bare tokens `NaN`, `Infinity` and `-Infinity`,
    which are not JSON, so a vendor that emits one hands the adapter a float
    that compares false against everything and survives arithmetic as another
    non-finite float. Each adapter already guards the fields it reads, but a
    guard per field is a guard someone forgets (`vendor_metrics` kept every
    infinite value). Doing it once, at the boundary, makes the property hold
    for every adapter including the ones not written yet: a non-finite number
    is an absent number, and absent is what the rest of the system already
    knows how to carry.

    In place and iterative: the SEC company-facts document holds over a
    million values, so neither a copy nor recursion is acceptable.
    """
    if isinstance(payload, float):
        return payload if math.isfinite(payload) else None
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if isinstance(value, float):
                    if not math.isfinite(value):
                        node[key] = None
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                if isinstance(value, float):
                    if not math.isfinite(value):
                        node[index] = None
                elif isinstance(value, (dict, list)):
                    stack.append(value)
    return payload


def _may_hold_non_finite(response: Any) -> bool:
    """Whether the raw body could contain a NaN/Infinity token.

    A substring scan in C is far cheaper than walking a large parsed payload,
    so the walk only runs when the bytes say it might find something. A body
    that cannot be inspected (a test double, a streamed response) is walked.
    """
    raw = getattr(response, "content", None)
    if isinstance(raw, (bytes, bytearray)):
        return b"NaN" in raw or b"Infinity" in raw
    if isinstance(raw, str):
        return "NaN" in raw or "Infinity" in raw
    return True


#: Top-level keys that, on their own, mean "the vendor is telling us it could
#: not answer" rather than "here is data". Deliberately conservative: a payload
#: that also carries data keys is data.
_ENVELOPE_KEYS = frozenset({
    "error", "errors", "code", "message", "status", "tag", "detail", "details",
    "request_id", "requestId", "timestamp", "path", "Error Message", "Note",
    "Information", "error_message", "type", "title", "description",
})
#: Statuses that always mean refusal. "failed" is left out on purpose: a job
#: object (an Apify run) legitimately reports `status: FAILED` as data.
_ERROR_STATUS_WORDS = frozenset({"error", "not_authorized", "unauthorized"})

_RATE_MARKERS = (
    "ratelimit", "toomanyrequests", "outofapicredits", "outofcredits", "apicredits",
    "exhaust", "quota", "callfrequency", "callsperminute", "callsperday",
    "throttl", "limitreach", "limitexceed", "exceededthe", "maximumresults",
    "requestsper", "dailylimit", "minutelimit",
)
_ENTITLEMENT_MARKERS = (
    "premium", "upgrade", "subscription", "notentitled", "notpermission",
    "yourplan", "currentplan", "notincluded", "paidplan", "paidplans",
)
_AUTH_WORDS = (
    "invalid", "incorrect", "unknown", "missing", "inactive", "expired",
    "rejected", "notprovided", "notspecified", "notvalid", "disabled",
    "wrong", "revoked", "denied",
)
_CREDENTIAL_NOUNS = ("apikey", "accesskey", "token", "credential", "authorization", "appid", "userid")
_NOTHING_HERE = re.compile(
    r"not\s*found|no\s+data|invalid\s+symbol|unknown\s+symbol|symbol.{0,40}(missing|invalid|not)",
    re.IGNORECASE,
)


def classify_api_error(code: Any, text: str) -> FailureClass:
    """The failure class a vendor's own error message describes.

    Several vendors report a bad key, an exhausted quota or a plan boundary as
    HTTP 200 with an error object instead of a status code. The wording is the
    only signal, and the wording varies ("Unknown API Key", "apikey parameter
    is incorrect", "run out of API credits", "Limit Reach"), so this matches
    stems on the letters alone - case, spacing and punctuation vary freely.
    A numeric `code`, where there is one, speaks first.
    """
    status = int(code) if isinstance(code, (int, float)) and not isinstance(code, bool) else None
    if status == 401:
        return FailureClass.AUTH_FAILURE
    if status in (402, 403):
        return FailureClass.NOT_ENTITLED
    if status == 429:
        return FailureClass.RATE_LIMITED
    squashed = re.sub(r"[^a-z]", "", (text or "").lower())
    if any(marker in squashed for marker in _RATE_MARKERS):
        return FailureClass.RATE_LIMITED
    if "unauthori" in squashed or "forbidden" in squashed or (
        any(noun in squashed for noun in _CREDENTIAL_NOUNS)
        and any(word in squashed for word in _AUTH_WORDS)
    ):
        return FailureClass.AUTH_FAILURE
    if any(marker in squashed for marker in _ENTITLEMENT_MARKERS):
        return FailureClass.NOT_ENTITLED
    if status is not None and status >= 500:
        return FailureClass.UPSTREAM
    return FailureClass.UNAVAILABLE


def api_error_in(payload: Any) -> Optional[tuple[Any, str]]:
    """(code, text) when a parsed body is a vendor error envelope, else None.

    Looks only at the top level and only at bodies made of nothing but
    envelope keys, so a data payload that happens to contain the word "error"
    or "status" somewhere is never mistaken for a refusal.
    """
    if not isinstance(payload, dict) or not payload:
        return None
    status = payload.get("status")
    explicit_status = isinstance(status, str) and status.strip().lower() in _ERROR_STATUS_WORDS
    # A marker only counts when it says something: `"errors": []` beside a
    # message is a clean response, not a refusal.
    has_marker = any(
        payload.get(k) not in (None, "", [], {})
        for k in ("Error Message", "Note", "Information", "error", "errors")
    )
    # A bare {"status": "ok"} / {"message": "..."} is not an error.
    if not explicit_status and not has_marker:
        return None
    if not set(payload) <= _ENVELOPE_KEYS and not explicit_status:
        # Data keys beside an "error" key: this is data. Only an explicit error
        # status (Polygon keeps `request_id` and `count` beside it) overrides.
        return None
    parts: list[str] = []
    for key in ("code", "message", "error", "errors", "error_message", "Error Message",
                "Note", "Information", "detail", "details", "type", "title"):
        value = payload.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict):
            parts.extend(str(v) for v in value.values() if isinstance(v, (str, int)))
        elif isinstance(value, list):
            parts.extend(str(v) for v in value if isinstance(v, (str, int)))
        else:
            parts.append(str(value))
    if not parts and not explicit_status:
        return None
    nested = payload.get("error")
    code = payload.get("code")
    if code is None and isinstance(nested, dict):
        code = nested.get("code")
    return code, " ".join(parts)[:240]


#: What reading one damaged row can raise. Anything else is a bug, not a bad row.
READ_ERRORS = (AttributeError, KeyError, IndexError, TypeError, ValueError, OverflowError, OSError)


def read_rows(rows: Any, parse) -> tuple[list, int]:
    """Parse each row of a vendor list; one unreadable row costs that row only.

    `parse(row)` returns the parsed item, or `None` for a row that is
    deliberately left out (a removed article, a placeholder). It raises one of
    `READ_ERRORS` for a row it cannot make sense of. Those are counted and
    returned, never swallowed silently: the caller reports them, so "the vendor
    sent 250 bars and we read 249" stays visible instead of becoming a shorter
    year.

    A reply that is not a list at all yields nothing, and says nothing was
    unreadable: the caller has already decided what a wrong container means.
    """
    if not isinstance(rows, list):
        return [], 0
    parsed: list = []
    unreadable = 0
    for row in rows:
        try:
            item = parse(row)
        except READ_ERRORS:
            unreadable += 1
            continue
        if item is not None:
            parsed.append(item)
    return parsed, unreadable


def _observe(vendor: str, operation: str, outcome: str, latency_ms: float) -> None:
    """Record one vendor call into the process registry and the live request.

    Labels are a closed set — vendor names, operation names, ok/error — so
    cardinality stays bounded. Deliberately never labelled by symbol: that is
    unbounded and would turn the registry into a memory leak.
    """
    _metrics.registry.observe(
        "vendor.call", latency_ms, vendor=vendor, operation=operation, outcome=outcome
    )


class RateLimiter:
    """Token bucket: `rpm` requests per minute, thread-safe, non-blocking check."""

    def __init__(self, rpm: int):
        self.capacity = max(1, rpm)
        self.tokens = float(self.capacity)
        self.refill_per_sec = self.capacity / 60.0
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.refill_per_sec)
            self.updated = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class VendorStats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total = 0
        self.successes = 0
        self.failures = 0
        self.rate_limited = 0
        self.consecutive_failures = 0
        self.total_latency_ms = 0.0
        self.max_latency_ms = 0.0
        self.last_error: Optional[str] = None
        self.last_success_at: Optional[float] = None
        self.last_failure_at: Optional[float] = None
        self.last_attempt_at: Optional[float] = None
        self.last_failure_class: Optional[str] = None
        #: The latest outcome of each operation. A 403 on one endpoint is a
        #: plan boundary for that endpoint, not a verdict on the vendor; this
        #: is what lets the health state say which.
        self.last_by_operation: dict[str, tuple[bool, Optional[str], float]] = {}

    def record(
        self,
        ok: bool,
        latency_ms: float,
        error: Optional[str] = None,
        failure_class: Optional[str] = None,
        operation: Optional[str] = None,
        request_specific: bool = False,
    ) -> None:
        with self._lock:
            now = time.time()
            if operation:
                self.last_by_operation[operation] = (
                    ok, None if ok else (failure_class or FailureClass.UNAVAILABLE.value), now,
                )
            self.total += 1
            self.last_attempt_at = now
            self.total_latency_ms += latency_ms
            self.max_latency_ms = max(self.max_latency_ms, latency_ms)
            if ok:
                self.successes += 1
                self.consecutive_failures = 0
                self.last_success_at = now
            else:
                self.failures += 1
                # A plan refusal is a deterministic answer about one request,
                # not a sign the vendor is down. Counting it toward cooldown
                # benched FMP for everything after three sector-fund lookups
                # its free plan does not cover.
                # A 404 or 422 is the same kind of answer: this input has
                # nothing here (Twelve Data asked for ^VIX, Marketstack for an
                # unsupported symbol), not an outage.
                if failure_class != FailureClass.NOT_ENTITLED.value and not request_specific:
                    self.consecutive_failures += 1
                self.last_error = (error or "unknown")[:300]
                self.last_failure_at = now
                self.last_failure_class = failure_class or FailureClass.UNAVAILABLE.value

    def record_rate_limit(self, failure_class: FailureClass) -> None:
        """Record a request rejected before transport under the stats lock."""
        with self._lock:
            self.rate_limited += 1
            self.last_attempt_at = time.time()
            self.last_failure_at = self.last_attempt_at
            self.last_failure_class = failure_class.value
            self.last_error = (
                "local rate limit reached"
                if failure_class is FailureClass.LOCAL_LIMITER
                else "upstream rate limit reached"
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg = self.total_latency_ms / self.total if self.total else 0.0
            return {
                "requests": self.total,
                "success_pct": round(100.0 * self.successes / self.total, 1) if self.total else None,
                "failures": self.failures,
                "rate_limited": self.rate_limited,
                "consecutive_failures": self.consecutive_failures,
                "avg_latency_ms": round(avg, 1),
                "max_latency_ms": round(self.max_latency_ms, 1),
                "last_error": self.last_error,
                "last_success_at": self.last_success_at,
                "last_failure_at": self.last_failure_at,
                "last_attempt_at": self.last_attempt_at,
                "last_failure_class": self.last_failure_class,
                "operations": {
                    op: {"ok": ok, "failure_class": cls, "at": at}
                    for op, (ok, cls, at) in sorted(self.last_by_operation.items())
                },
            }


class VendorError(Exception):
    def __init__(
        self,
        message: str,
        transient: bool = False,
        *,
        failure_class: FailureClass | str = FailureClass.UNAVAILABLE,
        status_code: Optional[int] = None,
        retry_after_seconds: Optional[float] = None,
    ):
        super().__init__(message)
        self.transient = transient
        self.failure_class = (
            failure_class.value if isinstance(failure_class, FailureClass) else failure_class
        )
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


#: Where bounded library calls run.
#:
#: Daemon threads, so a call that outlives its timeout cannot hold up
#: interpreter exit. Shared across vendors because the alternative — a pool
#: per vendor — multiplies idle threads by the number of adapters for no gain;
#: these calls are rate-limited upstream, so the pool is never the bottleneck.
_CALL_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="vendor-call")


def _guard_operation(fn):
    """Wrap an adapter operation so only a `VendorError` can leave it.

    An adapter reads a vendor's reply by subscripting and calling `.get` on it.
    When the reply is not the shape the adapter was written for - a list where
    a dict was expected, a row that is a string, a date that is not a date -
    that raises `AttributeError`, `KeyError`, `TypeError`, `ValueError` or a
    pydantic `ValidationError`. Left alone it escapes as a crash, and worse, the
    HTTP layer has already recorded the request as a *success*, so the vendor
    stays "HEALTHY" while every answer it gives is discarded.

    Here the surprise is translated once: it becomes a `parse_failure`, it is
    recorded against the vendor, and repeated surprises trip the same cooldown
    that repeated timeouts do. Adapters that can skip a single bad row and keep
    the rest still do so themselves - that is a better outcome than failing the
    batch - this is the net for what they did not anticipate.
    """

    @functools.wraps(fn)
    def guarded(self, *args, **kwargs):
        try:
            result = fn(self, *args, **kwargs)
        except VendorError:
            raise
        except Exception as exc:  # noqa: BLE001 - translated, never swallowed
            if getattr(exc, "vendor_passthrough", False):
                # A caller error (an unnamed period) raised on purpose, before
                # any request was made. Not the vendor's fault.
                raise
            raise self._unexpected_reply(fn.__name__, exc) from exc
        self._reply_failures = 0
        return result

    guarded.__vendor_guarded__ = True
    return guarded


class VendorClient:
    """Base adapter. Subclasses set NAME / KEY_ENV / DEFAULT_RPM and use _get_json."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for name, attr in list(cls.__dict__.items()):
            # Public functions defined on a concrete adapter are its
            # operations. Properties, class/static methods and `_private`
            # helpers are not wrapped.
            if name.startswith("_") or not inspect.isfunction(attr):
                continue
            if getattr(attr, "__vendor_guarded__", False):
                continue
            setattr(cls, name, _guard_operation(attr))

    NAME = "vendor"
    KEY_ENV: Optional[str] = None          # None → keyless vendor
    DEFAULT_RPM = 30
    TIMEOUT_SECONDS = 6.0
    #: Bound on a native library call. Separate from TIMEOUT_SECONDS because
    #: these libraries retry internally and legitimately take longer than one
    #: HTTP round trip; the point is that they end, not that they are fast.
    CALL_TIMEOUT_SECONDS = 20.0
    MAX_RETRIES = 2
    BACKOFF_BASE = 0.4
    COOLDOWN_AFTER_FAILURES = 3
    COOLDOWN_SECONDS = 60.0
    #: How long to leave a vendor alone after it rejects our credential. A
    #: rejected key is not a transient fault — retrying it a minute later gets
    #: the same answer — so the short cooldown meant a dead key was re-probed
    #: every 60 seconds indefinitely: wasted quota, noisy logs, and a status
    #: that read as "paused" rather than "your credential is wrong". One probe
    #: per window is enough to notice that the key has been fixed.
    AUTH_COOLDOWN_SECONDS = 900.0
    MAX_RETRY_AFTER_SECONDS = 2.0

    def __init__(self, session: Optional[requests.Session] = None):
        rpm_override = os.getenv(f"PROVIDER_{self.NAME.upper()}_RPM")
        rpm = int(rpm_override) if rpm_override and rpm_override.isdigit() else self.DEFAULT_RPM
        self.rate_limiter = RateLimiter(rpm)
        self.stats = VendorStats()
        self._cooldown_until = 0.0
        #: Consecutive operations whose reply the adapter could not read. The
        #: HTTP layer counts a decoded 200 as a success, which resets
        #: `consecutive_failures`, so a vendor that keeps returning garbage
        #: would never reach the cooldown on that counter alone.
        self._reply_failures = 0
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", "OmniSignal/2.0 (+https://omnisignalterminal.vercel.app)")

    def _note_unreadable(self, operation: str, count: int) -> None:
        """Make skipped rows observable: a log line and a counter, never silence."""
        if count <= 0:
            return
        logger.warning("%s: %s skipped %d unreadable row(s)", self.NAME, operation, count)
        _metrics.registry.increment(
            "vendor.unreadable_rows", count, vendor=self.NAME, operation=operation,
        )

    def _unexpected_reply(self, operation: str, exc: BaseException) -> "VendorError":
        """Record that a reply decoded but was not the shape this adapter reads."""
        self._reply_failures += 1
        detail = f"unexpected response shape in {operation}: {type(exc).__name__}"
        self.stats.record(
            False, 0.0, detail, FailureClass.PARSE.value, operation=operation,
        )
        _observe(self.NAME, operation, "error", 0.0)
        logger.warning("%s: %s (%s)", self.NAME, detail, redact(str(exc))[:160])
        if self._reply_failures >= self.COOLDOWN_AFTER_FAILURES:
            self._cooldown_until = time.monotonic() + self.COOLDOWN_SECONDS
            _metrics.registry.increment("vendor.cooldown", vendor=self.NAME)
        return VendorError(
            f"{self.NAME}: {detail}", transient=False,
            failure_class=FailureClass.PARSE,
        )

    # ── Availability & health ────────────────────────────────────────────────

    @property
    def api_key(self) -> str:
        return os.getenv(self.KEY_ENV, "") if self.KEY_ENV else ""

    @property
    def available(self) -> bool:
        """Key present (or keyless). Read at call time so env changes apply."""
        if self.KEY_ENV is None:
            return True
        return bool(self.api_key and len(self.api_key) > 5)

    @property
    def healthy(self) -> bool:
        """Available and not cooling down after repeated failures."""
        return self.available and time.monotonic() >= self._cooldown_until

    @property
    def credential_rejected(self) -> bool:
        """The vendor's most recent answer refused our credential.

        Stays true until a later request succeeds. A key being present says
        nothing about whether the vendor accepts it; this is the evidence that
        it does not.
        """
        stats = self.stats.snapshot()
        failed_at = stats.get("last_failure_at")
        return bool(
            failed_at
            and (stats.get("last_success_at") or 0) < failed_at
            and stats.get("last_failure_class") == FailureClass.AUTH_FAILURE.value
        )

    @property
    def operational(self) -> bool:
        """Configured and not known to be rejected — what "available" should
        mean to anyone reporting whether this vendor can currently answer."""
        return self.available and not self.credential_rejected

    @property
    def credential_state(self) -> str:
        """not_required | not_configured | unverified | accepted | rejected.

        "unverified" is the honest word for a configured key nothing has used
        yet in this process; it is neither a claim that the key works nor one
        that it does not.
        """
        if self.KEY_ENV is None:
            return "not_required"
        if not self.available:
            return "not_configured"
        if self.credential_rejected:
            return "rejected"
        return "accepted" if self.stats.snapshot().get("last_success_at") else "unverified"

    def health_snapshot(self) -> dict[str, Any]:
        stats = self.stats.snapshot()
        cooldown_remaining = max(0.0, self._cooldown_until - time.monotonic())
        if not self.available:
            health_state = "NOT_CONFIGURED"
        elif getattr(self, "DEV_ONLY", False):
            health_state = "DEV_ONLY"
        elif self.credential_rejected:
            # Checked before the cooldown, which would otherwise describe a
            # wrong credential as a vendor that is merely "paused after
            # repeated failures" — a transient-sounding state for a fault that
            # only the key's owner can fix.
            health_state = "AUTH_FAILURE"
        elif cooldown_remaining > 0:
            health_state = "COOLDOWN"
        elif (
            stats.get("last_failure_at")
            and (stats.get("last_success_at") or 0) < stats["last_failure_at"]
        ):
            health_state = {
                FailureClass.RATE_LIMITED.value: "RATE_LIMITED",
                FailureClass.LOCAL_LIMITER.value: "RATE_LIMITED",
                FailureClass.AUTH_FAILURE.value: "AUTH_FAILURE",
                FailureClass.NOT_ENTITLED.value: "NOT_ENTITLED",
                FailureClass.TIMEOUT.value: "TIMEOUT",
            }.get(stats.get("last_failure_class"), "UNAVAILABLE")
        elif stats.get("failures"):
            health_state = "DEGRADED"
        elif not stats.get("requests"):
            health_state = "IDLE"
        else:
            health_state = "HEALTHY"
        operations = stats.get("operations") or {}
        restricted = sorted(
            op for op, o in operations.items()
            if not o["ok"] and o["failure_class"] == FailureClass.NOT_ENTITLED.value
        )
        # A plan that excludes one endpoint while the others answer is a
        # degraded vendor, not an unentitled one. Every other failure class
        # (credentials, rate limits, timeouts) is about the vendor as a whole
        # and keeps its state.
        if health_state == "NOT_ENTITLED" and any(o["ok"] for o in operations.values()):
            health_state = "DEGRADED"
        return {
            "vendor": self.NAME,
            "configured": self.available,
            "cooling_down": cooldown_remaining > 0,
            "cooldown_remaining_seconds": round(cooldown_remaining, 1),
            "health_state": health_state,
            "credential_state": self.credential_state,
            "restricted_operations": restricted,
            **stats,
        }

    # ── HTTP core ────────────────────────────────────────────────────────────

    def _get_json(self, url: str, params: Optional[dict[str, Any]] = None,
                  headers: Optional[dict[str, str]] = None,
                  operation: str = "http", *,
                  expect: Optional[type | tuple[type, ...]] = None) -> Any:
        return self._request_json("GET", url, params=params, headers=headers,
                                  operation=operation, expect=expect)

    def _post_json(self, url: str, json_body: Any,
                   headers: Optional[dict[str, str]] = None,
                   operation: str = "http", *,
                   expect: Optional[type | tuple[type, ...]] = None) -> Any:
        return self._request_json("POST", url, json_body=json_body, headers=headers,
                                  operation=operation, expect=expect)

    def timed_call(self, fn, operation: str = "call", timeout: Optional[float] = None):
        """
        Wrap a library call (yfinance, fredapi) with the same rate limiting,
        stats, cooldown *and timeout* behavior as HTTP adapters.

        The timeout is the reason this method changed. It gave library calls
        the statistics and cooldown of an HTTP adapter and none of its bound:
        `fn()` ran to completion however long that took, so a yfinance or FRED
        call that hung held a FastAPI worker thread until the process
        restarted. A timeout that is not enforced is not a timeout, and these
        libraries do their own networking where `requests`' timeout cannot
        reach.

        The call runs on a worker and the wait is bounded. A Python thread
        cannot be killed, so a timed-out call may still be running when this
        returns — the resource is not reclaimed, only the request is released.
        That is the honest limit of the approach and it is the right trade:
        one leaked thread costs far less than a permanently stuck worker, and
        the daemon pool means a straggler cannot hold up interpreter exit.
        """
        if not self.rate_limiter.try_acquire():
            self.stats.record_rate_limit(FailureClass.LOCAL_LIMITER)
            _metrics.registry.increment(
                "vendor.rate_limited", vendor=self.NAME, operation=operation
            )
            raise VendorError(
                f"{self.NAME}: local rate limit reached", transient=True,
                failure_class=FailureClass.LOCAL_LIMITER,
            )
        started = time.perf_counter()
        budget = self.CALL_TIMEOUT_SECONDS if timeout is None else timeout
        try:
            value = _CALL_POOL.submit(fn).result(timeout=budget)
        except FuturesTimeout as exc:
            latency = (time.perf_counter() - started) * 1000
            self.stats.record(
                False, latency, f"timeout after {budget}s", FailureClass.TIMEOUT.value,
                operation=operation,
            )
            _observe(self.NAME, operation, "error", latency)
            if self.stats.consecutive_failures >= self.COOLDOWN_AFTER_FAILURES:
                self._cooldown_until = time.monotonic() + self.COOLDOWN_SECONDS
            raise VendorError(
                f"{self.NAME}: {operation} exceeded {budget}s", transient=True,
                failure_class=FailureClass.TIMEOUT,
            ) from exc
        except Exception as exc:  # noqa: BLE001 — normalized to VendorError
            latency = (time.perf_counter() - started) * 1000
            self.stats.record(
                False, latency, str(exc), FailureClass.UNAVAILABLE.value,
                operation=operation,
            )
            _observe(self.NAME, operation, "error", latency)
            if self.stats.consecutive_failures >= self.COOLDOWN_AFTER_FAILURES:
                self._cooldown_until = time.monotonic() + self.COOLDOWN_SECONDS
            raise VendorError(
                f"{self.NAME}: {exc}", transient=True,
                failure_class=FailureClass.UNAVAILABLE,
            ) from exc
        latency = (time.perf_counter() - started) * 1000
        self.stats.record(True, latency, operation=operation)
        _observe(self.NAME, operation, "ok", latency)
        return value

    def _request_json(self, method: str, url: str,
                      params: Optional[dict[str, Any]] = None,
                      json_body: Optional[Any] = None,
                      headers: Optional[dict[str, str]] = None,
                      operation: str = "http", *,
                      expect: Optional[type | tuple[type, ...]] = None) -> Any:
        """
        HTTP with rate limiting, timeout, bounded retries + exponential backoff.
        Raises VendorError on terminal failure; records stats either way.

        A reply is accepted only when it is a JSON object or array, is not the
        vendor's own error envelope, and (when the caller says what it
        expects) has that shape. Anything else is a failure with a reason, not
        an empty result: "the vendor said no" and "the vendor said nothing"
        are different facts and neither is "no data".
        """
        request_started = time.perf_counter()
        last_error: Optional[VendorError] = None
        for attempt in range(self.MAX_RETRIES + 1):
            # A token per *physical* request, not per logical call.
            #
            # This was acquired once, above the loop, so a call that retried
            # twice sent three requests on one token. The limiter therefore
            # undercounted by up to MAX_RETRIES precisely when the vendor was
            # already failing — the moment its quota matters most, and the
            # moment retries make the outbound rate highest. A limiter that is
            # accurate only while everything works is not a limiter.
            if not self.rate_limiter.try_acquire():
                self.stats.record_rate_limit(FailureClass.LOCAL_LIMITER)
                _metrics.registry.increment(
                    "vendor.rate_limited", vendor=self.NAME, operation=operation
                )
                limited = VendorError(
                    f"{self.NAME}: local rate limit reached", transient=True,
                    failure_class=FailureClass.LOCAL_LIMITER,
                )
                if attempt == 0:
                    # Nothing was sent, so there is no partial work to report.
                    raise limited
                # Mid-retry: stop here rather than sending an unmetered
                # request, and report the last real failure to the caller.
                last_error = last_error or limited
                break

            started = time.perf_counter()
            try:
                response = self._session.request(
                    method, url, params=params, json=json_body,
                    headers=headers, timeout=self.TIMEOUT_SECONDS,
                )
                latency = (time.perf_counter() - started) * 1000
                status = response.status_code
                if status == 401:
                    raise VendorError(
                        "HTTP 401", failure_class=FailureClass.AUTH_FAILURE,
                        status_code=status,
                    )
                if status in (402, 403):
                    # 402 is how FMP refuses a symbol outside the plan
                    # ("Premium Query Parameter") while serving others: a plan
                    # boundary, the same kind of answer as a 403.
                    raise VendorError(
                        f"HTTP {status}", failure_class=FailureClass.NOT_ENTITLED,
                        status_code=status,
                    )
                if status == 429:
                    retry_after = self._parse_retry_after(
                        getattr(response, "headers", {}).get("Retry-After")
                    )
                    raise VendorError(
                        "HTTP 429", transient=True,
                        failure_class=FailureClass.RATE_LIMITED,
                        status_code=status, retry_after_seconds=retry_after,
                    )
                if status in TRANSIENT_STATUS:
                    raise VendorError(
                        f"HTTP {status}", transient=True,
                        failure_class=FailureClass.UPSTREAM, status_code=status,
                    )
                if status >= 400 and self._is_empty_answer(response):
                    # The vendor answered the question: nothing matches. A
                    # failure here would push a healthy vendor into cooldown
                    # for every company it has nothing on.
                    self.stats.record(True, latency, operation=operation)
                    _observe(self.NAME, operation, "ok",
                             (time.perf_counter() - request_started) * 1000)
                    return None
                if status >= 400:
                    raise VendorError(
                        f"HTTP {status}", transient=False,
                        failure_class=FailureClass.UNAVAILABLE, status_code=status,
                    )
                response.raise_for_status()
                payload = response.json()
                if _may_hold_non_finite(response):
                    payload = scrub_non_finite(payload)
                if not isinstance(payload, (dict, list)):
                    # `null`, a bare string, a number, a boolean. No endpoint
                    # here answers with one; it is a proxy page, a maintenance
                    # string or a truncated reply, never "no results".
                    raise VendorError(
                        f"unexpected response ({type(payload).__name__}, not an object or array)",
                        transient=False, failure_class=FailureClass.PARSE,
                    )
                self._validate_payload(payload)
                if expect is not None and not isinstance(payload, expect):
                    raise VendorError(
                        f"unexpected response shape ({type(payload).__name__})",
                        transient=False, failure_class=FailureClass.PARSE,
                    )
                self.stats.record(True, latency, operation=operation)
                # Total elapsed, not this attempt's: retries and backoff are
                # time the caller genuinely waited, and hiding them is how a
                # vendor that "averages 800ms" costs 18s in practice.
                _observe(self.NAME, operation, "ok",
                         (time.perf_counter() - request_started) * 1000)
                return payload
            except VendorError as exc:
                latency = (time.perf_counter() - started) * 1000
                last_error = exc
            except requests.Timeout:
                latency = (time.perf_counter() - started) * 1000
                last_error = VendorError(
                    "timeout", transient=True, failure_class=FailureClass.TIMEOUT,
                )
            except requests.RequestException as exc:
                latency = (time.perf_counter() - started) * 1000
                # `requests` puts the full request URL in the message, which
                # for query-string-authenticated vendors contains the key.
                last_error = VendorError(
                    redact(str(exc)), transient=True,
                    failure_class=FailureClass.UPSTREAM,
                )
            except ValueError as exc:  # JSON decode
                latency = (time.perf_counter() - started) * 1000
                last_error = VendorError(
                    redact(f"invalid JSON: {exc}"), transient=False,
                    failure_class=FailureClass.PARSE,
                )

            if last_error.failure_class == FailureClass.RATE_LIMITED.value:
                self.stats.record_rate_limit(FailureClass.RATE_LIMITED)
            self.stats.record(
                False, latency, str(last_error), last_error.failure_class,
                operation=operation,
                request_specific=last_error.status_code in (404, 422),
            )
            if last_error.transient and attempt < self.MAX_RETRIES:
                delay = self.BACKOFF_BASE * (2 ** attempt)
                if last_error.retry_after_seconds is not None:
                    if last_error.retry_after_seconds > self.MAX_RETRY_AFTER_SECONDS:
                        self._cooldown_until = time.monotonic() + min(
                            last_error.retry_after_seconds, self.COOLDOWN_SECONDS,
                        )
                        break
                    delay = max(delay, last_error.retry_after_seconds)
                time.sleep(delay)
                continue
            break

        _observe(self.NAME, operation, "error",
                 (time.perf_counter() - request_started) * 1000)
        assert last_error is not None
        if last_error.failure_class == FailureClass.AUTH_FAILURE.value:
            # One rejection is enough: nothing a retry changes can make a wrong
            # credential right. Logged once per window, not once per call.
            if time.monotonic() >= self._cooldown_until:
                logger.error("%s rejected the credential (HTTP %s); not retrying for %.0fs",
                             self.NAME, last_error.status_code, self.AUTH_COOLDOWN_SECONDS)
                _metrics.registry.increment("vendor.credential_rejected", vendor=self.NAME)
            self._cooldown_until = time.monotonic() + self.AUTH_COOLDOWN_SECONDS
        elif (
            last_error.failure_class == FailureClass.RATE_LIMITED.value
            and not last_error.transient
        ):
            # The vendor said, in a 200 body, that its quota is spent. Nothing
            # about an immediate retry changes that, and the next request would
            # spend what is left of the window finding it out again.
            self._cooldown_until = time.monotonic() + self.COOLDOWN_SECONDS
            _metrics.registry.increment("vendor.cooldown", vendor=self.NAME)
        elif self.stats.consecutive_failures >= self.COOLDOWN_AFTER_FAILURES:
            self._cooldown_until = time.monotonic() + self.COOLDOWN_SECONDS
            logger.warning("%s cooling down for %.0fs after %d consecutive failures",
                           self.NAME, self.COOLDOWN_SECONDS, self.stats.consecutive_failures)
            _metrics.registry.increment("vendor.cooldown", vendor=self.NAME)
        raise last_error

    def _validate_payload(self, payload: Any) -> None:
        """Reject the vendor's own error envelope, delivered with HTTP 200.

        Overridden by adapters whose API has a specific envelope (BLS, BEA).
        The default recognises the common shapes - an explicit error status,
        `Error Message`, `Note`, a top-level `error` - and classifies them by
        what they say, so a bad key reads as `auth_failure` and an exhausted
        quota as `rate_limited` rather than both reading as "no data".
        """
        found = api_error_in(payload)
        if found is None:
            return
        code, text = found
        failure_class = classify_api_error(code, text)
        status = int(code) if isinstance(code, (int, float)) and not isinstance(code, bool) else None
        status = status if status and 400 <= status < 600 else None
        if failure_class is FailureClass.UNAVAILABLE and (
            status in (400, 404, 422) or _NOTHING_HERE.search(text or "")
        ):
            # "Symbol not found" is the vendor answering this request, not the
            # vendor being down. Recording it as a 404 keeps it out of the
            # consecutive-failure count, exactly as a real 404 is kept out.
            status = 404
        raise VendorError(
            redact(f"{self.NAME} API error: {text}")[:240],
            transient=False,
            failure_class=failure_class,
            status_code=status,
        )

    def _is_empty_answer(self, response: Any) -> bool:
        """Whether an error status is the vendor's way of saying "no matches".

        False by default: only an adapter that can recognise the vendor's own
        no-match body may treat a 4xx as an answer rather than a failure.
        """
        return False

    @staticmethod
    def _parse_retry_after(value: Optional[str]) -> Optional[float]:
        """Parse either Retry-After form without trusting an unbounded delay."""
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            try:
                moment = parsedate_to_datetime(value)
                return max(0.0, moment.timestamp() - time.time())
            except (TypeError, ValueError, OverflowError):
                return None
