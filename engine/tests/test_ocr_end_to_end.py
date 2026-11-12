"""Alur penuh dengan model OCR sungguhan, lewat CLI seperti yang dipanggil aplikasi."""

import json
import subprocess
import sys

import pytest

from synth import FAKTUR, KWITANSI, document, save

pytestmark = pytest.mark.ocr


def cli(*args):
    r = subprocess.run([sys.executable, "-m", "vouchocr", *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8")
    return r.returncode, [json.loads(l) for l in r.stdout.splitlines() if l.strip()], r.stderr


@pytest.fixture(scope="module")
def processed(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    src = tmp / "Kas Maret 2024"
    save(document(KWITANSI, rotate=6, shadow=True, blur=0.8), src / "kwitansi miring.jpg", quality=70)
    save(document(FAKTUR, hard_shadow=True, noise=6), src / "faktur.jpg")
    code, events, err = cli("process", src, "-w", tmp / "kerja")
    assert code == 0, err
    return tmp / "kerja", events


def fields_of(ws, name):
    _, [state], _ = cli("state", "-w", ws)
    page = next(p for p in state["pages"] if name in p["files"])
    return page, {(f["kind"], f["value"]) for f in page["fields"]}


def test_events_stream(processed):
    _, events = processed
    assert [e["type"] for e in events] == ["start", "page", "page", "done"]
    assert events[-1]["failed"] == 0


def test_kwitansi_values(processed):
    _, got = fields_of(processed[0], "kwitansi miring.jpg")
    assert {("doc_id", "KW-2024/0815"), ("doc_id", "INV-00123"), ("amount", "12450000.00"),
            ("date", "2024-03-12")} <= got


def test_faktur_values_and_bank_account_ignored(processed):
    page, got = fields_of(processed[0], "faktur.jpg")
    assert {("doc_id", "INV/2024/03/0457"), ("amount", "3552000"), ("date", "2024-03-05")} <= got
    assert not any("7890" in v for _, v in got)
    total = [f for f in page["fields"] if f["kind"] == "amount" and f["label"] == "total"]
    assert [f["value"] for f in total] == ["3552000"]


def test_page_command_returns_boxes_in_original_coordinates(processed):
    ws, _ = processed
    page, _ = fields_of(ws, "faktur.jpg")
    code, [full], _ = cli("page", "-w", ws, "--page", page["sha256"])
    assert code == 0 and full["size"] == [1240, 900]
    for line in full["lines"]:
        assert len(line["box"]) == 4
        assert all(0 <= x <= 1240 and 0 <= y <= 900 for x, y in line["box"])
    code, [e], _ = cli("page", "-w", ws, "--page", "../../etc/passwd")
    assert code == 2 and e["code"] == "BAD_PAGE_ID"


def test_review_flow_and_verify(processed):
    ws, _ = processed
    page, _ = fields_of(ws, "kwitansi miring.jpg")
    sha = page["sha256"]
    amt = next(f for f in page["fields"] if f["kind"] == "amount")

    code, [e], _ = cli("correct", "-w", ws, "--page", sha, "--field", amt["id"], "--value", "12.540.000",
                       "--reason", "cek fisik", "--expected", amt["value"], "--actor", "auditor1")
    assert code == 0 and e["type"] == "saved"
    code, [e], _ = cli("correct", "-w", ws, "--page", sha, "--field", amt["id"], "--value", "1", "--reason", "")
    assert code == 2 and e["code"] == "REASON_REQUIRED" and e["hint"]
    assert cli("confirm", "-w", ws, "--page", sha)[0] == 0

    code, [v], _ = cli("verify", "-w", ws)
    assert code == 0 and v["ok"] and v["pages_checked"] == 2

    log = ws / "audit.jsonl"
    log.write_text(log.read_text(encoding="utf-8").replace("12540000", "99999999"), encoding="utf-8")
    code, [v], _ = cli("verify", "-w", ws)
    assert code == 1 and not v["ok"]


def test_not_a_workspace_error_is_explained(tmp_path):
    code, [e], _ = cli("state", "-w", tmp_path)
    assert code == 2 and e["code"] == "NOT_A_WORKSPACE" and e["hint"]
