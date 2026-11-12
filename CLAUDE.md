# Meja Vouching: aturan kerja

Aplikasi desktop lokal untuk auditor: baca foto dokumen vouching dengan OCR lokal,
cek hasilnya di samping foto, susun dokumen pendukung per sampel. Ini software
audit, jadi setiap angka harus bisa ditelusuri asalnya.

Pemilik produk adalah auditor, bukan programmer. Balas dalam Bahasa Indonesia, santai, singkat.

## Aturan keras

1. File sumber klien tidak pernah diubah, dipindah, atau dihapus. Folder `Backup` tidak pernah dibuka.
   Folder kerja tidak boleh berada di dalam folder sumber. Filing hanya SALIN, diverifikasi SHA-256.
2. Data klien tidak keluar dari laptop: tidak ada API eksternal, telemetri, atau CDN.
   Model OCR ikut terpasang di paket `rapidocr`; tidak ada unduhan saat jalan.
3. Uang pakai `Decimal`, tidak pernah `float`. Di JSON, nominal disimpan sebagai string.
4. Perubahan penting hanya lewat jejak audit (`audit.jsonl`): siapa, kapan, nilai lama, nilai baru, alasan.
   Hasil OCR asli (`pages/<sha256>.json`) tidak pernah ditimpa; nilai akhir = OCR + koreksi diputar ulang.
5. Kecocokan nominal saja = REVIEW. OK hanya untuk kecocokan nomor dokumen.
6. Tidak ada kegagalan diam-diam. Galat berisi `message` (apa dan kenapa) dan `hint` (apa yang bisa dilakukan).
7. Mesin menandai indikator keraguan (`flags.py`), tidak menyimpulkan salah/benar.
8. Rumus Excel pakai titik koma `;`.

## Cara kerja

- Satu fase per sesi; berhenti untuk review sebelum commit ke `main`.
- Tes dulu untuk logika baru: normal, batas, nol, negatif, kosong, duplikat, tidak valid.
- Jangan menambah dependency tanpa alasan (kebutuhan, lisensi, pemeliharaan).
- Ragu soal aturan audit/akuntansi: tanya, jangan mengarang.
- Perubahan akurasi OCR wajib dibuktikan dengan `engine/bench/bench_synthetic.py` (sebelum vs sesudah).

## Perintah

```
cd engine
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -e .[dev]
python -m pytest -q                                   # semua tes, termasuk OCR sungguhan
python -m pytest -q -m "not ocr"                      # tes cepat saja
python bench/bench_synthetic.py                       # akurasi di 72 foto sintetis rusak
vouchocr process "<folder foto>" -w "<folder kerja>"
vouchocr verify -w "<folder kerja>"
```

## Peta kode (`engine/vouchocr`)

| File | Isi |
|---|---|
| `preprocess.py` | baca foto aman (EXIF, hash), perkecil, deteksi buram dan bayangan |
| `ocr.py` | RapidOCR (PP-OCR ONNX), baca ulang baris berangka yang ragu |
| `pipeline.py` | satu foto -> satu hasil halaman; cadangan versi tanpa bayangan |
| `fields.py` | ambil nomor dokumen, nominal, tanggal + indikator keraguan |
| `money.py`, `ids.py` | parse nominal ke Decimal; kunci kanonik nomor dokumen (O->0, I->1, L->1) |
| `audit.py` | log append-only berantai hash + `audit.head` |
| `workspace.py` | folder kerja: proses, koreksi, konfirmasi, state, verify |
| `cli.py` | antarmuka JSON Lines untuk aplikasi desktop |
