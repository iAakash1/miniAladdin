"""
Unit tests for src/services/screen_service.py — the natural-language
screening logic behind GET /api/screen.

The central case here is the regression test for a real production bug:
typing "NVDA" returned "Nothing Found" even though NVDA already sat in the
user's portfolio. Root cause was two-fold — (1) the resolver chain had no
keyless fallback, so a Finnhub/FMP outage meant total failure for a
completely ordinary ticker, and (2) the lookup<->thematic retry only ever
fired in one direction, so a symbol-shaped miss was never retried as a
thematic query. Both are fixed here and covered below. No network: every
vendor is a lightweight fake substituted onto the shared `providers`
singletons that screen_service imports.
"""

from __future__ import annotations

from typing import Optional

import pytest

from src.providers.schemas import ProviderResult, SearchResult
from src.services import screen_service
from src.services.screen_service import screen


class _FakeVendor:
    """Duck-types just enough of VendorClient for screen_service: .NAME,
    .healthy, .search_symbols(query, limit)."""

    def __init__(self, name: str, healthy: bool = True,
                 rows: Optional[list[dict]] = None, raises: bool = False):
        self.NAME = name
        self.healthy = healthy
        self._rows = rows
        self._raises = raises
        self.calls = 0

    def search_symbols(self, query: str, limit: int = 8) -> Optional[list[dict]]:
        self.calls += 1
        if self._raises:
            raise RuntimeError(f"{self.NAME} exploded")
        return self._rows


@pytest.fixture(autouse=True)
def _reset_cache():
    screen_service.reset_for_tests()
    yield
    screen_service.reset_for_tests()


def _patch_vendors(monkeypatch, finnhub=None, fmp=None, yfinance=None):
    monkeypatch.setattr(screen_service.providers.fundamentals, "finnhub",
                         finnhub or _FakeVendor("finnhub", healthy=False))
    monkeypatch.setattr(screen_service.providers.fundamentals, "fmp",
                         fmp or _FakeVendor("fmp", healthy=False))
    monkeypatch.setattr(screen_service.providers.market_data, "yfinance",
                         yfinance or _FakeVendor("yfinance", healthy=False))


def _patch_search(monkeypatch, data=None):
    result = ProviderResult(data=data, source="fake")
    monkeypatch.setattr(screen_service.providers.search, "search", lambda query, limit=8: result)


# ── the reported production bug ─────────────────────────────────────────────

class TestNvdaRegression:
    def test_nvda_resolves_via_well_known_anchor_when_every_vendor_is_down(self, monkeypatch):
        """The exact bug: NVDA -> Nothing Found while every live
        symbol-search vendor is unhealthy. The keyless anchor must resolve
        it without needing any of them."""
        _patch_vendors(monkeypatch)  # all default to healthy=False
        _patch_search(monkeypatch, data=None)

        result = screen("NVDA")

        assert result["results"], "NVDA must never come back empty"
        assert result["results"][0]["symbol"] == "NVDA"
        assert result["mode"] == "lookup"

    def test_symbol_shaped_miss_falls_back_to_thematic_search(self, monkeypatch):
        """Root-cause regression: a symbol-shaped query that misses direct
        resolution must still get a thematic retry. The old guard only
        retried thematic when the query did *not* look like a symbol, so
        this exact path never fired for a real ticker."""
        _patch_vendors(monkeypatch,
                        finnhub=_FakeVendor("finnhub", healthy=True, rows=None),
                        fmp=_FakeVendor("fmp", healthy=True, rows=None),
                        yfinance=_FakeVendor("yfinance", healthy=True, rows=None))
        _patch_search(monkeypatch, data=[
            SearchResult(title="ZZQX surges on housing data", url="https://example.com/a",
                         snippet="$ZZQX rallied 8%"),
        ])
        monkeypatch.setattr(screen_service, "_validate_symbol",
                             lambda symbol: "ZZQX Corp" if symbol == "ZZQX" else None)

        result = screen("ZZQX")  # symbol-shaped, not in WELL_KNOWN_SYMBOLS

        assert result["mode"] == "thematic"
        assert result["results"]
        assert result["results"][0]["symbol"] == "ZZQX"

    def test_thematic_miss_falls_back_to_direct_lookup(self, monkeypatch):
        """Symmetric case: a thematic-shaped query where web search comes up
        empty should still get a direct resolver attempt."""
        # The row names a bank: a description's rows must be about its subject (see
        # TestDescriptiveQueryRowsMustBeAboutTheSubject), so a row that names nothing
        # of the query would rightly be dropped.
        _patch_vendors(monkeypatch, finnhub=_FakeVendor(
            "finnhub", healthy=True, rows=[{"symbol": "BAC", "name": "Bank of America Corporation"}]))
        _patch_search(monkeypatch, data=None)

        result = screen("largest banks by market cap")

        assert result["mode"] == "lookup"
        assert result["results"][0]["symbol"] == "BAC"


