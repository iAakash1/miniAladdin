"""Clerk JWT verification — hermetic (local RSA keypair, no JWKS fetch)."""

from __future__ import annotations

import time

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


class TestDependencies:
    def test_require_user_valid(self, configured, keypair):
        private, _ = keypair
        assert clerk_auth.require_clerk_user(f"Bearer {_token(private)}") == "user_123"

    def test_require_user_missing_token(self, configured):
        with pytest.raises(HTTPException) as err:
            clerk_auth.require_clerk_user("")
        assert err.value.status_code == 401

    def test_require_user_unconfigured_is_503(self, monkeypatch):
        monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
        clerk_auth._reset_for_testing()
        with pytest.raises(HTTPException) as err:
            clerk_auth.require_clerk_user("Bearer whatever")
        assert err.value.status_code == 503

    def test_optional_user_never_raises(self, monkeypatch):
        monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
        clerk_auth._reset_for_testing()
        assert clerk_auth.optional_clerk_user("Bearer junk") is None
