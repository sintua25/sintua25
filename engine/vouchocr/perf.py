"""Atur kecepatan OCR sesuai laptop: berapa foto dibaca bersamaan dan berapa thread per foto.

Model PP-OCR kecil; di CPU satu foto ~1 dtk. Membaca beberapa foto sekaligus (satu proses
per foto) jauh lebih cepat daripada menambah thread di satu foto. Batasnya RAM: satu proses
OCR butuh sekitar 700 MB saat membaca foto besar, jadi jumlah proses diturunkan kalau RAM
sedikit, dan selalu disisakan ruang untuk Windows dan aplikasi lain.

GPU sengaja tidak dipakai: untuk model sekecil ini, menyalin gambar ke GPU memakan waktu
sebanding dengan menghitungnya, dan hasil di GPU tidak dijamin identik bit demi bit dengan
benchmark akurasi (bench/bench_synthetic.py) yang dijalankan di CPU.
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass

RAM_PER_WORKER = 700 * 2**20
RAM_RESERVE = 1536 * 2**20     # untuk Windows, aplikasi ini, dan program lain yang sedang terbuka
MAX_WORKERS = 6


@dataclass(frozen=True)
class Plan:
    workers: int          # proses OCR yang berjalan bersamaan
    threads: int          # thread onnxruntime per proses
    cpus: int
    ram_free_mb: int | None

    def to_dict(self) -> dict:
        return {"workers": self.workers, "threads": self.threads, "cpus": self.cpus, "ram_free_mb": self.ram_free_mb}


def available_ram() -> int | None:
    """RAM yang masih bebas (byte), tanpa paket tambahan. None kalau tidak bisa dibaca."""
    try:
        if sys.platform == "win32":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MemoryStatus()
            st.dwLength = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullAvailPhys)
            return None
        if hasattr(os, "sysconf") and "SC_AVPHYS_PAGES" in os.sysconf_names:
            return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError):
        pass
    return None


def plan(jobs: int, cpus: int | None = None, ram: int | None = -1, override: int | None = None) -> Plan:
    """`ram=-1` = baca dari sistem. `override` = jumlah proses yang dipaksa pengguna/tes."""
    cpus = max(1, cpus or os.cpu_count() or 1)
    ram = available_ram() if ram == -1 else ram
    if override:
        workers = override
    else:
        # Separuh CPU logis ~ jumlah core fisik (hyper-threading); sisakan satu untuk layar.
        workers = max(1, min(MAX_WORKERS, cpus // 2 if cpus >= 4 else 1))
        if ram is not None:
            workers = max(1, min(workers, (ram - RAM_RESERVE) // RAM_PER_WORKER))
    workers = max(1, min(workers, jobs or 1))
    threads = max(1, cpus // workers)
    return Plan(workers=workers, threads=threads, cpus=cpus,
                ram_free_mb=None if ram is None else ram // 2**20)
