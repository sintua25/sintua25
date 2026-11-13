"""Export hasil review ke Excel (untuk kertas kerja) dan JSON (untuk mesin lain).

- Jejak audit diperiksa dulu; kalau rantainya putus, export ditolak.
- File ditulis atomik ke `<folder kerja>/export/`, nama berisi waktu, tidak menimpa.
- SHA-256 setiap file dicatat di jejak audit (aksi `export`).
- Nominal di JSON tetap string; di Excel ditulis sebagai angka dari Decimal supaya bisa
  dijumlah, dengan teks aslinya tetap ada di sheet Detail.
- Tidak ada rumus: teks dari OCR yang diawali "=" ditulis sebagai teks biasa.
"""

from __future__ import annotations

import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import __version__
from .flags import MESSAGES
from .storage import atomic_write_bytes, dump_json
from .workspace import Workspace, WorkspaceError

STATUS_TEXT = {"dikonfirmasi": "Dikonfirmasi", "belum_dicek": "Belum dicek"}
KIND_TEXT = {"doc_id": "Nomor dokumen", "amount": "Nominal", "date": "Tanggal"}
ACTION_TEXT = {
    "open_workspace": "Folder kerja dibuat", "process": "Foto dibaca OCR", "correct": "Koreksi",
    "add_field": "Nilai ditambahkan", "confirm": "Konfirmasi", "unconfirm": "Batal konfirmasi",
    "export": "Export",
}
MONEY_FORMAT = "#,##0.00"


def export(ws: Workspace, now: datetime | None = None) -> dict:
    """Tulis Excel + JSON. Kembalikan ringkasan + daftar file dan hash-nya."""
    check = ws.verify()
    if not check["ok"]:
        raise WorkspaceError("AUDIT_BROKEN", "Jejak audit tidak utuh, export dibatalkan: " + "; ".join(check["problems"]),
                          "Jangan pakai hasil folder kerja ini. Proses ulang dari foto asli di folder kerja baru.")
    state = ws.state()
    pages = sorted(state["pages"], key=lambda p: p["files"][0].lower())
    now = (now or datetime.now()).astimezone()
    info = {
        "source": state["source"], "workspace": str(ws.root), "engine": __version__,
        "exported": now.isoformat(timespec="seconds"), "audit_entries": check["entries"],
        "audit_last_hash": check["last_hash"],
    }
    stamp = now.strftime("%Y%m%d-%H%M%S")
    out_dir = ws.root / "export"
    xlsx_path = _free_path(out_dir / f"vouching-{stamp}.xlsx")
    json_path = xlsx_path.with_suffix(".json")

    # Teks lengkap per halaman (semua baris OCR, bukan hanya nilai yang diambil).
    texts = {p["sha256"]: [{"line": i, "text": l["text"], "score": l["score"], "reread": l.get("reread")}
                           for i, l in enumerate(ws.page(p["sha256"])["lines"])] for p in pages}
    payload = {"schema": "meja-vouching.export/1", **info,
               "pages": [{**_page_json(p), "text": texts[p["sha256"]]} for p in pages]}
    # Susun dua-duanya di memori dulu: kalau Excel gagal dibuat, tidak ada file setengah jadi.
    xlsx = _xlsx(info, pages, ws.audit.entries(), texts)
    files = [
        {"path": str(json_path), "sha256": atomic_write_bytes(json_path, dump_json(payload))},
        {"path": str(xlsx_path), "sha256": atomic_write_bytes(xlsx_path, xlsx)},
    ]
    ws.audit.append("export", "workspace", data={"files": [
        {"name": Path(f["path"]).name, "sha256": f["sha256"]} for f in files]})
    confirmed = sum(p["status"] == "dikonfirmasi" for p in pages)
    return {"type": "exported", "files": files, "pages": len(pages), "confirmed": confirmed}


def _free_path(path: Path) -> Path:
    """Dua export di detik yang sama tidak boleh saling menimpa."""
    n, candidate = 1, path
    while candidate.exists() or candidate.with_suffix(".json").exists():
        n += 1
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
    return candidate


