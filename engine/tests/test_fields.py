from vouchocr.fields import extract, fix_digits
from vouchocr.models import OcrLine


def L(text, score=0.99, y=0, x=0, w=400, h=30, **kw):
    return OcrLine(text=text, score=score, box=[(x, y), (x + w, y), (x + w, y + h), (x, y + h)], **kw)


def kinds(fields, kind):
    return [f for f in fields if f.kind == kind]


def test_kwitansi():
    fields, flags = extract([
        L("KWITANSI No: KW-2024/0815", y=0),
        L("Tanggal: 12/03/2024", y=50),
        L("Uang sejumlah: Rp 12.450.000,00", y=100),
        L("Faktur: INV-00123", y=150),
    ])
    assert [f.value for f in kinds(fields, "doc_id")] == ["KW-2024/0815", "INV-00123"]
    [amt] = kinds(fields, "amount")
    assert (amt.value, amt.label, amt.line, amt.raw) == ("12450000.00", "total", 2, "Rp 12.450.000,00")
    assert [f.value for f in kinds(fields, "date")] == ["2024-03-12"]
    assert flags == []


def test_bank_account_and_phone_are_not_amounts_or_ids():
    fields, _ = extract([L("No. Rek: 123-456-7890"), L("Telp 021-555.1234", y=40), L("NPWP 01.234.567.8-901.000", y=80)])
    assert fields == []


def test_total_label_in_separate_box_same_row():
    fields, _ = extract([
        L("Total", y=200, x=50, w=100),
        L("Rp 3.552.000", y=202, x=600, w=200),
        L("Rp 352.000", y=150, x=600, w=200),
    ])
    amts = {f.value: f.label for f in kinds(fields, "amount")}
    assert amts == {"3552000": "total", "352000": ""}


def test_multiple_totals_flagged_not_resolved():
    fields, flags = extract([L("Total Rp 1.000.000"), L("Jumlah Rp 1.100.000", y=40)])
    assert len(kinds(fields, "amount")) == 2  # dua-duanya tetap ditampilkan
    assert [f["code"] for f in flags] == ["NO_DOC_ID", "MULTIPLE_TOTALS"]


def test_duplicate_totals_same_value_not_flagged():
    _, flags = extract([L("Total Rp 1.000.000"), L("Jumlah Rp 1.000.000", y=40)])
    assert "MULTIPLE_TOTALS" not in [f["code"] for f in flags]


def test_digit_correction_flagged_and_raw_kept():
    fields, _ = extract([L("Total Rp 1.O5O.000")])
    [amt] = kinds(fields, "amount")
    assert amt.value == "1050000"
    assert amt.raw == "Rp 1.O5O.000"
    assert "DIGIT_CORRECTED" in [f["code"] for f in amt.flags]


def test_low_confidence_flagged():
    fields, _ = extract([L("Total Rp 9.000", score=0.6)])
    assert "LOW_CONFIDENCE" in [f["code"] for f in fields[0].flags]


def test_reread_used_when_better_and_difference_flagged():
    line = L("Total Rp 8.300.000", score=0.80, reread="Total Rp 8.800.000", reread_score=0.98)
    fields, _ = extract([line])
    [amt] = kinds(fields, "amount")
    assert amt.value == "8800000"
    assert "REREAD_DIFFERS" in [f["code"] for f in amt.flags]
    assert line.text == "Total Rp 8.300.000"  # teks asli tidak ditimpa


def test_dates_variants():
    fields, _ = extract([L("5 Maret 2024"), L("2024-12-31", y=40), L("31-12-24", y=80)])
    assert [f.value for f in kinds(fields, "date")] == ["2024-03-05", "2024-12-31", "2024-12-31"]


def test_invalid_and_us_dates_flagged():
    fields, _ = extract([L("Tgl 31/02/2024"), L("Tgl 03/25/2024", y=40)])
    d = kinds(fields, "date")
    assert [f.flags[0]["code"] for f in d] == ["DATE_INVALID", "DATE_US_ORDER"]
    assert d[1].value == "2024-03-25"


def test_faktur_pajak_number_not_amount():
    fields, _ = extract([L("Kode dan Nomor Seri Faktur Pajak: 010.000-24.12345678")])
    assert [f.kind for f in fields] == ["doc_id"]
    assert fields[0].value == "010.000-24.12345678"


def test_plain_numbers_without_context_ignored():
    fields, _ = extract([L("Halaman 1 dari 2"), L("Kode pos 12345", y=40)])
    assert kinds(fields, "amount") == []


def test_empty_page():
    fields, flags = extract([])
    assert fields == [] and [f["code"] for f in flags] == ["NO_TEXT"]


def test_fix_digits_leaves_words_alone():
    assert fix_digits("SBY BOLD INV-00123") == "SBY BOLD INV-00123"
    assert fix_digits("Rp 1O.5OO") == "Rp 10.500"


def test_comma_read_as_dot_is_guessed_and_flagged():
    fields, _ = extract([L("Uang sejumlah: Rp 12.450.000.00")])
    [amt] = kinds(fields, "amount")
    assert amt.value == "12450000.00"
    assert "SEPARATOR_GUESSED" in [f["code"] for f in amt.flags]


def test_greek_lookalikes_normalized():
    fields, _ = extract([L("Total Rρ 1.500")])
    assert kinds(fields, "amount")[0].value == "1500"


def test_amount_in_sentence_with_magnitude_word_is_not_a_value():
    # Catatan kaki PO: "total value more than IDR 1 Million" bukan nominal transaksi.
    fields, flags = extract([
        L("Total", y=200, x=50, w=100),
        L("Rp 13.400.000,00", y=202, x=600, w=200),
        L("All invoices that has total value more than IDR 1 Million must use a legal stamp", y=400),
        L("Denda Rp 5 juta per hari", y=440),
        L("Biaya 2,5 jt", y=480),
    ])
    assert [(f.value, f.label) for f in kinds(fields, "amount")] == [("13400000.00", "total")]
    assert not any(f["code"] == "MULTIPLE_TOTALS" for f in flags)


def test_magnitude_word_must_be_a_whole_word():
    # "Rp 1.500 rbt" bukan "ribu"; "jtx" bukan "jt": nominal tetap dibaca.
    fields, _ = extract([L("Rp 1.500.000 jtx"), L("Total Rp 2.000.000 Jumlah", y=40)])
    assert [f.value for f in kinds(fields, "amount")] == ["1500000", "2000000"]
