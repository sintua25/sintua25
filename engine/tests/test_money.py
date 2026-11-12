from decimal import Decimal

import pytest

from vouchocr.money import AmountError, format_idr, parse_amount, try_parse_amount


@pytest.mark.parametrize("text, expected", [
    ("Rp 12.450.000,00", "12450000.00"),
    ("Rp12.450.000", "12450000"),
    ("IDR 12,450,000.00", "12450000.00"),
    ("12.450.000,-", "12450000"),
    ("12.450.000.-", "12450000"),
    ("Rp. 1.500", "1500"),
    ("1,50", "1.50"),
    ("1.5", "1.5"),
    ("1234,56", "1234.56"),
    ("12. 450.000", "12450000"),        # spasi sisipan OCR
    ("999", "999"),
    ("1.000.000.000.000", "1000000000000"),
])
def test_normal(text, expected):
    assert parse_amount(text).value == Decimal(expected)


@pytest.mark.parametrize("text", ["0", "Rp 0", "0,00", "-0", "(0)"])
def test_zero_has_no_sign(text):
    p = parse_amount(text)
    assert p.value == 0 and not p.negative and not str(p.value).startswith("-")


@pytest.mark.parametrize("text, expected", [
    ("-1.000", "-1000"), ("(1.000)", "-1000"), ("Rp -2.500,50", "-2500.50"), ("-Rp 750", "-750"),
])
def test_negative(text, expected):
    p = parse_amount(text)
    assert p.value == Decimal(expected) and p.negative


@pytest.mark.parametrize("text", ["", "   ", None, "Rp", "Rp -"])
def test_empty(text):
    with pytest.raises(AmountError):
        parse_amount(text)


@pytest.mark.parametrize("text", [
    "12.45.000",        # kelompok ribuan bukan 3 digit
    "1.2345",           # 4 digit setelah pemisah tunggal: tidak jelas
    "12,450.000,00",    # desimal muncul dua kali
    "1.000,123",        # desimal 3 digit
    "12a00", "abc", ".500", "500.", "1..000",
])
def test_invalid(text):
    with pytest.raises(AmountError):
        parse_amount(text)
    assert try_parse_amount(text) is None


def test_result_is_decimal_not_float():
    v = parse_amount("0,10").value + parse_amount("0,20").value
    assert isinstance(v, Decimal) and v == Decimal("0.30")


def test_raw_kept():
    assert parse_amount("Rp 1.000").raw == "Rp 1.000"


@pytest.mark.parametrize("value, text", [
    (Decimal("12450000"), "Rp 12.450.000,00"),
    (Decimal("-1500.5"), "-Rp 1.500,50"),
    (Decimal("0"), "Rp 0,00"),
])
def test_format_idr(value, text):
    assert format_idr(value) == text
