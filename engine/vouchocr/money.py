"""Parse nominal uang dari teks OCR menjadi Decimal.

Aturan pemisah (konvensi dokumen Indonesia, tetap menerima format Inggris):
- Ada titik DAN koma: pemisah yang muncul terakhir adalah desimal.
- Hanya satu jenis pemisah, muncul lebih dari sekali: pemisah ribuan.
- Hanya satu pemisah, diikuti tepat 3 digit: pemisah ribuan ("1.500" = 1500).
- Hanya satu pemisah, diikuti 1-2 digit: desimal ("1,50" = 1.50).
Kelompok ribuan wajib 3 digit; kalau tidak, teks dianggap bukan nominal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

__all__ = ["AmountError", "ParsedAmount", "parse_amount", "try_parse_amount", "format_idr"]


class AmountError(ValueError):
    """Teks tidak bisa dibaca sebagai nominal. Pesan menjelaskan alasannya."""


@dataclass(frozen=True)
class ParsedAmount:
    value: Decimal
    raw: str
    negative: bool


_CURRENCY = re.compile(r"^(?:rp\.?|idr)", re.IGNORECASE)
_TRAILING_DASH = re.compile(r"[.,]\s*-+$")  # "12.000,-" atau "12.000.-"
_GROUPED = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")


def parse_amount(text: str) -> ParsedAmount:
    raw = text
    s = (text or "").strip()
    if not s:
        raise AmountError("Nominal kosong.")

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    if s.startswith("-"):
        negative, s = True, s[1:].strip()

    s = _CURRENCY.sub("", s).strip()
    if s.startswith("-"):  # "Rp -1.000"
        negative, s = True, s[1:].strip()
    s = _TRAILING_DASH.sub("", s)
    s = re.sub(r"\s+", "", s)  # OCR sering menyisipkan spasi: "12. 450.000"

    if not s:
        raise AmountError(f"Tidak ada angka di '{raw}'.")
    if not re.fullmatch(r"[\d.,]+", s):
        raise AmountError(f"'{raw}' mengandung karakter selain angka dan pemisah.")
    if not s[0].isdigit() or not s[-1].isdigit():
        raise AmountError(f"'{raw}' diawali atau diakhiri pemisah.")

    integer, fraction = _split(s, raw)
    if integer and not (integer.isdigit() or _GROUPED.fullmatch(integer)):
        raise AmountError(f"Kelompok ribuan di '{raw}' tidak 3 digit.")
    digits = re.sub(r"[.,]", "", integer)
    value = Decimal(f"{digits}.{fraction}" if fraction else digits)
    if value == 0:
        negative = False  # "-0" tetap nol, tanpa tanda
    elif negative:
        value = -value
    return ParsedAmount(value=value, raw=raw, negative=negative)


def _split(s: str, raw: str) -> tuple[str, str]:
    """Pisahkan bagian bulat dan desimal. Bagian bulat masih memuat pemisah ribuan."""
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        thousands = "," if dec == "." else "."
        integer, _, fraction = s.rpartition(dec)
        if dec in integer:
            raise AmountError(f"Pemisah desimal muncul lebih dari sekali di '{raw}'.")
        if not 1 <= len(fraction) <= 2:
            raise AmountError(f"Bagian desimal di '{raw}' harus 1-2 digit.")
        if not re.fullmatch(rf"\d{{1,3}}(?:\{thousands}\d{{3}})*", integer):
            raise AmountError(f"Kelompok ribuan di '{raw}' tidak 3 digit.")
        return integer, fraction

    sep = "." if has_dot else "," if has_comma else ""
    if not sep:
        return s, ""
    parts = s.split(sep)
    if len(parts) > 2:
        return s, ""  # ribuan; divalidasi pemanggil
    tail = parts[1]
    if len(tail) == 3:
        return s, ""
    if len(tail) in (1, 2):
        return parts[0], tail
    raise AmountError(f"Tidak jelas apakah '{sep}' di '{raw}' pemisah ribuan atau desimal.")


def try_parse_amount(text: str) -> ParsedAmount | None:
    try:
        return parse_amount(text)
    except AmountError:
        return None


def format_idr(value: Decimal) -> str:
    """Decimal -> 'Rp 12.450.000,00' (tampilan saja, bukan untuk disimpan)."""
    sign = "-" if value < 0 else ""
    q = abs(value).quantize(Decimal("0.01"))
    integer, _, frac = f"{q:f}".partition(".")
    grouped = f"{int(integer):,}".replace(",", ".")
    return f"{sign}Rp {grouped},{frac}"
