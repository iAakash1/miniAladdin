"""Vendor statement figures, normalised into facts that carry their own meaning.

This module exists because of a defect, and the defect is worth stating.

`fabric.merge_fundamentals` iterates fourteen field names — `revenue`,
`total_assets`, `free_cash_flow` and eleven others — and reads them off the
vendor object with `getattr(data, name, None)`. The object it actually
receives is `FundamentalsData`, which has **one** of those fourteen fields:
`eps`. The other thirteen return `None` silently, as do `period` and
`history`, which are also absent from the model. So `statements.fields` could
never hold more than a single entry, `statements.period` could never be
anything but `""`, and `statements.history` could never be anything but `[]`.
That is not a coverage problem; the structure was incapable of being filled.

It survived because the unit test builds its own fixture class with all
fourteen attributes set, so the dead path was exercised against a schema that
does not exist in production and passed.

Meanwhile the figures themselves were never missing. They arrive on every
request inside `FundamentalsData.vendor_metrics` — 131 keys from Finnhub, 10
from yfinance — and are dropped at the API boundary, where the ratios block
is built with `if k not in ("symbol", "profile", "vendor_metrics")`.

Recovering them is not a matter of passing the dictionary through. Measured
against AAPL, MSFT, NVDA and WMT, that raw bag contains four distinct traps:

**Scale differs between vendors for the same concept.** Finnhub reports
`marketCapitalization` and `enterpriseValue` in *millions*; yfinance reports
`enterprise_value` in units. The ratio between the two vendors' enterprise
value is 966,142 for AAPL, 996,663 for MSFT, 1,020,088 for NVDA and 1,033,887
for WMT — a factor of a million, with the residual explained by the two
measuring at slightly different times. Merged naively they are off by six
orders of magnitude.

**Basis differs between vendors for the same concept.** Finnhub reports
revenue *per share* (31.725 TTM for AAPL); yfinance reports it *absolute*
(466,822,987,776). Both are right. Their ratio is the share count, and their
difference is meaningless.

**One vendor's dictionary mixes bases with no marker.** yfinance's
`book_value` is 7.36 for AAPL, which is per share — it agrees with Finnhub's
`bookValuePerShareQuarterly` of 7.3599 to four decimal places, and does so
again for MSFT (59.565 / 59.5647) and NVDA (9.483 / 9.4829). It sits in the
same flat dictionary as `total_revenue`, which is absolute, and its name says
nothing about which it is.

**One vendor's dictionary mixes scales with no marker.** `ebitda` is
167,959,003,136 — currency. `ebitda_margins` is 35.979 — a percentage. Same
dictionary, no unit anywhere.

So every key is mapped explicitly to a concept, a basis, a period, a unit and
the scale factor that reaches that unit. A key that is not in the map is not
surfaced: an unmapped number is a number whose meaning nobody has established,
and this product does not render those.

Periods come from the vendor's own key names, which is the only place they
exist. Finnhub encodes them as suffixes — `Annual`, `TTM`, `Quarterly` — and
yfinance encodes them nowhere, so yfinance facts are marked as having no
stated period and the semantic layer refuses to compare them across periods.
That refusal is the correct outcome, not a gap to paper over.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


#: A period a vendor actually names. `""` means the vendor did not say, which
#: is different from "the vendor said it covers all time" and is treated as
#: uncomparable rather than as a wildcard.
TTM = "TTM"
FY = "FY"
MRQ = "MRQ"
UNSTATED = ""

#: Bases. Two figures on different bases are not the same measurement even
#: when they carry the same concept name.
PER_SHARE = "per share"
TOTAL = "total"
PER_EMPLOYEE = "per employee"


@dataclass(frozen=True)
class FactSpec:
    """What a vendor-native key actually means."""

    concept: str
    basis: str
    period: str
    #: `currency` or `currency/share`. Not a currency code — the reporting
    #: currency belongs to the security, not to the field.
    unit: str
    #: Multiply the vendor's raw number by this to reach `unit`. Finnhub
    #: reports company-level totals in millions; everything else is 1.
    scale: float = 1.0


# ── Finnhub /stock/metric ────────────────────────────────────────────────────
#
# Finnhub's per-share figures are the richest statement data in this stack
# that nothing has ever displayed, and they are safe precisely because the
# period is part of the key. `revenuePerShareAnnual` and `revenuePerShareTTM`
# are different measurements and Finnhub says so in the name.
FINNHUB: dict[str, FactSpec] = {
    "revenuePerShareAnnual": FactSpec("Revenue", PER_SHARE, FY, "currency/share"),
    "revenuePerShareTTM": FactSpec("Revenue", PER_SHARE, TTM, "currency/share"),

    "epsAnnual": FactSpec("Earnings per share", PER_SHARE, FY, "currency/share"),
    "epsTTM": FactSpec("Earnings per share", PER_SHARE, TTM, "currency/share"),
    "epsNormalizedAnnual": FactSpec(
        "Earnings per share, normalised", PER_SHARE, FY, "currency/share"),
    "epsExclExtraItemsAnnual": FactSpec(
        "Earnings per share, excluding extraordinary items", PER_SHARE, FY, "currency/share"),
    "epsExclExtraItemsTTM": FactSpec(
        "Earnings per share, excluding extraordinary items", PER_SHARE, TTM, "currency/share"),

    "cashFlowPerShareAnnual": FactSpec("Operating cash flow", PER_SHARE, FY, "currency/share"),
    "cashFlowPerShareQuarterly": FactSpec("Operating cash flow", PER_SHARE, MRQ, "currency/share"),
    "cashFlowPerShareTTM": FactSpec("Operating cash flow", PER_SHARE, TTM, "currency/share"),

    "bookValuePerShareAnnual": FactSpec("Book value", PER_SHARE, FY, "currency/share"),
    "bookValuePerShareQuarterly": FactSpec("Book value", PER_SHARE, MRQ, "currency/share"),
    "tangibleBookValuePerShareAnnual": FactSpec(
        "Tangible book value", PER_SHARE, FY, "currency/share"),
    "tangibleBookValuePerShareQuarterly": FactSpec(
        "Tangible book value", PER_SHARE, MRQ, "currency/share"),

    "dividendPerShareAnnual": FactSpec("Dividend paid", PER_SHARE, FY, "currency/share"),
    "dividendPerShareTTM": FactSpec("Dividend paid", PER_SHARE, TTM, "currency/share"),

    "ebitdPerShareAnnual": FactSpec("EBITDA", PER_SHARE, FY, "currency/share"),
    "ebitdPerShareTTM": FactSpec("EBITDA", PER_SHARE, TTM, "currency/share"),

    # Company-level totals, reported in millions. The scale is measured, not
    # assumed: against yfinance's unit-scaled enterprise value the ratio is
    # 0.97e6 to 1.03e6 across four securities on four different fiscal
    # calendars. Getting this wrong is a factor-of-a-million error that looks
    # like a plausible number.
    "marketCapitalization": FactSpec(
        "Market capitalisation", TOTAL, UNSTATED, "currency", scale=1e6),
    "enterpriseValue": FactSpec("Enterprise value", TOTAL, UNSTATED, "currency", scale=1e6),
}


# ── yfinance ────────────────────────────────────────────────────────────────
#
# Absolute figures, and no period on any of them. They are still worth having
# — they are the only statement-level totals in this stack — but a total with
# no period cannot be compared with another period's total, and the semantic
# layer is left to say so rather than this module guessing "probably TTM".
YFINANCE: dict[str, FactSpec] = {
    "total_revenue": FactSpec("Revenue", TOTAL, UNSTATED, "currency"),
    "ebitda": FactSpec("EBITDA", TOTAL, UNSTATED, "currency"),
    "free_cash_flow": FactSpec("Free cash flow", TOTAL, UNSTATED, "currency"),
    "operating_cash_flow": FactSpec("Operating cash flow", TOTAL, UNSTATED, "currency"),
    "total_cash": FactSpec("Cash and equivalents", TOTAL, UNSTATED, "currency"),
    "total_debt": FactSpec("Total debt", TOTAL, UNSTATED, "currency"),
    "enterprise_value": FactSpec("Enterprise value", TOTAL, UNSTATED, "currency"),

    # Named `book_value` and measured per share. Verified against Finnhub's
    # explicitly-named per-share figure on AAPL (7.36 / 7.3599), MSFT
    # (59.565 / 59.5647) and NVDA (9.483 / 9.4829). Mapping it as a total
    # would put a seven-dollar number in a column of hundred-billion-dollar
    # ones and call it Apple's equity.
    "book_value": FactSpec("Book value", PER_SHARE, UNSTATED, "currency/share"),

    # Deliberately absent: `ebitda_margins` is a percentage and `peg_ratio` is
    # a ratio. Neither is a statement figure, both already have a home on the
    # ratio surface, and mixing them in here would put three scales in one
    # table.
}


VENDOR_KEYS: dict[str, dict[str, FactSpec]] = {
    "finnhub": FINNHUB,
    "yfinance": YFINANCE,
}


def comparability_key(fact: dict[str, Any]) -> tuple[str, str, str, str]:
    """What has to match before two observations may be compared.

    Concept alone is not enough, and this is the whole point of the module:
    revenue per share TTM and revenue in dollars are both "Revenue".
    """
    return (fact["concept"], fact["basis"], fact["period"], fact["unit"])


def normalise(provider: str, metrics: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn one vendor's raw metric bag into facts that carry their meaning.

    Unmapped keys are dropped rather than passed through with a guessed
    meaning. A number whose unit, basis and period nobody has established is
    not a fact; it is a numeral.
    """
    if not metrics:
        return []
    spec_by_key = VENDOR_KEYS.get(provider, {})
    facts: list[dict[str, Any]] = []
    for key, spec in spec_by_key.items():
        raw = metrics.get(key)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue
        value = float(raw)
        if value != value:  # NaN
            continue
        facts.append({
            "concept": spec.concept,
            "basis": spec.basis,
            "period": spec.period,
            "unit": spec.unit,
            "value": value * spec.scale,
            "provider": provider,
            #: What the vendor actually sent, kept so a reader inspecting the
            #: number can see that this product rescaled it and by how much.
            "vendor_key": key,
            "vendor_value": value,
            "scale": spec.scale,
        })
    return facts


