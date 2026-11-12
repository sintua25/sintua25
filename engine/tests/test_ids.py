import pytest

from vouchocr.ids import canon_doc_id, same_doc_id


@pytest.mark.parametrize("a, b", [
    ("INV-00123", "1NV-0O123"),
    ("KW-2024/0815", "kw 2024 0815"),
    ("AL-01", "A1-0l"),
])
def test_ocr_confusions_match(a, b):
    assert canon_doc_id(a) == canon_doc_id(b)
    assert same_doc_id(a, b)


def test_canon_shape():
    assert canon_doc_id("inv-0O12 3") == "1NV00123"


@pytest.mark.parametrize("raw", ["", None, "---", "  / "])
def test_empty_never_matches(raw):
    assert canon_doc_id(raw) == ""
    assert not same_doc_id(raw, raw)


def test_different_ids_do_not_match():
    assert not same_doc_id("INV-00123", "INV-00124")