# ── vendor chain behavior ────────────────────────────────────────────────────

class TestVendorChain:
    def test_first_healthy_vendor_wins_and_later_vendors_are_skipped(self, monkeypatch):
        finnhub = _FakeVendor("finnhub", healthy=True,
                               rows=[{"symbol": "NVDA", "name": "NVIDIA Corporation"}])
        fmp = _FakeVendor("fmp", healthy=True, rows=[{"symbol": "NVDA", "name": "should not win"}])
        yfin = _FakeVendor("yfinance", healthy=True, rows=[{"symbol": "NVDA", "name": "should not win either"}])
        _patch_vendors(monkeypatch, finnhub=finnhub, fmp=fmp, yfinance=yfin)

        result = screen("NVDA")

        assert result["results"][0] == {
            "symbol": "NVDA", "name": "NVIDIA Corporation",
            "via": "finnhub symbol search", "snippet": None, "url": None,
        }
        assert fmp.calls == 0
        assert yfin.calls == 0

    def test_vendor_exception_does_not_break_the_chain(self, monkeypatch):
        _patch_vendors(
            monkeypatch,
            finnhub=_FakeVendor("finnhub", healthy=True, raises=True),
            fmp=_FakeVendor("fmp", healthy=True, rows=[{"symbol": "MSFT", "name": "Microsoft Corporation"}]),
        )

        result = screen("MSFT")

        assert result["results"][0]["symbol"] == "MSFT"
        assert result["results"][0]["via"] == "fmp symbol search"

    def test_unhealthy_vendor_is_skipped_without_being_called(self, monkeypatch):
        finnhub = _FakeVendor("finnhub", healthy=False)
        fmp = _FakeVendor("fmp", healthy=True, rows=[{"symbol": "AAPL", "name": "Apple Inc."}])
        _patch_vendors(monkeypatch, finnhub=finnhub, fmp=fmp)

        screen("AAPL")

        assert finnhub.calls == 0


# ── never a dead end ─────────────────────────────────────────────────────────

class TestNeverDeadEnds:
    def test_did_you_mean_offers_fuzzy_suggestions_when_everything_misses(self, monkeypatch):
        _patch_vendors(monkeypatch)
        _patch_search(monkeypatch, data=None)

        result = screen("NVDAA")  # one letter off a real, extremely common ticker

        assert not result["results"]
        assert result["suggestions"]
        assert result["suggestions"][0]["symbol"] == "NVDA"
        assert result["suggestions"][0]["via"] == "did you mean"

    def test_screen_never_raises_and_always_returns_a_well_formed_payload(self, monkeypatch):
        _patch_vendors(monkeypatch)
        _patch_search(monkeypatch, data=None)

        result = screen("qzxjklw")

        assert result["results"] == []
        assert isinstance(result["suggestions"], list)
        assert "note" in result and "query" in result and "mode" in result


# ── preserved / strengthened existing behavior ──────────────────────────────

