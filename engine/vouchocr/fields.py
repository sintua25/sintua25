"""Ambil nomor dokumen, nominal, dan tanggal dari baris OCR.

Setiap nilai menyimpan baris sumbernya (indeks baris -> kotak di foto) dan
potongan teks persis, supaya angka bisa ditelusuri balik ke foto.
"""

from __future__ import annotations

import re
from datetime import date

from .flags import flag
from .ids import canon_doc_id
from .models import Field, OcrLine
from .money import try_parse_amount

LOW_CONFIDENCE = 0.85

# --- perbaikan huruf->angka, HANYA di dalam deretan yang memang angka -------

_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "|": "1",
                            "S": "5", "B": "8", "Z": "2"})
_GROUP_SHAPE = re.compile(r"[^.,]{1,3}(?:[.,][^.,]{3})+(?:[.,][^.,]{1,2})?")
_SAME_SEP_CENTS = re.compile(r"\d{1,3}(?:([.,])\d{3})(?:\1\d{3})*\1\d{2}")
_NUMERIC_RUN = re.compile(r"[0-9OoDIl|SBZ][0-9OoDIl|SBZ.,]*[0-9OoDIl|SBZ]")


_LOOKALIKE = str.maketrans({"ρ": "p", "μ": "u", "Ο": "O", "ο": "o", "Ι": "I", "Ѕ": "S", "，": ",", "．": "."})


def fix_digits(text: str) -> str:
    """Ganti huruf mirip angka di deretan yang mayoritas angka. Panjang teks tetap,
    jadi posisi karakter hasil tetap menunjuk ke teks asli."""

    def repl(m: re.Match) -> str:
        run = m.group(0)
        # Jangan sentuh deretan yang menempel ke huruf lain ("SBY", "BOLD", "INV").
        before = text[m.start() - 1] if m.start() else " "
        after = text[m.end()] if m.end() < len(text) else " "
        if before.isalpha() or after.isalpha():
            return run
        alnum = [c for c in run if c not in ".,"]
        digits = sum(c.isdigit() for c in alnum)
        grouped = _GROUP_SHAPE.fullmatch(run) is not None  # bentuk "x.xxx.xxx" = jelas angka
        if digits == 0 or (not grouped and (digits < 2 or digits / len(alnum) < 0.6)):
            return run
        return run.translate(_DIGIT_FIX)

    text = text.translate(_LOOKALIKE)  # huruf Yunani/kiri-kanan penuh yang mirip Latin; panjang tetap
    return _NUMERIC_RUN.sub(repl, text)


# --- pola ---------------------------------------------------------------------

_TOTAL_KW = re.compile(
    r"\b(total|grand\s*total|jumlah|sejumlah|sebesar|dibayar|bayar|tagihan|nilai|amount)\b", re.I)
_SKIP_AMOUNT_KW = re.compile(r"\b(rek(ening)?|a/?c|acc(ount)?|npwp|nik|telp|tel|hp|fax|no\.?\s*rek)\b", re.I)
_TERBILANG = re.compile(r"\bterbilang\b|\brupiah\b(?!.*\d)", re.I)
# "IDR 1 Million", "Rp 5 juta": angka di kalimat (syarat, catatan kaki), bukan nilai transaksi.
_MAGNITUDE_WORD = re.compile(
    r"\s*(juta|jt|ribu|rb|miliar|milyar|triliun|million|mio|thousand|billion|bn)\b", re.I)

_AMOUNT = re.compile(
    r"(?<![\w/.,-])"
    r"(?P<cur>(?:Rp\.?|IDR)\s*)?"
    r"(?P<num>\(?-?\s?\d{1,3}(?:[.,]\s?\d{3})+(?:[.,]\d{1,2})?\)?"
    r"|\(?-?\d+(?:[.,]\d{1,2})?\)?)"
    r"(?P<dash>[.,]-)?"
    r"(?![\w/]|[.,]\d|-\d)",
    re.I,
)

