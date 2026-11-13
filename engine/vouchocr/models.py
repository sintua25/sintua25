"""Struktur data hasil OCR. Semua bisa diserialisasi ke JSON apa adanya."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

Point = tuple[float, float]


@dataclass
class OcrLine:
    text: str                   # teks OCR pertama, tidak pernah ditimpa
    score: float
    box: list[Point]            # 4 titik searah jarum jam, koordinat foto ASLI
    reread: str | None = None   # hasil baca ulang (crop diperbesar), kalau dilakukan
    reread_score: float | None = None

    @property
    def best(self) -> tuple[str, float]:
        if self.reread is not None and (self.reread_score or 0) > self.score:
            return self.reread, float(self.reread_score)
        return self.text, self.score


@dataclass
class Field:
    kind: str                   # "doc_id" | "amount" | "date"
    value: str                  # amount: Decimal sebagai string; date: ISO; doc_id: teks bersih
    key: str                    # kunci pencocokan (doc_id kanonik; selain itu = value)
    raw: str                    # potongan teks persis seperti dibaca
    line: int                   # indeks baris sumber -> kotak di foto
    label: str = ""             # konteks: "total", "nomor", "tanggal", ""
    score: float = 0.0
    flags: list[dict] = field(default_factory=list)


def to_json(obj) -> dict:
    return asdict(obj)