class TestBroadThematicRouting:
    def test_short_sector_query_uses_relevant_thematic_evidence_before_symbol_lookup(self, monkeypatch):
        _patch_vendors(monkeypatch)  # the keyless known-symbol anchor validates candidates
        _patch_search(monkeypatch, data=[
            SearchResult(
                title="Technology stocks to watch include $NVDA and $MSFT",
                url="https://example.com/technology",
                snippet="Large technology companies lead the list",
            ),
        ])

        result = screen("tech stocks")

        assert result["mode"] == "thematic"
        assert [row["symbol"] for row in result["results"]] == ["NVDA", "MSFT"]
        assert all(row["via"] == "mentioned by example.com" for row in result["results"])

    @pytest.mark.parametrize("query", [
        "tech stocks", "dividend stocks", "semiconductor stocks",
        "cybersecurity stocks", "small cap stocks",
    ])
    def test_sector_and_strategy_phrases_are_recognized(self, query):
        assert screen_service._is_broad_theme_query(query)

    @pytest.mark.parametrize("query", [
        "AAPL", "BRK B", "Tesla stocks", "Apple technology stocks",
    ])
    def test_security_queries_are_not_misclassified_as_broad_themes(self, query):
        assert not screen_service._is_broad_theme_query(query)


class TestThematicSearch:
    def test_thematic_query_extracts_and_validates_tickers(self, monkeypatch):
        _patch_vendors(monkeypatch)  # all unhealthy — validation must fall back to the anchor table
        _patch_search(monkeypatch, data=[
            SearchResult(title="Top AI stocks include $NVDA and $AMD", url="https://example.com/ai",
                         snippet="AI rally continues"),
        ])

        result = screen("AI companies to watch")

        assert {row["symbol"] for row in result["results"]} == {"NVDA", "AMD"}
        assert result["mode"] == "thematic"


class TestCaching:
    def test_successful_result_is_cached_and_vendor_is_not_called_again(self, monkeypatch):
        finnhub = _FakeVendor("finnhub", healthy=True, rows=[{"symbol": "AAPL", "name": "Apple Inc."}])
        _patch_vendors(monkeypatch, finnhub=finnhub)

        first = screen("AAPL")
        assert first["cached"] is False
        assert finnhub.calls == 1

        second = screen("AAPL")
        assert second["cached"] is True
        assert finnhub.calls == 1


class TestWellKnownHelpers:
    def test_resolve_well_known_exact_symbol_hit_is_case_insensitive(self):
        hits = screen_service._resolve_well_known("nvda")
        assert hits == [{
            "symbol": "NVDA", "name": "NVIDIA Corporation",
            "via": "known symbol", "snippet": None, "url": None,
        }]

    def test_resolve_well_known_name_substring_hit(self):
        hits = screen_service._resolve_well_known("nvidia")
        assert any(hit["symbol"] == "NVDA" for hit in hits)

    def test_resolve_well_known_returns_empty_for_unknown_query(self):
        assert screen_service._resolve_well_known("qzxjklw") == []


# ── share classes: one listing, several spellings ───────────────────────────

class _SpellingVendor(_FakeVendor):
    """Knows one symbol, spelled one way — as real vendors do. Anything else
    is a miss, which is what a vendor does with "BRK B"."""

    def __init__(self, name: str, symbol: str, label: str):
        super().__init__(name)
        self._symbol, self._label = symbol, label
        self.queries: list[str] = []

    def search_symbols(self, query: str, limit: int = 8) -> Optional[list[dict]]:
        self.queries.append(query)
        self.calls += 1
        if query.upper() == self._symbol:
            return [{"symbol": self._symbol, "name": self._label}]
        return None


