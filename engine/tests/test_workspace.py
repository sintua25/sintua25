import hashlib
import json
import os

import pytest

from synth import KWITANSI, document, save
from vouchocr.ocr import RawLine
from vouchocr.workspace import Workspace, WorkspaceError


class FakeBackend:
    name = "fake"

    def __init__(self, lines=None, fail_on=None):
        self.lines = lines or [("KWITANSI No: KW-2024/0815", 0.99), ("Uang sejumlah: Rp 12.450.000,00", 0.99)]
        self.calls = 0

    def detect_and_read(self, image):
        self.calls += 1
        return [RawLine(t, s, [(10, 10 + 40 * i), (300, 10 + 40 * i), (300, 40 + 40 * i), (10, 40 + 40 * i)])
                for i, (t, s) in enumerate(self.lines)]

    def read_crop(self, crop):
        return "", 0.0


def snapshot(folder):
    out = {}
    for root, _, files in os.walk(folder):
        for n in files:
            p = os.path.join(root, n)
            st = os.stat(p)
            out[p] = (hashlib.sha256(open(p, "rb").read()).hexdigest(), st.st_mtime_ns, st.st_size)
    return out


@pytest.fixture
def source(tmp_path):
    src = tmp_path / "klien" / "Kas Maret"
    save(document(KWITANSI), src / "a.jpg")
    save(document(KWITANSI, rotate=3), src / "sub" / "b.jpg")
    (src / "b_copy.jpg").write_bytes((src / "sub" / "b.jpg").read_bytes())  # foto duplikat
    (src / "catatan.txt").write_text("bukan foto")
    (src / "rusak.jpg").write_bytes(b"\xff\xd8 rusak")
    save(document(["JANGAN DIBACA"]), src / "Backup" / "z.jpg")
    return src


@pytest.fixture
def ws(source, tmp_path):
    w = Workspace.open_for(source, tmp_path / "kerja")
    list(w.process(FakeBackend()))
    return w


def page_sha(ws):
    return ws.state()["pages"][0]["sha256"]


def test_process_events_and_dedup(source, tmp_path):
    w = Workspace.open_for(source, tmp_path / "kerja")
    backend = FakeBackend()
    events = list(w.process(backend))
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "done"
    assert events[0]["total"] == 4  # a, b_copy, rusak, sub/b; Backup & .txt tidak ikut
    [err] = [e for e in events if e["type"] == "error"]
    assert err["file"] == "rusak.jpg" and err["code"] == "IMAGE_UNREADABLE" and err["hint"]
    assert events[-1] == {**events[-1], "processed": 2, "skipped": 1, "failed": 1}
    st = w.state()
    assert sorted(len(p["files"]) for p in st["pages"]) == [1, 2]  # duplikat jadi satu halaman, dua file


def test_source_folder_untouched_and_backup_never_read(source, tmp_path, monkeypatch):
    before = snapshot(source)
    opened = []
    real_open = open

    def spy(path, *a, **k):
        opened.append(str(path))
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", spy)
    w = Workspace.open_for(source, tmp_path / "kerja")
    list(w.process(FakeBackend()))
    monkeypatch.undo()
    assert snapshot(source) == before
    assert not any("Backup" in p for p in opened)


def test_resume_skips_done_pages(ws):
    backend = FakeBackend()
    events = list(ws.process(backend))
    assert backend.calls == 0
    assert events[-1]["skipped"] == 3


def test_workspace_inside_source_refused(source):
    with pytest.raises(WorkspaceError) as e:
        Workspace.open_for(source, source / "hasil")
    assert e.value.code == "WORKSPACE_INSIDE_SOURCE" and e.value.hint


def test_backup_as_source_refused(source, tmp_path):
    with pytest.raises(WorkspaceError, match="Backup"):
        Workspace.open_for(source / "Backup", tmp_path / "k2")


def test_workspace_of_other_source_refused(ws, tmp_path):
    other = tmp_path / "lain"; other.mkdir()
    with pytest.raises(WorkspaceError) as e:
        Workspace.open_for(other, ws.root)
    assert e.value.code == "WORKSPACE_OTHER_SOURCE"


