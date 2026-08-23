"""Portfolio arithmetic has to be checkable by hand.

Every figure this module produces is shown to a user as a fact about their
own money, so each one is pinned here against a number worked out on paper
rather than against whatever the implementation happened to return. The
properties that matter most are the ones that would flatter a portfolio if
they broke quietly: concentration understated by splitting lots, coverage
overstated by dropping unanalysed names, and risk presented as something it
is not.
"""

from __future__ import annotations

import pytest

from src.services.portfolio_intelligence import (
    analyse,
    concentration_band,
    headlines,
    herfindahl,
)


def _pos(ticker: str, shares: float, price: float) -> dict:
    return {"ticker": ticker, "shares": shares, "average_price": price}


def test_an_empty_book_reports_that_rather_than_zeroes():
    # Zeroed concentration on an empty book would read as "diversified",
    # which is a claim about a portfolio that does not exist.
    report = analyse([], {})
    assert report["covered"] is False
    assert report["positions"] == 0


def test_two_lots_of_one_ticker_are_one_bet():
    """The failure this guards: splitting a holding across two rows halves
    its apparent weight and makes a concentrated book look diversified."""
    split = analyse([_pos("AAPL", 5, 100), _pos("AAPL", 5, 100), _pos("KO", 10, 100)], {})
    merged = analyse([_pos("AAPL", 10, 100), _pos("KO", 10, 100)], {})
    assert split["positions"] == merged["positions"] == 2
    assert split["concentration"]["hhi"] == merged["concentration"]["hhi"]
    assert split["concentration"]["largest"]["weight_pct"] == pytest.approx(50.0)


def test_herfindahl_matches_the_published_scale():
    # One position is the maximum; ten equal positions score 1000. These are
    # the anchors the band thresholds are defined against.
    assert herfindahl({"A": 100.0}) == 10_000.0
    assert herfindahl({chr(65 + i): 10.0 for i in range(10)}) == 1_000.0
    assert concentration_band(10_000.0) == "concentrated"
    assert concentration_band(1_000.0) == "diversified"
    assert concentration_band(2_000.0) == "moderate"


def test_weights_are_cost_basis_and_say_so():
    # 10 x 200 = 2000 against 5 x 100 = 500 → 80/20.
    report = analyse([_pos("AAPL", 10, 200), _pos("NVDA", 5, 100)], {})
    assert report["total_basis"] == 2500.0
    assert report["concentration"]["largest"] == {"ticker": "AAPL", "weight_pct": 80.0}
    assert "cost basis" in report["weight_basis"]


def test_unanalysed_positions_are_counted_not_dropped():
    """A book where half the names were never scored must not present its
    figures as though they covered everything."""
    report = analyse(
        [_pos("AAPL", 10, 200), _pos("NVDA", 5, 100)],
        {"AAPL": {"risk_score": 40, "verdict": "Buy", "sector": "Technology"}},
    )
    assert report["coverage"] == {
        "scored": 1,
        "unscored": 1,
        "covered_pct": 80.0,
        "unscored_tickers": ["NVDA"],
    }
    # And the gap is stated in prose, not left for the reader to infer.
    assert any("never been analysed" in h["text"] for h in headlines(report))


def test_risk_share_attributes_the_whole_book_and_nothing_more():
    """Risk shares are shares — they have to sum to 100% across scored names,
    or the panel is attributing risk that does not exist."""
    report = analyse(
        [_pos("A", 1, 100), _pos("B", 1, 100), _pos("C", 1, 100)],
        {
            "A": {"risk_score": 90, "verdict": "Hold"},
            "B": {"risk_score": 30, "verdict": "Hold"},
            "C": {"risk_score": 30, "verdict": "Hold"},
        },
    )
    shares = [r["risk_share_pct"] for r in report["risk"]["top_contributors"]]
    assert sum(shares) == pytest.approx(100.0, abs=0.3)
    # Equal weights, so the riskiest name must lead.
    assert report["risk"]["top_contributors"][0]["ticker"] == "A"
    # Equal weights and 90/30/30 → weighted mean 50.
    assert report["risk"]["weighted_score"] == pytest.approx(50.0, abs=0.1)


def test_risk_is_never_presented_as_a_portfolio_volatility():
    """The claim being guarded: no covariance is estimated anywhere, so the
    output must not imply a portfolio-level volatility figure."""
    report = analyse([_pos("A", 1, 100)], {"A": {"risk_score": 50, "verdict": "Hold"}})
    basis = report["risk"]["basis"].lower()
    assert "not a portfolio volatility" in basis
    assert "no covariance" in basis