class TestShareClassSpellings:
    @pytest.mark.parametrize("typed", ["BRK B", "brk b", "BRK/B", "BRK-B", "BRK.B"])
    def test_every_spelling_reaches_the_listing_the_vendor_knows(self, monkeypatch, typed):
        finnhub = _SpellingVendor("finnhub", "BRK.B", "Berkshire Hathaway Inc-Cl B")
        _patch_vendors(monkeypatch, finnhub=finnhub)
        _patch_search(monkeypatch, data=[])

        out = screen(typed)

        assert [r["symbol"] for r in out["results"]] == ["BRK.B"], (typed, out)
        assert out["mode"] == "lookup"

    def test_a_spaced_query_is_tried_as_a_symbol_before_the_text_as_typed(self, monkeypatch):
        finnhub = _SpellingVendor("finnhub", "BRK.B", "Berkshire Hathaway Inc-Cl B")
        _patch_vendors(monkeypatch, finnhub=finnhub)
        _patch_search(monkeypatch, data=[])

        screen("BRK B")

        # "BRK B" is not a symbol at any vendor, so it must not be the first
        # thing asked — and the answer is found on the first spelling.
        assert finnhub.queries == ["BRK.B"]

    def test_the_hyphenated_vendor_spelling_is_a_fallback_for_a_dotted_query(self, monkeypatch):
        yfinance = _SpellingVendor("yfinance", "BRK-B", "Berkshire Hathaway Inc. New")
        _patch_vendors(monkeypatch, yfinance=yfinance)
        _patch_search(monkeypatch, data=[])

        out = screen("BRK.B")

        assert yfinance.queries == ["BRK.B", "BRK-B"]
        assert [r["symbol"] for r in out["results"]] == ["BRK-B"]

    def test_an_ordinary_query_is_searched_exactly_as_typed_and_once(self, monkeypatch):
        finnhub = _SpellingVendor("finnhub", "AAPL", "Apple Inc")
        _patch_vendors(monkeypatch, finnhub=finnhub)
        _patch_search(monkeypatch, data=[])

        out = screen("AAPL")

        assert finnhub.queries == ["AAPL"]
        assert [r["symbol"] for r in out["results"]] == ["AAPL"]

    def test_the_keyless_anchor_resolves_a_spaced_share_class_when_every_vendor_is_down(self, monkeypatch):
        _patch_vendors(monkeypatch)
        _patch_search(monkeypatch, data=[])

        out = screen("BRK B")

        assert [r["symbol"] for r in out["results"]] == ["BRK.B"]
        assert out["results"][0]["via"] == "known symbol"

    def test_an_unknown_ticker_still_returns_no_results(self, monkeypatch):
        finnhub = _SpellingVendor("finnhub", "AAPL", "Apple Inc")
        _patch_vendors(monkeypatch, finnhub=finnhub)
        _patch_search(monkeypatch, data=[])

        out = screen("QZXW")

        assert out["results"] == []


# ── what the live search matrix found ────────────────────────────────────────

class _RowsVendor(_FakeVendor):
    """Answers each exact query string with its own rows, as a symbol database does."""

    def __init__(self, name: str, answers: dict[str, list[dict]]):
        super().__init__(name)
        self._answers = answers
        self.queries: list[str] = []

    def search_symbols(self, query: str, limit: int = 8) -> Optional[list[dict]]:
        self.queries.append(query)
        self.calls += 1
        return self._answers.get(query.upper())


class TestOneResultPerSecurity:
    def test_a_symbol_a_vendor_lists_twice_is_one_result(self, monkeypatch):
        # META came back twice: a US listing and a cross-listing under the same ticker.
        finnhub = _RowsVendor("finnhub", {"META": [
            {"symbol": "META", "name": "META PLATFORMS INC-CLA"},
            {"symbol": "META", "name": "Meta Platforms Inc"},
            {"symbol": "CMC", "name": "Commercial Metals Co"},
        ]})
        _patch_vendors(monkeypatch, finnhub=finnhub)
        _patch_search(monkeypatch, data=[])
        out = screen("META")
        assert [r["symbol"] for r in out["results"]] == ["META", "CMC"]
        assert out["results"][0]["name"] == "META PLATFORMS INC-CLA"

    def test_symbols_are_compared_without_regard_to_case(self, monkeypatch):
        finnhub = _RowsVendor("finnhub", {"MSFT": [
            {"symbol": "MSFT", "name": "Microsoft Corp"}, {"symbol": "msft", "name": "microsoft corp"},
        ]})
        _patch_vendors(monkeypatch, finnhub=finnhub)
        _patch_search(monkeypatch, data=[])
        assert len(screen("MSFT")["results"]) == 1


BERKSHIRE_NOISE = [
    {"symbol": "BRKU", "name": "Direxion Daily BRKB Bull 2X Shares"},
    {"symbol": "BRK2.L", "name": "LEVERAGE SHARES PUBLIC LIMITED COMPANY"},
]


