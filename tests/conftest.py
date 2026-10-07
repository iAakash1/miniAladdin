"""
Shared test fixtures for OmniSignal test suite.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.models import (
    AggregateSentiment,
    MacroIndicators,
    MacroStatus,
    RiskAssessment,
    SentimentLabel,
    SentimentResult,
    SignalVerdict,
    TechnicalAnalysis,
)


# ── Macro Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def normal_indicators() -> MacroIndicators:
    """Macro indicators with normal (stable) conditions."""
    return MacroIndicators(
        yield_spread=1.5,
        inflation_rate=2.5,
        fed_funds_rate=3.0,
    )


@pytest.fixture
def inverted_yield_indicators() -> MacroIndicators:
    """Macro indicators with inverted yield curve."""
    return MacroIndicators(
        yield_spread=-0.5,
        inflation_rate=2.5,
        fed_funds_rate=3.0,
    )


@pytest.fixture
def high_inflation_indicators() -> MacroIndicators:
    """Macro indicators with high inflation (> 4%)."""
    return MacroIndicators(
        yield_spread=1.0,
        inflation_rate=5.5,
        fed_funds_rate=3.0,
    )


@pytest.fixture
def crisis_indicators() -> MacroIndicators:
    """Macro indicators with inverted yield + high inflation + high rates."""
    return MacroIndicators(
        yield_spread=-0.8,
        inflation_rate=6.0,
        fed_funds_rate=5.5,
    )


@pytest.fixture
def stable_risk() -> RiskAssessment:
    """A stable risk assessment with multiplier 1.0."""
    return RiskAssessment(
        risk_multiplier=1.0,
        yield_curve_inverted=False,
        status=MacroStatus.STABLE,
    )


@pytest.fixture
def critical_risk() -> RiskAssessment:
    """A critical risk assessment with high multiplier."""
    return RiskAssessment(
        risk_multiplier=1.5,
        yield_curve_inverted=True,
        status=MacroStatus.CRITICAL,
        recession_warning=True,
    )


# ── Sentiment Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def bullish_headlines() -> list[dict]:
    """Headlines with bullish sentiment."""
    return [
        {"title": "NVDA surges to record high on AI boom", "source": "Yahoo Finance"},
        {"title": "Strong earnings beat expectations, stock rallies", "source": "Reuters"},
        {"title": "Analyst upgrades to Strong Buy with growth momentum", "source": "Bloomberg"},
    ]


@pytest.fixture
def bearish_headlines() -> list[dict]:
    """Headlines with bearish sentiment."""
    return [
        {"title": "Stock crashes on fraud investigation", "source": "Yahoo Finance"},
        {"title": "Regulatory concerns and lawsuit risks decline shares", "source": "Reuters"},
        {"title": "Weak earnings miss, warns of layoffs", "source": "Bloomberg"},
    ]


@pytest.fixture
def neutral_headlines() -> list[dict]:
    """Headlines with neutral sentiment."""
    return [
        {"title": "Company announces new product line", "source": "Yahoo Finance"},
        {"title": "CEO speaks at industry conference", "source": "Reuters"},
    ]


# ── Price Data Fixture ───────────────────────────────────────────────────────

@pytest.fixture
def mock_price_data() -> pd.DataFrame:
    """Mock price data for technical analysis (60 days)."""
    dates = pd.date_range(end=datetime.now(), periods=60, freq="B")
    base_price = 100.0
    closes = [base_price + i * 0.5 + (i % 5 - 2) for i in range(60)]
    volumes = [1000000 + i * 10000 for i in range(60)]
    return pd.DataFrame(
        {
            "Open": [c - 0.5 for c in closes],
            "High": [c + 1.0 for c in closes],
            "Low": [c - 1.0 for c in closes],
            "Close": closes,
            "Volume": volumes,
        },
        index=dates,
    )


# ── test isolation ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_threaded_prefetch(request, monkeypatch):
    """Stop the research handler's prefetch from fanning out in background threads.

    `research_prefetch.warm` runs its warmers through `map_concurrent`, which
    abandons a worker when the future times out. Python cannot kill a thread,
    so the outbound call still happens — just later, and later can be inside a
    *different* test's `patch` window.

    That is not hypothetical: it is how a broker test asserting that no
    request was made saw seven calls to sec.gov.

    (The separate `test_result_is_cached` failure looked like this one but was
    not — instrumenting the patch window named a `factor-lab-mega30` thread,
    not a prefetch worker. That one is handled by the panel-build guard
    below. Both are the same class of defect and neither fix substitutes for
    the other.)

    Applied suite-wide because the leak is a property of the suite rather than
    of any one file, and no test's assertions depend on a warm cache: a cold
    cache is slower, never different. `test_research_prefetch.py` is exempt —
    it is the module that tests this function.
    """
    if request.node.module.__name__.endswith("test_research_prefetch"):
        yield
        return

    from src.services import research_prefetch

    monkeypatch.setattr(research_prefetch, "warm", lambda ticker: {})
    yield


@pytest.fixture(autouse=True)
def _no_background_panel_build(request, monkeypatch):
    """Stop factor-lab build workers from doing real work during tests.

    `/api/factors` starts a panel build on a daemon thread and returns
    immediately — deliberately, and there is a test for exactly that. The
    thread then keeps loading prices long after the test that started it has
    finished, and calls `providers.market_data.get_series` from inside
    whichever `patch` a later test has installed. That is the second half of
    the `test_result_is_cached` failure: the extra two calls were this builder
    fetching its benchmark and its first symbol.

    The job registry, the payload and the endpoint's non-blocking behaviour
    are untouched; only the body of the worker is stubbed, so a test asserting
    "returns promptly with status building" still asserts it. The factor-lab
    modules that test the job machinery itself are exempt.
    """
    module = request.node.module.__name__
    if module.endswith("test_factor_lab_termination") or module.endswith("test_factor_lab"):
        yield
        return

    from src.services import factor_lab_service

    monkeypatch.setattr(factor_lab_service, "_run_job", lambda *a, **k: None)
    yield
    # Any worker that did start is joined before the next test installs its
    # own patches. `_run_job` is stubbed to a no-op above, so a worker that
    # still hasn't joined within the timeout is not "a slow build" — it is a
    # daemon thread stuck on something the stub does not do, which is worth
    # failing loudly here rather than letting it surface three tests later as
    # an unrelated assertion about vendor call counts.
    leaked = factor_lab_service.reset_for_tests(timeout=5.0)
    assert leaked == 0, (
        f"{leaked} factor-lab worker(s) did not join before the next test; "
        "see reset_for_tests"
    )


# ── no live network ──────────────────────────────────────────────────────────

import ipaddress
import os
import re
import socket
import threading

#: Names that never leave the machine. "testserver" is Starlette's in-process
#: TestClient host; it is never resolved.
_LOCAL_NAMES = frozenset({"", "localhost", "127.0.0.1", "::1", "0.0.0.0", "testserver"})

#: Proxy variables the sandbox and many dev machines set. A connection to the
#: local proxy looks like loopback, so a request to any external host would
#: pass a check on the address alone and still reach the internet.
_PROXY_ENV = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
)

#: Environment variables that carry credentials or select a real backend.
#: `load_dotenv()` runs at import time in several modules, so on a developer
#: machine the suite starts with live provider keys, the Supabase service-role
#: key and the broker's credentials already in `os.environ`. Four role-lookup
#: tests were found resolving the production Supabase host for that reason.
_SECRET_ENV = re.compile(
    r"(_API_KEY|_KEY|_SECRET|_TOKEN|_PASSWORD)$"
    r"|^(SUPABASE|CLERK|APCA|ALPACA|PAPER_TRADING|METRICS_RESET|ADMIN_CLERK)_"
)

_attempts: dict[str, list[str]] = {}
_attempts_lock = threading.Lock()


def _is_local(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if not isinstance(host, str):
        return True
    if host in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LiveNetworkAttempt(OSError):
    """A test tried to reach a host outside this machine."""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_network: the test deliberately reaches a real external service",
    )


@pytest.fixture(autouse=True)
def _credential_free_environment(request, monkeypatch):
    """Start every test without credentials, as CI does.

    A test that wants a key sets it (`monkeypatch.setenv`) and so states the
    dependency; one that wants none no longer inherits whatever the developer's
    `.env` happened to hold. This is the half of hermeticity the network guard
    cannot give: with the keys present a test is *configured* to call the real
    service, and only the guard stands between it and the request.
    """
    if request.node.get_closest_marker("live_network"):
        yield
        return
    for name in list(os.environ):
        if _SECRET_ENV.search(name):
            monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture(autouse=True)
def _no_live_network(request, monkeypatch):
    """Make a test unable to depend on a service it does not control.

    A test that reaches a vendor measures the vendor's availability, not this
    code's correctness. It passes while the vendor answers and fails when the
    vendor is slow, rate-limited or in cooldown — which is how a panel
    reproducibility test came to fail once in two full runs with no change to
    the code under test. Vendor clients make this worse by design: they catch
    their own failures, so the test usually *passes* on a network error and
    the dependency stays invisible. Two earlier fixtures here (prefetch,
    background panel build) closed individual leaks of this kind; this closes
    the class.

    Two layers:
      * the attempt is refused, so the code under test sees an ordinary
        connection failure, the same thing it sees offline;
      * the attempt is recorded, and the test is failed afterwards even if the
        code swallowed the error, so a hidden dependency cannot stay hidden.

    A test that genuinely needs a real service is marked `live_network`.
    OMNI_NETWORK_GUARD=record reports attempts without failing, for taking an
    inventory of an unfamiliar suite.
    """
    if request.node.get_closest_marker("live_network"):
        yield
        return

    node = request.node.nodeid
    for name in _PROXY_ENV:
        monkeypatch.delenv(name, raising=False)

    def note(kind: str, target: object) -> None:
        with _attempts_lock:
            _attempts.setdefault(node, []).append(f"{kind} {target!r}")

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if getattr(self, "family", None) == getattr(socket, "AF_UNIX", None) or _is_local(host):
            return real_connect(self, address)
        note("connect", address)
        raise LiveNetworkAttempt(f"live network blocked in tests: connect {address!r}")

    def guarded_connect_ex(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if getattr(self, "family", None) == getattr(socket, "AF_UNIX", None) or _is_local(host):
            return real_connect_ex(self, address)
        note("connect_ex", address)
        raise LiveNetworkAttempt(f"live network blocked in tests: connect {address!r}")

    def guarded_getaddrinfo(host, *args, **kwargs):
        if _is_local(host):
            return real_getaddrinfo(host, *args, **kwargs)
        note("resolve", host)
        raise socket.gaierror(socket.EAI_NONAME, f"live network blocked in tests: resolve {host!r}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)

    yield

    seen = _attempts.get(node)
    if seen and os.getenv("OMNI_NETWORK_GUARD", "strict") == "strict":
        pytest.fail(
            "test reached the live network (mark it `live_network` if that is the point, "
            "otherwise inject the dependency): " + "; ".join(list(dict.fromkeys(seen))[:5]),
            pytrace=False,
        )


def pytest_sessionfinish(session, exitstatus):
    """Print every test that attempted a live connection, however it ended."""
    if not _attempts:
        return
    path = os.getenv("OMNI_NETWORK_REPORT")
    lines = [f"{node}\t{'; '.join(dict.fromkeys(seen))}" for node, seen in sorted(_attempts.items())]
    if path:
        with open(path, "w") as handle:
            handle.write("\n".join(lines) + "\n")


# ── offline stand-ins for tests that drive whole routes ──────────────────────

@pytest.fixture
def offline_network(monkeypatch):
    """Every outbound HTTP call and vendor library call fails like a dead network.

    For a test that drives a whole route (`/api/research/..`, `/api/dashboard`)
    and pins one behaviour of it. The route fans out to many vendors; the test
    patches the few it cares about, and the rest used to reach the real
    service and fail quietly. This makes that failure explicit and immediate:
    the call raises an ordinary connection error before any lookup happens, so
    the code under test takes the same degraded path it takes offline and the
    network guard has nothing to report. A test that needs a particular
    answer from a vendor patches that vendor, which states the dependency.
    """
    import requests

    from src.providers.base import FailureClass, VendorClient, VendorError

    def refuse_http(self, request, *args, **kwargs):
        raise requests.exceptions.ConnectionError(f"offline in tests: {getattr(request, 'url', '')}")

    def refuse_call(self, fn, operation="call", timeout=None):
        raise VendorError(
            f"{self.NAME}: offline in tests", transient=True, failure_class=FailureClass.UNAVAILABLE,
        )

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", refuse_http)
    monkeypatch.setattr(VendorClient, "timed_call", refuse_call)
    yield


@pytest.fixture
def synthetic_series():
    """A factory for a deterministic daily price series, as a provider answer.

    Business days, a slow trend plus a repeating wobble, so indicators that
    need real movement (RSI, a 50-day average) have it and nothing is random.
    """
    from src.providers.schemas import OHLCVBar, PriceSeries, ProviderResult

    def make(symbol: str = "TEST", sessions: int = 260, start: float = 100.0, drift: float = 0.12):
        dates = pd.bdate_range("2025-01-01", periods=sessions).strftime("%Y-%m-%d")
        closes = [start + i * drift + (i % 7) * 0.9 for i in range(sessions)]
        bars = [
            OHLCVBar(date=d, open=c, high=c * 1.004, low=c * 0.996, close=c, volume=1_000_000 + i)
            for i, (d, c) in enumerate(zip(dates, closes))
        ]
        return ProviderResult(data=PriceSeries(symbol=symbol, bars=bars), source="fixture", confidence=0.85)

    return make
