"""
Portfolio intelligence — concentration, exposure and risk, from the book the
user actually holds and the analyses they have actually run.

## Why this is a separate module

The portfolio screen previously showed positions and their cost basis, which
answers "what do I own" and nothing else. The questions a book raises are
different in kind: *how much of this is one bet?* *Which three names carry
the risk?* *Is my exposure drifting?* Those are arithmetic over the whole
book, not per-row facts, and they have to be computed somewhere that can be
tested against hand-worked numbers.

## What is and is not computed here

Everything below is derived from two things the product already stores: the
user's positions (ticker, shares, average price) and the most recent stored
analysis per ticker (verdict, confidence, risk score, sector). Nothing is
fetched, nothing is modelled, and nothing is estimated.

In particular there is **no covariance and no portfolio volatility**. Real
portfolio risk needs a return covariance matrix across the holdings; we do
not compute one, and a "portfolio risk" number derived from per-name risk
scores alone would be a fabrication wearing a statistic's clothes. What is
computed instead is *risk concentration* — how much of the book sits in the
names the engine scored as riskiest — which is an honest weighted sum and is
labelled as exactly that.

Weights are cost-basis weights, not market-value weights, because average
price is what the product stores. That is stated in the output so a reader
is never left to assume it is mark-to-market.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

# Herfindahl thresholds. These are the conventional competition-policy
# boundaries (1500 / 2500 on a 0–10 000 scale), reused because they are a
# published, checkable standard rather than numbers we picked to make a
# portfolio look diversified.
HHI_CONCENTRATED = 2500.0
HHI_MODERATE = 1500.0

# A verdict is "actionable" for the deteriorating/improving counts only when
# the engine actually reached one; a Hold is neither.
BULLISH = {"Buy", "Strong Buy"}
BEARISH = {"Sell", "Strong Sell"}


def _weights(
    positions: Iterable[dict[str, Any]],
    market_values: Optional[dict[str, float]] = None,
) -> tuple[dict[str, float], float]:
    """Weight per ticker, and the total the weights are shares of.

    Positions in the same ticker are summed rather than kept apart: two lots
    of AAPL are one bet on AAPL, and treating them as two positions would
    understate concentration exactly where it matters.

    When `market_values` is supplied — a ticker → current market value map —
    weights are shares of the book's *current* value, which is the honest
    denominator once prices are known: a position that has doubled is twice
    the bet it was at purchase, and cost-basis weights would still call it
    the smaller one. A ticker missing from the map falls back to its cost, so
    one unreachable quote degrades the precision of the weights rather than
    collapsing the whole calculation.
    """
    basis: dict[str, float] = {}
    for row in positions:
        ticker = str(row.get("ticker") or "").upper().strip()
        try:
            shares = float(row.get("shares") or 0)
            price = float(row.get("average_price") or 0)
        except (TypeError, ValueError):
            continue
        if not ticker or shares <= 0 or price < 0:
            continue
        basis[ticker] = basis.get(ticker, 0.0) + shares * price

    if market_values:
        for ticker in list(basis):
            value = market_values.get(ticker)
            if isinstance(value, (int, float)) and value > 0:
                basis[ticker] = float(value)

    total = sum(basis.values())
    if total <= 0:
        return {}, 0.0
    return {t: (v / total) * 100.0 for t, v in basis.items()}, total


def herfindahl(weights_pct: dict[str, float]) -> float:
    """Sum of squared percentage weights, 0–10 000.

    A single position scores 10 000; ten equal positions score 1 000. Reported
    raw rather than normalised so it can be checked against the published
    thresholds it is compared to.
    """
    return round(sum(w * w for w in weights_pct.values()), 1)


def concentration_band(hhi: float) -> str:
    if hhi >= HHI_CONCENTRATED:
        return "concentrated"
    if hhi >= HHI_MODERATE:
        return "moderate"
    return "diversified"


def analyse(
    positions: list[dict[str, Any]],
    analyses: dict[str, dict[str, Any]],
    market_values: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """Portfolio intelligence over one book.

    `analyses` maps an upper-case ticker to that ticker's most recent stored
    analysis row. A position with no analysis is not dropped — it is counted
    as uncovered, because a book where half the names have never been scored
    is a fact about the book and hiding it would flatter the numbers.
    """
    weights, total_basis = _weights(positions, market_values)
    if not weights:
        return {
            "covered": False,
            "reason": "No positions recorded.",
            "positions": 0,
        }

    ranked = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    hhi = herfindahl(weights)

    top_three = ranked[:3]
    top_three_pct = round(sum(w for _, w in top_three), 1)

    # ── coverage ─────────────────────────────────────────────────────────────
    scored = [t for t in weights if t in analyses]
    uncovered = [t for t in weights if t not in analyses]
    covered_pct = round(sum(weights[t] for t in scored), 1)

    # ── risk concentration ───────────────────────────────────────────────────
    # A weighted mean of the engine's own per-name risk scores. Explicitly not
    # a portfolio volatility: no covariance is involved, so this says "the
    # book is tilted toward names the engine scored as risky", not "the book
    # will move this much".
    risk_num = 0.0
    risk_den = 0.0
    risk_rows: list[dict[str, Any]] = []
    for ticker in scored:
        row = analyses[ticker]
        risk = row.get("risk_score")
        weight = weights[ticker]
        if isinstance(risk, (int, float)):
            risk_num += weight * float(risk)
            risk_den += weight
            risk_rows.append(
                {
                    "ticker": ticker,
                    "weight_pct": round(weight, 1),
                    "risk_score": int(risk),
                    # Share of the book's total risk exposure that this one
                    # name accounts for. Filled in below once the total known.
                    "risk_share_pct": 0.0,
                }
            )
    weighted_risk = round(risk_num / risk_den, 1) if risk_den > 0 else None

    total_risk_units = sum(r["weight_pct"] * r["risk_score"] for r in risk_rows)
    if total_risk_units > 0:
        for r in risk_rows:
            r["risk_share_pct"] = round(
                100.0 * r["weight_pct"] * r["risk_score"] / total_risk_units, 1
            )
    risk_rows.sort(key=lambda r: r["risk_share_pct"], reverse=True)
    top_risk = risk_rows[:3]
    top_risk_share = round(sum(r["risk_share_pct"] for r in top_risk), 1)

    # ── sector exposure ──────────────────────────────────────────────────────
    sectors: dict[str, float] = {}
    for ticker in scored:
        sector = analyses[ticker].get("sector")
        if not sector:
            continue
        sectors[str(sector)] = sectors.get(str(sector), 0.0) + weights[ticker]
    sector_rows = sorted(
        ({"sector": s, "weight_pct": round(w, 1)} for s, w in sectors.items()),
        key=lambda r: r["weight_pct"],
        reverse=True,
    )
    unknown_sector_pct = round(
        sum(weights[t] for t in weights if not analyses.get(t, {}).get("sector")), 1
    )

    # ── verdict mix ──────────────────────────────────────────────────────────
    mix = {"bullish": 0.0, "neutral": 0.0, "bearish": 0.0}
    for ticker in scored:
        verdict = analyses[ticker].get("verdict")
        bucket = "bullish" if verdict in BULLISH else "bearish" if verdict in BEARISH else "neutral"
        mix[bucket] += weights[ticker]
    verdict_mix = {k: round(v, 1) for k, v in mix.items()}

    return {
        "covered": True,
        "positions": len(weights),
        "total_basis": round(total_basis, 2),
        # Stated, not implied — the reader must never have to guess which
        # denominator a percentage is a share of.
        "weight_basis": (
            "current market value (shares × current price)"
            if market_values else "cost basis (shares × average price)"
        ),
        "concentration": {
            "hhi": hhi,
            "band": concentration_band(hhi),
            "top_three_pct": top_three_pct,
            "top_three": [{"ticker": t, "weight_pct": round(w, 1)} for t, w in top_three],
            "largest": {"ticker": ranked[0][0], "weight_pct": round(ranked[0][1], 1)},
        },
        "coverage": {
            "scored": len(scored),
            "unscored": len(uncovered),
            "covered_pct": covered_pct,
            "unscored_tickers": sorted(uncovered),
        },
        "risk": {
            "weighted_score": weighted_risk,
            "basis": "weighted mean of per-name engine risk scores — not a "
                     "portfolio volatility; no covariance is estimated",
            "top_contributors": top_risk,
            "top_three_share_pct": top_risk_share,
        },
        "sectors": {
            "rows": sector_rows,
            "unknown_pct": unknown_sector_pct,
        },
        "verdict_mix": verdict_mix,
    }


def headlines(report: dict[str, Any]) -> list[dict[str, str]]:
    """The two or three sentences worth saying about this book.

    Each is generated only when its own threshold is crossed, so a balanced
    portfolio produces a short list rather than three sentences straining to
    find something alarming to say. Every number quoted is read back out of
    the report — nothing here recomputes anything.
    """
    if not report.get("covered"):
        return []

    out: list[dict[str, str]] = []
    conc = report["concentration"]
    # "100% of capital sits in 3 names" is arithmetic, not a finding, when the
    # book has three names in it. A top-N share is only informative once
    # there is something outside the N for it to be a share *of*.
    positions = report.get("positions", 0)
    top_n = len(conc["top_three"])
    if conc["band"] != "diversified":
        basis = "market value" if "market" in report.get("weight_basis", "") else "cost basis"
        if positions > top_n:
            text = (
                f"{conc['top_three_pct']}% of {basis} sits in {top_n} of {positions} names — "
                f"{conc['largest']['ticker']} alone is {conc['largest']['weight_pct']}%. "
                f"Herfindahl {conc['hhi']:.0f} ({conc['band']})."
            )
        else:
            # With no tail to compare against, the largest single weight is
            # the only non-tautological thing that can be said.
            text = (
                f"{conc['largest']['ticker']} is {conc['largest']['weight_pct']}% of "
                f"{basis} across {positions} position{'s' if positions != 1 else ''}. "
                f"Herfindahl {conc['hhi']:.0f} ({conc['band']})."
            )
        out.append({"tone": "warn" if conc["band"] == "concentrated" else "accent", "text": text})

    risk = report["risk"]
    scored = report.get("coverage", {}).get("scored", 0)
    if (
        risk["top_contributors"]
        and risk["top_three_share_pct"] >= 60
        # Same guard: the top three of three names always carry 100%.
        and scored > len(risk["top_contributors"])
    ):
        names = ", ".join(r["ticker"] for r in risk["top_contributors"])
        out.append({
            "tone": "warn",
            "text": (
                f"{risk['top_three_share_pct']}% of weighted risk exposure comes from "
                f"{names}, out of {scored} scored holdings. Risk is more concentrated "
                f"than capital."
            ),
        })

    cov = report["coverage"]
    if cov["unscored"] > 0:
        out.append({
            "tone": "muted",
            "text": (
                f"{cov['unscored']} of {report['positions']} positions have never been "
                f"analysed, so {round(100 - cov['covered_pct'], 1)}% of the book is "
                f"excluded from every figure above."
            ),
        })

    sectors = report["sectors"]["rows"]
    if sectors and sectors[0]["weight_pct"] >= 40:
        out.append({
            "tone": "accent",
            "text": (
                f"{sectors[0]['weight_pct']}% of scored capital is in "
                f"{sectors[0]['sector']}."
            ),
        })

    return out


# ══════════════════════════════════════════════════════════════════════════
# VALUATION — what the book is worth today, against what it cost
# ══════════════════════════════════════════════════════════════════════════
#
# The concentration analysis above works in cost basis, because that is what
# the product stores and it is defined even when no market data is reachable.
# Valuation is the other half: shares × *current* price, which needs a live
# quote and therefore has a failure mode the concentration figures do not.
#
# The rule that governs every function below: **a missing price is never
# replaced by the average buy price.** Doing so would silently report a
# holding as exactly break-even, which is a specific and wrong claim rather
# than an absence. Unpriced holdings are carried through as unpriced, are
# excluded from the totals, and are counted so the UI can say how much of the
# book the totals actually cover.


def _quote_price(quote: Optional[dict[str, Any]]) -> Optional[float]:
    """The usable current price in a quote entry, or None.

    `/api/quotes` answers per-symbol errors as `{"error": ...}` rather than
    failing the batch, so an entry existing does not mean it has a price.
    Non-positive prices are rejected too: a zero close is a data fault, not a
    security that became worthless.
    """
    if not isinstance(quote, dict):
        return None
    if quote.get("error"):
        return None
    price = quote.get("price")
    if not isinstance(price, (int, float)):
        return None
    price = float(price)
    return price if price > 0 else None


def value_positions(
    positions: list[dict[str, Any]],
    quotes: dict[str, Any],
) -> dict[str, Any]:
    """Per-holding and whole-book valuation.

    Lots in the same ticker are merged first, for the same reason the
    concentration math merges them: two lots of AAPL are one holding, and a
    weighted average cost is the only cost the position actually has.

    Returns per-holding rows carrying invested, current, P&L and return, plus
    totals computed **only over priced holdings** — a total that mixed priced
    and unpriced positions would understate the book without saying so.
    """
    merged: dict[str, dict[str, float]] = {}
    for row in positions:
        ticker = str(row.get("ticker") or "").upper().strip()
        try:
            shares = float(row.get("shares") or 0)
            price = float(row.get("average_price") or 0)
        except (TypeError, ValueError):
            continue
        if not ticker or shares <= 0 or price < 0:
            continue
        bucket = merged.setdefault(ticker, {"shares": 0.0, "cost": 0.0})
        bucket["shares"] += shares
        bucket["cost"] += shares * price

    rows: list[dict[str, Any]] = []
    total_invested = 0.0
    total_current = 0.0
    priced_invested = 0.0
    day_change = 0.0
    day_change_known = False

    for ticker, bucket in merged.items():
        shares = bucket["shares"]
        invested = bucket["cost"]
        # Weighted average cost across the merged lots — not the last lot's
        # price, which is what a naive merge would leave behind.
        avg_price = invested / shares if shares > 0 else 0.0
        total_invested += invested

        quote = quotes.get(ticker)
        current_price = _quote_price(quote)

        row: dict[str, Any] = {
            "ticker": ticker,
            "shares": round(shares, 6),
            "avg_price": round(avg_price, 4),
            "invested": round(invested, 2),
            "current_price": None,
            "current_value": None,
            "pnl": None,
            "pnl_pct": None,
            "day_change_pct": None,
            "priced": False,
            # Why a row has no valuation, in the reader's language.
            "price_note": None,
        }

        if current_price is None:
            row["price_note"] = (
                (quote or {}).get("error") if isinstance(quote, dict) else None
            ) or "no current price available"
            rows.append(row)
            continue

        current_value = shares * current_price
        pnl = current_value - invested
        row.update(
            current_price=round(current_price, 4),
            current_value=round(current_value, 2),
            pnl=round(pnl, 2),
            # A zero-cost holding (a gift, a spin-off recorded at 0) has a
            # defined P&L but no defined *return* — dividing by zero would
            # produce an infinity the UI would have to special-case anyway.
            pnl_pct=(round((pnl / invested) * 100.0, 2) if invested > 0 else None),
            priced=True,
            stale=bool(isinstance(quote, dict) and quote.get("stale")),
            source=(quote or {}).get("source") if isinstance(quote, dict) else None,
        )
        # Today's move in money, from the same 1-day percentage the watchlist
        # shows. Only accumulated when the quote actually carries one.
        change_1d = (quote or {}).get("change_1d") if isinstance(quote, dict) else None
        if isinstance(change_1d, (int, float)):
            row["day_change_pct"] = round(float(change_1d), 2)
            previous_value = current_value / (1.0 + float(change_1d) / 100.0) if change_1d != -100 else 0.0
            day_change += current_value - previous_value
            day_change_known = True

        total_current += current_value
        priced_invested += invested
        rows.append(row)

    # Ranked by size of the position, which is the order a holder reads them.
    rows.sort(key=lambda r: r["invested"], reverse=True)

    priced = [r for r in rows if r["priced"]]
    unpriced = [r for r in rows if not r["priced"]]
    total_pnl = total_current - priced_invested if priced else None

    return {
        "rows": rows,
        "totals": {
            # Cost of the whole book, priced or not — this one is always known.
            "invested": round(total_invested, 2),
            # Everything below covers priced holdings only.
            "priced_invested": round(priced_invested, 2),
            "current_value": round(total_current, 2) if priced else None,
            "pnl": round(total_pnl, 2) if total_pnl is not None else None,
            "pnl_pct": (
                round((total_pnl / priced_invested) * 100.0, 2)
                if total_pnl is not None and priced_invested > 0 else None
            ),
            "day_pnl": round(day_change, 2) if day_change_known else None,
            "day_pnl_pct": (
                round(day_change / (total_current - day_change) * 100.0, 2)
                if day_change_known and (total_current - day_change) > 0 else None
            ),
        },
        "coverage": {
            "priced": len(priced),
            "unpriced": len(unpriced),
            "unpriced_tickers": sorted(r["ticker"] for r in unpriced),
            # Share of cost basis the totals above actually account for.
            "priced_pct": (
                round(priced_invested / total_invested * 100.0, 1)
                if total_invested > 0 else 0.0
            ),
        },
    }


def value_curve(
    positions: list[dict[str, Any]],
    closes_by_ticker: dict[str, list[tuple[str, float]]],
    *,
    min_points: int = 5,
) -> Optional[dict[str, Any]]:
    """Historical mark-to-market value of *today's* holdings.

    This is real history, not a simulation: each point is
    ``Σ shares × that day's actual close`` over the price series the provider
    already returned. What it is **not** is a track record — it holds the
    current share counts fixed across the whole window, so it answers "what
    would this book have been worth" and not "what did I make". A holding
    bought last week appears at its full size a month ago. That assumption is
    returned in the payload rather than left for the UI to remember, because
    a curve labelled "portfolio performance" that quietly meant something
    else would be the most misleading thing on the page.

    Only dates every priced holding has a close for are used. Forward-filling
    a missing day would invent a price; dropping the day loses nothing except
    resolution, and the dropped count is reported.
    """
    merged: dict[str, float] = {}
    for row in positions:
        ticker = str(row.get("ticker") or "").upper().strip()
        try:
            shares = float(row.get("shares") or 0)
        except (TypeError, ValueError):
            continue
        if ticker and shares > 0:
            merged[ticker] = merged.get(ticker, 0.0) + shares

    usable = {t: dict(closes_by_ticker.get(t) or []) for t in merged if closes_by_ticker.get(t)}
    if not usable:
        return None

    # The intersection of the date axes. A union with gaps would need a fill
    # rule, and every fill rule invents a price that was never observed.
    common: Optional[set[str]] = None
    for series in usable.values():
        dates = set(series)
        common = dates if common is None else (common & dates)
    if not common or len(common) < min_points:
        return None

    axis = sorted(common)
    points = [
        {
            "date": day,
            "value": round(sum(merged[t] * usable[t][day] for t in usable), 2),
        }
        for day in axis
    ]

    # The baseline is what the covered holdings cost, so the shaded area
    # between the two lines is the P&L on exactly the same set of holdings
    # the curve is drawn from.
    covered_cost = 0.0
    for row in positions:
        ticker = str(row.get("ticker") or "").upper().strip()
        if ticker not in usable:
            continue
        try:
            covered_cost += float(row.get("shares") or 0) * float(row.get("average_price") or 0)
        except (TypeError, ValueError):
            continue

    return {
        "points": points,
        "invested_baseline": round(covered_cost, 2),
        "tickers": sorted(usable),
        "excluded_tickers": sorted(t for t in merged if t not in usable),
        "assumption": (
            "Current share counts held constant across the window — this is what "
            "today's holdings would have been worth, not a record of past positions."
        ),
    }


# ══════════════════════════════════════════════════════════════════════════
# RISK & ATTRIBUTION — descriptive statistics over real price history
#
# Everything below is computed from the same daily closes the value curve is
# drawn from. Each figure is named for what it actually is: `volatility` is
# the annualised standard deviation of daily log returns and is called that,
# not "risk"; there is no Sharpe ratio because there is no defensible
# risk-free series in this system to subtract, and a Sharpe computed against
# an assumed zero would be a different statistic wearing the name.
# ══════════════════════════════════════════════════════════════════════════

import math

# Below this many observations a standard deviation is noise. 20 sessions is
# roughly a trading month — the shortest window where an annualised figure is
# worth printing rather than caveating into meaninglessness.
MIN_RETURN_OBSERVATIONS = 20
TRADING_DAYS = 252


def _returns(values: Sequence[float]) -> list[float]:
    """Simple period returns. Non-positive prices break the ratio and are
    skipped rather than allowed to produce an infinity."""
    out: list[float] = []
    for prev, curr in zip(values, values[1:]):
        if prev and prev > 0 and curr > 0:
            out.append(curr / prev - 1.0)
    return out


def volatility(values: Sequence[float]) -> Optional[float]:
    """Annualised standard deviation of daily returns, in percent.

    Returns None rather than a number below the observation floor: an
    annualised vol from six days is arithmetic, not a measurement.
    """
    rets = _returns(values)
    if len(rets) < MIN_RETURN_OBSERVATIONS:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round(math.sqrt(var) * math.sqrt(TRADING_DAYS) * 100, 2)


def max_drawdown(values: Sequence[float]) -> Optional[dict[str, Any]]:
    """Deepest peak-to-trough decline over the window.

    Reports the peak and trough values as well as the percentage, because
    "−14.7%" is a statistic and "from $71,500 down to $61,000" is a fact
    somebody can recognise.
    """
    if len(values) < 2:
        return None
    peak = values[0]
    worst = 0.0
    peak_at = trough_at = 0
    best_peak = best_trough = values[0]
    for i, value in enumerate(values):
        if value > peak:
            peak = value
            peak_at = i
        if peak > 0:
            decline = value / peak - 1.0
            if decline < worst:
                worst = decline
                trough_at = i
                best_peak, best_trough = peak, value
    if worst == 0.0:
        # A series that only ever rose has no drawdown — that is a real
        # answer, not a missing one.
        return {"pct": 0.0, "peak": round(values[0], 2), "trough": round(values[0], 2),
                "peak_index": 0, "trough_index": 0}
    return {
        "pct": round(worst * 100, 2),
        "peak": round(best_peak, 2),
        "trough": round(best_trough, 2),
        "peak_index": peak_at,
        "trough_index": trough_at,
    }


def correlation(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    """Pearson correlation of two return series.

    Computed on *returns*, never on price levels: two stocks that both drift
    upward correlate at ~0.99 on levels regardless of whether their daily
    moves have anything to do with each other, which is the classic way to
    make a concentrated book look diversified.
    """
    ra, rb = _returns(a), _returns(b)
    n = min(len(ra), len(rb))
    if n < MIN_RETURN_OBSERVATIONS:
        return None
    ra, rb = ra[-n:], rb[-n:]
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra)
    vb = sum((y - mb) ** 2 for y in rb)
    if va <= 0 or vb <= 0:
        return None
    return round(cov / math.sqrt(va * vb), 3)


def correlation_matrix(
    closes_by_ticker: dict[str, list[tuple[str, float]]],
) -> Optional[dict[str, Any]]:
    """Pairwise correlations across holdings, on the overlapping date axis.

    Only pairs with enough shared history are computed; a pair that does not
    clear the floor is omitted rather than reported as uncorrelated, because
    "we could not measure it" and "they move independently" are opposite
    conclusions.
    """
    aligned = {t: dict(series) for t, series in closes_by_ticker.items() if series}
    tickers = sorted(aligned)
    if len(tickers) < 2:
        return None

    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            common = sorted(set(aligned[a]) & set(aligned[b]))
            if len(common) < MIN_RETURN_OBSERVATIONS + 1:
                continue
            rho = correlation([aligned[a][d] for d in common],
                              [aligned[b][d] for d in common])
            if rho is None:
                continue
            pairs.append({"a": a, "b": b, "rho": rho, "sessions": len(common)})

    if not pairs:
        return None
    pairs.sort(key=lambda p: p["rho"], reverse=True)
    high = [p for p in pairs if p["rho"] >= 0.7]
    return {
        "pairs": pairs,
        "highest": pairs[0],
        "lowest": pairs[-1],
        "high_count": len(high),
        # The mean pairwise correlation is the single most useful summary of
        # whether a book is diversified in the way its holder thinks it is.
        "mean_rho": round(sum(p["rho"] for p in pairs) / len(pairs), 3),
        "tickers": tickers,
    }


def benchmark_comparison(
    portfolio_points: list[dict[str, Any]],
    benchmark_closes: list[tuple[str, float]],
    *,
    symbol: str,
    label: str,
) -> Optional[dict[str, Any]]:
    """Portfolio return against a benchmark over the same sessions.

    Both series are rebased to their first *common* date so the comparison is
    like-for-like; rebasing to their own first dates would compare different
    windows and manufacture outperformance out of a calendar mismatch.

    The difference is reported as `outperformance` — a plain return
    difference. It is explicitly **not** alpha: no beta is estimated, no
    risk-free rate is subtracted, and calling it alpha would claim a
    risk-adjusted result this system does not compute.
    """
    if not portfolio_points or not benchmark_closes:
        return None
    bench = dict(benchmark_closes)
    common = [p for p in portfolio_points if p["date"] in bench]
    if len(common) < 2:
        return None

    p_start, p_end = common[0]["value"], common[-1]["value"]
    b_start, b_end = bench[common[0]["date"]], bench[common[-1]["date"]]
    if p_start <= 0 or b_start <= 0:
        return None

    p_ret = (p_end / p_start - 1.0) * 100
    b_ret = (b_end / b_start - 1.0) * 100

    return {
        "symbol": symbol,
        "label": label,
        "portfolio_return_pct": round(p_ret, 2),
        "benchmark_return_pct": round(b_ret, 2),
        "outperformance_pct": round(p_ret - b_ret, 2),
        # Named so the UI cannot accidentally present it as a risk-adjusted
        # figure, and so the caveat travels with the number.
        "basis": "simple return difference over the same sessions — not alpha; "
                 "no beta is estimated and no risk-free rate is subtracted",
        "sessions": len(common),
        "from": common[0]["date"],
        "to": common[-1]["date"],
        # Rebased to 100 at the common start so both lines share one axis.
        "points": [
            {"date": p["date"],
             "portfolio": round(p["value"] / p_start * 100, 3),
             "benchmark": round(bench[p["date"]] / b_start * 100, 3)}
            for p in common
        ],
    }


def contributions(
    valuation_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Each holding's share of the book's total gain or loss.

    Contribution is in *money*, then expressed as a share of the total P&L —
    not `weight × return`, which is only equal to it when weights are taken at
    the start of the period, and these weights are current. Money always adds
    up; the weighted-return identity does not once positions have moved.

    When the totals net to roughly zero the share is undefined rather than
    enormous: a +$500 and a −$490 book has a $10 net, and reporting the winner
    as "+5000% of P&L" would be arithmetically true and completely useless.
    """
    priced = [r for r in valuation_rows if r.get("priced") and r.get("pnl") is not None]
    if not priced:
        return []
    total_pnl = sum(r["pnl"] for r in priced)
    gross = sum(abs(r["pnl"]) for r in priced)
    # Net near zero relative to the gross means the book's winners and losers
    # cancel; shares of that net are meaningless.
    meaningful = gross > 0 and abs(total_pnl) > gross * 0.05

    out = [
        {
            "ticker": r["ticker"],
            "pnl": r["pnl"],
            "pnl_pct": r.get("pnl_pct"),
            "contribution_pct": (
                round(r["pnl"] / total_pnl * 100, 1) if meaningful else None
            ),
            # Always defined: share of total movement regardless of sign,
            # which answers "who moved the needle" even in a netting book.
            "share_of_movement_pct": round(abs(r["pnl"]) / gross * 100, 1) if gross else None,
        }
        for r in priced
    ]
    out.sort(key=lambda r: abs(r["pnl"]), reverse=True)
    return out