def test_sector_exposure_reports_what_it_does_not_know():
    report = analyse(
        [_pos("A", 1, 100), _pos("B", 1, 100)],
        {
            "A": {"risk_score": 10, "verdict": "Hold", "sector": "Technology"},
            "B": {"risk_score": 10, "verdict": "Hold"},  # no sector recorded
        },
    )
    assert report["sectors"]["rows"] == [{"sector": "Technology", "weight_pct": 50.0}]
    assert report["sectors"]["unknown_pct"] == 50.0


def test_verdict_mix_is_weighted_by_capital_not_by_count():
    # One big bearish name outweighs two small bullish ones — a count would
    # say the opposite, and the money is what is at stake.
    report = analyse(
        [_pos("BIG", 8, 100), _pos("S1", 1, 100), _pos("S2", 1, 100)],
        {
            "BIG": {"risk_score": 50, "verdict": "Strong Sell"},
            "S1": {"risk_score": 50, "verdict": "Buy"},
            "S2": {"risk_score": 50, "verdict": "Buy"},
        },
    )
    assert report["verdict_mix"] == {"bullish": 20.0, "neutral": 0.0, "bearish": 80.0}


def test_a_balanced_book_produces_no_alarming_prose():
    """Headlines fire on thresholds, not on a quota. Ten equal, fully scored,
    sector-spread names should have nothing worth saying."""
    positions = [_pos(f"T{i}", 1, 100) for i in range(10)]
    analyses = {
        f"T{i}": {"risk_score": 40, "verdict": "Hold", "sector": f"Sector{i % 5}"}
        for i in range(10)
    }
    assert headlines(analyse(positions, analyses)) == []


def test_malformed_positions_are_skipped_not_crashed_on():
    report = analyse(
        [
            _pos("AAPL", 10, 200),
            {"ticker": "BAD", "shares": "not a number", "average_price": 10},
            {"ticker": "", "shares": 5, "average_price": 5},
            _pos("NEG", -5, 10),
        ],
        {},
    )
    assert report["positions"] == 1
    assert report["concentration"]["largest"]["ticker"] == "AAPL"


# ══════════════════════════════════════════════════════════════════════════
# VALUATION
#
# These figures are the ones a holder checks against their broker, so each is
# pinned to a hand-worked number. The property that matters most is the one
# that would be invisible if it broke: a holding whose price could not be
# fetched must never be valued at its own cost, because that reports it as
# exactly break-even — a specific claim, and a false one.
# ══════════════════════════════════════════════════════════════════════════

from src.services.portfolio_intelligence import value_curve, value_positions


def _quote(price=None, change_1d=None, error=None, stale=False):
    if error:
        return {"error": error}
    return {"price": price, "change_1d": change_1d, "stale": stale, "source": "polygon"}


def test_one_holding_in_profit_matches_the_arithmetic_by_hand():
    # 34 x 305.93 = 10,401.62 invested; 34 x 309.35 = 10,517.90 current.
    report = value_positions([_pos("AAPL", 34, 305.93)], {"AAPL": _quote(309.35)})
    row = report["rows"][0]
    assert row["invested"] == 10_401.62
    assert row["current_value"] == 10_517.90
    assert row["pnl"] == 116.28
    assert row["pnl_pct"] == pytest.approx(1.12, abs=0.01)


def test_a_holding_at_a_loss_carries_the_sign_through():
    # 10 x 200 = 2,000 invested; 10 x 150 = 1,500 → −500, −25%.
    report = value_positions([_pos("X", 10, 200)], {"X": _quote(150)})
    row = report["rows"][0]
    assert row["pnl"] == -500.0
    assert row["pnl_pct"] == -25.0
    assert report["totals"]["pnl"] == -500.0


def test_an_unchanged_price_is_exactly_zero_not_a_rounding_artefact():
    report = value_positions([_pos("X", 3, 50)], {"X": _quote(50)})
    assert report["rows"][0]["pnl"] == 0.0
    assert report["rows"][0]["pnl_pct"] == 0.0


def test_multiple_holdings_total_to_the_sum_of_their_parts():
    report = value_positions(
        [_pos("A", 10, 100), _pos("B", 5, 200), _pos("C", 2, 50)],
        {"A": _quote(110), "B": _quote(180), "C": _quote(50)},
    )
    totals = report["totals"]
    assert totals["invested"] == 1000 + 1000 + 100
    assert totals["current_value"] == 1100 + 900 + 100
    assert totals["pnl"] == 0.0  # +100 −100 +0
    assert totals["pnl_pct"] == 0.0


