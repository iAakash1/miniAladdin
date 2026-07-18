"""Street & Insider Intelligence engine (v4.5 P0-B) — deterministic tests."""

from __future__ import annotations

from src.providers.schemas import EarningsSurprise, RecommendationMonth, StreetData
from src.services import street_intelligence as si


def _month(period: str, sb: int, b: int, h: int, s: int, ss: int) -> RecommendationMonth:
    return RecommendationMonth(period=period, strong_buy=sb, buy=b, hold=h, sell=s, strong_sell=ss)


def test_none_input_and_empty_data():
    assert si.build(None) is None
    assert si.build(StreetData(symbol="X")) is None


def test_improving_recommendations_read_positive():
    street = StreetData(
        symbol="NVDA",
        recommendations=[
            _month("2026-07-01", 30, 20, 8, 1, 0),  # newest: 85% buy
            _month("2026-04-01", 20, 18, 18, 3, 0),  # oldest: 64% buy
        ],
    )
    block = si.build(street)
    recs = block["recommendations"]
    assert recs["trend"] == "improving"
    assert recs["buy_ratio"] == round(50 / 59, 3)
    assert any(f["tone"] == "pos" for f in block["findings"])


def test_deteriorating_trend_detected():
    street = StreetData(
        symbol="X",
        recommendations=[
            _month("2026-07-01", 5, 10, 20, 10, 5),   # newest: 30% buy
            _month("2026-04-01", 20, 15, 10, 3, 2),   # oldest: 70% buy
        ],
    )
    assert si.build(street)["recommendations"]["trend"] == "deteriorating"


def test_perfect_beat_streak():
    street = StreetData(
        symbol="AAPL",
        surprises=[
            EarningsSurprise(period="2026-06-30", actual=2.1, estimate=2.0, surprise_pct=5.0),
            EarningsSurprise(period="2026-03-31", actual=1.9, estimate=1.8, surprise_pct=5.56),
        ],
    )
    block = si.build(street)
    assert block["surprises"]["beats"] == 2
    assert "all 2 reported quarters" in block["findings"][0]["text"]
    assert block["findings"][0]["tone"] == "pos"


def test_all_misses_read_negative():
    street = StreetData(
        symbol="X",
        surprises=[EarningsSurprise(period="2026-06-30", actual=1.0, estimate=1.2, surprise_pct=-16.7)],
    )
    block = si.build(street)
    assert block["surprises"]["beats"] == 0
    assert block["findings"][0]["tone"] == "neg"


def test_insider_thresholds():
    buying = si.build(StreetData(symbol="X", insider_mspr=45.0))
    assert buying["insider"]["read"] == "buying"
    assert buying["findings"][0]["tone"] == "pos"

    selling = si.build(StreetData(symbol="X", insider_mspr=-30.0))
    assert selling["insider"]["read"] == "selling"
    assert selling["findings"][0]["tone"] == "neg"

    neutral = si.build(StreetData(symbol="X", insider_mspr=5.0))
    assert neutral["insider"]["read"] == "neutral"
    assert neutral["findings"] == []  # neutral insider activity is not a finding


def test_deterministic():
    street = StreetData(
        symbol="X",
        recommendations=[_month("2026-07-01", 10, 10, 10, 2, 1)],
        surprises=[EarningsSurprise(period="2026-06-30", actual=1.0, estimate=0.9, surprise_pct=11.1)],
        insider_mspr=25.0,
    )
    assert si.build(street) == si.build(street)
