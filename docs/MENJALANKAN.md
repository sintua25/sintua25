# Menjalankan Meja Vouching di Windows

## Cara paling gampang (untuk pengguna): installer

1. Buka halaman Releases repo, bagian **Meja Vouching (installer terbaru)**, download `Meja-Vouching-Setup.exe`
   (atau minta file itu dari pemilik produk).
2. Double-click. Kalau muncul "Windows protected your PC": klik **More info** lalu **Run anyway**
   (installer belum ditandatangani sertifikat berbayar).
3. Next sampai selesai. Tidak perlu hak admin, tidak perlu Python/Node/Rust.
4. Buka **Meja Vouching** dari ikon di desktop atau Start Menu.

Hasil (folder kerja dan Excel) ada di folder `Output OCR` di dalam folder program
(`%LOCALAPPDATA%\Meja Vouching\Output OCR`); tombol **Buka folder hasil** muncul setelah export.

Installer dibuat otomatis oleh GitHub Actions (`.github/workflows/installer-windows.yml`) setiap ada
perubahan di `app/` atau `engine/`.

## Untuk pengembang: dari kode

Sekali saja (persiapan), lalu cukup langkah "Setiap kali".

## Persiapan (sekali)

1. Pasang **Python 3.12** dari python.org (atau `winget install Python.Python.3.12`). Saat memasang, centang
   "Add python.exe to PATH". Jangan 3.15: numpy/Pillow untuk versi itu rusak di Windows.
2. Pasang **Node.js LTS** dari nodejs.org.
3. Pasang **Rust** dari rustup.rs (pilih pilihan bawaan). Kalau diminta "Visual Studio C++ Build Tools", pasang juga.
4. Unduh kode: di halaman repo GitHub, klik **Code → Download ZIP**, lalu ekstrak, misal ke `C:\MejaVouching`.
5. Buka **PowerShell**. Sekali saja, izinkan npm berjalan: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
   (jawab `Y`). Lalu jalankan:

```
cd C:\MejaVouching\engine
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd ..\app
npm install
```

## Setiap kali

```
cd C:\MejaVouching\app
npm run tauri dev
```

Jendela Meja Vouching terbuka. Klik **Pilih folder**, pilih folder berisi foto (JPG/PNG/TIFF), PDF, atau
Word (.docx). PDF dibaca per halaman; dari Word, teksnya dibaca langsung dan gambar yang ditempel di-OCR.
Word lama (.doc) belum bisa: simpan ulang sebagai .docx atau PDF.

## Setelah memperbarui kode

Kalau kode diperbarui (ZIP baru), ulangi `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` di folder
`engine` supaya paket baru ikut terpasang, lalu `npm run tauri dev` seperti biasa.

## Export Excel

Klik **Export Excel** di kanan atas. File `vouching-<tanggal-jam>.xlsx` dan `.json` disimpan di
`Output OCR\<nama folder> - <kode>\export` di folder program (path lengkapnya tampil di layar). Export lama tidak pernah ditimpa.
Sheet: Ringkasan (satu baris per foto), Detail (nilai OCR asli vs nilai akhir + alasan koreksi),
Jejak audit, Info.

## Yang perlu diketahui

- Folder foto klien hanya dibaca. Hasil OCR, koreksi, jejak audit, dan Excel disimpan di folder
  `Output OCR\<nama folder> - <kode>` di folder program. Folder kerja lama di `Dokumen\Meja Vouching`
  disalin otomatis ke sana saat folder yang sama dibuka (yang lama tidak dihapus).
- Folder bernama `Backup` dilewati.
- Kalau muncul pesan "Python tidak ditemukan" atau "vouchocr belum terpasang", ulangi langkah 5 di atas.
- Membuka di browser biasa (`npm run dev`, lalu http://localhost:1420) menampilkan **mode demo** dengan
  foto contoh buatan, bukan data klien.
