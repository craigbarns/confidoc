"""Tests sanitisation texte PostgreSQL."""

from app.core.text_sanitize import postgres_safe_text


def test_postgres_safe_text_removes_nul():
    assert postgres_safe_text("hello\x00world") == "helloworld"
    assert postgres_safe_text("\x00\x00") == ""
    assert postgres_safe_text("") == ""
    assert postgres_safe_text(None) == ""


def test_postgres_safe_text_preserves_normal():
    s = "café\nPDF\tok"
    assert postgres_safe_text(s) == s
