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
vouchocr export -w "<folder kerja>"                   # Excel + JSON ke <folder kerja>/export
```

Aplikasi desktop (`app/`, Tauri 2 + React + TS):

```
cd app
npm install
npm run typecheck && npm test                         # TypeScript + unit test UI
npm run dev                                           # browser, mode demo (data sintetis)
npm run tauri dev                                     # jendela desktop + mesin OCR sungguhan
cd src-tauri && cargo test                            # tes jembatan Rust
# tes jembatan dengan mesin asli:
VOUCHOCR_PYTHON=../../engine/.venv/bin/python VOUCHOCR_TEST_FOLDER=<folder foto contoh> cargo test
```

Aplikasi memanggil `python -m vouchocr` (venv `engine/.venv`, atau `VOUCHOCR_PYTHON`). Semua
aturan audit ada di mesin; Rust hanya meneruskan perintah dan galat. Nilai dari pengguna dikirim
sebagai `--nama=nilai` supaya nilai berawalan "-" tidak terbaca sebagai opsi.
Panduan untuk pemilik produk: `docs/MENJALANKAN.md`.

## Peta kode (`engine/vouchocr`)

| File | Isi |
|---|---|
| `preprocess.py` | baca foto aman (EXIF, hash), perkecil, deteksi buram dan bayangan |
| `ocr.py` | RapidOCR (PP-OCR ONNX), baca ulang baris berangka yang ragu |
| `documents.py` | PDF -> halaman (pypdfium2), Word .docx -> teks + gambar; ID halaman turunan |
| `pipeline.py` | satu foto/halaman -> satu hasil halaman; cadangan versi tanpa bayangan |
| `fields.py` | ambil nomor dokumen, nominal, tanggal + indikator keraguan |
| `money.py`, `ids.py` | parse nominal ke Decimal; kunci kanonik nomor dokumen (O->0, I->1, L->1) |
| `audit.py` | log append-only berantai hash + `audit.head` |
| `workspace.py` | folder kerja: proses, koreksi, konfirmasi, state, verify |
| `export.py` | Excel (openpyxl) + JSON; atomik, hash dicatat di jejak audit; nominal utama tidak ditebak |
| `cli.py` | antarmuka JSON Lines untuk aplikasi desktop |

## Peta kode (`app/`)

| File | Isi |
|---|---|
| `src-tauri/src/engine.rs` | jalankan mesin, baca JSON Lines, terjemahkan galat; nama folder kerja |
| `src-tauri/src/lib.rs` | perintah Tauri; folder kerja di `<program>\Output OCR`; izin asset protocol |
| `src/api/` | antarmuka `Api`: `tauri.ts` (desktop) dan `demo.ts` (browser/tes, data `src/demo/data.json`) |
| `src/lib/` | format angka (string, tanpa float), saringan & urutan ledger, geometri kotak |
| `src/components/` | TopBar, PhotoList, PhotoView (foto + kotak SVG), Ledger (koreksi, tambah nilai, konfirmasi) |
