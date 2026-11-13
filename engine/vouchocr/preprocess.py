"""Siapkan foto untuk OCR: baca aman, ukuran wajar, deteksi buram dan bayangan.

Foto sumber hanya DIBACA. Semua transformasi terjadi di memori, dan matriksnya
disimpan supaya kotak OCR bisa dipetakan balik ke koordinat foto asli.

Catatan pelurusan: foto TIDAK diputar utuh. Detektor teks memberi kotak miring
per baris dan tiap baris diluruskan sendiri sebelum dibaca. Di benchmark 72 foto
sintetis rusak (bench/bench_synthetic.py), memutar foto utuh lebih dulu justru
menurunkan akurasi (239 vs 244 dari 252 nilai) karena interpolasi menambah buram.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 3000          # foto lebih besar diperkecil; teks kuitansi tetap terbaca
BLUR_THRESHOLD = 35.0    # varians Laplacian di lebar 1000 px
SHADOW_SPREAD = 45.0     # selisih terang latar (p95 - p5) yang dianggap bayangan

Image.MAX_IMAGE_PIXELS = 120_000_000  # cegah "decompression bomb", tetap muat foto 100 MP


class ImageLoadError(Exception):
    """Foto tidak bisa dibuka. Pesan menjelaskan apa yang terjadi dan apa yang bisa dilakukan."""


@dataclass
class Loaded:
    image: np.ndarray       # BGR, orientasi EXIF sudah diterapkan (sama seperti yang dilihat orang)
    sha256: str             # hash byte file ASLI di disk
    size: tuple[int, int]   # (lebar, tinggi) setelah orientasi EXIF


@dataclass
class Prepared:
    image: np.ndarray       # BGR siap OCR (warna asli)
    matrix: np.ndarray      # affine 2x3: koordinat asli -> koordinat siap OCR
    scale: float
    has_shadow: bool        # latar tidak rata; versi rata tersedia lewat flattened()
    blur_score: float

    def flattened(self) -> np.ndarray:
        """Versi tanpa bayangan, geometri sama persis (kotak tetap valid)."""
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(flatten_shadows(gray), cv2.COLOR_GRAY2BGR)

    def to_original(self, points) -> list[tuple[float, float]]:
        inv = cv2.invertAffineTransform(self.matrix)
        pts = np.asarray(points, dtype=np.float64)
        mapped = pts @ inv[:, :2].T + inv[:, 2]
        return [(round(float(x), 1), round(float(y), 1)) for x, y in mapped]

    def summary(self) -> dict:
        return {"scale": round(self.scale, 4),
                "has_shadow": self.has_shadow, "blur_score": round(self.blur_score, 1)}


def load_image(path: Path) -> Loaded:
    try:
        data = Path(path).read_bytes()  # baca sekali: hash & decode dari byte yang sama
    except FileNotFoundError:
        raise ImageLoadError(f"File '{path}' tidak ditemukan. Mungkin dipindah atau dihapus setelah folder dipilih.")
    except PermissionError:
        raise ImageLoadError(f"Tidak punya izin membaca '{path}'. Tutup aplikasi lain yang sedang membukanya, lalu coba lagi.")
    except OSError as e:
        raise ImageLoadError(f"Gagal membaca '{path}': {e}. Kalau file ada di drive jaringan, salin dulu ke laptop.")
    if not data:
        raise ImageLoadError(f"File '{path}' kosong (0 byte). Ambil ulang fotonya.")

    sha = hashlib.sha256(data).hexdigest()
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            rgb = np.asarray(im.convert("RGB"))
    except (UnidentifiedImageError, Image.DecompressionBombError) as e:
        raise ImageLoadError(f"'{Path(path).name}' bukan foto yang bisa dibaca ({type(e).__name__}). "
                             "Pastikan formatnya JPG, PNG, atau TIFF dan filenya tidak rusak.")
    except OSError as e:
        raise ImageLoadError(f"'{Path(path).name}' rusak atau terpotong ({e}). Salin ulang dari sumbernya.")
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return Loaded(image=bgr, sha256=sha, size=(bgr.shape[1], bgr.shape[0]))


def prepare(bgr: np.ndarray) -> Prepared:
    h, w = bgr.shape[:2]
    scale = min(1.0, MAX_SIDE / max(h, w))
    img = cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else bgr
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    M = np.array([[scale, 0, 0], [0, scale, 0]], dtype=np.float64)
    return Prepared(image=img, matrix=M, scale=scale, has_shadow=needs_flattening(gray), blur_score=blur_score(gray))


def blur_score(gray: np.ndarray) -> float:
    small = _resize_width(gray, 1000)
    return float(cv2.Laplacian(small, cv2.CV_64F).var())


def needs_flattening(gray: np.ndarray) -> bool:
    bg = _background(_resize_width(gray, 800))
    p5, p95 = np.percentile(bg, [5, 95])
    return float(p95 - p5) > SHADOW_SPREAD


def flatten_shadows(gray: np.ndarray) -> np.ndarray:
    bg = _background(gray)
    norm = cv2.divide(gray, bg, scale=255)  # teks gelap tetap gelap, latar jadi putih rata
    return cv2.normalize(norm, None, 0, 255, cv2.NORM_MINMAX)


def _background(gray: np.ndarray) -> np.ndarray:
    k = max(15, (min(gray.shape) // 40) | 1)
    dil = cv2.dilate(gray, np.ones((7, 7), np.uint8))
    return cv2.medianBlur(dil, min(k, 255))


def _resize_width(gray: np.ndarray, width: int) -> np.ndarray:
    h, w = gray.shape[:2]
    if w <= width:
        return gray
    return cv2.resize(gray, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
