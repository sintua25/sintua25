"""PDF dan Word sebagai sumber: dipecah jadi halaman, gambar halaman disimpan di folder kerja."""

import hashlib
import json

import pytest
from PIL import Image

from synth import FAKTUR, KWITANSI, document, save, save_docx, save_pdf
from test_workspace import FakeBackend, snapshot
from vouchocr.documents import expand, file_sha
from vouchocr.preprocess import ImageLoadError
from vouchocr.workspace import Workspace


@pytest.fixture
def mixed(tmp_path):
    src = tmp_path / "klien" / "Campuran"
    save(document(KWITANSI), src / "foto.jpg")
    save_pdf([document(KWITANSI), document(FAKTUR)], src / "dua halaman.pdf")
    save_pdf([document(FAKTUR)], src / "satu.pdf")
    save_docx(src / "memo.docx", ["Memo pembayaran", "No: INV-2024/0099", "Tanggal 05/03/2024"],
              table=[["Keterangan", "Jumlah"], ["Total", "Rp 7.250.000"]],
              images=[document(FAKTUR), Image.new("RGB", (40, 40))],  # gambar kecil = logo, dilewati
              extra_media={"rusak.png": b"bukan png", "logo.emf": b"vektor"})
    (src / "lama.doc").write_bytes(b"\xd0\xcf\x11\xe0 word lama")
    (src / "~$memo.docx").write_bytes(b"file kunci Word")  # file sementara Word, bukan dokumen
    return src


def test_expand_pdf_pages_and_keys(mixed):
    data = (mixed / "dua halaman.pdf").read_bytes()
    sha = file_sha(data)
    units = expand(mixed / "dua halaman.pdf", "dua halaman.pdf", data, sha)
    assert [u.rel for u in units] == ["dua halaman.pdf#hal1", "dua halaman.pdf#hal2"]
    assert len({u.key for u in units}) == 2 and all(len(u.key) == 64 and u.key != sha for u in units)
    image, png, size = units[1].load()
    assert png.startswith(b"\x89PNG") and image.shape[1] == size[0] > 1000  # 200 dpi
    one = expand(mixed / "satu.pdf", "satu.pdf", (mixed / "satu.pdf").read_bytes(), "x" * 64)
    assert [u.rel for u in one] == ["satu.pdf"]  # PDF satu halaman: tanpa akhiran


def test_expand_docx_text_table_and_images(mixed):
    data = (mixed / "memo.docx").read_bytes()
    units = expand(mixed / "memo.docx", "memo.docx", data, file_sha(data))
    assert [u.kind for u in units] == ["docx_text", "docx_image"]
    assert "Total | Rp 7.250.000" in units[0].text_lines
    assert units[0].notes and "rusak.png" in units[0].notes[0]


@pytest.mark.parametrize("name,content,msg", [
    ("x.pdf", b"%PDF-1.4 rusak", "rusak"),
    ("x.docx", b"PK bukan zip", "rusak"),
    ("x.doc", b"\xd0\xcf", ".doc"),
])
def test_bad_documents_explain_themselves(tmp_path, name, content, msg):
    (tmp_path / name).write_bytes(content)
    with pytest.raises(ImageLoadError, match=msg):
        expand(tmp_path / name, name, content, file_sha(content))


def test_empty_docx_refused(tmp_path):
    p = save_docx(tmp_path / "kosong.docx", [])
    with pytest.raises(ImageLoadError, match="tidak berisi"):
        expand(p, "kosong.docx", p.read_bytes(), "0" * 64)


def test_workspace_processes_mixed_folder(mixed, tmp_path):
    before = snapshot(mixed)
    ws = Workspace.open_for(mixed, tmp_path / "kerja")
    events = list(ws.process(FakeBackend()))
    assert events[0]["total"] == 5  # foto, 2 pdf, docx, doc; file ~$ dilewati
    files = sorted(e["file"] for e in events if e["type"] == "page")
    assert files == ["dua halaman.pdf#hal1", "dua halaman.pdf#hal2", "foto.jpg", "memo.docx#gambar1",
                     "memo.docx#teks", "satu.pdf"]
    [err] = [e for e in events if e["type"] == "error"]
    assert err["file"] == "lama.doc" and ".docx" in err["message"] and err["hint"]
    assert snapshot(mixed) == before  # sumber tidak berubah

    st = {p["files"][0]: p for p in ws.state()["pages"]}
    assert st["foto.jpg"]["image"] is None and st["foto.jpg"]["source_kind"] == "image"
    pdf = st["dua halaman.pdf#hal2"]
    assert pdf["image"] == f"renders/{pdf['sha256']}.png" and (ws.root / pdf["image"]).exists()
    text = st["memo.docx#teks"]
    assert text["image"] is None and text["source_kind"] == "docx_text"
    assert ("amount", "7250000") in {(f["kind"], f["value"]) for f in text["fields"]}
    assert any(f["label"] == "total" for f in text["fields"] if f["kind"] == "amount")
    assert any(f["code"] == "MEDIA_SKIPPED" for f in text["flags"])

    # Jejak audit mencatat hash file sumber dan gambar halaman; verify memeriksanya.
    rec = next(e for e in ws.audit.entries() if e["target"] == f"page:{pdf['sha256']}")["data"]
    assert rec["source_sha256"] == hashlib.sha256((mixed / "dua halaman.pdf").read_bytes()).hexdigest()
    assert ws.verify()["ok"]
    (ws.root / pdf["image"]).write_bytes(b"diganti")
    v = ws.verify()
    assert not v["ok"] and any("Gambar halaman" in p for p in v["problems"])


def test_reprocess_skips_and_review_on_pdf_page(mixed, tmp_path):
    ws = Workspace.open_for(mixed, tmp_path / "kerja")
    list(ws.process(FakeBackend()))
    key = next(p["sha256"] for p in ws.state()["pages"] if p["files"] == ["dua halaman.pdf#hal1"])
    ws.correct(key, 1, "12.500.000", "cek fisik")
    ws.confirm(key)
    again = list(ws.process(FakeBackend(), force=True))
    assert any(e["type"] == "skipped" and e["sha256"] == key and e["reason"] == "sudah direview" for e in again)
    assert next(p for p in ws.state()["pages"] if p["sha256"] == key)["status"] == "dikonfirmasi"


def test_changed_pdf_drops_stale_pages(mixed, tmp_path):
    ws = Workspace.open_for(mixed, tmp_path / "kerja")
    list(ws.process(FakeBackend()))
    save_pdf([document(["HANYA SATU HALAMAN No: INV-777"])], mixed / "dua halaman.pdf")
    list(ws.process(FakeBackend()))
    names = json.loads((ws.root / "index.json").read_text(encoding="utf-8"))
    assert "dua halaman.pdf" in names and not any(k.startswith("dua halaman.pdf#") for k in names)


@pytest.mark.ocr
def test_real_ocr_reads_pdf_page(tmp_path):
    from vouchocr.ocr import RapidOcrBackend

    src = tmp_path / "pdf"
    save_pdf([document(KWITANSI, rotate=2)], src / "scan.pdf")
    ws = Workspace.open_for(src, tmp_path / "kerja")
    list(ws.process(RapidOcrBackend()))
    [page] = ws.state()["pages"]
    got = {(f["kind"], f["value"]) for f in page["fields"]}
    assert {("doc_id", "KW-2024/0815"), ("amount", "12450000.00"), ("date", "2024-03-12")} <= got
