import json

import pytest

from vouchocr.audit import GENESIS, AuditError, AuditLog


@pytest.fixture
def log(tmp_path):
    a = AuditLog(tmp_path / "audit.jsonl")
    for i in range(3):
        a.append("correct", f"page:x/field:{i}", before="1", after="2", reason="cek fisik", actor="tes")
    return a


def rewrite(log, fn):
    lines = log.path.read_text(encoding="utf-8").splitlines()
    log.path.write_text("\n".join(fn(lines)) + "\n", encoding="utf-8")


def test_empty_log_is_valid(tmp_path):
    r = AuditLog(tmp_path / "a.jsonl").verify()
    assert r.ok and r.entries == 0 and r.last_hash == GENESIS


def test_chain_intact(log):
    r = log.verify()
    assert r.ok and r.entries == 3
    e = log.entries()
    assert e[0]["prev"] == GENESIS and e[1]["prev"] == e[0]["hash"]
    assert {"seq", "ts", "actor", "action", "target", "before", "after", "reason", "prev", "hash"} <= e[0].keys()


def test_edit_detected(log):
    rewrite(log, lambda ls: [ls[0], ls[1].replace('"after":"2"', '"after":"9"'), ls[2]])
    r = log.verify()
    assert not r.ok and r.bad_seq == 2 and "berubah" in r.problem


def test_delete_middle_detected(log):
    rewrite(log, lambda ls: [ls[0], ls[2]])
    assert not log.verify().ok


def test_truncate_tail_detected(log):
    rewrite(log, lambda ls: ls[:2])
    r = log.verify()
    assert not r.ok and "hilang" in r.problem


def test_recompute_hash_still_detected_by_next_entry(log):
    # Pemalsu mengubah entri #2 dan menghitung ulang hash-nya: entri #3 tetap menunjuk hash lama.
    from vouchocr.audit import _digest
    lines = log.path.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[1]); e["after"] = "9"; e["hash"] = _digest(e)
    lines[1] = json.dumps(e, separators=(",", ":"))
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    r = log.verify()
    assert not r.ok and r.bad_seq == 3


def test_crash_between_log_and_head_is_not_tampering(log):
    head = log.head_path.read_text()
    log.append("confirm", "page:x")
    log.head_path.write_text(head)  # head tertinggal satu entri, seperti mati listrik
    assert log.verify().ok
    log.append("confirm", "page:y")  # entri berikutnya memperbaiki head
    assert log.verify().ok and log.verify().entries == 5


def test_append_refused_on_broken_chain(log):
    rewrite(log, lambda ls: [ls[0], ls[2]])
    with pytest.raises(AuditError):
        log.append("confirm", "page:x")


def test_garbage_line_reported(log):
    with open(log.path, "a", encoding="utf-8") as f:
        f.write("{bukan json\n")
    r = log.verify()
    assert not r.ok and "bukan JSON" in r.problem


def test_unicode_reason_roundtrip(log):
    log.append("correct", "page:x/field:0", before="1", after="2", reason="angka 8 terbaca 3 — cek fisik ✓")
    assert log.verify().ok