def test_correct_keeps_original_and_history(ws):
    sha = page_sha(ws)
    amount_id = next(f["id"] for f in ws.state()["pages"][0]["fields"] if f["kind"] == "amount")
    ws.correct(sha, amount_id, "12.540.000", "angka 4 dan 5 tertukar, cek fisik", expected="12450000.00", actor="ani")
    f = ws.state()["pages"][0]["fields"][amount_id]
    assert f["original"] == "12450000.00" and f["value"] == "12540000"
    [h] = f["history"]
    assert (h["actor"], h["before"], h["after"]) == ("ani", "12450000.00", "12540000")
    page = ws.page(sha)
    assert page["fields"][amount_id]["value"] == "12450000.00"  # hasil OCR asli tidak ditimpa


@pytest.mark.parametrize("value, reason, expected, code", [
    ("1.000", "", None, "REASON_REQUIRED"),
    ("1.000", "   ", None, "REASON_REQUIRED"),
    ("", "x", None, "EMPTY_VALUE"),
    ("12,45.0", "x", None, "BAD_AMOUNT"),
    ("12.450.000,00", "x", None, "NO_CHANGE"),
    ("1.000", "x", "999", "STALE"),
])
def test_correct_rejections(ws, value, reason, expected, code):
    sha = page_sha(ws)
    amount_id = next(f["id"] for f in ws.state()["pages"][0]["fields"] if f["kind"] == "amount")
    n = len(ws.audit.entries())
    with pytest.raises(WorkspaceError) as e:
        ws.correct(sha, amount_id, value, reason, expected=expected)
    assert e.value.code == code
    assert len(ws.audit.entries()) == n  # penolakan tidak menulis apa pun


def test_negative_and_zero_corrections_allowed(ws):
    sha = page_sha(ws)
    amount_id = next(f["id"] for f in ws.state()["pages"][0]["fields"] if f["kind"] == "amount")
    ws.correct(sha, amount_id, "-500", "nota kredit")
    ws.correct(sha, amount_id, "0", "batal")
    assert ws.state()["pages"][0]["fields"][amount_id]["value"] == "0"


def test_confirm_locks_until_unconfirmed_with_reason(ws):
    sha = page_sha(ws)
    ws.confirm(sha)
    with pytest.raises(WorkspaceError, match="terkunci"):
        ws.correct(sha, 0, "KW-1", "x")
    with pytest.raises(WorkspaceError) as e:
        ws.confirm(sha)
    assert e.value.code == "ALREADY_CONFIRMED"
    with pytest.raises(WorkspaceError):
        ws.unconfirm(sha, "")
    ws.unconfirm(sha, "salah konfirmasi")
    ws.correct(sha, 0, "KW-2024/0816", "angka terakhir 6")
    assert ws.state()["pages"][0]["status"] == "belum_dicek"


def test_add_missing_field(ws):
    sha = page_sha(ws)
    ws.add_field(sha, "date", "15/03/2024", "tanggal tulisan tangan tidak terbaca")
    f = ws.state()["pages"][0]["fields"][-1]
    assert (f["kind"], f["value"], f["source"], f["original"]) == ("date", "2024-03-15", "auditor", None)
    with pytest.raises(WorkspaceError):
        ws.add_field(sha, "date", "31/02/2024", "x")


def test_reviewed_page_not_overwritten_by_force(ws):
    sha = page_sha(ws)
    ws.confirm(sha)
    before = (ws.pages_dir / f"{sha}.json").read_bytes()
    events = list(ws.process(FakeBackend([("lain", 0.9)]), force=True))
    assert any(e.get("reason") == "sudah direview" for e in events)
    assert (ws.pages_dir / f"{sha}.json").read_bytes() == before


def test_verify_ok_then_detects_tampered_ocr_result(ws):
    assert ws.verify()["ok"]
    sha = page_sha(ws)
    p = ws.pages_dir / f"{sha}.json"
    data = json.loads(p.read_text()); data["fields"][1]["value"] = "99999999"
    p.write_text(json.dumps(data))
    r = ws.verify()
    assert not r["ok"] and "berubah" in r["problems"][0]


def test_unknown_page(ws):
    with pytest.raises(WorkspaceError) as e:
        ws.confirm("0" * 64)
    assert e.value.code == "PAGE_NOT_FOUND"
