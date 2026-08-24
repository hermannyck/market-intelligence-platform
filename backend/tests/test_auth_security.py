"""Phase 13 tests for app.auth.security."""
from __future__ import annotations

from datetime import timedelta

from app.auth import security


def test_hash_and_verify_password_roundtrip():
    hashed = security.hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert security.verify_password("correct horse battery staple", hashed)
    assert not security.verify_password("wrong password", hashed)


def test_create_and_decode_access_token_roundtrip():
    token = security.create_access_token(subject="user@example.com")
    assert security.decode_access_token(token) == "user@example.com"


def test_decode_access_token_rejects_garbage():
    assert security.decode_access_token("not-a-real-token") is None


def test_decode_access_token_rejects_expired():
    token = security.create_access_token(subject="user@example.com", expires_delta=timedelta(seconds=-1))
    assert security.decode_access_token(token) is None
