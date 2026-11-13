# Desain Meja Vouching

Meja kerja auditor, bukan dashboard. Rasanya seperti kertas kerja ledger di atas
meja: tenang, padat informasi, dan jelas mana yang sudah dicek.

## Bahan

| Token | Nilai | Dipakai untuk |
|---|---|---|
| `--paper` | `#F3F6EE` | latar, hijau pucat kertas ledger |
| `--paper-rule` | `#D9E3CF` | garis baris ledger, pemisah |
| `--ink` | `#1C2B4A` | teks utama, tinta navy |
| `--ink-soft` | `#5A6680` | teks sekunder |
| `--highlighter` | `#FFE45C` (latar 55%) | nilai yang diragukan mesin: stabilo |
| `--tick` | `#2F7D4F` | centang hijau untuk yang sudah dicek |
| `--red-pen` | `#B3261E` | galat dan koreksi (coretan nilai lama) |

Mode gelap: kertas `#151B26`, tinta `#E6EAF2`, stabilo tetap kuning tapi 30%.

## Huruf

- Angka dan nomor dokumen: `IBM Plex Mono` (dibundel lokal, bukan CDN), angka tabular.
- Teks: `IBM Plex Sans`. Judul pakai ukuran dan tebal, bukan huruf kapital semua.

## Tata letak

Tiga panel: daftar foto | foto dengan kotak OCR | ledger nilai + panel koreksi.
Baris ledger setinggi baris kertas (28 px), garis tipis `--paper-rule`.
Klik nilai di ledger = kotaknya menyala di foto, dan sebaliknya.

## Gerak

Satu animasi saja: centang tergambar (stroke) saat foto dikonfirmasi, 220 ms.
Sisanya tanpa animasi masuk.

## Kata-kata

Bahasa Indonesia, kalimat aktif, aksi konsisten:
"Simpan koreksi" -> "Koreksi disimpan", "Konfirmasi" -> "Foto dikonfirmasi",
"Batalkan konfirmasi" -> "Konfirmasi dibatalkan".
Indikator keraguan memakai pesan dari `engine/vouchocr/flags.py`.

## Dilarang

Gradient hiasan, kartu identik berbayang abu, emoji sebagai ikon, label ALL-CAPS di
atas tiap judul, aksen krem/terakota, ungu/indigo bawaan Tailwind, animasi masuk
di tiap section. Ikon: garis tunggal 1.6 px, `currentColor`.

## Catatan dari referensi

Belum diisi. Pemilik produk menyerahkan gaya ke tim; arah di atas dipakai sampai ada catatan baru.