def test_a_missing_price_is_never_silently_the_buy_price():
    """The failure this exists for: valuing an unreachable holding at its own
    cost reports it as exactly break-even, which reads as a measurement."""
    report = value_positions(
        [_pos("A", 10, 100), _pos("B", 10, 100)],
        {"A": _quote(120), "B": _quote(error="no data")},
    )
    unpriced = next(r for r in report["rows"] if r["ticker"] == "B")
    assert unpriced["priced"] is False
    assert unpriced["current_value"] is None
    assert unpriced["pnl"] is None
    assert unpriced["price_note"]

    # And the totals must cover only what was actually priced, and say so.
    totals = report["totals"]
    assert totals["invested"] == 2000.0        # whole book's cost is still known
    assert totals["priced_invested"] == 1000.0  # but only half was valued
    assert totals["current_value"] == 1200.0
    assert totals["pnl"] == 200.0
    assert report["coverage"] == {
        "priced": 1, "unpriced": 1, "unpriced_tickers": ["B"], "priced_pct": 50.0,
    }


def test_a_book_with_no_reachable_prices_reports_no_value_rather_than_zero():
    report = value_positions([_pos("A", 10, 100)], {"A": _quote(error="unavailable")})
    assert report["totals"]["current_value"] is None
    assert report["totals"]["pnl"] is None
    assert report["totals"]["pnl_pct"] is None


def test_a_zero_cost_holding_has_a_pnl_but_no_return_percentage():
    """A spin-off recorded at zero cost has a defined gain and an undefined
    return; an infinity here would have to be special-cased in every caller."""
    report = value_positions([_pos("FREE", 10, 0)], {"FREE": _quote(25)})
    row = report["rows"][0]
    assert row["invested"] == 0.0
    assert row["pnl"] == 250.0
    assert row["pnl_pct"] is None
    assert report["totals"]["pnl_pct"] is None


def test_zero_and_negative_quantities_are_dropped():
    report = value_positions(
        [_pos("A", 0, 100), _pos("B", -5, 100), _pos("C", 1, 100)],
        {"A": _quote(1), "B": _quote(1), "C": _quote(100)},
    )
    assert [r["ticker"] for r in report["rows"]] == ["C"]


def test_two_lots_value_at_their_weighted_average_cost():
    # 10 @ 100 and 10 @ 200 → 20 shares at an average of 150.
    report = value_positions(
        [_pos("A", 10, 100), _pos("A", 10, 200)], {"A": _quote(150)},
    )
    assert len(report["rows"]) == 1
    row = report["rows"][0]
    assert row["shares"] == 20
    assert row["avg_price"] == 150.0
    assert row["pnl"] == 0.0


def test_a_nonsense_quote_is_treated_as_no_quote():
    for bad in ({"price": 0}, {"price": -5}, {"price": None}, {}, None, "nope"):
        report = value_positions([_pos("A", 1, 10)], {"A": bad})
        assert report["rows"][0]["priced"] is False, bad


def test_todays_move_is_money_derived_from_the_same_percentage_shown_elsewhere():
    # 100 shares now worth 110 each = 11,000, after a +10% day → the day
    # opened at 10,000, so today contributed +1,000.
    report = value_positions([_pos("A", 100, 50)], {"A": _quote(110, change_1d=10.0)})
    assert report["totals"]["day_pnl"] == pytest.approx(1000.0, abs=0.5)
    assert report["totals"]["day_pnl_pct"] == pytest.approx(10.0, abs=0.1)


def test_weights_follow_current_value_once_prices_are_known():
    """Cost-basis weights call a position that has doubled the smaller bet.
    Once a price exists, the current value is the honest denominator."""
    positions = [_pos("UP", 10, 100), _pos("FLAT", 10, 100)]
    at_cost = analyse(positions, {})
    assert at_cost["concentration"]["largest"]["weight_pct"] == 50.0
    assert "cost basis" in at_cost["weight_basis"]

    at_market = analyse(positions, {}, {"UP": 3000.0, "FLAT": 1000.0})
    assert at_market["concentration"]["largest"] == {"ticker": "UP", "weight_pct": 75.0}
    assert "current market value" in at_market["weight_basis"]


def test_an_unpriced_ticker_falls_back_to_its_cost_inside_market_weights():
    # One unreachable quote must degrade precision, not collapse the panel.
    report = analyse(
        [_pos("A", 10, 100), _pos("B", 10, 100)], {}, {"A": 3000.0},
    )
    assert report["positions"] == 2
    assert report["concentration"]["largest"]["ticker"] == "A"


