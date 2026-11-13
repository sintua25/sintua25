"""CLI JSON Lines. Setiap baris stdout = satu objek JSON, supaya aplikasi desktop
bisa membaca progres secara bertahap. Kode keluar: 0 sukses, 1 verifikasi gagal,
2 galat yang perlu tindakan pengguna."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .workspace import Workspace, WorkspaceError


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vouchocr", description="OCR lokal untuk dokumen vouching.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("process", help="OCR semua foto di folder sumber.")
    pr.add_argument("source", type=Path)
    pr.add_argument("--workspace", "-w", type=Path, required=True)
    pr.add_argument("--force", action="store_true", help="Proses ulang foto yang belum direview.")

    st = sub.add_parser("state", help="Kondisi review saat ini (JSON).")
    st.add_argument("--workspace", "-w", type=Path, required=True)

    pg = sub.add_parser("page", help="Hasil OCR lengkap satu foto (baris teks + kotak).")
    pg.add_argument("--workspace", "-w", type=Path, required=True)
    pg.add_argument("--page", required=True)

    co = sub.add_parser("correct", help="Koreksi satu nilai (alasan wajib).")
    co.add_argument("--workspace", "-w", type=Path, required=True)
    co.add_argument("--page", required=True)
    co.add_argument("--field", type=int, required=True)
    co.add_argument("--value", required=True)
    co.add_argument("--reason", required=True)
    co.add_argument("--expected", help="Nilai yang dilihat pengguna; ditolak kalau sudah berubah.")
    co.add_argument("--actor")

    ad = sub.add_parser("add-field", help="Tambah nilai yang tidak terbaca OCR (alasan wajib).")
    ad.add_argument("--workspace", "-w", type=Path, required=True)
    ad.add_argument("--page", required=True)
    ad.add_argument("--kind", required=True, choices=["doc_id", "amount", "date"])
    ad.add_argument("--value", required=True)
    ad.add_argument("--reason", required=True)
    ad.add_argument("--actor")

    cf = sub.add_parser("confirm", help="Konfirmasi satu foto sudah dicek.")
    cf.add_argument("--workspace", "-w", type=Path, required=True)
    cf.add_argument("--page", required=True)
    cf.add_argument("--actor")

    uc = sub.add_parser("unconfirm", help="Batalkan konfirmasi (alasan wajib).")
    uc.add_argument("--workspace", "-w", type=Path, required=True)
    uc.add_argument("--page", required=True)
    uc.add_argument("--reason", required=True)
    uc.add_argument("--actor")

    ex = sub.add_parser("export", help="Tulis Excel + JSON ke <folder kerja>/export (hash dicatat di jejak audit).")
    ex.add_argument("--workspace", "-w", type=Path, required=True)

    ve = sub.add_parser("verify", help="Periksa rantai jejak audit dan hasil OCR.")
    ve.add_argument("--workspace", "-w", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "process":
            from .ocr import RapidOcrBackend

            ws = Workspace.open_for(args.source, args.workspace)
            for event in ws.process(RapidOcrBackend(), force=args.force):
                _emit(event)
            return 0

        ws = Workspace(args.workspace)
        ws.meta()  # galat jelas kalau bukan folder kerja
        if args.cmd == "state":
            _emit({"type": "state", **ws.state()})
        elif args.cmd == "page":
            _emit(ws.page(args.page))
        elif args.cmd == "correct":
            _emit({"type": "saved", "entry": ws.correct(args.page, args.field, args.value, args.reason,
                                                        expected=args.expected, actor=args.actor)})
        elif args.cmd == "add-field":
            _emit({"type": "saved", "entry": ws.add_field(args.page, args.kind, args.value, args.reason, actor=args.actor)})
        elif args.cmd == "confirm":
            _emit({"type": "saved", "entry": ws.confirm(args.page, actor=args.actor)})
        elif args.cmd == "unconfirm":
            _emit({"type": "saved", "entry": ws.unconfirm(args.page, args.reason, actor=args.actor)})
        elif args.cmd == "export":
            from .export import export

            _emit(export(ws))
        elif args.cmd == "verify":
            result = ws.verify()
            _emit(result)
            return 0 if result["ok"] else 1
        return 0
    except WorkspaceError as e:
        _emit(e.to_dict())
        return 2
    except KeyboardInterrupt:
        _emit({"type": "error", "code": "CANCELLED", "message": "Proses dihentikan.",
               "hint": "Jalankan lagi; foto yang sudah selesai tidak diproses ulang."})
        return 130
