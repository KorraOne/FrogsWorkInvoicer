"""Tests for invoicing.format."""

from decimal import Decimal

from invoicing.format import (
    format_abn,
    format_account,
    format_invoice_number,
    format_money,
    format_qty,
    parse_amount,
)


def test_format_money():
    assert format_money(Decimal("1234.5")) == "$1,234.50"


def test_format_invoice_number():
    assert format_invoice_number(42) == "00000042"


def test_format_abn():
    assert format_abn("12345678901") == "12 345 678 901"


def test_format_account():
    assert format_account("123456") == "123 456"


def test_format_qty_whole():
    assert format_qty(Decimal("2")) == "2"


def test_parse_amount():
    assert parse_amount("$1,234.50") == Decimal("1234.50")
