"""Marketaux normalization and truthful provider state without a live API call."""

from unittest.mock import Mock

from src.providers.vendors.news_vendors import MarketauxVendor


def test_marketaux_maps_only_symbol_sentiment(monkeypatch):
    monkeypatch.setenv("MARKETAUX_API_KEY", "test-token-placeholder")
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"data": [{
        "title": "Company announces results",
        "source": "Example Publisher",
        "url": "https://example.org/article",
        "published_at": "2026-09-28T09:00:00Z",
        "description": "Reported results.",
        "image_url": "https://example.org/image.jpg",
        "entities": [
            {"symbol": "MSFT", "sentiment_score": -0.8},
            {"symbol": "AAPL", "sentiment_score": 0.35},
        ],
    }]}
    session = Mock()
    session.headers = {}
    session.request.return_value = response
    vendor = MarketauxVendor(session=session)

    assert vendor.health_snapshot()["health_state"] == "IDLE"
    item = vendor.get_news("aapl")[0]
    assert item.source == "Example Publisher"
    assert item.image_url == "https://example.org/image.jpg"
    assert item.sentiment_score == 0.35
    assert item.sentiment_source == "marketaux"
    assert item.tickers == ["MSFT", "AAPL"]
    assert session.request.call_args.kwargs["params"]["symbols"] == "AAPL"
    assert vendor.health_snapshot()["health_state"] == "HEALTHY"


def test_marketaux_does_not_assign_other_entity_sentiment(monkeypatch):
    monkeypatch.setenv("MARKETAUX_API_KEY", "test-token-placeholder")
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"data": [{
        "title": "Sector update", "entities": [{"symbol": "MSFT", "sentiment_score": 0.8}],
    }]}
    session = Mock()
    session.headers = {}
    session.request.return_value = response

    item = MarketauxVendor(session=session).get_news("AAPL")[0]
    assert item.sentiment_score is None
    assert item.sentiment_source is None
