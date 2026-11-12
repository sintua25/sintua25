"""Lapisan OCR. Semua model jalan lokal (ONNX); tidak ada panggilan jaringan."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

REREAD_BELOW = 0.97      # baris berangka di bawah keyakinan ini dibaca ulang
REREAD_UPSCALE = 2.0
# Ambang deteksi lebih rendah dari bawaan (0.5): di foto redup/buram, baris teks
# tipis sering tidak terdeteksi sama sekali. Kotak palsu tetap tersaring oleh skor
# pengenalan (text_score), jadi yang bertambah hanya baris asli yang tadinya hilang.
DET_BOX_THRESH = 0.3


@dataclass
class RawLine:
    text: str
    score: float
    box: list[tuple[float, float]]   # koordinat gambar yang diberikan ke OCR


class OcrBackend(Protocol):
    name: str

    def detect_and_read(self, image: np.ndarray) -> list[RawLine]: ...

    def read_crop(self, crop: np.ndarray) -> tuple[str, float]: ...


class RapidOcrBackend:
    """PaddleOCR (PP-OCR) dalam format ONNX lewat RapidOCR. Model ikut terpasang di paket."""

    def __init__(self) -> None:
        self._engine = None
        self.name = "rapidocr"

    def _get(self):
        if self._engine is None:
            from rapidocr import RapidOCR  # impor lambat: ~1 dtk, tidak perlu saat tes unit

            self._engine = RapidOCR(params={"Global.log_level": "error", "Global.max_side_len": 3000,
                                             "Det.box_thresh": DET_BOX_THRESH})
            logging.getLogger("RapidOCR").setLevel(logging.ERROR)
            import rapidocr
            self.name = f"rapidocr {getattr(rapidocr, '__version__', '?')}"
        return self._engine

    def detect_and_read(self, image: np.ndarray) -> list[RawLine]:
        res = self._get()(image, use_det=True, use_cls=True, use_rec=True)
        if res.boxes is None or res.txts is None:
            return []
        return [RawLine(text=str(t), score=float(s), box=[(float(x), float(y)) for x, y in b])
                for b, t, s in zip(res.boxes, res.txts, res.scores)]

    def read_crop(self, crop: np.ndarray) -> tuple[str, float]:
        res = self._get()(crop, use_det=False, use_cls=False, use_rec=True)
        if not res.txts:
            return "", 0.0
        return str(res.txts[0]), float(res.scores[0])


def reread_line(backend: OcrBackend, image: np.ndarray, box) -> tuple[str, float] | None:
    """Potong baris (diluruskan per kotak), perbesar, baca ulang. Untuk angka kecil/samar."""
    crop = _crop_quad(image, box)
    if crop is None:
        return None
    crop = cv2.resize(crop, None, fx=REREAD_UPSCALE, fy=REREAD_UPSCALE, interpolation=cv2.INTER_CUBIC)
    pad = max(4, crop.shape[0] // 6)
    crop = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    text, score = backend.read_crop(crop)
    return (text, score) if text else None


def _crop_quad(image: np.ndarray, box) -> np.ndarray | None:
    pts = np.asarray(box, dtype=np.float32)
    w = int(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[2] - pts[3])))
    h = int(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2])))
    if w < 4 or h < 4:
        return None
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(pts, dst)
    return cv2.warpPerspective(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