class TestShareClassIsOneSecurity:
    @pytest.mark.parametrize("typed", ["BRK.B", "BRK-B", "BRK B", "BRK/B", "brk-b", "BRKB", "brkb"])
    def test_every_spelling_lands_on_the_dotted_symbol(self, monkeypatch, typed):
        finnhub = _RowsVendor("finnhub", {
            "BRK.B": [{"symbol": "BRK.B", "name": "BERKSHIRE HATHAWAY INC"}],
            "BRK-B": [{"symbol": "BRK-B", "name": "Berkshire Hathaway Inc"}, *BERKSHIRE_NOISE],
            "BRKB": list(BERKSHIRE_NOISE),
        })
        _patch_vendors(monkeypatch, finnhub=finnhub)
        _patch_search(monkeypatch, data=[])
        out = screen(typed)
        assert [r["symbol"] for r in out["results"]] == ["BRK.B"], (typed, out["results"])
        assert finnhub.queries[0] == "BRK.B", "the dotted spelling must be asked first"

    def test_fuzzy_funds_are_dropped_when_the_security_itself_answered(self, monkeypatch):
        # A source that knows only the hyphenated form, and pads its answer with text-similar funds.
        yfinance = _RowsVendor("yfinance", {"BRK-B": [{"symbol": "BRK-B", "name": "Berkshire Hathaway Inc"}, *BERKSHIRE_NOISE]})
        _patch_vendors(monkeypatch, yfinance=yfinance)
        _patch_search(monkeypatch, data=[])
        out = screen("BRK-B")
        assert [r["symbol"] for r in out["results"]] == ["BRK-B"]
        assert yfinance.queries == ["BRK.B", "BRK-B"], "the hyphenated spelling is still the fallback"

    def test_both_spellings_in_one_answer_collapse_to_the_dotted_one(self, monkeypatch):
        finnhub = _RowsVendor("finnhub", {"BRK.B": [
            {"symbol": "BRK-B", "name": "Berkshire Hathaway Inc"}, {"symbol": "BRK.B", "name": "BERKSHIRE HATHAWAY INC"},
        ]})
        _patch_vendors(monkeypatch, finnhub=finnhub)
        _patch_search(monkeypatch, data=[])
        assert [r["symbol"] for r in screen("BRK.B")["results"]] == ["BRK.B"]

    def test_the_concatenated_form_resolves_from_the_keyless_anchor_too(self, monkeypatch):
        _patch_vendors(monkeypatch)
        _patch_search(monkeypatch, data=[])
        out = screen("BRKB")
        assert [r["symbol"] for r in out["results"]] == ["BRK.B"]
        assert out["results"][0]["via"] == "known symbol"

    def test_only_the_anchor_share_classes_are_recognised_without_a_separator(self):
        assert screen_service._lookup_spellings("BRKB") == ["BRK.B", "BRK-B", "BRKB"]
        for ordinary in ("AAPL", "MSFT", "NVDA", "META", "GOOGL", "BRKU"):
            assert screen_service._lookup_spellings(ordinary) == [ordinary]

    def test_a_query_that_is_not_a_share_class_keeps_every_fuzzy_hit(self, monkeypatch):
        finnhub = _RowsVendor("finnhub", {"APPLE": [
            {"symbol": "AAPL", "name": "Apple Inc"}, {"symbol": "APLE", "name": "Apple Hospitality REIT"},
        ]})
        _patch_vendors(monkeypatch, finnhub=finnhub)
        _patch_search(monkeypatch, data=[])
        assert [r["symbol"] for r in screen("apple")["results"]] == ["AAPL", "APLE"]


class TestThematicSearchMustBeAboutTheQuery:
    PAGES = [SearchResult(title="Best dividend stocks to buy now", url="https://example.com/dividends",
                          snippet="$KO $PEP $JNJ lead the list")]

    def test_a_term_no_page_contains_gets_no_tickers(self, monkeypatch):
        _patch_vendors(monkeypatch)
        _patch_search(monkeypatch, data=self.PAGES)
        out = screen("QZXWQZXW")
        assert out["results"] == []
        assert "suggestions" in out

    def test_a_theme_the_pages_do_discuss_still_resolves(self, monkeypatch):
        _patch_vendors(monkeypatch)
        _patch_search(monkeypatch, data=self.PAGES)
        out = screen("dividend stocks to buy")
        assert {r["symbol"] for r in out["results"]} == {"KO", "PEP", "JNJ"}

    @pytest.mark.parametrize("query,expected", [
        ("QZXWQZXW", False),
        ("blockchain stocks", False),
        ("dividend stocks", True),
        ("AI companies to watch", False),   # no page mentions "ai" in PAGES
        ("best stocks", True),               # nothing but generic words: nothing to check
    ])
    def test_results_are_about_truth_table(self, query, expected):
        assert screen_service._results_are_about(query, self.PAGES) is expected


