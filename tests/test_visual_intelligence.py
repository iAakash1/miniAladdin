"""Verified-identity visual policy: Logo.dev only, no decorative imagery."""

from unittest.mock import patch

from fastapi.testclient import TestClient

import api.index as api
from src.services import visual_intelligence as vi


def setup_function():
    vi.reset_for_tests()


def test_identity_is_absent_without_the_publishable_key(monkeypatch):
    monkeypatch.delenv("LOGO_DEV_PUBLISHABLE_KEY", raising=False)
    assert vi.identity("AAPL", "apple.com") is None


def test_identity_uses_only_the_publishable_key_in_the_client_url(monkeypatch):
    monkeypatch.setenv("LOGO_DEV_PUBLISHABLE_KEY", "fixture-publishable-key")
    monkeypatch.setenv("LOGO_DEV_SECRET_KEY", "fixture-secret-key")
    mark = vi.identity("AAPL", "apple.com")
    assert mark is not None
    assert "fixture-publishable-key" in mark["logo_url"]
    assert "fixture-secret-key" not in str(mark)


def test_domain_recovery_is_cached(monkeypatch):
    monkeypatch.setenv("LOGO_DEV_SECRET_KEY", "fixture-secret-key")
    with patch.object(vi._logo, "search_brand", return_value=[{"domain": "example.com"}]) as search:
        assert vi.resolve_domain("EXM", "Example Incorporated") == "example.com"
        assert vi.resolve_domain("EXM", "Example Incorporated") == "example.com"
    assert search.call_count == 1


def test_diagnostics_declares_identity_only_and_never_exposes_keys(monkeypatch):
    monkeypatch.setenv("LOGO_DEV_PUBLISHABLE_KEY", "fixture-publishable-key")
    monkeypatch.setenv("LOGO_DEV_SECRET_KEY", "fixture-secret-key")
    diagnostics = vi.diagnostics()
    assert diagnostics["policy"] == "verified_identity_only"
    assert diagnostics["logo_dev"]["configured"] is True
    assert diagnostics["logo_dev"]["secret_configured"] is True
    assert "fixture" not in str(diagnostics)


def test_media_compatibility_route_returns_no_context(monkeypatch):
    monkeypatch.setenv("LOGO_DEV_PUBLISHABLE_KEY", "fixture-publishable-key")
    with patch.object(api.providers.fundamentals, "profile_evidence", return_value=[]):
        payload = TestClient(api.app).get("/api/company/AAPL/media").json()
    assert payload["context"] is None
    assert payload["visual_policy"] == "verified_identity_only"
