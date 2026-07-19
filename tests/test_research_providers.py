"""SEC + Wikidata vendor normalization — hermetic (no network)."""

from __future__ import annotations

from unittest.mock import patch

from src.providers.vendors.sec_vendor import SECVendor
from src.providers.vendors.wikidata_vendor import WikidataVendor


class TestSECNormalization:
    def test_filings_normalize_and_filter_to_known_forms(self):
        vendor = SECVendor()
        vendor._ticker_map = {"NVDA": {"cik": "0001045810", "name": "NVIDIA CORP"}}
        submissions = {
            "filings": {"recent": {
                "form": ["10-K", "NT 10-K", "8-K"],
                "accessionNumber": ["0001-24-000029", "0001-24-000030", "0001-24-000031"],
                "primaryDocument": ["nvda-10k.htm", "nt.htm", "nvda-8k.htm"],
                "filingDate": ["2026-02-21", "2026-02-22", "2026-03-01"],
                "reportDate": ["2026-01-28", "", ""],
                "items": ["", "", "2.02"],
            }}
        }
        with patch.object(SECVendor, "_get_json", return_value=submissions):
            filings = vendor.get_filings("NVDA")
        # NT 10-K is not in FORM_MEANING — unknown forms are dropped, not guessed at.
        assert [f["form"] for f in filings] == ["10-K", "8-K"]
        assert filings[0]["meaning"] == "Annual report"
        # CIK is zero-stripped in archive URLs but zero-padded in API paths.
        assert "/data/1045810/000124000029/nvda-10k.htm" in filings[0]["url"]

    def test_xbrl_keeps_latest_restatement_per_year(self):
        vendor = SECVendor()
        vendor._ticker_map = {"X": {"cik": "0000000001", "name": "X CORP"}}
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            {"fy": 2025, "fp": "FY", "form": "10-K", "val": 100, "filed": "2025-02-01"},
            {"fy": 2025, "fp": "FY", "form": "10-K", "val": 110, "filed": "2026-02-01"},  # restated
            {"fy": 2024, "fp": "FY", "form": "10-K", "val": 90, "filed": "2024-02-01"},
            {"fy": 2025, "fp": "Q1", "form": "10-Q", "val": 25, "filed": "2025-05-01"},  # ignored
        ]}}}}}
        with patch.object(SECVendor, "_get_json", return_value=facts):
            series = vendor.get_xbrl_facts("X")
        revenue = series["Revenue"]
        assert [r["fiscal_year"] for r in revenue] == [2025, 2024]
        assert revenue[0]["value"] == 110  # restatement supersedes

    def test_knowledge_bundle_carries_evidence_for_every_finding(self):
        vendor = SECVendor()
        vendor._ticker_map = {"X": {"cik": "0000000001", "name": "X CORP"}}
        with patch.object(SECVendor, "get_filings", return_value=[]), \
             patch.object(SECVendor, "get_xbrl_facts", return_value={"Revenue": [
                 {"fiscal_year": 2026, "value": 120.0, "unit": "USD", "form": "10-K", "filed": "2026-02-01"},
                 {"fiscal_year": 2025, "value": 100.0, "unit": "USD", "form": "10-K", "filed": "2025-02-01"},
             ]}):
            bundle = vendor.get_knowledge("X")
        assert len(bundle.findings) == 1
        finding = bundle.findings[0]
        assert "+20.0%" in finding.text
        assert finding.tone == "pos"
        # Evidence-first: no finding without a cited source.
        assert finding.evidence and finding.evidence[0].source.provider == "sec"

    def test_unknown_ticker_yields_empty_bundle_not_error(self):
        vendor = SECVendor()
        vendor._ticker_map = {}
        bundle = vendor.get_knowledge("NOPE")
        assert bundle.nodes == [] and bundle.findings == []


class TestWikidataNormalization:
    def _rows(self):
        def binding(prop, label):
            return {"prop": {"value": f"http://www.wikidata.org/prop/direct/{prop}"},
                    "value": {"value": "http://www.wikidata.org/entity/Q1"},
                    "valueLabel": {"value": label}}
        return [binding("P169", "Jensen Huang"), binding("P1056", "graphics processing unit"),
                binding("P452", "semiconductor industry"), binding("P999", "ignored property")]

    def test_edges_carry_correct_direction_per_semantics(self):
        vendor = WikidataVendor()
        with patch.object(WikidataVendor, "find_company",
                          return_value={"qid": "Q182477", "label": "Nvidia", "description": "chip maker"}), \
             patch.object(WikidataVendor, "_query", return_value=self._rows()):
            bundle = vendor.get_knowledge("NVDA")
        edges = {e.type: (e.source_id, e.target_id) for e in bundle.edges}
        # A person is CEO *of* a company: person → company.
        assert edges["ceo_of"][1] == "company:NVDA"
        # A company produces a product: company → product.
        assert edges["produces"][0] == "company:NVDA"
        # Unmapped properties never enter the graph.
        assert len(bundle.edges) == 3

    def test_unresolvable_company_yields_empty_bundle(self):
        vendor = WikidataVendor()
        with patch.object(WikidataVendor, "find_company", return_value=None):
            assert vendor.get_knowledge("NOPE").nodes == []