_ID_KEYWORD = re.compile(
    r"\b(?:no(?:mor)?|nr|number|invoice|inv|faktur|kwitansi|kuitansi|voucher|ref(?:erensi)?|"
    r"bukti|po|do|sj)\b\.?\s*(?:[:#.]\s*)?"
    r"(?P<id>[A-Za-z0-9][A-Za-z0-9./\-]*\d[A-Za-z0-9./\-]*)",
    re.I,
)
_ID_PATTERN = re.compile(r"(?<![\w./-])(?P<id>[A-Za-z]{1,6}[-/.]?\d[A-Za-z0-9./\-]{2,})(?![\w])")
_CURRENCY_PREFIX = re.compile(r"(rp|idr)\.?\d", re.I)
_FAKTUR_PAJAK = re.compile(r"(?<![\d.])(?P<id>\d{3}[.-]\d{3}[.-]\d{2}[.-]\d{8})(?!\d)")

_MONTHS = {
    "jan": 1, "januari": 1, "january": 1, "feb": 2, "februari": 2, "february": 2,
    "mar": 3, "maret": 3, "march": 3, "apr": 4, "april": 4, "mei": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6, "jul": 7, "juli": 7, "july": 7,
    "agu": 8, "agt": 8, "agus": 8, "agustus": 8, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "okt": 10, "oktober": 10, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "des": 12, "desember": 12, "dec": 12, "december": 12,
}
_DATE_NUM = re.compile(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})(?!\d)")
_DATE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_DATE_TEXT = re.compile(r"(?<!\d)(\d{1,2})\s*[- ]?\s*([A-Za-z]{3,9})\.?\s*[- ]?\s*(\d{4})(?!\d)")


# --- ekstraksi ----------------------------------------------------------------

def extract(lines: list[OcrLine]) -> tuple[list[Field], list[dict]]:
    """Kembalikan (fields, page_flags)."""
    fields: list[Field] = []
    if not lines:
        return fields, [flag("NO_TEXT")]

    total_rows = _total_label_rows(lines)
    for i, line in enumerate(lines):
        text, score = line.best
        fixed = fix_digits(text)
        taken: list[tuple[int, int]] = []
        line_flags = []
        if line.reread is not None and line.reread != line.text:
            line_flags.append(flag("REREAD_DIFFERS", first=line.text, reread=line.reread))

        for f, span in _dates(fixed, text, i, score):
            fields.append(f)
            taken.append(span)
        for f, span in _doc_ids(fixed, text, i, score, taken):
            fields.append(f)
            taken.append(span)
        if not _SKIP_AMOUNT_KW.search(text) or re.search(r"\bRp|IDR", text, re.I):
            is_total = bool(_TOTAL_KW.search(text)) or i in total_rows
            for f, span in _amounts(fixed, text, i, score, taken, is_total):
                fields.append(f)

        for f in fields:
            if f.line == i:
                if score < LOW_CONFIDENCE:
                    f.flags.append(flag("LOW_CONFIDENCE", score=round(score, 3)))
                f.flags.extend(line_flags)

    return fields, _page_flags(fields)


def _field(kind, value, key, raw_text, start, end, fixed, line, score, label=""):
    f = Field(kind=kind, value=value, key=key, raw=raw_text[start:end].strip(),
              line=line, label=label, score=round(score, 4))
    if fixed[start:end] != raw_text[start:end]:
        f.flags.append(flag("DIGIT_CORRECTED", read=raw_text[start:end].strip()))
    return f


def _overlaps(span, taken) -> bool:
    return any(span[0] < e and s < span[1] for s, e in taken)


def _dates(fixed: str, raw: str, i: int, score: float):
    found = []
    for m in _DATE_ISO.finditer(fixed):
        y, mo, d = map(int, m.groups())
        found.append((m.span(), _make_date(y, mo, d, swap_ok=False)))
    for m in _DATE_NUM.finditer(fixed):
        if _overlaps(m.span(), [s for s, _ in found]):
            continue
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        y = y + 2000 if y < 100 else y
        found.append((m.span(), _make_date(y, mo, d, swap_ok=True)))
    for m in _DATE_TEXT.finditer(fixed):
        mo = _MONTHS.get(m[2].lower())
        if mo is None or _overlaps(m.span(), [s for s, _ in found]):
            continue
        found.append((m.span(), _make_date(int(m[3]), mo, int(m[1]), swap_ok=False)))

    for span, (iso, flags) in found:
        f = _field("date", iso, iso, raw, *span, fixed, i, score, label="tanggal")
        f.flags.extend(flags)
        yield f, span