class TestDescriptiveQueryRowsMustBeAboutTheSubject:
    """A symbol database matches the frame words of a description ("stocks") against fund
    names. Live, "qzxwqzxw stocks" returned the largest stock funds there are."""

    FUNDS = [
        {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF"},
        {"symbol": "VXUS", "name": "Vanguard Total International Stock ETF"},
    ]

    def test_a_nonsense_subject_with_a_frame_word_gets_no_funds(self, monkeypatch):
        _patch_vendors(monkeypatch, finnhub=_FakeVendor("finnhub", rows=self.FUNDS))
        _patch_search(monkeypatch, data=None)
        out = screen("qzxwqzxw stocks")
        assert out["results"] == []
        assert "suggestions" in out

    def test_a_named_company_with_a_frame_word_keeps_its_own_row_only(self, monkeypatch):
        rows = [{"symbol": "TSLA", "name": "Tesla, Inc."}, *self.FUNDS]
        _patch_vendors(monkeypatch, finnhub=_FakeVendor("finnhub", rows=rows))
        _patch_search(monkeypatch, data=None)
        assert [r["symbol"] for r in screen("tesla stocks")["results"]] == ["TSLA"]

    def test_a_theme_keeps_the_rows_that_name_it(self, monkeypatch):
        rows = [{"symbol": "SCHD", "name": "Schwab US Dividend Equity ETF"}, self.FUNDS[0],
                {"symbol": "VYM", "name": "Vanguard High Dividend Yield Index Fund ETF"}]
        _patch_vendors(monkeypatch, finnhub=_FakeVendor("finnhub", rows=rows))
        _patch_search(monkeypatch, data=None)
        assert [r["symbol"] for r in screen("dividend stocks")["results"]] == ["SCHD", "VYM"]

    def test_a_single_term_is_not_held_to_the_name(self, monkeypatch):
        """Vendors resolve aliases ("facebook" is Meta Platforms); nothing to check against."""
        rows = [{"symbol": "META", "name": "Meta Platforms, Inc."}]
        _patch_vendors(monkeypatch, finnhub=_FakeVendor("finnhub", rows=rows))
        _patch_search(monkeypatch, data=None)
        assert [r["symbol"] for r in screen("facebook")["results"]] == ["META"]

    def test_a_query_of_frame_words_alone_is_not_filtered(self, monkeypatch):
        _patch_vendors(monkeypatch, finnhub=_FakeVendor("finnhub", rows=self.FUNDS))
        _patch_search(monkeypatch, data=None)
        assert [r["symbol"] for r in screen("best stocks")["results"]] == ["VTI", "VXUS"]

    @pytest.mark.parametrize("terms,row,expected", [
        (["tesla"], {"symbol": "TSLA", "name": "Tesla, Inc."}, True),
        (["aapl"], {"symbol": "AAPL", "name": "Apple Inc."}, True),
        (["tech"], {"symbol": "XLK", "name": "Technology Select Sector SPDR Fund"}, True),
        (["dividend"], {"symbol": "SCHD", "name": "Schwab US Dividends Equity ETF"}, True),
        (["ai"], {"symbol": "AI", "name": "C3.ai, Inc."}, True),
        (["ai"], {"symbol": "ABNB", "name": "Airbnb, Inc."}, False),       # a short term is a whole word
        (["tesla"], {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF"}, False),
        (["oil"], {"symbol": "XOM", "name": None}, False),                 # a row without a name is not an error
    ])
    def test_row_is_about_truth_table(self, terms, row, expected):
        assert screen_service._row_is_about(terms, row) is expected
