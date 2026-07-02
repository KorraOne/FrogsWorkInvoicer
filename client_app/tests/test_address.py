"""Tests for invoicing.address helpers."""

import pytest

from invoicing.address import (
    compact_address_line,
    compact_postcode,
    compact_suburb,
    normalize_au_address,
)


def test_compact_address_line():
    assert compact_address_line("  12  Main   St  ") == "12 Main St"
    assert compact_address_line("") == ""


def test_compact_suburb():
    assert compact_suburb("  north   sydney ") == "North Sydney"
    assert compact_suburb("") == ""


def test_compact_postcode():
    assert compact_postcode(" 20 61 ") == "2061"
    assert compact_postcode("20610") == "2061"


def test_normalize_au_address_compacts_fields():
    addr = normalize_au_address(
        line1="  1  George   St ",
        line2=" level  5 ",
        suburb=" sydney ",
        state="nsw",
        postcode="200 0",
    )
    assert addr == {
        "address_line1": "1 George St",
        "address_line2": "level 5",
        "suburb": "Sydney",
        "state": "NSW",
        "postcode": "2000",
    }


def test_normalize_au_address_rejects_invalid_postcode():
    with pytest.raises(ValueError, match="4 digits"):
        normalize_au_address(
            line1="1 Main St",
            line2="",
            suburb="Sydney",
            state="NSW",
            postcode="20",
        )
