"""Clerk JWT verification — hermetic (local RSA keypair, no JWKS fetch)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from src.services import clerk_auth

ISSUER = "https://test-instance.clerk.accounts.dev"


@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


class _StubSigningKey:
    def __init__(self, key):
        self.key = key


class _StubJWKSClient:
    def __init__(self, public_key):
        self._public = public_key

    def get_signing_key_from_jwt(self, _token):
        return _StubSigningKey(self._public)


@pytest.fixture()
def configured(monkeypatch, keypair):
    _, public = keypair
    monkeypatch.setenv("CLERK_JWKS_URL", f"{ISSUER}/.well-known/jwks.json")
    monkeypatch.setenv("CLERK_ISSUER", ISSUER)
    monkeypatch.setattr(clerk_auth, "_jwks_client", _StubJWKSClient(public))
    yield
    clerk_auth._reset_for_testing()


def _token(private, *, sub="user_123", iss=ISSUER, exp_offset=600) -> str:
    return jwt.encode(
        {"sub": sub, "iss": iss, "exp": int(time.time()) + exp_offset},
        private,
        algorithm="RS256",
    )


class TestVerifyToken:
    def test_valid_token_returns_sub(self, configured, keypair):
        private, _ = keypair
        assert clerk_auth.verify_token(_token(private)) == "user_123"

    def test_expired_token_rejected(self, configured, keypair):
        private, _ = keypair
        assert clerk_auth.verify_token(_token(private, exp_offset=-120)) is None

    def test_wrong_issuer_rejected(self, configured, keypair):
        private, _ = keypair
        assert clerk_auth.verify_token(_token(private, iss="https://evil.example")) is None

    def test_garbage_rejected(self, configured):
        assert clerk_auth.verify_token("not-a-jwt") is None

    def test_wrong_signature_rejected(self, configured):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        assert clerk_auth.verify_token(_token(other)) is None


def _stub_request():
    """Minimal stand-in for fastapi.Request: the dependency only touches .state."""
    return SimpleNamespace(state=SimpleNamespace())


class TestDependencies:
    def test_require_user_valid(self, configured, keypair):
        private, _ = keypair
        request = _stub_request()
        assert clerk_auth.require_clerk_user(request, f"Bearer {_token(private)}") == "user_123"
        # The middleware reads the verified user from request.state for logging.
        assert request.state.clerk_user == "user_123"

    def test_require_user_missing_token(self, configured):
        with pytest.raises(HTTPException) as err:
            clerk_auth.require_clerk_user(_stub_request(), "")
        assert err.value.status_code == 401

    def test_require_user_unconfigured_is_503(self, monkeypatch):
        monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
        clerk_auth._reset_for_testing()
        with pytest.raises(HTTPException) as err:
            clerk_auth.require_clerk_user(_stub_request(), "Bearer whatever")
        assert err.value.status_code == 503

    def test_optional_user_never_raises(self, monkeypatch):
        monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
        clerk_auth._reset_for_testing()
        assert clerk_auth.optional_clerk_user(_stub_request(), "Bearer junk") is None


class TestAuthorizedParties:
    """A session token is for an origin, and the backend can say which it accepts."""

    @staticmethod
    def _with_azp(private, azp, **kw):
        claims = {"sub": "user_123", "iss": ISSUER, "exp": int(time.time()) + 600}
        if azp is not None:
            claims["azp"] = azp
        return jwt.encode(claims, private, algorithm="RS256")

    def test_unset_checks_nothing_so_nobody_is_locked_out(self, configured, keypair, monkeypatch):
        monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)
        private, _ = keypair
        assert clerk_auth.verify_token(self._with_azp(private, "https://anywhere.example")) == "user_123"

    def test_a_listed_origin_is_accepted_whatever_its_case_or_trailing_slash(self, configured, keypair, monkeypatch):
        monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://app.example.com, https://other.example/")
        private, _ = keypair
        assert clerk_auth.verify_token(self._with_azp(private, "https://APP.example.com/")) == "user_123"
        assert clerk_auth.verify_token(self._with_azp(private, "https://other.example")) == "user_123"

    def test_an_unlisted_origin_is_refused_by_both_entry_points(self, configured, keypair, monkeypatch):
        monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://app.example.com")
        private, _ = keypair
        token = self._with_azp(private, "https://preview-abc.vercel.app")
        assert clerk_auth.verify_token(token) is None
        assert clerk_auth.verify_token_claims(token) is None

    def test_a_token_that_names_no_origin_is_not_refused_for_it(self, configured, keypair, monkeypatch):
        """Clerk does not put `azp` on every token; its own SDK treats absence the same way."""
        monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://app.example.com")
        private, _ = keypair
        assert clerk_auth.verify_token(self._with_azp(private, None)) == "user_123"

    def test_the_check_adds_to_signature_and_issuer_it_does_not_replace_them(self, configured, keypair, monkeypatch):
        monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://app.example.com")
        private, _ = keypair
        forged = jwt.encode({"sub": "user_123", "iss": "https://evil.example", "azp": "https://app.example.com",
                             "exp": int(time.time()) + 600}, private, algorithm="RS256")
        assert clerk_auth.verify_token(forged) is None
