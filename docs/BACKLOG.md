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
- [ ] Uji `npm run tauri dev` di Windows (alur penuh + `vouchocr verify`)
- [ ] Mesin Python dibundel sebagai sidecar (installer tanpa instal Python terpisah)

## Fase 2: Ekspor
- [ ] JSON gabungan + koreksi, alasan, status review
- [ ] Excel: satu sheet per folder sumber; nilai asli / nilai akhir / status / alasan
- [ ] Atomik, SHA-256 hasil dicatat di jejak audit

## Fase 3: Filing
- [ ] `samples.py` baca List_Filling.xlsx, konfigurasi per sheet di YAML/JSON
- [ ] `matching.py`: nomor dokumen kanonik; rekening bank dan awalan APM-/AP-/OUT- bukan kunci
- [ ] `plan.py` dry-run, penyalinan terverifikasi SHA-256, log CSV BERHASIL/DILEWATI/GAGAL

## Fase 4: Layar pencocokan sampel

## Fase 5 (tanya dulu): peran pengguna, status workpaper, pembatalan proses

## Ide (belum dijadwalkan)
- Foto terputar 90 derajat tanpa data EXIF: deteksi otomatis
- Uji akurasi dengan foto dokumen asli non-klien (contoh kuitansi kosong yang difoto)
