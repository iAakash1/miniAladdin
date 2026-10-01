"""Official records and publisher-owned macro context.

Each source is asked only the question it answers, and every outcome —
records, no records, failure, missing credential, not applicable — stays
distinguishable all the way to the payload.
"""

from unittest.mock import Mock

import pytest

from src.providers.vendors.macro_vendors import EcbVendor, TreasuryFiscalVendor, WorldBankVendor
from src.providers.vendors.record_vendors import (
    ClinicalTrialsVendor, FederalRegisterVendor, OpenFdaVendor,
)
from src.services import official_record


def _session(payload, status=200):
    session = Mock()
    session.headers = {}
    response = Mock()
    response.status_code = status
    response.json.return_value = payload
    session.request.return_value = response
    return session


# ── macro context ────────────────────────────────────────────────────────────

def test_treasury_reads_only_the_total_marketable_row():
    session = _session({"data": [
        {"record_date": "2026-08-31", "security_desc": "Total Marketable", "avg_interest_rate_amt": "3.475"},
        {"record_date": "2026-08-31", "security_desc": "Treasury Bills", "avg_interest_rate_amt": "4.1"},
        {"record_date": "2026-07-31", "security_desc": "Total Marketable", "avg_interest_rate_amt": "3.443"},
    ]})
    vendor = TreasuryFiscalVendor(session=session)
    assert vendor.get_context_series("TSY_AVG_RATE") == [("2026-07-31", 3.443), ("2026-08-31", 3.475)]
    assert vendor.get_context_series("ECB_DFR") is None


def _sdmx(values, dates):
    return {
        "dataSets": [{"series": {"0:0:0:0:0:0:0": {"observations": {
            str(i): [v, 0, 0, None, None] for i, v in enumerate(values)
        }}}}],
        "structure": {"dimensions": {"observation": [{"values": [{"id": d} for d in dates]}]}},
    }


def test_ecb_deposit_rate_keeps_decision_dates_and_fx_keeps_its_month():
    vendor = EcbVendor(session=_session(_sdmx([2.0, 2.25, 2.5], ["2025-06-11", "2026-06-17", "2026-09-16"])))
    assert vendor.get_context_series("ECB_DFR") == [
        ("2025-06-11", 2.0), ("2026-06-17", 2.25), ("2026-09-16", 2.5),
    ]
    fx = EcbVendor(session=_session(_sdmx([1.1593, 1.1513], ["2026-08", "2026-09"])))
    assert fx.get_context_series("ECB_EURUSD") == [("2026-08-01", 1.1593), ("2026-09-01", 1.1513)]


def test_world_bank_error_envelope_is_not_a_series():
    error = [{"message": [{"id": "120", "key": "Invalid value", "value": "The provided parameter value is not valid"}]}]
    assert WorldBankVendor(session=_session(error)).get_context_series("WB_GDP_WORLD") is None
    rows = [{"page": 1}, [
        {"indicator": {"id": "NY.GDP.MKTP.KD.ZG"}, "countryiso3code": "WLD", "date": "2025", "value": 2.92},
        {"indicator": {"id": "NY.GDP.MKTP.KD.ZG"}, "countryiso3code": "WLD", "date": "2024", "value": None},
    ]]
    assert WorldBankVendor(session=_session(rows)).get_context_series("WB_GDP_WORLD") == [("2025-01-01", 2.92)]


def test_context_series_are_asked_of_their_publisher_only(monkeypatch):
    from src.providers import macro

    calls = []
    monkeypatch.setattr(macro.fred, "get_observations", lambda *a: calls.append("fred") or None)
    monkeypatch.setattr(macro.ecb, "get_context_series", lambda sid, n: calls.append(("ecb", sid)) or [("2026-09-16", 2.5)])
    result = macro.get_series_snapshot("ECB_DFR", count=3)
    assert result.ok and result.source == "ecb"
    assert calls == [("ecb", "ECB_DFR")], "a publisher-owned series fell back to FRED"


# ── record vendors ───────────────────────────────────────────────────────────