# --- ringkasan per foto ----------------------------------------------------------

def summarize(page: dict) -> dict:
    """Satu baris ringkasan. Mesin tidak memilih nilai yang 'benar': kalau ada beberapa
    nilai berbeda, semuanya ditulis dan ditandai."""
    by_kind: dict[str, list[str]] = {"doc_id": [], "date": [], "amount": []}
    totals: list[str] = []
    for f in page["fields"]:
        vals = by_kind.setdefault(f["kind"], [])
        if f["value"] not in vals:
            vals.append(f["value"])
        if f["kind"] == "amount" and f.get("label") == "total" and f["value"] not in totals:
            totals.append(f["value"])
    # Nominal utama: nilai berlabel total kalau hanya satu; kalau tidak ada label total,
    # nominal kalau hanya satu nilai berbeda. Selain itu kosong dan auditor yang memilih.
    candidates = totals or by_kind["amount"]
    main = candidates[0] if len(candidates) == 1 else None
    flags = [f["message"] for f in page["flags"]]
    field_flags = {fl["code"] for f in page["fields"] for fl in f.get("flags", [])}
    flags += [MESSAGES[c] for c in sorted(field_flags) if c in MESSAGES]
    if main is None and len(candidates) > 1:
        flags.append("Nominal utama tidak dipilih otomatis: ada beberapa nilai berbeda.")
    return {
        "doc_ids": by_kind["doc_id"], "dates": by_kind["date"], "amounts": by_kind["amount"],
        "main_amount": main, "flags": flags,
        "corrections": sum(len(f["history"]) for f in page["fields"]),
    }


def _page_json(page: dict) -> dict:
    return {
        "sha256": page["sha256"], "files": page["files"], "status": page["status"],
        "flags": page["flags"], "summary": summarize(page),
        "fields": [{k: f.get(k) for k in ("id", "kind", "value", "original", "source", "label", "raw", "line",
                                          "score", "flags", "history")} for f in page["fields"]],
    }


# --- Excel -----------------------------------------------------------------------

