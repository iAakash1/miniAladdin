"""Foreign-filer facts: taxonomy families never mix, currencies never mix, IFRS map caveats, availability, no shares."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.quant.pit import foreign_facts as X
from src.quant.pit import sec_facts as S
from src.quant.pit.calendar import TradingCalendar

CAL = TradingCalendar.from_dates([d.date() for d in pd.bdate_range("2023-03-01", "2023-06-30")])


def reg(adsh="F-1", cik=9, form="20-F", accepted="2023-03-10 17:30:00"):
    return pd.DataFrame([{"adsh": adsh, "cik": cik, "name": "FOREIGN PLC", "sic": 3571, "form": form, "period": "20221231", "fy": 2022, "fp": "FY",
                          "filed": "20230310", "accepted_at": pd.Timestamp(accepted), "prevrpt": 0, "former": pd.NA, "changed": pd.NA,
                          "countryinc": "GB", "stprinc": pd.NA, "ein": "0", "source_archive": "2023q1.zip"}])


def num(tag, value, *, version="ifrs/2022", uom="EUR", qtrs=0, adsh="F-1", ddate="20221231", segments=pd.NA, coreg=pd.NA):
    return {"adsh": adsh, "tag": tag, "version": version, "ddate": ddate, "qtrs": qtrs, "uom": uom, "segments": segments, "coreg": coreg,
            "value": value, "footnote": pd.NA}


def curate(rows, registry=None):
    return X.curate_foreign_num(pd.DataFrame(rows), reg() if registry is None else registry, archive_name="2023q1.zip",
                                archive_sha256="h" * 64, calendar=CAL)


def test_the_version_and_the_map_are_explicit_and_versioned():
    table = X.mapping_table()
    assert X.IFRS_MAP_VERSION == "ifrs-core-facts-v1" and set(table["map_version"]) == {X.IFRS_MAP_VERSION}
    assert {"canonical_fact", "taxonomy", "tag", "unit_requirement", "context", "priority", "is_fallback", "semantic_caveat"} <= set(table.columns)
    assert set(table["taxonomy"]) == {"ifrs", "us-gaap"}
    assert not table["tag"].str.contains("CashFlowsFromUsedInOperations$").any()      # the different-quantity tag is not a fallback


def test_ifrs_fallbacks_carry_their_semantic_caveat():
    table = X.mapping_table()
    equity = table[(table["canonical_fact"] == "equity") & (table["taxonomy"] == "ifrs")].sort_values("priority")
    assert list(equity["tag"]) == ["EquityAttributableToOwnersOfParent", "Equity"] and list(equity["is_fallback"]) == [False, True]
    assert "non-controlling" in equity.iloc[0]["semantic_caveat"]
    income = table[(table["canonical_fact"] == "operating_income") & (table["taxonomy"] == "ifrs")].iloc[0]
    assert "not comparable" in income["semantic_caveat"]


def test_only_the_filings_own_taxonomy_family_is_used_never_a_mixture():
    rows = [num("Assets", 1000.0), num("Revenue", 400.0, qtrs=4), num("CashAndCashEquivalents", 50.0),
            num("Assets", 999.0, version="us-gaap/2022")]      # a stray us-gaap tag in an IFRS filing
    out, counts = curate(rows)
    assert set(out["taxonomy_family"]) == {"ifrs"} and 999.0 not in set(out["value"])
    assert counts["other_family_excluded"] == 1


def test_a_us_gaap_foreign_filing_uses_the_us_gaap_tags_with_its_currency():
    rows = [num("Assets", 1000.0, version="us-gaap/2022", uom="CNY"), num("Revenues", 400.0, version="us-gaap/2022", uom="CNY", qtrs=4),
            num("StockholdersEquity", 300.0, version="us-gaap/2022", uom="CNY")]
    out, _ = curate(rows)
    assert set(out["taxonomy_family"]) == {"us-gaap"} and set(out["unit"]) == {"CNY"} and set(out["currency"]) == {"CNY"}
    assert set(out["canonical_fact"]) == {"assets", "revenue", "equity"}


def test_facts_in_another_currency_are_dropped_not_converted_or_mixed():
    rows = [num("Assets", 1000.0), num("CashAndCashEquivalents", 50.0), num("Liabilities", 400.0),
            num("Revenue", 77.0, qtrs=4, uom="USD")]           # a convenience translation
    out, counts = curate(rows)
    assert set(out["unit"]) == {"EUR"} and 77.0 not in set(out["value"]) and counts["other_currency_excluded"] == 1


def test_dimensional_context_and_wrong_context_types_are_excluded_and_counted():
    rows = [num("Assets", 1000.0), num("Assets", 5.0, segments="Segment=A;"), num("Revenue", 3.0, qtrs=0), num("CashAndCashEquivalents", 4.0, qtrs=4)]
    out, counts = curate(rows)
    assert list(out["value"]) == [1000.0] and counts["dimensional_excluded"] == 1 and counts["context_mismatch_excluded"] == 2


def test_the_ifrs_priority_order_and_fallback_are_kept_not_coalesced():
    rows = [num("EquityAttributableToOwnersOfParent", 300.0), num("Equity", 320.0)]
    out, _ = curate(rows)
    assert sorted(zip(out["tag"], out["tag_priority"])) == [("Equity", 1), ("EquityAttributableToOwnersOfParent", 0)]
    canonical = S.canonical_per_filing(out.assign(cik=9))
    assert list(canonical["value"]) == [300.0]                # the primary tag wins inside the filing


def test_availability_follows_acceptance_after_close():
    out, _ = curate([num("Assets", 1000.0)])
    assert out.iloc[0]["available_session"] == date(2023, 3, 13)        # 2023-03-10 17:30 is a Friday after the close
    assert S.ACCEPTANCE_TIMEZONE == "America/New_York"


def test_no_shares_or_price_dependent_concept_exists_for_foreign_filers():
    assert "shares_outstanding" not in X.IFRS_FACTS and "shares_outstanding" not in X.US_GAAP_FACTS
    out, _ = curate([num("Assets", 1000.0)])
    assert "shares_outstanding" not in set(out["canonical_fact"])


def test_registry_keeps_annual_forms_and_counts_6k_without_treating_it_as_periodic(tmp_path):
    import zipfile
    sub = ("adsh\tcik\tname\tsic\tform\tperiod\tfy\tfp\tfiled\taccepted\tprevrpt\tformer\tchanged\tcountryinc\tstprinc\tein\n"
           "A\t1\tX\t3571\t20-F\t20221231\t2022\tFY\t20230310\t2023-03-10 09:00:00.0\t0\t\t\tGB\t\t1\n"
           "B\t1\tX\t3571\t6-K\t20230331\t2023\tQ1\t20230510\t2023-05-10 09:00:00.0\t0\t\t\tGB\t\t1\n"
           "C\t2\tY\t3571\t10-K\t20221231\t2022\tFY\t20230310\t2023-03-10 09:00:00.0\t0\t\t\tUS\t\t1\n")
    path = tmp_path / "2023q1.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("sub.txt", sub)
    out = X.read_foreign_registry(path)
    assert sorted(out["form"]) == ["20-F", "6-K"]           # the domestic 10-K is not here
    assert "6-K" not in X.FOREIGN_ANNUAL_FORMS and "6-K" in X.AUDITED_EVENT_FORMS


def test_truncating_the_source_leaves_earlier_foreign_facts_identical():
    rows = [num("Assets", 1000.0), num("Assets", 900.0, ddate="20211231"), num("Revenue", 5.0, qtrs=4)]
    early_registry, late_registry = reg("F-1", accepted="2023-03-10 09:00:00"), reg("F-2", accepted="2024-03-11 09:00:00")
    both = pd.concat([early_registry, late_registry], ignore_index=True)
    all_rows = rows + [num("Assets", 1100.0, adsh="F-2", ddate="20231231")]
    full, _ = curate(all_rows, both)
    early, _ = curate(rows, early_registry)
    cut = full[full["accepted_at"] <= pd.Timestamp("2023-06-01")].reset_index(drop=True)
    assert S.content_hash(cut) == S.content_hash(early)


def _archive(tmp_path, rows):
    import zipfile

    path = tmp_path / "2023q1.zip"
    pd.DataFrame(rows).to_csv(tmp_path / "num.txt", sep="\t", index=False)
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(tmp_path / "num.txt", "num.txt")
    return path


def test_currency_policy_is_filing_global_across_chunk_boundaries(tmp_path, monkeypatch):
    registry = reg()
    # EUR wins 3:2 globally, while either two-row parser chunk can appear to
    # prefer USD. The USD values are convenience translations and must vanish.
    rows = [num("Assets", 1000, uom="EUR"), num("Liabilities", 400, uom="USD"),
            num("Revenue", 500, uom="EUR", qtrs=4), num("CashAndCashEquivalents", 50, uom="USD"),
            num("Equity", 600, uom="EUR")]
    path = _archive(tmp_path, rows)
    monkeypatch.setattr(X, "read_foreign_registry", lambda *a, **k: registry)
    _, facts, counts = X.curate_foreign_archive(path, "h" * 64, calendar=CAL, chunk_rows=2)
    assert set(facts["currency"]) == {"EUR"} and set(facts["unit"]) == {"EUR"}
    assert 400 not in set(facts["value"]) and 50 not in set(facts["value"])
    assert facts.groupby("accession")["currency"].nunique().max() == 1
    assert counts["other_currency_excluded"] == 2


def test_two_pass_result_is_chunk_size_invariant_and_deterministic(tmp_path, monkeypatch):
    registry = reg()
    rows = [num("Assets", 1000, uom="JPY"), num("Liabilities", 400, uom="USD"),
            num("Revenue", 500, uom="JPY", qtrs=4), num("CashAndCashEquivalents", 50, uom="USD"),
            num("Equity", 600, uom="JPY")]
    path = _archive(tmp_path, rows)
    monkeypatch.setattr(X, "read_foreign_registry", lambda *a, **k: registry)
    _, small, small_counts = X.curate_foreign_archive(path, "h" * 64, calendar=CAL, chunk_rows=1)
    _, large, large_counts = X.curate_foreign_archive(path, "h" * 64, calendar=CAL, chunk_rows=100)
    pd.testing.assert_frame_equal(small, large)
    assert small_counts == large_counts
    _, repeated, repeated_counts = X.curate_foreign_archive(path, "h" * 64, calendar=CAL, chunk_rows=1)
    pd.testing.assert_frame_equal(small, repeated)
    assert small_counts == repeated_counts


def test_currency_tie_uses_alphabetical_iso_code_not_coverage(tmp_path, monkeypatch):
    registry = reg()
    rows = [num("Assets", 1000, uom="USD"), num("Liabilities", 400, uom="EUR")]
    path = _archive(tmp_path, rows)
    monkeypatch.setattr(X, "read_foreign_registry", lambda *a, **k: registry)
    _, facts, counts = X.curate_foreign_archive(path, "h" * 64, calendar=CAL, chunk_rows=1)
    assert counts["currency_ties"] == 1
    assert set(facts["currency"]) == {"EUR"} and list(facts["canonical_fact"]) == ["liabilities"]


def test_cross_currency_ratio_inputs_cannot_survive_one_filing(tmp_path, monkeypatch):
    registry = reg()
    rows = [num("Assets", 1000, uom="TWD"), num("Revenue", 500, uom="TWD", qtrs=4),
            num("Revenue", 16, uom="USD", qtrs=4), num("ProfitLoss", 2, uom="USD", qtrs=4)]
    path = _archive(tmp_path, rows)
    monkeypatch.setattr(X, "read_foreign_registry", lambda *a, **k: registry)
    _, facts, _ = X.curate_foreign_archive(path, "h" * 64, calendar=CAL, chunk_rows=2)
    assert facts.groupby("accession")["unit"].nunique().max() == 1
    assert set(facts["unit"]) == {"TWD"}
