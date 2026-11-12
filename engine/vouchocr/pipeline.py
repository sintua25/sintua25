"""Satu foto -> satu hasil halaman (dict siap JSON)."""

from __future__ import annotations

import os
import re
import time
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .fields import extract
from .flags import flag
from .models import OcrLine
from .ocr import REREAD_BELOW, OcrBackend, reread_line
from .preprocess import BLUR_THRESHOLD, load_image, prepare

SCHEMA = 1
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def process_image(path: Path, backend: OcrBackend, rel: str | None = None) -> dict:
    t0 = time.perf_counter()
    loaded = load_image(path)
    prep = prepare(loaded.image)

    # Pembacaan utama di foto warna asli (paling akurat di benchmark). Versi tanpa
    # bayangan hanya dipakai sebagai cadangan kalau nomor dokumen atau nominal
    # tidak ketemu di foto berbayang; versi dengan nilai terlengkap yang dipakai.
    lines, fields, page_flags = _read(prep.image, prep, backend)
    variant = "asli"
    if prep.has_shadow and {"doc_id", "amount"} - {f.kind for f in fields}:
        alt = _read(prep.flattened(), prep, backend)
        if _page_score(alt[0], alt[1]) > _page_score(lines, fields):
            lines, fields, page_flags = alt
            variant = "tanpa_bayangan"

    if prep.blur_score < BLUR_THRESHOLD:
        page_flags.append(flag("BLURRY", blur_score=round(prep.blur_score, 1)))

    return {
        "type": "page",
        "schema": SCHEMA,
        "file": rel or Path(path).name,
        "sha256": loaded.sha256,
        "size": list(loaded.size),
        "preprocess": {**prep.summary(), "variant": variant},
        "lines": [asdict(l) for l in lines],
        "fields": [asdict(f) for f in fields],
        "flags": page_flags,
        "engine": {"vouchocr": __version__, "ocr": backend.name},
        "elapsed_ms": round((time.perf_counter() - t0) * 1000),
    }


def _read(image, prep, backend: OcrBackend):
    lines: list[OcrLine] = []
    for r in backend.detect_and_read(image):
        line = OcrLine(text=r.text, score=round(r.score, 4), box=prep.to_original(r.box))
        if r.score < REREAD_BELOW and re.search(r"\d", r.text):
            again = reread_line(backend, image, r.box)
            if again:
                line.reread, line.reread_score = again[0], round(again[1], 4)
        lines.append(line)
    fields, page_flags = extract(lines)
    return lines, fields, page_flags


def _page_score(lines, fields) -> tuple:
    kinds = {f.kind for f in fields}
    return (len(kinds), sum(l.score for l in lines) / len(lines) if lines else 0.0)


def find_images(folder: Path) -> list[Path]:
    """Semua foto di folder (rekursif), urut stabil. Folder 'Backup' tidak dibuka sama sekali."""
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted((d for d in dirs if d.lower() != "backup" and not d.startswith(".")), key=str.lower)
        for name in sorted(files, key=str.lower):
            if not name.startswith(".") and Path(name).suffix.lower() in IMAGE_SUFFIXES:
                out.append(Path(root) / name)
    return out
