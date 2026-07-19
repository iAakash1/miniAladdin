"""Apify vendor — evidence discipline (hermetic)."""

from __future__ import annotations

from unittest.mock import patch

from src.providers.vendors.apify_vendor import WEB_CLAIM_CONFIDENCE, ApifyVendor


def _vendor(monkeypatch=None) -> ApifyVendor:
    vendor = ApifyVendor()
    return vendor


class TestClaimExtraction:
    def _items(self, sources):
        return [{
            "answer": (
                "The company reported record data center revenue this quarter and expanded margins. "
                "Management guided higher for the coming year citing sustained AI demand. "
                "Short."
            ),
            "sources": sources,
        }]

    def test_sourced_answer_becomes_claims_with_evidence(self):
        vendor = _vendor()
        items = self._items([{"url": "https://reuters.com/a", "title": "Reuters"}])
        bundle = vendor._claims_from_items("NVDA", items, "apify.perplexity")
        assert len(bundle.claims) == 2  # the fragment "Short." is dropped
        claim = bundle.claims[0]
        assert claim.evidence and claim.evidence[0].source.url == "https://reuters.com/a"
        assert claim.confidence == WEB_CLAIM_CONFIDENCE

    def test_unsourced_answer_is_discarded_entirely(self):
        # The central safeguard: web text with no citation never enters the
        # platform as a claim.
        vendor = _vendor()
        bundle = vendor._claims_from_items("NVDA", self._items([]), "apify.perplexity")
        assert bundle.claims == []

    def test_low_quality_hosts_are_rejected_as_sources(self):
        vendor = _vendor()
        items = self._items([{"url": "https://reddit.com/r/stocks/x", "title": "reddit"}])
        assert vendor._claims_from_items("NVDA", items, "apify.perplexity").claims == []

    def test_malformed_source_entries_do_not_crash(self):
        vendor = _vendor()
        items = self._items([{"title": "no url"}, "not-a-url", {"url": "https://ft.com/x"}])
        bundle = vendor._claims_from_items("NVDA", items, "apify.perplexity")
        assert bundle.claims
        assert all(e.source.url.startswith("http") for c in bundle.claims for e in c.evidence)

    def test_web_confidence_stays_below_filing_authority(self):
        # Web research must never outrank SEC (1.0) or Wikidata (0.9).
        assert WEB_CLAIM_CONFIDENCE < 0.9


class TestAvailability:
    def test_without_token_research_returns_empty_not_error(self, monkeypatch):
        monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
        vendor = ApifyVendor()
        assert vendor.research_company("NVDA", "NVIDIA").claims == []
        assert vendor.search("anything") == []

    def test_actor_failure_degrades_silently(self, monkeypatch):
        monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
        vendor = ApifyVendor()
        with patch.object(ApifyVendor, "_run_actor", side_effect=RuntimeError("actor down")):
            assert vendor.research_company("NVDA", "NVIDIA").claims == []
            assert vendor.search("x") == []
