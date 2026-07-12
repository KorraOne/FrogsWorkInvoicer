"""Tests for path_safety helpers."""

import os

import pytest

from app_platform.path_safety import is_pdf_bytes, is_safe_basename, is_safe_invoice_key, safe_join


def test_is_safe_basename_rejects_traversal():
    assert not is_safe_basename("../etc/passwd")
    assert not is_safe_basename("..\\secret")
    assert not is_safe_basename("foo/bar")
    assert not is_safe_basename("%2e%2e%2fsecret")
    assert not is_safe_basename("")


def test_is_safe_basename_accepts_simple_names():
    assert is_safe_basename("Invoice_00000001_2026-07-12.pdf")
    assert is_safe_basename("customers.json")


def test_safe_join_blocks_escape(tmp_path):
    base = str(tmp_path / "data")
    os.makedirs(base, exist_ok=True)
    assert safe_join(base, "file.json") == os.path.realpath(os.path.join(base, "file.json"))
    with pytest.raises(ValueError):
        safe_join(base, "..", "outside.txt")


def test_is_safe_invoice_key():
    assert is_safe_invoice_key("00000001")
    assert not is_safe_invoice_key("../0001")
    assert not is_safe_invoice_key("1")


def test_is_pdf_bytes():
    assert is_pdf_bytes(b"%PDF-1.4\n")
    assert not is_pdf_bytes(b"not a pdf")
