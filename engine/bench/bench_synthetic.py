"""Ukur akurasi ekstraksi di foto sintetis yang sengaja dirusak.

    python bench/bench_synthetic.py

Membandingkan RapidOCR dengan setelan bawaan (+ ekstraksi nilai yang sama) dengan
pipeline penuh vouchocr. Hanya data sintetis; tidak ada foto klien.
"""

from __future__ import annotations

import itertools
import sys
import tempfile
from pathlib import Path

sys.path[:0] = [str(Path(__file__).parent.parent), str(Path(__file__).parent.parent / "tests")]

from synth import FAKTUR, KWITANSI, document, save  # noqa: E402
from vouchocr.fields import extract  # noqa: E402
from vouchocr.models import OcrLine  # noqa: E402
from vouchocr.ocr import RapidOcrBackend  # noqa: E402
from vouchocr.pipeline import process_image  # noqa: E402
from vouchocr.preprocess import load_image  # noqa: E402

DOCS = {
    "kwitansi": (KWITANSI, {("doc_id", "KW-2024/0815"), ("doc_id", "INV-00123"),
                            ("amount", "12450000.00"), ("date", "2024-03-12")}),
    "faktur": (FAKTUR, {("doc_id", "INV/2024/03/0457"), ("amount", "3552000"), ("date", "2024-03-05")}),
}
CONDITIONS = list(itertools.product(
    [0, -6, 11],                          # miring (derajat)
    ["none", "soft", "hard"],             # bayangan
    [1.0, 2.0],                           # blur
    [26, 17],                             # ukuran huruf (px)
))


def main() -> None:
    be = RapidOcrBackend()
    from rapidocr import RapidOCR
    default = RapidOCR(params={"Global.log_level": "error"})
    tmp = Path(tempfile.mkdtemp())
    raw_hit = full_hit = total = 0
    worst = []
    for (name, (lines, truth)), (i, (rot, shadow, blur, fs)) in itertools.product(DOCS.items(), enumerate(CONDITIONS)):
        im = document(lines, rotate=rot, shadow=shadow == "soft", hard_shadow=shadow == "hard",
                      blur=blur, font_size=fs, noise=10, dim=0.55, seed=i)
        path = save(im, tmp / f"{name}_{i}.jpg", quality=45)

        res = default(load_image(path).image)
        raw_lines = [OcrLine(t, float(sc), [tuple(p) for p in b.tolist()])
                     for b, t, sc in zip(res.boxes if res.boxes is not None else [], res.txts or [], res.scores or [])]
        raw_got = {(f.kind, f.value) for f in extract(raw_lines)[0]}
        page = process_image(path, be)
        full_got = {(f["kind"], f["value"]) for f in page["fields"]}

        raw_hit += len(truth & raw_got)
        full_hit += len(truth & full_got)
        total += len(truth)
        if truth - full_got:
            worst.append((name, rot, shadow, blur, fs, sorted(truth - full_got)))

    print(f"Foto: {len(DOCS) * len(CONDITIONS)}, nilai yang dicari: {total}")
    print(f"RapidOCR bawaan: {raw_hit}/{total} ({raw_hit / total:.0%})")
    print(f"vouchocr       : {full_hit}/{total} ({full_hit / total:.0%})")
    for w in worst:
        print("  terlewat:", w)


if __name__ == "__main__":
    main()
