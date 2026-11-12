"""Kanonisasi nomor dokumen jadi kunci pencocokan.

Kunci kanonik dipakai untuk MEMBANDINGKAN, bukan untuk ditampilkan. Teks asli
selalu disimpan terpisah.
"""

from __future__ import annotations

import re

__all__ = ["canon_doc_id", "same_doc_id"]

# OCR sering tertukar antara huruf dan angka yang mirip. Dua sisi pencocokan
# dikanonkan dengan aturan yang sama, jadi pemetaan ini simetris dan aman.
_CONFUSABLE = str.maketrans({"O": "0", "I": "1", "L": "1"})


def canon_doc_id(raw: str) -> str:
    """'inv-0O12 3' -> '1NV00123'. Hanya huruf besar dan angka; '' kalau kosong."""
    s = re.sub(r"[^0-9A-Za-z]", "", raw or "").upper()
    return s.translate(_CONFUSABLE)


def same_doc_id(a: str, b: str) -> bool:
    ca, cb = canon_doc_id(a), canon_doc_id(b)
    return bool(ca) and ca == cb