# ── historical curve ──────────────────────────────────────────────────────

def _series(*pairs):
    return list(pairs)


def test_the_curve_marks_todays_shares_against_real_closes():
    curve = value_curve(
        [_pos("A", 2, 100), _pos("B", 1, 50)],
        {
            "A": _series(("2026-01-01", 100.0), ("2026-01-02", 110.0),
                         ("2026-01-03", 120.0), ("2026-01-04", 130.0),
                         ("2026-01-05", 140.0)),
            "B": _series(("2026-01-01", 50.0), ("2026-01-02", 50.0),
                         ("2026-01-03", 50.0), ("2026-01-04", 50.0),
                         ("2026-01-05", 50.0)),
        },
    )
    assert curve is not None
    # 2 x 100 + 1 x 50 = 250 on day one; 2 x 140 + 50 = 330 on day five.
    assert curve["points"][0] == {"date": "2026-01-01", "value": 250.0}
    assert curve["points"][-1] == {"date": "2026-01-05", "value": 330.0}
    # Baseline covers exactly the holdings the curve is drawn from.
    assert curve["invested_baseline"] == 250.0
    # And the window's meaning is carried with it, not left to the caller.
    assert "not a record of past positions" in curve["assumption"]


def test_only_dates_every_holding_has_a_close_for_are_plotted():
    """Forward-filling a gap invents a price that was never observed; the
    day is dropped instead and the shortfall is visible in the axis."""
    curve = value_curve(
        [_pos("A", 1, 10), _pos("B", 1, 10)],
        {
            "A": _series(("d1", 1.0), ("d2", 1.0), ("d3", 1.0), ("d4", 1.0),
                         ("d5", 1.0), ("d6", 1.0)),
            "B": _series(("d1", 1.0), ("d3", 1.0), ("d4", 1.0), ("d5", 1.0),
                         ("d6", 1.0)),
        },
    )
    assert [p["date"] for p in curve["points"]] == ["d1", "d3", "d4", "d5", "d6"]


def test_a_holding_with_no_series_is_excluded_and_named():
    curve = value_curve(
        [_pos("A", 1, 10), _pos("GONE", 5, 10)],
        {"A": _series(*[(f"d{i}", 10.0) for i in range(6)])},
    )
    assert curve["tickers"] == ["A"]
    assert curve["excluded_tickers"] == ["GONE"]
    # The baseline covers only the plotted holding, so the gap between the
    # curve and the baseline is P&L on the same set.
    assert curve["invested_baseline"] == 10.0


def test_too_little_history_produces_no_curve_rather_than_a_stub():
    assert value_curve([_pos("A", 1, 10)], {"A": _series(("d1", 1.0), ("d2", 2.0))}) is None
    assert value_curve([_pos("A", 1, 10)], {}) is None
    assert value_curve([], {"A": _series(("d1", 1.0))}) is None


def test_a_top_three_share_is_not_reported_when_there_is_no_tail():
    """"100% of capital sits in 3 names" is arithmetic, not a finding, when
    the book has exactly three names. A share needs something to be a share
    of before it says anything."""
    three = analyse(
        [_pos("A", 6, 100), _pos("B", 3, 100), _pos("C", 1, 100)],
        {t: {"risk_score": 50, "verdict": "Hold"} for t in ("A", "B", "C")},
    )
    texts = " ".join(h["text"] for h in headlines(three))
    assert "100.0% of" not in texts
    # The largest single weight is still worth saying, and is not tautological.
    assert "A is 60.0%" in texts
    # The risk line needs a tail too, and there is none here.
    assert "weighted risk exposure" not in texts


def test_the_top_three_share_is_reported_once_a_tail_exists():
    positions = [_pos("BIG", 70, 100)] + [_pos(f"T{i}", 5, 100) for i in range(6)]
    analyses = {p["ticker"]: {"risk_score": 50, "verdict": "Hold"} for p in positions}
    texts = " ".join(h["text"] for h in headlines(analyse(positions, analyses)))
    assert "of 7 names" in texts


def test_the_concentration_headline_names_the_denominator_it_used():
    positions = [_pos("A", 8, 100), _pos("B", 1, 100), _pos("C", 1, 100), _pos("D", 1, 100)]
    at_cost = " ".join(h["text"] for h in headlines(analyse(positions, {})))
    assert "cost basis" in at_cost
    at_market = " ".join(
        h["text"] for h in headlines(analyse(positions, {}, {"A": 9000.0, "B": 100.0}))
    )
    assert "market value" in at_market
