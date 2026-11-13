"""Folder kerja: hasil OCR, koreksi, dan jejak audit untuk satu folder sumber.

Folder sumber klien hanya dibaca. Semua yang ditulis masuk ke folder kerja,
yang tidak boleh berada di dalam folder sumber.

Nilai akhir tidak pernah disimpan langsung. Nilai akhir = hasil OCR asli
+ semua koreksi di jejak audit, diputar ulang berurutan. Jadi setiap angka
punya riwayat lengkap: dibaca dari baris mana, siapa mengubah, kapan, kenapa.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator

from . import __version__
from .audit import AuditLog
from .ids import canon_doc_id
from .money import AmountError, parse_amount
from .ocr import OcrBackend
from .documents import IMAGE_SUFFIXES, expand, file_sha, read_source
from .pipeline import SCHEMA, find_images, process_image, process_unit
from .preprocess import ImageLoadError
from .storage import atomic_write_bytes, dump_json, sha256_file

KINDS = ("doc_id", "amount", "date")


class WorkspaceError(Exception):
    """Galat yang bisa ditindaklanjuti pengguna. `hint` = apa yang bisa dilakukan."""

    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint

    def to_dict(self) -> dict:
        return {"type": "error", "code": self.code, "message": self.message, "hint": self.hint}


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.pages_dir = self.root / "pages"
        self.audit = AuditLog(self.root / "audit.jsonl")
        self.meta_path = self.root / "workspace.json"
        self.index_path = self.root / "index.json"

    # --- pembuatan --------------------------------------------------------

    @classmethod
    def open_for(cls, source: Path, root: Path) -> "Workspace":
        source, root = Path(source).resolve(), Path(root).resolve()
        if not source.is_dir():
            raise WorkspaceError("SOURCE_MISSING", f"Folder sumber '{source}' tidak ada.",
                                 "Pilih ulang folder foto.")
        if any(p.name.lower() == "backup" for p in (source, *source.parents)):
            raise WorkspaceError("SOURCE_IS_BACKUP", f"'{source}' berada di folder Backup.",
                                 "Folder Backup tidak boleh diproses. Pilih folder kerja yang asli.")
        if root == source or source in root.parents:
            raise WorkspaceError("WORKSPACE_INSIDE_SOURCE",
                                 "Folder kerja ada di dalam folder sumber klien.",
                                 "Pilih lokasi folder kerja di luar folder foto klien, supaya folder klien tidak berubah.")
        if root in source.parents:
            raise WorkspaceError("SOURCE_INSIDE_WORKSPACE", "Folder sumber ada di dalam folder kerja.",
                                 "Pilih folder kerja yang terpisah.")

        ws = cls(root)
        if ws.meta_path.exists():
            meta = ws.meta()
            if Path(meta["source"]) != source:
                raise WorkspaceError("WORKSPACE_OTHER_SOURCE",
                                     f"Folder kerja ini milik folder sumber lain: {meta['source']}.",
                                     "Pilih folder kerja baru untuk folder sumber ini.")
        else:
            root.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(ws.meta_path, dump_json({
                "schema": SCHEMA, "source": str(source), "engine": __version__,
                "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            }))
            ws.audit.append("open_workspace", str(source), data={"workspace": str(root)})
        return ws

    def meta(self) -> dict:
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise WorkspaceError("NOT_A_WORKSPACE", f"'{self.root}' bukan folder kerja Meja Vouching.",
                                 "Pilih folder kerja yang dibuat oleh aplikasi ini.")

    # --- proses OCR -----------------------------------------------------------

    def process(self, backend: OcrBackend, force: bool = False) -> Iterator[dict]:
        """Proses semua foto. Menghasilkan event satu per satu (untuk progres di UI).
        Foto yang sudah diproses dengan versi mesin yang sama dilewati, jadi proses
        yang terputus bisa dilanjutkan."""
        source = Path(self.meta()["source"])
        images = find_images(source)
        index = self.index()
        reviewed = {e["target"][5:].partition("/")[0] for e in self.audit.entries()
                    if e["action"] in ("correct", "add_field", "confirm", "unconfirm")}
        yield {"type": "start", "source": str(source), "total": len(images)}
        ok = skipped = failed = 0
        t0 = time.perf_counter()
        for n, path in enumerate(images, 1):
            rel = path.relative_to(source).as_posix()
            try:
                if path.suffix.lower() in IMAGE_SUFFIXES:
                    sha = sha256_file(path)
                    jobs = [(rel, sha, lambda path=path, rel=rel, sha=sha: self._photo(path, rel, sha, backend))]
                else:
                    data = read_source(path)
                    sha = file_sha(data)
                    jobs = [(u.rel, u.key, lambda u=u: process_unit(u, backend))
                            for u in expand(path, rel, data, sha)]
                    for old in [k for k in index if k == rel or k.startswith(rel + "#")]:
                        del index[old]  # file berubah (jumlah halaman beda): buang entri lama
            except ImageLoadError as e:
                failed += 1
                yield {"type": "error", "n": n, "file": rel, "code": "IMAGE_UNREADABLE", "message": str(e),
                       "hint": "File ini dilewati; file lain tetap diproses."}
                continue
            for unit_rel, key, run in jobs:
                try:
                    page_path = self.pages_dir / f"{key}.json"
                    if page_path.exists() and key in reviewed:
                        # Koreksi menunjuk ke nilai hasil OCR ini; menimpanya memutus jejak.
                        index[unit_rel] = key
                        skipped += 1
                        yield {"type": "skipped", "n": n, "file": unit_rel, "sha256": key, "reason": "sudah direview"}
                        continue
                    if not force and page_path.exists() and self._page_engine(page_path) == __version__:
                        index[unit_rel] = key
                        skipped += 1
                        yield {"type": "skipped", "n": n, "file": unit_rel, "sha256": key, "reason": "sudah diproses"}
                        continue
                    page, render = run()
                    rec = {"file": unit_rel}
                    if render is not None:
                        rec["render_sha256"] = atomic_write_bytes(self.root / page["image"], render)
                    if key != sha:
                        rec["source_sha256"] = sha
                    rec["result_sha256"] = atomic_write_bytes(page_path, dump_json(page))
                    rec["engine"] = page["engine"]
                    index[unit_rel] = key
                    self._save_index(index)
                    self.audit.append("process", f"page:{key}", data=rec)
                    ok += 1
                    yield {"type": "page", "n": n, "file": unit_rel, "sha256": key,
                           "fields": len(page["fields"]), "flags": [f["code"] for f in page["flags"]],
                           "elapsed_ms": page["elapsed_ms"]}
                except ImageLoadError as e:
                    failed += 1
                    yield {"type": "error", "n": n, "file": unit_rel, "code": "IMAGE_UNREADABLE", "message": str(e),
                           "hint": "File ini dilewati; file lain tetap diproses."}
                except Exception as e:  # satu halaman bermasalah tidak boleh menghentikan semuanya
                    failed += 1
                    yield {"type": "error", "n": n, "file": unit_rel, "code": "OCR_FAILED",
                           "message": f"OCR gagal untuk '{unit_rel}': {type(e).__name__}: {e}",
                           "hint": "Halaman ini dilewati. Coba proses ulang; kalau tetap gagal, laporkan nama filenya."}
        self._save_index(index)
        yield {"type": "done", "processed": ok, "skipped": skipped, "failed": failed,
               "elapsed_s": round(time.perf_counter() - t0, 1)}

    @staticmethod
    def _photo(path: Path, rel: str, sha: str, backend: OcrBackend) -> tuple[dict, None]:
        page = process_image(path, backend, rel=rel)
        if page["sha256"] != sha:
            raise ImageLoadError(f"'{rel}' berubah saat sedang dibaca. Tunggu sinkronisasi selesai, lalu proses ulang.")
        return page, None

    def index(self) -> dict[str, str]:
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def _save_index(self, index: dict) -> None:
        atomic_write_bytes(self.index_path, dump_json(dict(sorted(index.items()))))

    def _page_engine(self, page_path: Path) -> str | None:
        try:
            return json.loads(page_path.read_text(encoding="utf-8"))["engine"]["vouchocr"]
        except (OSError, ValueError, KeyError):
            return None  # file hasil rusak -> proses ulang

    def page(self, sha: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{64}", sha or ""):
            raise WorkspaceError("BAD_PAGE_ID", "ID foto tidak valid.", "Muat ulang data.")
        p = self.pages_dir / f"{sha}.json"
        if not p.exists():
            raise WorkspaceError("PAGE_NOT_FOUND", f"Hasil OCR untuk {sha[:12]}… tidak ada.",
                                 "Proses ulang folder ini.")
        return json.loads(p.read_text(encoding="utf-8"))

    # --- review ------------------------------------------------------------

    def state(self) -> dict:
        """Putar ulang jejak audit di atas hasil OCR -> kondisi review saat ini."""
        pages: dict[str, dict] = {}
        for rel, sha in self.index().items():
            if sha in pages:
                pages[sha]["files"].append(rel)
                continue
            page = self.page(sha)
            pages[sha] = {
                "sha256": sha, "files": [rel], "flags": page["flags"], "status": "belum_dicek",
                "image": page.get("image"), "source_kind": page.get("source_kind", "image"),
                "fields": [{**f, "id": i, "original": f["value"], "source": "ocr", "history": []}
                           for i, f in enumerate(page["fields"])],
            }
        for e in self.audit.entries():
            target = e["target"]
            if not target.startswith("page:"):
                continue
            sha, _, rest = target[5:].partition("/")
            p = pages.get(sha)
            if p is None:
                continue
            act = e["action"]
            if act == "correct":
                f = p["fields"][int(rest.split(":")[1])]
                f["value"] = e["after"]
                f["key"] = _key(f["kind"], e["after"])
                f["history"].append(_hist(e))
            elif act == "add_field":
                a = e["after"]
                p["fields"].append({"id": len(p["fields"]), "kind": a["kind"], "value": a["value"],
                                    "key": _key(a["kind"], a["value"]), "raw": "", "line": None,
                                    "label": a.get("label", ""), "score": None, "flags": [],
                                    "original": None, "source": "auditor", "history": [_hist(e)]})
            elif act == "confirm":
                p["status"] = "dikonfirmasi"
            elif act == "unconfirm":
                p["status"] = "belum_dicek"
        return {"source": self.meta()["source"], "pages": list(pages.values())}

    def correct(self, sha: str, field_id: int, new_value: str, reason: str,
                expected: str | None = None, actor: str | None = None) -> dict:
        page = self._state_page(sha)
        if not 0 <= field_id < len(page["fields"]):
            raise WorkspaceError("FIELD_NOT_FOUND", f"Nilai #{field_id} tidak ada di foto ini.", "Muat ulang data.")
        f = page["fields"][field_id]
        if expected is not None and expected != f["value"]:
            raise WorkspaceError("STALE", f"Nilai sudah berubah menjadi '{f['value']}' sejak layar dibuka.",
                                 "Muat ulang, cek nilai terbaru, lalu koreksi lagi kalau masih perlu.")
        new_value = _normalize(f["kind"], new_value)
        if new_value == f["value"]:
            raise WorkspaceError("NO_CHANGE", "Nilai baru sama dengan nilai sekarang.", "Tidak ada yang disimpan.")
        self._require_reason(reason)
        self._require_open(page)
        return self.audit.append("correct", f"page:{sha}/field:{field_id}", before=f["value"],
                                 after=new_value, reason=reason.strip(), actor=actor)

    def add_field(self, sha: str, kind: str, value: str, reason: str, actor: str | None = None) -> dict:
        page = self._state_page(sha)
        if kind not in KINDS:
            raise WorkspaceError("BAD_KIND", f"Jenis '{kind}' tidak dikenal.", f"Pakai salah satu: {', '.join(KINDS)}.")
        self._require_reason(reason)
        self._require_open(page)
        return self.audit.append("add_field", f"page:{sha}", after={"kind": kind, "value": _normalize(kind, value)},
                                 reason=reason.strip(), actor=actor)

    def confirm(self, sha: str, actor: str | None = None) -> dict:
        page = self._state_page(sha)
        if page["status"] == "dikonfirmasi":
            raise WorkspaceError("ALREADY_CONFIRMED", "Foto ini sudah dikonfirmasi.", "")
        return self.audit.append("confirm", f"page:{sha}", actor=actor,
                                 data={"values": {str(f["id"]): f["value"] for f in page["fields"]}})

    def unconfirm(self, sha: str, reason: str, actor: str | None = None) -> dict:
        page = self._state_page(sha)
        if page["status"] != "dikonfirmasi":
            raise WorkspaceError("NOT_CONFIRMED", "Foto ini belum dikonfirmasi.", "")
        self._require_reason(reason)
        return self.audit.append("unconfirm", f"page:{sha}", reason=reason.strip(), actor=actor)

    def _state_page(self, sha: str) -> dict:
        for p in self.state()["pages"]:
            if p["sha256"] == sha:
                return p
        raise WorkspaceError("PAGE_NOT_FOUND", f"Foto {sha[:12]}… tidak ada di folder kerja ini.", "Muat ulang data.")

    @staticmethod
    def _require_reason(reason: str) -> None:
        if not (reason or "").strip():
            raise WorkspaceError("REASON_REQUIRED", "Alasan wajib diisi.",
                                 "Tulis singkat kenapa nilai diubah, misal 'angka 8 terbaca 3, cek fisik dokumen'.")

    @staticmethod
    def _require_open(page: dict) -> None:
        if page["status"] == "dikonfirmasi":
            raise WorkspaceError("CONFIRMED_LOCKED", "Foto ini sudah dikonfirmasi, nilainya terkunci.",
                                 "Batalkan konfirmasi dulu (dengan alasan), baru koreksi.")

    # --- verifikasi ---------------------------------------------------------

    def verify(self) -> dict:
        chain = self.audit.verify()
        problems = [] if chain.ok else [chain.problem]
        expected: dict[str, str] = {}
        renders: dict[str, str] = {}
        if chain.ok:
            for e in self.audit.entries():
                if e["action"] == "process":
                    expected[e["target"][5:]] = e["data"]["result_sha256"]
                    if "render_sha256" in e["data"]:
                        renders[e["target"][5:]] = e["data"]["render_sha256"]
        for sha, h in expected.items():
            p = self.pages_dir / f"{sha}.json"
            if not p.exists():
                problems.append(f"Hasil OCR {sha[:12]}… hilang.")
            elif sha256_file(p) != h:
                problems.append(f"Hasil OCR {sha[:12]}… berubah setelah dicatat di jejak audit.")
        for sha, h in renders.items():
            p = self.root / "renders" / f"{sha}.png"
            if not p.exists() or sha256_file(p) != h:
                problems.append(f"Gambar halaman {sha[:12]}… hilang atau berubah setelah dicatat di jejak audit.")
        return {"type": "verify", "ok": not problems, "entries": chain.entries,
                "pages_checked": len(expected), "last_hash": chain.last_hash, "problems": problems}


def _normalize(kind: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise WorkspaceError("EMPTY_VALUE", "Nilai baru kosong.", "Isi nilai yang benar sesuai dokumen fisik.")
    if kind == "amount":
        try:
            return str(parse_amount(value).value)
        except AmountError as e:
            raise WorkspaceError("BAD_AMOUNT", str(e), "Tulis nominal seperti 12.450.000,00 atau 12450000.")
    if kind == "date":
        try:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        except ValueError:
            try:
                return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
            except ValueError:
                raise WorkspaceError("BAD_DATE", f"'{value}' bukan tanggal yang valid.", "Tulis seperti 31/12/2024.")
    return value


def _key(kind: str, value: str) -> str:
    return canon_doc_id(value) if kind == "doc_id" else value


def _hist(e: dict) -> dict:
    return {k: e[k] for k in ("seq", "ts", "actor", "action", "before", "after", "reason")}
