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
from .documents import DOCUMENT_SUFFIXES, IMAGE_SUFFIXES, Unit
from .preprocess import BLUR_THRESHOLD, load_image, prepare

SCHEMA = 1


def process_image(path: Path, backend: OcrBackend, rel: str | None = None) -> dict:
    t0 = time.perf_counter()
    loaded = load_image(path)
    return _ocr_page(loaded.image, loaded.size, loaded.sha256, rel or Path(path).name, backend, t0)


def process_unit(unit: Unit, backend: OcrBackend) -> tuple[dict, bytes | None]:
    """Halaman dari PDF/Word -> (hasil halaman, PNG untuk ditampilkan atau None untuk teks)."""
    t0 = time.perf_counter()
    if unit.load is None:  # teks Word: dibaca langsung, tanpa OCR, keyakinan 100%
        lines = [OcrLine(text=t, score=1.0, box=[(10, 10 + 40 * i), (990, 10 + 40 * i), (990, 40 + 40 * i),
                                                 (10, 40 + 40 * i)]) for i, t in enumerate(unit.text_lines)]
        fields, page_flags = extract(lines)
        page = {"type": "page", "schema": SCHEMA, "file": unit.rel, "sha256": unit.key,
                "size": [1000, 40 * len(lines) + 20], "preprocess": {"variant": "teks"},
                "lines": [asdict(l) for l in lines], "fields": [asdict(f) for f in fields], "flags": page_flags,
                "engine": {"vouchocr": __version__, "ocr": "teks-word"},
                "elapsed_ms": round((time.perf_counter() - t0) * 1000)}
        render = None
    else:
        image, render, size = unit.load()
        page = _ocr_page(image, size, unit.key, unit.rel, backend, t0)
    return finish_unit_page(page, unit.kind, unit.key, unit.notes, render is not None), render


def finish_unit_page(page: dict, kind: str, key: str, notes: list[str], has_render: bool) -> dict:
    page["source_kind"] = kind
    page["image"] = f"renders/{key}.png" if has_render else None
    for note in notes:
        page["flags"].append(flag("MEDIA_SKIPPED", detail=note))
    return page


# --- pekerja OCR paralel -----------------------------------------------------------
# Satu proses per pekerja, masing-masing memuat model sendiri sekali. Tugas dikirim
# sebagai tuple sederhana supaya bisa dipickle (Windows memakai "spawn").

_WORKER_BACKEND: OcrBackend | None = None


def init_worker(threads: int) -> None:
    global _WORKER_BACKEND
    from .ocr import RapidOcrBackend

    _WORKER_BACKEND = RapidOcrBackend(threads=threads)


def run_task(task: tuple, backend: OcrBackend | None = None) -> dict:
    """("photo", path, rel, sha) atau ("array", image, size, key, rel, kind, notes, has_render)."""
    backend = backend or _WORKER_BACKEND
    if task[0] == "photo":
        _, path, rel, sha = task
        page = process_image(Path(path), backend, rel=rel)
        if page["sha256"] != sha:
            from .preprocess import ImageLoadError
            raise ImageLoadError(f"'{rel}' berubah saat sedang dibaca. Tunggu sinkronisasi selesai, lalu proses ulang.")
        return page
    _, image, size, key, rel, kind, notes, has_render = task
    page = _ocr_page(image, size, key, rel, backend, time.perf_counter())
    return finish_unit_page(page, kind, key, notes, has_render)


def _ocr_page(image, size, sha: str, rel: str, backend: OcrBackend, t0: float) -> dict:
    prep = prepare(image)

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
        "file": rel,
        "sha256": sha,
        "size": list(size),
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
    """Semua foto, PDF, dan Word di folder (rekursif), urut stabil. Folder 'Backup' tidak dibuka sama sekali."""
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted((d for d in dirs if d.lower() != "backup" and not d.startswith(".")), key=str.lower)
        for name in sorted(files, key=str.lower):
            if not name.startswith(".") and Path(name).suffix.lower() in DOCUMENT_SUFFIXES and not name.startswith("~$"):
                out.append(Path(root) / name)
    return out
