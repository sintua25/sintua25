"""Indikator keraguan. Mesin hanya MENANDAI; auditor yang menyimpulkan."""

from __future__ import annotations

MESSAGES: dict[str, str] = {
    "NO_TEXT": "Tidak ada teks yang terbaca di foto ini.",
    "NO_DOC_ID": "Nomor dokumen tidak ditemukan.",
    "NO_AMOUNT": "Nominal tidak ditemukan.",
    "MULTIPLE_TOTALS": "Ada lebih dari satu nominal total dengan nilai berbeda.",
    "LOW_CONFIDENCE": "Keyakinan OCR rendah untuk nilai ini.",
    "DIGIT_CORRECTED": "Ada huruf yang dibaca sebagai angka (misal O jadi 0).",
    "REREAD_DIFFERS": "Pembacaan ulang memberi hasil berbeda dari pembacaan pertama.",
    "SEPARATOR_GUESSED": "Pemisah desimal ditebak (terbaca '12.450.000.00'); cek sen-nya.",
    "DATE_INVALID": "Tanggal tidak valid di kalender.",
    "DATE_US_ORDER": "Tanggal hanya valid kalau dibaca bulan/hari (format AS).",
    "BLURRY": "Foto kemungkinan buram; cek angka dengan teliti.",
    "MEDIA_SKIPPED": "Ada gambar di file Word ini yang rusak dan tidak dibaca.",
}


def flag(code: str, **extra: object) -> dict:
    if code not in MESSAGES:
        raise KeyError(f"Kode indikator tidak dikenal: {code}")
    return {"code": code, "message": MESSAGES[code], **extra}