def _xlsx(info: dict, pages: list[dict], audit_entries, texts: dict[str, list[dict]]) -> bytes:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        raise WorkspaceError("OPENPYXL_MISSING", "Paket Excel (openpyxl) belum terpasang di mesin OCR.",
                             'Di folder engine jalankan: .\\.venv\\Scripts\\python.exe -m pip install -e ".[dev]"')

    wb = Workbook()
    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1C2B4A")
    doubt_fill = PatternFill("solid", fgColor="FFF2A8")

    def sheet(title: str, headers: list[str], widths: list[int], first: bool = False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws.append(headers)
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w
            c = ws.cell(1, i)
            c.font, c.fill = head_font, head_fill
            c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.freeze_panes = "A2"
        return ws

    # Ringkasan: satu baris per foto.
    rs = sheet("Ringkasan",
               ["No", "File foto", "Status", "Nomor dokumen", "Tanggal", "Nominal utama", "Semua nominal terbaca",
                "Indikator keraguan", "Jumlah koreksi", "SHA-256 foto"],
               [5, 30, 14, 28, 14, 18, 36, 50, 10, 20], first=True)
    for n, p in enumerate(pages, 1):
        s = summarize(p)
        _row(rs, [n, "; ".join(p["files"]), STATUS_TEXT.get(p["status"], p["status"]), "; ".join(s["doc_ids"]),
                  "; ".join(_date_text(d) for d in s["dates"]), _money(s["main_amount"]),
                  "; ".join(_money_text(a) for a in s["amounts"]), "\n".join(s["flags"]), s["corrections"],
                  p["sha256"]])
        rs.cell(rs.max_row, 6).number_format = MONEY_FORMAT
        if s["flags"]:
            rs.cell(rs.max_row, 8).fill = doubt_fill
    rs.auto_filter.ref = rs.dimensions

    # Detail: setiap nilai, OCR asli vs akhir, dan asal barisnya.
    ds = sheet("Detail",
               ["No", "File foto", "Jenis", "Nilai akhir", "Nominal (angka)", "Nilai OCR asli", "Sumber", "Label",
                "Teks terbaca", "Baris OCR", "Keyakinan", "Indikator", "Riwayat koreksi"],
               [5, 30, 15, 22, 18, 22, 10, 10, 34, 9, 10, 40, 50])
    for n, p in enumerate(pages, 1):
        for f in p["fields"]:
            amount = _money(f["value"]) if f["kind"] == "amount" else None
            _row(ds, [n, p["files"][0], KIND_TEXT.get(f["kind"], f["kind"]), f["value"], amount,
                      f.get("original") if f.get("original") is not None else "(ditambah auditor)",
                      "OCR" if f.get("source") == "ocr" else "Auditor", f.get("label") or "", f.get("raw") or "",
                      f.get("line"), f.get("score"), "\n".join(fl["message"] for fl in f.get("flags", [])),
                      "\n".join(_hist_text(h) for h in f.get("history", []))])
            ds.cell(ds.max_row, 5).number_format = MONEY_FORMAT
            if f.get("flags"):
                ds.cell(ds.max_row, 12).fill = doubt_fill
    ds.auto_filter.ref = ds.dimensions

    # Teks lengkap: semua baris yang terbaca, urut seperti di foto.
    ts = sheet("Teks lengkap", ["No", "File foto", "Baris", "Teks", "Keyakinan", "Dibaca ulang"],
               [5, 30, 7, 70, 10, 40])
    for n, p in enumerate(pages, 1):
        for t in texts.get(p["sha256"], []):
            _row(ts, [n, p["files"][0], t["line"], t["text"], t["score"],
                      t["reread"] if t["reread"] and t["reread"] != t["text"] else ""])
    ts.auto_filter.ref = ts.dimensions

    # Jejak audit lengkap.
    js = sheet("Jejak audit", ["Urutan", "Waktu", "Oleh", "Aksi", "Target", "Nilai lama", "Nilai baru", "Alasan", "Hash"],
               [8, 22, 14, 18, 30, 22, 22, 40, 20])
    for e in audit_entries:
        _row(js, [e["seq"], e["ts"], e.get("actor", ""), ACTION_TEXT.get(e["action"], e["action"]), e["target"],
                  _plain(e.get("before")), _plain(e.get("after")), e.get("reason", ""), e["hash"]])

    # Info: asal file ini.
    inf = sheet("Info", ["Keterangan", "Nilai"], [26, 90])
    for k, v in [("Folder foto klien", info["source"]), ("Folder kerja", info["workspace"]),
                 ("Waktu export", info["exported"]), ("Versi mesin", info["engine"]),
                 ("Jumlah foto", len(pages)),
                 ("Foto dikonfirmasi", sum(p["status"] == "dikonfirmasi" for p in pages)),
                 ("Catatan jejak audit", info["audit_entries"]), ("Hash catatan terakhir", info["audit_last_hash"]),
                 ("Catatan", "Nilai akhir = hasil OCR asli + koreksi di jejak audit. Mesin hanya menandai keraguan; "
                             "kesimpulan ada pada auditor.")]:
        _row(inf, [k, v])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(ws, values: list) -> None:
    from openpyxl.styles import Alignment

    ws.append(values)
    for c in ws[ws.max_row]:
        if isinstance(c.value, str):
            c.data_type = "s"  # teks seperti "=1+1" dari OCR tidak boleh jadi rumus
            if "\n" in c.value:
                c.alignment = Alignment(wrap_text=True, vertical="top")


def _money(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _money_text(value: str) -> str:
    d = _money(value)
    if d is None:
        return value
    sign, s = ("-" if d < 0 else ""), f"{abs(d):,.2f}"
    return sign + s.replace(",", "_").replace(".", ",").replace("_", ".")


def _date_text(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _plain(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return ", ".join(f"{k}: {x}" for k, x in v.items())
    return str(v)


def _hist_text(h: dict) -> str:
    return f"#{h['seq']} {h['ts']} {h.get('actor', '')}: {_plain(h.get('before'))} -> {_plain(h.get('after'))} ({h.get('reason', '')})"
