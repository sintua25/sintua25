"""Jejak audit append-only dengan hash berantai.

Setiap entri memuat hash entri sebelumnya, jadi mengubah, menyisipkan, atau
menghapus satu entri di tengah membuat rantai putus. File `audit.head` mencatat
entri terakhir, sehingga memotong ekor log juga ketahuan.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .storage import atomic_write_text

GENESIS = "0" * 64


class AuditError(Exception):
    pass


def _digest(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def default_actor() -> str:
    try:
        return getpass.getuser()
    except Exception:  # getuser bisa gagal di lingkungan tanpa variabel user
        return "tidak-diketahui"


@dataclass
class VerifyResult:
    ok: bool
    entries: int
    last_hash: str
    problem: str = ""
    bad_seq: int | None = None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "entries": self.entries, "last_hash": self.last_hash,
                "problem": self.problem, "bad_seq": self.bad_seq}


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.head_path = self.path.with_suffix(".head")

    def append(self, action: str, target: str, *, before=None, after=None,
               reason: str = "", actor: str | None = None, data: dict | None = None) -> dict:
        check = self.verify()
        if not check.ok:
            raise AuditError(f"Jejak audit rusak, tidak bisa menambah entri: {check.problem}")
        entry = {
            "seq": check.entries + 1,
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "actor": actor or default_actor(),
            "action": action,
            "target": target,
            "before": before,
            "after": after,
            "reason": reason,
            "data": data or {},
            "prev": check.last_hash,
        }
        entry["hash"] = _digest(entry)
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        atomic_write_text(self.head_path, json.dumps({"seq": entry["seq"], "hash": entry["hash"]}))
        return entry

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for n, raw in enumerate(f, 1):
                if not raw.strip():
                    continue
                try:
                    out.append(json.loads(raw))
                except json.JSONDecodeError:
                    raise AuditError(f"Baris {n} jejak audit bukan JSON yang valid (file terpotong atau diedit).")
        return out

    def verify(self) -> VerifyResult:
        try:
            entries = self.entries()
        except AuditError as e:
            return VerifyResult(False, 0, GENESIS, str(e))
        prev = GENESIS
        hashes = [GENESIS]
        for i, e in enumerate(entries, 1):
            if e.get("seq") != i:
                return VerifyResult(False, i - 1, prev, f"Nomor urut entri ke-{i} tertulis {e.get('seq')}.", i)
            if e.get("prev") != prev:
                return VerifyResult(False, i - 1, prev, f"Entri #{i} tidak menyambung ke entri sebelumnya.", i)
            if _digest(e) != e.get("hash"):
                return VerifyResult(False, i - 1, prev, f"Isi entri #{i} berubah setelah dicatat.", i)
            prev = e["hash"]
            hashes.append(prev)

        n = len(entries)
        head = self._read_head()
        if head is None:
            head = {"seq": 0, "hash": GENESIS}
        seq, h = head.get("seq"), head.get("hash")
        if (seq, h) == (n, prev):
            return VerifyResult(True, n, prev)
        # Aplikasi mati tepat setelah menulis entri tapi sebelum memperbarui head:
        # log lebih panjang satu entri yang rantainya sah. Itu bukan perusakan.
        if isinstance(seq, int) and seq == n - 1 and h == hashes[n - 1]:
            return VerifyResult(True, n, prev)
        return VerifyResult(False, n, prev,
                            f"audit.head mencatat {seq} entri, log berisi {n}. "
                            "Ada entri yang hilang dari akhir log, atau audit.head diubah.")

    def _read_head(self) -> dict | None:
        try:
            return json.loads(self.head_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError):
            return {"seq": None, "hash": None}
