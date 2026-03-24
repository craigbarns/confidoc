"""Tests for core security utilities."""

import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    get_password_hash,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "TestPassword123!"
        hashed = get_password_hash(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self):
        hashed = get_password_hash("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_empty_password_fails(self):
        hashed = get_password_hash("some_password")
        assert not verify_password("", hashed)

    def test_different_hashes_for_same_password(self):
        h1 = get_password_hash("same_password")
        h2 = get_password_hash("same_password")
        assert h1 != h2  # bcrypt salt makes them different

    def test_verify_invalid_hash_returns_false(self):
        assert not verify_password("password", "not-a-valid-hash")


class TestJWT:
    def test_create_and_decode_token(self):
        token = create_access_token("user-123")
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"

    def test_decode_invalid_token_returns_none(self):
        assert decode_access_token("invalid.token.here") is None

    def test_decode_empty_token_returns_none(self):
        assert decode_access_token("") is None

    def test_token_contains_expiry(self):
        token = create_access_token("user-456")
        payload = decode_access_token(token)
        assert "exp" in payload


class TestOpaqueToken:
    def test_generates_unique_tokens(self):
        t1 = generate_opaque_token()
        t2 = generate_opaque_token()
        assert t1 != t2

    def test_default_length(self):
        token = generate_opaque_token()
        assert len(token) > 20

    def test_custom_length(self):
        short = generate_opaque_token(10)
        long = generate_opaque_token(80)
        assert len(short) < len(long)
