"""Provider failure-injection matrix: every HTTP adapter x every way to fail.

The rule under test is the one the product is built on: **a failure must never
become a legitimate-looking success.**  A vendor that times out, is refused, is
rate-limited, answers with garbage or answers with its own error envelope must
surface as a typed `VendorError` (or, where the vendor genuinely said "nothing
here", as `None` / an empty container).  It must not surface as a populated
object, a zero, an empty list standing in for a result, or a healthy vendor.

Four invariants are asserted for every (operation, failure) pair:

  1. **Typed.**  Only `VendorError` escapes.  An `AttributeError`, `KeyError`
     or pydantic `ValidationError` leaking out of an adapter means the adapter
     did not recognise the response and the chain only survives by accident.
  2. **Classified.**  The failure carries the class an operator needs: 401 is
     `auth_failure` (the key is wrong - fix the key), 403 is `not_entitled`
     (the plan excludes it), 429 is `rate_limited`, a timeout is `timeout`,
     5xx is `upstream_failure`, undecodable output is `parse_failure`.
  3. **Recorded.**  The vendor's own health shows the failure.  A malformed
     body that counts as a *success* leaves the vendor "HEALTHY" while it
     returns garbage.
  4. **Silent about the key.**  No error string, stat or snapshot contains the
     credential, whatever the transport put in its message.

The matrix is deliberately data-driven: adding an adapter operation to
`HTTP_OPS` buys it all of the above.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import requests

from provider_faults import (
    ERROR_ENVELOPE,
    EMPTY_ANSWER,
    SECRET_KEY,
    TRANSPORT,
    UNPARSEABLE,
    WRONG_SHAPE,
    ScriptedSession,
    contains_non_finite,
    is_empty_value,
)
from src.providers.base import FailureClass, VendorError
from src.providers.vendors.macro_vendors import (
    BeaVendor,
    BlsVendor,
    EcbVendor,
    EiaVendor,
    TreasuryFiscalVendor,
    WorldBankVendor,
)
from src.providers.vendors.market_vendors import (
    FinnhubVendor,
    FMPVendor,
    MarketStackVendor,
    PolygonVendor,
    TwelveDataVendor,
)
from src.providers.vendors.massive_vendor import MassiveVendor
from src.providers.vendors.news_vendors import GNewsVendor, MarketauxVendor, NewsApiVendor
from src.providers.vendors.apify_vendor import ApifyVendor
from src.providers.vendors.openfigi_vendor import OpenFigiVendor
from src.providers.vendors.record_vendors import ClinicalTrialsVendor, FederalRegisterVendor, OpenFdaVendor
from src.providers.vendors.search_vendors import ExaVendor, TavilyVendor
from src.providers.vendors.sec_vendor import SECVendor
from src.providers.vendors.tiingo_vendor import TiingoVendor
from src.providers.vendors.visual_vendors import LogoDevVendor
from src.providers.vendors.wikidata_vendor import WikidataVendor
from src.services.research.providers import _BraveVendor


# (vendor class, method, positional args).  One row per distinct network path.
HTTP_OPS: list[tuple[type, str, tuple]] = [
    (PolygonVendor, "get_price", ("AAPL",)),
    (PolygonVendor, "get_company", ("AAPL",)),
    (PolygonVendor, "get_series", ("AAPL", "1mo")),
    (MassiveVendor, "get_price", ("AAPL",)),
    (MassiveVendor, "get_company", ("AAPL",)),
    (MassiveVendor, "get_series", ("AAPL", "1mo")),
    (MassiveVendor, "get_option_chain", ("AAPL",)),
    (FinnhubVendor, "get_price", ("AAPL",)),
    (FinnhubVendor, "get_company", ("AAPL",)),
    (FinnhubVendor, "search_symbols", ("apple",)),
    (FinnhubVendor, "get_fundamentals", ("AAPL",)),
    (FinnhubVendor, "get_analyst_targets", ("AAPL",)),
    (FinnhubVendor, "get_street", ("AAPL",)),
    (TwelveDataVendor, "get_price", ("AAPL",)),
    (TwelveDataVendor, "get_series", ("AAPL", "1mo")),
    (FMPVendor, "get_price", ("AAPL",)),
    (FMPVendor, "get_series", ("AAPL", "1mo")),
    (FMPVendor, "search_symbols", ("apple",)),
    (FMPVendor, "get_company", ("AAPL",)),
    (FMPVendor, "get_fundamentals", ("AAPL",)),
    (MarketStackVendor, "get_series", ("AAPL", "1mo")),
    (MarketStackVendor, "get_price", ("AAPL",)),
    (TiingoVendor, "get_quote", ("AAPL",)),
    (TiingoVendor, "get_series", ("AAPL", "1mo")),
    (TiingoVendor, "get_company", ("AAPL",)),
    (TiingoVendor, "get_news", ("AAPL", 5)),
    (TiingoVendor, "get_fundamentals", ("AAPL",)),
    (NewsApiVendor, "get_news", ("AAPL", "Apple", 5)),
    (GNewsVendor, "get_news", ("AAPL", "Apple", 5)),
    (MarketauxVendor, "get_news", ("AAPL", "Apple", 5)),
    (TavilyVendor, "get_news", ("AAPL", "Apple", 5)),
    (TavilyVendor, "search", ("apple earnings", 5)),
    (ExaVendor, "search", ("apple earnings", 5)),
    (BlsVendor, "get_official_series", ("UNRATE", 8)),
    (BeaVendor, "get_official_series", ("A191RL1Q225SBEA", 8)),
    (EiaVendor, "get_energy_series", ("EIA_WTI_M", 8)),
    (TreasuryFiscalVendor, "get_context_series", ("TSY_AVG_RATE", 8)),
    (EcbVendor, "get_context_series", ("ECB_DFR", 8)),
    (WorldBankVendor, "get_context_series", ("WB_GDP_WORLD", 8)),
    (SECVendor, "get_filings", ("AAPL", 5)),
    (SECVendor, "get_xbrl_facts", ("AAPL",)),
    (SECVendor, "get_xbrl_timeline", ("AAPL",)),
    (SECVendor, "get_entity", ("AAPL",)),
    (FederalRegisterVendor, "get_official_actions", (["Apple"], 5)),
    (OpenFdaVendor, "get_recalls", ("Apple", "drug", 5)),
    (ClinicalTrialsVendor, "get_trials", ("Apple", 5)),
    (OpenFigiVendor, "get_instrument_identity", ("AAPL",)),
    (LogoDevVendor, "search_brand", ("apple",)),
    (WikidataVendor, "find_company", ("AAPL", "Apple")),
    (WikidataVendor, "get_knowledge", ("AAPL", "Apple")),
    (WikidataVendor, "expand_entity", ("Q312", "Apple", "company", "company:AAPL")),
    (ApifyVendor, "research_company", ("AAPL", "Apple")),
    (ApifyVendor, "search", ("apple earnings", 5)),
    (_BraveVendor, "web_search", ("apple earnings", 5)),
    (_BraveVendor, "news_search", ("apple earnings", 5)),
]

#: (vendor, method) pairs documented to turn a permission answer into "no data"
#: rather than a failure, so a plan boundary does not cool the whole vendor.
ENTITLEMENT_IS_NONE = {("TiingoVendor", "get_fundamentals")}

#: Operations that make several independent requests for one logical call.
REQUESTS_PER_CALL = {("FinnhubVendor", "get_street"): 3}

EXPECTED_CLASS = {
    "timeout": {FailureClass.TIMEOUT},
    "connection_error": {FailureClass.UPSTREAM},
    "http_401": {FailureClass.AUTH_FAILURE},
    "http_403": {FailureClass.NOT_ENTITLED},
    "http_404": {FailureClass.UNAVAILABLE},
    "http_418": {FailureClass.UNAVAILABLE},
    "http_429": {FailureClass.RATE_LIMITED},
    "http_429_long_retry_after": {FailureClass.RATE_LIMITED},
    "http_500": {FailureClass.UPSTREAM},
    "http_502": {FailureClass.UPSTREAM},
    "http_503": {FailureClass.UPSTREAM},
    "http_504": {FailureClass.UPSTREAM},
}


def _id(op: tuple[type, str, tuple]) -> str:
    return f"{op[0].NAME}.{op[1]}"


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    """No real sleeping on backoff, and rate limits out of the way."""
    monkeypatch.setattr("src.providers.base.time.sleep", lambda _s: None)
    for cls in {op[0] for op in HTTP_OPS}:
        monkeypatch.setenv(f"PROVIDER_{cls.NAME.upper()}_RPM", "100000")


def _call(op, outcome, monkeypatch):
    cls, method, args = op
    if cls.KEY_ENV:
        monkeypatch.setenv(cls.KEY_ENV, SECRET_KEY)
    monkeypatch.setenv("LOGO_DEV_SECRET_KEY", SECRET_KEY)   # server-side logo lookup
    session = ScriptedSession(lambda *_a, **_k: outcome())
    vendor = cls(session=session)
    try:
        value = getattr(vendor, method)(*args)
        return vendor, session, value, None
    except BaseException as exc:  # noqa: BLE001 - the point is to see what escapes
        return vendor, session, None, exc


def _assert_no_secret(vendor, exc) -> None:
    haystack = [json.dumps(vendor.health_snapshot(), default=str)]
    if exc is not None:
        haystack.append(str(exc))
        haystack.append(repr(exc))
    for text in haystack:
        assert SECRET_KEY not in text, f"credential leaked: {text[:200]}"


# ── 1. a failed connection or refused request ────────────────────────────────

@pytest.mark.parametrize("scenario", sorted(TRANSPORT))
@pytest.mark.parametrize("op", HTTP_OPS, ids=_id)
def test_a_transport_failure_is_a_typed_classified_recorded_failure(op, scenario, monkeypatch):
    vendor, session, value, exc = _call(op, TRANSPORT[scenario], monkeypatch)
    cls, method, _args = op

    if (cls.__name__, method) in ENTITLEMENT_IS_NONE and scenario in {"http_403", "http_404"}:
        assert exc is None and value is None
        return

    assert exc is not None, (
        f"{_id(op)} answered {scenario} with {value!r} - a failure became a result"
    )
    assert isinstance(exc, VendorError), (
        f"{_id(op)} leaked {type(exc).__name__}: {exc} on {scenario}; only VendorError may escape"
    )
    assert FailureClass(exc.failure_class) in EXPECTED_CLASS[scenario], (
        f"{_id(op)} reported {exc.failure_class!r} for {scenario}"
    )
    stats = vendor.stats.snapshot()
    assert stats["failures"] >= 1, f"{_id(op)} did not record the {scenario}"
    assert vendor.health_snapshot()["health_state"] != "HEALTHY"
    # Bounded: one logical call may retry, but never without limit.
    requests_made = REQUESTS_PER_CALL.get((cls.__name__, method), 1)
    assert len(session.calls) <= requests_made * (vendor.MAX_RETRIES + 1), (
        f"{_id(op)} sent {len(session.calls)} requests for one failing call"
    )
    _assert_no_secret(vendor, exc)


# ── 2. HTTP 200 whose body cannot be decoded ─────────────────────────────────

@pytest.mark.parametrize("scenario", sorted(UNPARSEABLE))
@pytest.mark.parametrize("op", HTTP_OPS, ids=_id)
def test_an_undecodable_body_is_a_parse_failure(op, scenario, monkeypatch):
    vendor, _session, value, exc = _call(op, UNPARSEABLE[scenario], monkeypatch)
    assert isinstance(exc, VendorError), f"{_id(op)} -> {value!r} / {exc!r}"
    assert exc.failure_class == FailureClass.PARSE.value
    assert vendor.stats.snapshot()["failures"] >= 1
    assert vendor.health_snapshot()["health_state"] != "HEALTHY"
    _assert_no_secret(vendor, exc)


# ── 3. HTTP 200 whose body parses into the wrong kind of thing ───────────────

@pytest.mark.parametrize("scenario", sorted(WRONG_SHAPE))
@pytest.mark.parametrize("op", HTTP_OPS, ids=_id)
def test_a_body_of_the_wrong_shape_is_a_parse_failure_not_a_crash_or_an_empty_result(
    op, scenario, monkeypatch,
):
    vendor, _session, value, exc = _call(op, WRONG_SHAPE[scenario], monkeypatch)
    assert isinstance(exc, VendorError), (
        f"{_id(op)} given a {scenario} returned {value!r} / raised {type(exc).__name__ if exc else None}: "
        f"it must raise a PARSE VendorError"
    )
    assert exc.failure_class == FailureClass.PARSE.value
    assert vendor.stats.snapshot()["failures"] >= 1
    assert vendor.health_snapshot()["health_state"] != "HEALTHY"
    _assert_no_secret(vendor, exc)


# ── 4. a legitimate "nothing here" must not be dressed up as data ────────────

@pytest.mark.parametrize("scenario", sorted(EMPTY_ANSWER))
@pytest.mark.parametrize("op", HTTP_OPS, ids=_id)
def test_an_empty_answer_is_none_or_empty_never_a_populated_object(op, scenario, monkeypatch):
    vendor, _session, value, exc = _call(op, EMPTY_ANSWER[scenario], monkeypatch)
    # An empty `[]` can be a *wrong shape* for a dict-expecting endpoint (and
    # the reverse), so a typed failure is as acceptable as an honest empty.
    if exc is not None:
        assert isinstance(exc, VendorError), f"{_id(op)} leaked {type(exc).__name__}: {exc}"
        return
    assert is_empty_value(value), (
        f"{_id(op)} built {value!r} out of {scenario}"
    )


# ── 5. the vendor's own error envelope, delivered with HTTP 200 ──────────────

@pytest.mark.parametrize("scenario", sorted(ERROR_ENVELOPE))
@pytest.mark.parametrize("op", HTTP_OPS, ids=_id)
def test_an_error_envelope_with_http_200_is_a_failure_not_no_data(op, scenario, monkeypatch):
    vendor, _session, value, exc = _call(op, ERROR_ENVELOPE[scenario], monkeypatch)
    assert isinstance(exc, VendorError), (
        f"{_id(op)} treated the {scenario} envelope as {value!r}; the vendor said it could not answer"
    )
    expected = {
        "status_error_rate_limit": FailureClass.RATE_LIMITED,
        "status_error_bad_key": FailureClass.AUTH_FAILURE,
        "error_message_key": FailureClass.AUTH_FAILURE,
        "note_key": FailureClass.RATE_LIMITED,
        "polygon_error": FailureClass.AUTH_FAILURE,
    }[scenario]
    assert exc.failure_class == expected.value, (
        f"{_id(op)}: {scenario} classified as {exc.failure_class!r}, expected {expected.value!r}"
    )
    assert vendor.stats.snapshot()["failures"] >= 1
    assert vendor.health_snapshot()["health_state"] != "HEALTHY"
    _assert_no_secret(vendor, exc)
