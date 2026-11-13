import pytest

from vouchocr.perf import plan

GB = 2**30


@pytest.mark.parametrize("cpus,ram,jobs,workers", [
    (8, 16 * GB, 100, 4),     # laptop kantor biasa: 4 core fisik
    (16, 32 * GB, 100, 6),    # dibatasi MAX_WORKERS
    (8, 3 * GB, 100, 2),      # RAM sempit: (3 GB - 1.5 GB) / 700 MB = 2
    (8, 1 * GB, 100, 1),      # RAM hampir habis: tetap jalan satu
    (2, 8 * GB, 100, 1),      # dual core: satu proses
    (8, 16 * GB, 2, 2),       # tidak lebih banyak dari jumlah foto
    (8, 16 * GB, 0, 1),       # folder kosong
    (8, None, 100, 4),        # RAM tidak terbaca: pakai jumlah CPU saja
])
def test_plan(cpus, ram, jobs, workers):
    p = plan(jobs, cpus=cpus, ram=ram)
    assert p.workers == workers
    assert p.threads >= 1 and p.workers * p.threads <= max(cpus, p.workers)


def test_override_and_real_system():
    assert plan(10, cpus=8, ram=16 * GB, override=1).workers == 1
    p = plan(10)
    assert p.workers >= 1 and p.cpus >= 1