def group(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect facts into groups that are actually comparable.

    Within a group every observation shares a concept, a basis, a period and a
    unit, so a spread between them is a genuine disagreement between vendors
    rather than a difference of measurement. Across groups nothing is
    compared at all.

    Agreement is reported only where there is more than one observation.
    A single vendor agreeing with itself is not evidence.
    """
    buckets: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for f in facts:
        buckets.setdefault(comparability_key(f), []).append(f)

    out: list[dict[str, Any]] = []
    for (concept, basis, period, unit), obs in buckets.items():
        values = [o["value"] for o in obs]
        lo, hi = min(values), max(values)
        spread_pct = ((hi - lo) / abs(lo) * 100) if lo else None
        out.append({
            "concept": concept,
            "basis": basis,
            "period": period,
            "unit": unit,
            "observations": sorted(obs, key=lambda o: o["provider"]),
            "providers": sorted({o["provider"] for o in obs}),
            #: None where there is one observation — an absent measurement,
            #: not a spread of zero.
            "spread_pct": round(spread_pct, 4) if spread_pct is not None and len(obs) > 1 else None,
            "agrees": None if len(obs) < 2 else (spread_pct is not None and spread_pct <= 1.0),
        })
    out.sort(key=lambda g: (g["concept"], g["basis"], g["period"]))
    return out