def _make_date(y: int, mo: int, d: int, swap_ok: bool) -> tuple[str, list[dict]]:
    try:
        return date(y, mo, d).isoformat(), []
    except ValueError:
        pass
    if swap_ok:
        try:
            return date(y, d, mo).isoformat(), [flag("DATE_US_ORDER")]
        except ValueError:
            pass
    return f"{y:04d}-{mo:02d}-{d:02d}", [flag("DATE_INVALID")]


def _doc_ids(fixed: str, raw: str, i: int, score: float, taken):
    seen: list[tuple[int, int]] = []
    if _SKIP_AMOUNT_KW.search(raw):  # "No. Rek 123..." bukan nomor dokumen
        return
    for pattern, label in ((_FAKTUR_PAJAK, "faktur pajak"), (_ID_KEYWORD, "nomor"), (_ID_PATTERN, "")):
        # Nomor dokumen dibaca dari teks asli: huruf di dalam ID memang bagian ID.
        for m in pattern.finditer(raw):
            span = m.span("id")
            if _overlaps(span, taken) or _overlaps(span, seen):
                continue
            value = m["id"].strip(".-/")
            if sum(c.isdigit() for c in value) < 3 or _CURRENCY_PREFIX.match(value):
                continue
            seen.append(span)
            f = Field(kind="doc_id", value=value, key=canon_doc_id(value), raw=value,
                      line=i, label=label, score=round(score, 4))
            yield f, span


def _amounts(fixed: str, raw: str, i: int, score: float, taken, is_total: bool):
    if _TERBILANG.search(raw) and not re.search(r"\d", raw):
        return
    for m in _AMOUNT.finditer(fixed):
        span = m.span()
        if _overlaps(span, taken) or _MAGNITUDE_WORD.match(fixed, span[1]):
            continue
        num = m["num"]
        digits = sum(c.isdigit() for c in num)
        grouped = bool(re.search(r"\d[.,]\s?\d{3}(?!\d)", num))
        if not (m["cur"] or grouped or (is_total and digits >= 4)):
            continue
        compact = num.replace(" ", "")
        parsed, guessed = try_parse_amount(compact), False
        if parsed is None and _SAME_SEP_CENTS.fullmatch(compact.strip("()-")):
            # OCR sering membaca koma desimal sebagai titik: "12.450.000.00".
            sep = compact.strip("()-")[-3]
            other = "," if sep == "." else "."
            parsed, guessed = try_parse_amount(compact[:-3] + other + compact[-2:]), True
        if parsed is None:
            continue
        label = "total" if is_total else ""
        f = _field("amount", str(parsed.value), str(parsed.value), raw, *span, fixed, i, score, label=label)
        if guessed:
            f.flags.append(flag("SEPARATOR_GUESSED", read=compact))
        yield f, span


def _total_label_rows(lines: list[OcrLine]) -> set[int]:
    """Baris yang sejajar (satu baris tabel) dan di kanan label 'Total' yang berdiri sendiri."""
    rows: set[int] = set()
    for i, line in enumerate(lines):
        text, _ = line.best
        if not _TOTAL_KW.search(text) or re.search(r"\d", text):
            continue
        cy, h, right = _center_y(line.box), _height(line.box), max(p[0] for p in line.box)
        for j, other in enumerate(lines):
            if j != i and abs(_center_y(other.box) - cy) < h * 0.6 and min(p[0] for p in other.box) >= right - 5:
                rows.add(j)
    return rows


def _center_y(box) -> float:
    return sum(p[1] for p in box) / len(box)


def _height(box) -> float:
    ys = [p[1] for p in box]
    return max(ys) - min(ys) or 1.0


def _page_flags(fields: list[Field]) -> list[dict]:
    out = []
    if not any(f.kind == "doc_id" for f in fields):
        out.append(flag("NO_DOC_ID"))
    amounts = [f for f in fields if f.kind == "amount"]
    if not amounts:
        out.append(flag("NO_AMOUNT"))
    totals = {f.value for f in amounts if f.label == "total"}
    if len(totals) > 1:
        out.append(flag("MULTIPLE_TOTALS", values=sorted(totals)))
    return out