def test_federal_register_leaves_out_exchange_rule_filings():
    session = _session({"count": 3, "results": [
        {"document_number": "2026-1", "title": "Notice of Receipt of Complaint", "type": "Notice",
         "publication_date": "2026-10-01", "agencies": [{"name": "International Trade Commission"}],
         "html_url": "https://www.federalregister.gov/documents/2026/10/01/2026-1/x"},
        {"document_number": "2026-2", "title": "Self-Regulatory Organizations; BOX Exchange LLC; Notice",
         "type": "Notice", "publication_date": "2026-09-29", "agencies": [],
         "html_url": "https://www.federalregister.gov/documents/2026/09/29/2026-2/x"},
        {"document_number": "2026-3", "title": "Off-site link", "type": "Notice",
         "publication_date": "2026-09-28", "html_url": "https://example.com/x"},
    ]})
    out = FederalRegisterVendor(session=session).get_official_actions(["NVIDIA Corporation", "NVIDIA Corp."])
    assert [d["id"] for d in out["documents"]] == ["2026-1"]
    assert out["routine_excluded"] == 1 and out["total"] == 3
    term = session.request.call_args.kwargs["params"]["conditions[term]"]
    assert term == '"NVIDIA Corporation" | "NVIDIA Corp."'


def test_openfda_no_match_is_an_answer_not_a_failure(monkeypatch):
    monkeypatch.setenv("OPENFDA_API_KEY", "test-key-placeholder")
    session = _session({"error": {"code": "NOT_FOUND", "message": "No matches found!"}}, status=404)
    vendor = OpenFdaVendor(session=session)
    for _ in range(4):
        assert vendor.get_recalls("Nvidia", "drug") == {"kind": "drug", "firm": "Nvidia", "total": 0, "recalls": []}
    snap = vendor.health_snapshot()
    assert snap["failures"] == 0 and not snap["cooling_down"]


def test_openfda_other_404s_are_still_failures(monkeypatch):
    monkeypatch.setenv("OPENFDA_API_KEY", "test-key-placeholder")
    vendor = OpenFdaVendor(session=_session({"error": {"code": "BAD_REQUEST"}}, status=404))
    from src.providers.base import VendorError
    with pytest.raises(VendorError):
        vendor.get_recalls("Pfizer", "drug")


def test_openfda_recall_dates_are_normalised(monkeypatch):
    monkeypatch.setenv("OPENFDA_API_KEY", "test-key-placeholder")
    session = _session({"meta": {"results": {"total": 156}}, "results": [{
        "recall_number": "D-0853-2026", "classification": "Class II", "status": "Ongoing",
        "report_date": "20260923", "recall_initiation_date": "20260904", "recalling_firm": "Pfizer",
        "product_description": "Dopamine HCl Inj.", "reason_for_recall": "Lack of Assurance of Sterility",
    }]})
    out = OpenFdaVendor(session=session).get_recalls("PFIZER", "drug")
    assert out["total"] == 156
    assert out["recalls"][0]["reported"] == "2026-09-23" and out["recalls"][0]["initiated"] == "2026-09-04"
    assert session.request.call_args.kwargs["params"]["search"] == 'recalling_firm:"PFIZER"'


def test_clinical_trials_attributes_only_studies_the_company_leads():
    def study(nct, lead):
        return {"protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": "A study"},
            "statusModule": {"overallStatus": "RECRUITING"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": lead}},
            "designModule": {"phases": ["PHASE3"]},
        }}
    session = Mock()
    session.headers = {}
    page = Mock(status_code=200)
    page.json.return_value = {"totalCount": 2, "studies": [study("NCT00000001", "Pfizer"), study("NCT00000002", "Other Sponsor")]}
    count = Mock(status_code=200)
    count.json.return_value = {"totalCount": 1, "studies": []}
    session.request.side_effect = [page, count]
    out = ClinicalTrialsVendor(session=session).get_trials("PFIZER")
    assert [t["id"] for t in out["trials"]] == ["NCT00000001"]
    assert out["active_total"] == 2 and out["phase3_active"] == 1


def test_clinical_trials_skip_the_phase_count_when_nothing_is_active():
    session = _session({"totalCount": 0, "studies": []})
    out = ClinicalTrialsVendor(session=session).get_trials("NVIDIA")
    assert out["phase3_active"] == 0 and session.request.call_count == 1


