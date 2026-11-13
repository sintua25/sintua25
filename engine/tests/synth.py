"""Foto dokumen sintetis untuk tes. Tidak ada data klien sungguhan di repo."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def document(lines: list[str], *, size=(1240, 900), font_size=34, rotate=0.0,
             shadow=False, hard_shadow=False, blur=0.0, noise=0.0, dim=1.0, seed=0) -> Image.Image:
    im = Image.new("RGB", size, (250, 250, 247))
    d = ImageDraw.Draw(im)
    f = font(font_size)
    for i, text in enumerate(lines):
        d.text((70, 70 + i * int(font_size * 2.1)), text, fill=(20, 20, 30), font=f)
    if shadow:
        # Bayangan tangan/ponsel: separuh kanan bawah gelap bertahap.
        w, h = size
        xx, yy = np.meshgrid(np.linspace(0, 1, w), np.linspace(0, 1, h))
        shade = 1.0 - 0.55 * np.clip((xx + yy - 0.8) * 1.4, 0, 1)
        arr = (np.asarray(im, dtype=np.float32) * shade[..., None]).clip(0, 255).astype(np.uint8)
        im = Image.fromarray(arr)
    if hard_shadow:
        # Bayangan tegas (kepala/ponsel) di sepertiga kanan, menutupi angka.
        w, h = size
        mask = Image.new("L", size, 0)
        ImageDraw.Draw(mask).polygon([(w * 0.55, 0), (w, 0), (w, h), (w * 0.4, h)], fill=255)
        dark = Image.eval(im, lambda v: int(v * 0.45))
        im = Image.composite(dark, im, mask.filter(ImageFilter.GaussianBlur(12)))
    if dim != 1.0 or noise:
        arr = np.asarray(im, dtype=np.float32) * dim + (1 - dim) * 128
        arr += np.random.default_rng(seed).normal(0, noise, arr.shape) if noise else 0
        im = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
    if rotate:
        im = im.rotate(rotate, expand=True, fillcolor=(235, 235, 230), resample=Image.BICUBIC)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    return im


KWITANSI = [
    "CV SUMBER MAKMUR ABADI",
    "KWITANSI No: KW-2024/0815",
    "Tanggal: 12/03/2024",
    "Telah terima dari: PT Klien Jaya",
    "Uang sejumlah: Rp 12.450.000,00",
    "Untuk pembayaran: Jasa konsultasi Maret",
    "Faktur: INV-00123",
]

FAKTUR = [
    "PT ANGIN SEPOI LOGISTIK",
    "INVOICE",
    "Nomor: INV/2024/03/0457",
    "Tanggal: 5 Maret 2024",
    "No. Rek: 123-456-7890",
    "Biaya angkut          Rp 3.200.000",
    "PPN 11%               Rp 352.000",
    "Total                 Rp 3.552.000",
]


def save(im: Image.Image, path: Path, quality: int = 85) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=quality)
    return path


def save_pdf(pages: list[Image.Image], path: Path) -> Path:
    """PDF hasil scan: tiap halaman satu gambar (Pillow menulis PDF tanpa paket tambahan)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(path, "PDF", resolution=150, save_all=True, append_images=pages[1:])
    return path


_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def save_docx(path: Path, paragraphs: list[str], table: list[list[str]] = (), images: list[Image.Image] = (),
              extra_media: dict[str, bytes] | None = None) -> Path:
    """.docx minimal: paragraf, satu tabel, dan gambar di word/media (cukup untuk pembaca kita)."""
    import io
    import zipfile
    from xml.sax.saxutils import escape

    def p(t):
        return f"<w:p><w:r><w:t>{escape(t)}</w:t></w:r></w:p>"

    rows = "".join("<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in r) + "</w:tr>" for r in table)
    body = "".join(map(p, paragraphs)) + (f"<w:tbl>{rows}</w:tbl>" if table else "")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {_W}><w:body>{body}</w:body></w:document>')
        for i, im in enumerate(images, 1):
            buf = io.BytesIO()
            im.save(buf, "PNG")
            z.writestr(f"word/media/image{i}.png", buf.getvalue())
        for name, data in (extra_media or {}).items():
            z.writestr(f"word/media/{name}", data)
    return path
