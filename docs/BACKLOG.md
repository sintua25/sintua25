# Backlog

Urutan kerja. Setiap fase berhenti untuk review.

## Fase 0: Mesin OCR (selesai, menunggu review)
- [x] Baca foto aman (EXIF, SHA-256, galat jelas), deteksi buram dan bayangan
- [x] OCR lokal PP-OCR ONNX (RapidOCR), baca ulang baris berangka yang ragu
- [x] Ambil nomor dokumen, nominal (Decimal), tanggal + indikator keraguan
- [x] Folder kerja: proses bisa dilanjutkan, foto duplikat jadi satu, Backup dilewati
- [x] Jejak audit berantai hash, koreksi wajib alasan, konfirmasi mengunci, `verify`
- [x] CLI JSON Lines, benchmark sintetis

## Fase 1: Aplikasi desktop jalan (selesai di Linux, menunggu uji Windows)
- [x] Tauri 2 + React + TS, UI tiga panel sesuai DESIGN.md, mode gelap
- [x] Pilih folder, proses (progres dari JSON Lines), review, koreksi, tambah nilai, konfirmasi, verify
- [x] Pratinjau gambar lewat asset protocol, kotak OCR di atas foto (diuji di path Unicode + spasi)
- [x] Buka folder dari argumen baris perintah; "Buka lagi" folder terakhir
- [x] Uji `npm run tauri dev` di Windows (2026-11-13, 208 foto asli; perlu Python 3.12, bukan 3.15)
- [ ] Mesin Python dibundel sebagai sidecar (installer tanpa instal Python terpisah)

## Fase 2: Ekspor
- [x] JSON gabungan + koreksi, alasan, status review (`vouchocr export`, tombol "Export Excel")
- [x] Excel: Ringkasan (satu baris per foto), Detail (nilai asli / akhir / alasan), Jejak audit, Info.
      Satu file per folder kerja (= satu folder sumber), bukan satu sheet per folder.
- [x] Atomik, nama berwaktu (tidak menimpa), SHA-256 dicatat di jejak audit; ditolak kalau jejak audit putus
- [x] Nominal utama hanya diisi kalau tidak ambigu; selain itu kosong + ditandai (mesin tidak menebak)
- [ ] Tombol "Buka file" langsung dari aplikasi (perlu plugin opener)

## Fase 3: Filing
- [ ] `samples.py` baca List_Filling.xlsx, konfigurasi per sheet di YAML/JSON
- [ ] `matching.py`: nomor dokumen kanonik; rekening bank dan awalan APM-/AP-/OUT- bukan kunci
- [ ] `plan.py` dry-run, penyalinan terverifikasi SHA-256, log CSV BERHASIL/DILEWATI/GAGAL

## Fase 4: Layar pencocokan sampel

## Fase 5 (tanya dulu): peran pengguna, status workpaper, pembatalan proses

## Ide (belum dijadwalkan)
- Foto terputar 90 derajat tanpa data EXIF: deteksi otomatis
- Uji akurasi dengan foto dokumen asli non-klien (contoh kuitansi kosong yang difoto)
