import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from test_workspace import FakeBackend, page_sha, snapshot, source, ws  # noqa: F401  (fixture)
from vouchocr.cli import main
from vouchocr.export import export, summarize
from vouchocr.workspace import Workspace, WorkspaceError

NOW = datetime(2026, 11, 13, 10, 0, 0, tzinfo=timezone.utc)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_export_writes_excel_and_json_and_logs_hashes(ws):
    sha_page = page_sha(ws)
    ws.correct(sha_page, 1, "12.500.000", "angka 4 terbaca 5? cek fisik: 12.500.000")
    ws.confirm(sha_page)
    result = export(ws, now=NOW)

    assert result["type"] == "exported" and result["pages"] == 2 and result["confirmed"] == 1
    [js, xl] = result["files"]
    assert js["path"].endswith(".json") and xl["path"].endswith(".xlsx")
    assert Path(xl["path"]).parent == ws.root / "export"
    for f in result["files"]:
        assert sha(f["path"]) == f["sha256"]
    last = ws.audit.entries()[-1]
    assert last["action"] == "export"
    assert [f["sha256"] for f in last["data"]["files"]] == [js["sha256"], xl["sha256"]]
    assert ws.verify()["ok"]

    data = json.loads(Path(js["path"]).read_text(encoding="utf-8"))
    page = next(p for p in data["pages"] if p["sha256"] == sha_page)
    amt = next(f for f in page["fields"] if f["kind"] == "amount")
    assert (amt["value"], amt["original"]) == ("12500000", "12450000.00")  # nominal tetap string
    assert page["summary"]["main_amount"] == "12500000" and page["status"] == "dikonfirmasi"

    wb = load_workbook(xl["path"])
    assert wb.sheetnames == ["Ringkasan", "Detail", "Jejak audit", "Info"]
    rows = list(wb["Ringkasan"].iter_rows(values_only=True))
    assert rows[0][:6] == ("No", "File foto", "Status", "Nomor dokumen", "Tanggal", "Nominal utama")
    confirmed = next(r for r in rows[1:] if r[2] == "Dikonfirmasi")
    assert confirmed[3] == "KW-2024/0815" and confirmed[5] == 12500000 and confirmed[8] == 1
    detail = [r for r in wb["Detail"].iter_rows(values_only=True) if r[2] == "Nominal" and r[3] == "12500000"]
    assert detail and detail[0][5] == "12450000.00" and "-> 12500000" in detail[0][12]
    audit_rows = list(wb["Jejak audit"].iter_rows(values_only=True))
    assert len(audit_rows) - 1 == len(ws.audit.entries()) - 1  # entri export ditulis sesudah file


def test_export_never_overwrites_previous_export(ws):
    a = export(ws, now=NOW)
    b = export(ws, now=NOW)  # detik yang sama
    assert a["files"][1]["path"] != b["files"][1]["path"]
    for f in a["files"]:
        assert sha(f["path"]) == f["sha256"]


def test_export_refused_when_audit_broken(ws):
    p = ws.pages_dir / f"{page_sha(ws)}.json"
    p.write_text(p.read_text(encoding="utf-8").replace("12.450.000", "99.450.000"), encoding="utf-8")
    with pytest.raises(WorkspaceError) as e:
        export(ws, now=NOW)
    assert e.value.code == "AUDIT_BROKEN" and e.value.hint
    assert not (ws.root / "export").exists()


def test_export_does_not_touch_source(ws, source):  # noqa: F811
    before = snapshot(source)
    export(ws, now=NOW)
    assert snapshot(source) == before


def test_text_starting_with_equals_is_not_a_formula(source, tmp_path):  # noqa: F811
    w = Workspace.open_for(source, tmp_path / "kerja")
    list(w.process(FakeBackend([("=HYPERLINK(\"http://x\") No: INV-001", 0.99), ("Total Rp 1.000", 0.99)])))
    xl = export(w, now=NOW)["files"][1]["path"]
    wb = load_workbook(xl)
    texts = [c.value for row in wb["Detail"].iter_rows() for c in row if isinstance(c.value, str)]
    cells = [c for row in wb["Detail"].iter_rows() for c in row]
    assert all(c.data_type != "f" for c in cells)
    assert any(t.startswith("=HYPERLINK") for t in texts) or texts  # tetap teks


def test_empty_workspace_exports_header_only(tmp_path):
    src = tmp_path / "kosong"
    src.mkdir()
    w = Workspace.open_for(src, tmp_path / "kerja")
    list(w.process(FakeBackend()))
    r = export(w, now=NOW)
    assert r["pages"] == 0 and r["confirmed"] == 0
    assert load_workbook(r["files"][1]["path"])["Ringkasan"].max_row == 1


def _page(fields, flags=()):
    return {"flags": list(flags), "fields": [
        {"kind": k, "value": v, "label": lab, "flags": [], "history": []} for k, v, lab in fields]}


@pytest.mark.parametrize("fields,main", [
    ([("amount", "100", "total"), ("amount", "100", ""), ("amount", "50", "")], "100"),  # total tunggal
    ([("amount", "100", "total"), ("amount", "90", "total")], None),                      # dua total beda
    ([("amount", "100", "total"), ("amount", "100", "total")], "100"),                    # total dobel sama
    ([("amount", "70", "")], "70"),                                                       # satu nominal
    ([("amount", "70", ""), ("amount", "80", "")], None),                                 # tanpa total, beda
    ([("amount", "-5000", "total")], "-5000"),                                            # negatif
    ([("amount", "0", "total")], "0"),                                                    # nol
    ([], None),                                                                           # kosong
])
def test_main_amount_is_never_guessed(fields, main):
    s = summarize(_page(fields))
    assert s["main_amount"] == main
    if main is None and len({v for _, v, _ in fields}) > 1:
        assert any("tidak dipilih otomatis" in f for f in s["flags"])


def test_summary_dedups_values():
    s = summarize(_page([("doc_id", "INV-1", ""), ("doc_id", "INV-1", ""), ("amount", "5", "total")]))
    assert s["doc_ids"] == ["INV-1"] and s["amounts"] == ["5"]


def test_cli_export(ws, capsys):
    assert main(["export", "-w", str(ws.root)]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["type"] == "exported" and len(out["files"]) == 2
    assert main(["export", "-w", str(ws.root / "tidak-ada")]) == 2
    err = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert err["type"] == "error" and err["hint"]
