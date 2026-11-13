"""Ubah satu file sumber (foto, PDF, Word) menjadi satu atau lebih "halaman" untuk dibaca.

- Foto: satu halaman, ID = SHA-256 file (sama seperti sebelumnya).
- PDF: satu halaman per halaman PDF, dirender 200 dpi lalu di-OCR.
- Word (.docx): teks dokumen (paragraf + baris tabel) dibaca langsung tanpa OCR, dan
  setiap gambar yang ditempel (misal foto kuitansi) di-OCR sebagai halaman sendiri.
- Word lama (.doc) tidak didukung: diberi pesan jelas, tidak dilewati diam-diam.

ID halaman turunan = SHA-256 dari "<sha file>#<bagian>", jadi tetap 64 heksa dan stabil
selama isi file tidak berubah. File sumber hanya dibaca sekali ke memori.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .preprocess import ImageLoadError

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
PDF_SUFFIXES = {".pdf"}
WORD_SUFFIXES = {".docx"}
UNSUPPORTED_SUFFIXES = {".doc": "Format Word lama (.doc) belum bisa dibaca. Buka di Word, Simpan Sebagai .docx atau PDF."}
DOCUMENT_SUFFIXES = IMAGE_SUFFIXES | PDF_SUFFIXES | WORD_SUFFIXES | set(UNSUPPORTED_SUFFIXES)

PDF_DPI = 200
MAX_PDF_PAGES = 300
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class Unit:
    """Satu halaman yang siap dibaca."""
    rel: str                       # nama yang tampil, misal "Kas/inv.pdf#hal2"
    key: str                       # ID halaman (64 heksa)
    kind: str                      # "pdf_page" | "docx_image" | "docx_text"
    # Gambar dimuat saat dibutuhkan saja (PDF ratusan halaman tidak dirender sekaligus).
    # Hasil: (BGR untuk OCR, PNG untuk ditampilkan, (lebar, tinggi)).
    load: Callable[[], tuple[np.ndarray, bytes, tuple[int, int]]] | None = None
    text_lines: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def file_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sub_key(sha: str, part: str) -> str:
    return hashlib.sha256(f"{sha}#{part}".encode()).hexdigest()


def read_source(path: Path) -> bytes:
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        raise ImageLoadError(f"File '{path}' tidak ditemukan. Mungkin dipindah atau dihapus setelah folder dipilih.")
    except PermissionError:
        raise ImageLoadError(f"Tidak punya izin membaca '{path}'. Tutup aplikasi lain yang sedang membukanya, lalu coba lagi.")
    except OSError as e:
        raise ImageLoadError(f"Gagal membaca '{path}': {e}. Kalau file ada di drive jaringan, salin dulu ke laptop.")
    if not data:
        raise ImageLoadError(f"File '{path}' kosong (0 byte).")
    return data


def expand(path: Path, rel: str, data: bytes, sha: str) -> list[Unit]:
    """Pecah file non-foto menjadi halaman. Foto ditangani pipeline foto biasa."""
    suffix = Path(path).suffix.lower()
    if suffix in UNSUPPORTED_SUFFIXES:
        raise ImageLoadError(f"'{rel}': {UNSUPPORTED_SUFFIXES[suffix]}")
    if suffix in PDF_SUFFIXES:
        return _pdf(rel, data, sha)
    if suffix in WORD_SUFFIXES:
        return _docx(rel, data, sha)
    raise ImageLoadError(f"'{rel}' bukan foto, PDF, atau Word.")


# --- PDF ---------------------------------------------------------------------

def _pdf(rel: str, data: bytes, sha: str) -> list[Unit]:
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as e:
        msg = str(e).lower()
        if "password" in msg:
            raise ImageLoadError(f"PDF '{rel}' dikunci password. Minta versi tanpa password, atau cetak ulang ke PDF.")
        raise ImageLoadError(f"PDF '{rel}' rusak atau tidak bisa dibuka ({e}). Coba buka di pembaca PDF lalu simpan ulang.")
    try:
        n = len(doc)
        if n == 0:
            raise ImageLoadError(f"PDF '{rel}' tidak punya halaman.")
        if n > MAX_PDF_PAGES:
            raise ImageLoadError(f"PDF '{rel}' punya {n} halaman (batas {MAX_PDF_PAGES}). Pecah dulu jadi beberapa file.")
    finally:
        doc.close()
    return [Unit(rel=f"{rel}#hal{i + 1}" if n > 1 else rel, key=sub_key(sha, f"hal{i + 1}"), kind="pdf_page",
                 load=lambda i=i: _pdf_page(data, i)) for i in range(n)]


def _pdf_page(data: bytes, i: int):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(data)
    try:
        page = doc[i]
        try:
            return _image(page.render(scale=PDF_DPI / 72).to_pil().convert("RGB"))
        finally:
            page.close()
    finally:
        doc.close()


# --- Word ----------------------------------------------------------------------

def _docx(rel: str, data: bytes, sha: str) -> list[Unit]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        body = ET.fromstring(zf.read("word/document.xml")).find(f"{_W}body")
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise ImageLoadError(f"Word '{rel}' rusak atau bukan .docx asli ({type(e).__name__}). Buka di Word lalu simpan ulang.")

    lines: list[str] = []
    for el in (body if body is not None else []):
        if el.tag == f"{_W}p":
            t = _text(el)
            if t:
                lines.append(t)
        elif el.tag == f"{_W}tbl":
            for tr in el.iter(f"{_W}tr"):
                cells = [_text(tc) for tc in tr.findall(f"{_W}tc")]
                if any(cells):
                    lines.append(" | ".join(c for c in cells if c))  # satu baris tabel = satu baris

    units: list[Unit] = []
    if lines:
        units.append(Unit(rel=f"{rel}#teks", key=sub_key(sha, "teks"), kind="docx_text", text_lines=lines))
    media = sorted((n for n in zf.namelist() if n.startswith("word/media/")), key=_natural)
    skipped = []
    for k, name in enumerate(m for m in media if Path(m).suffix.lower() in IMAGE_SUFFIXES):
        try:
            with Image.open(io.BytesIO(zf.read(name))) as im:
                im.load()
                if min(im.size) < 120:
                    continue  # ikon/logo kecil, bukan foto dokumen
        except (UnidentifiedImageError, OSError):
            skipped.append(Path(name).name)
            continue
        part = f"gambar{k + 1}"
        units.append(Unit(rel=f"{rel}#{part}", key=sub_key(sha, part), kind="docx_image",
                          load=lambda name=name: _docx_image(data, name)))
    if not units:
        raise ImageLoadError(f"Word '{rel}' tidak berisi teks atau gambar yang bisa dibaca.")
    if skipped:
        units[0].notes.append(f"{len(skipped)} gambar di file Word ini rusak dan tidak dibaca: {', '.join(skipped)}")
    return units


def _docx_image(data: bytes, name: str):
    with zipfile.ZipFile(io.BytesIO(data)) as zf, Image.open(io.BytesIO(zf.read(name))) as im:
        return _image(ImageOps.exif_transpose(im).convert("RGB"))


def _text(el) -> str:
    parts = []
    for node in el.iter():
        if node.tag == f"{_W}t" and node.text:
            parts.append(node.text)
        elif node.tag in (f"{_W}tab", f"{_W}br"):
            parts.append(" ")
        elif node.tag == f"{_W}p" and parts and parts[-1] != " ":
            parts.append(" ")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _natural(name: str):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", name)]


# --- bersama -----------------------------------------------------------------

def _image(pil: Image.Image) -> tuple[np.ndarray, bytes, tuple[int, int]]:
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR), buf.getvalue(), pil.size