# ── composition ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("registrant, core", [
    ("NVIDIA CORP", "NVIDIA"),
    ("MERCK & CO., INC.", "MERCK"),
    ("PFIZER INC", "PFIZER"),
    ("JOHNSON & JOHNSON", "JOHNSON & JOHNSON"),
    ("META PLATFORMS, INC.", "META PLATFORMS"),
    ("APPLE INC /DE/", "APPLE"),
])
def test_core_name_strips_only_corporate_suffixes(registrant, core):
    assert official_record.core_name(registrant) == core


def test_a_name_without_a_suffix_is_searched_as_itself():
    assert official_record.legal_name_phrases("JOHNSON & JOHNSON") == ["JOHNSON & JOHNSON"]
    assert "NVIDIA Corporation" in official_record.legal_name_phrases("NVIDIA CORP")


@pytest.fixture
def record(monkeypatch):
    from src.providers import official_record as sources

    official_record.reset_for_tests()
    calls = []
    monkeypatch.setattr(sources.federal_register, "get_official_actions",
                        lambda names: calls.append("fr") or {"total": 0, "routine_excluded": 0, "documents": [], "query": names})
    monkeypatch.setattr(sources.openfda, "get_recalls",
                        lambda firm, kind: calls.append(f"fda:{kind}") or {"kind": kind, "firm": firm, "total": 0, "recalls": []})
    monkeypatch.setattr(sources.clinicaltrials, "get_trials",
                        lambda sponsor: calls.append("ct") or {"sponsor": sponsor, "active_total": 3, "phase3_active": 1, "trials": []})
    yield sources, calls
    official_record.reset_for_tests()


def test_healthcare_sources_are_asked_only_for_healthcare_registrants(record, monkeypatch):
    sources, calls = record
    monkeypatch.setenv("OPENFDA_API_KEY", "test-key-placeholder")
    monkeypatch.setattr(sources.sec, "get_entity", lambda s: {"cik": "1", "name": "NVIDIA CORP", "sic": "3674", "sic_description": "Semiconductors"})
    out = official_record.build("NVDA")
    assert calls == ["fr"]
    assert out["sections"]["federal_register"]["status"] == "empty"
    assert out["sections"]["clinical_trials"]["status"] == "not_applicable"

    calls.clear()
    monkeypatch.setattr(sources.sec, "get_entity", lambda s: {"cik": "2", "name": "PFIZER INC", "sic": "2834", "sic_description": "Pharmaceutical Preparations"})
    out = official_record.build("PFE")
    assert sorted(calls) == ["ct", "fda:device", "fda:drug", "fr"]
    assert out["sections"]["clinical_trials"]["status"] == "ok"
    assert out["sections"]["fda_drug_recalls"]["status"] == "empty"


def test_missing_key_and_failure_are_reported_not_hidden(record, monkeypatch):
    sources, calls = record
    monkeypatch.delenv("OPENFDA_API_KEY", raising=False)
    monkeypatch.setattr(sources.sec, "get_entity", lambda s: {"cik": "2", "name": "PFIZER INC", "sic": "2834"})
    def boom(names):
        raise RuntimeError("upstream down")
    monkeypatch.setattr(sources.federal_register, "get_official_actions", boom)
    out = official_record.build("PFE")
    assert out["sections"]["fda_drug_recalls"]["status"] == "not_configured"
    assert out["sections"]["federal_register"]["status"] == "unavailable"
    assert "fda:drug" not in calls


def test_an_edgar_miss_is_unavailable_and_not_cached(record, monkeypatch):
    sources, calls = record
    monkeypatch.setattr(sources.sec, "get_entity", lambda s: None)
    assert official_record.build("ZZZZ")["status"] == "unavailable"
    assert calls == [], "a search ran without the registrant's legal name"
    monkeypatch.setattr(sources.sec, "get_entity", lambda s: {"cik": "1", "name": "ZZZZ CORP", "sic": "3674"})
    assert official_record.build("ZZZZ")["status"] == "ok"
