# Menjalankan Meja Vouching di Windows

Sekali saja (persiapan), lalu cukup langkah "Setiap kali".

## Persiapan (sekali)

1. Pasang **Python 3.11 atau lebih baru** dari python.org. Saat memasang, centang "Add python.exe to PATH".
2. Pasang **Node.js LTS** dari nodejs.org.
3. Pasang **Rust** dari rustup.rs (pilih pilihan bawaan). Kalau diminta "Visual Studio C++ Build Tools", pasang juga.
4. Unduh kode: di halaman repo GitHub, klik **Code → Download ZIP**, lalu ekstrak, misal ke `C:\MejaVouching`.
5. Buka **PowerShell**, lalu jalankan:

```
cd C:\MejaVouching\engine
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
cd ..\app
npm install
```

## Setiap kali

```
cd C:\MejaVouching\app
npm run tauri dev
```

Jendela Meja Vouching terbuka. Klik **Pilih folder**, pilih folder foto vouching.

## Yang perlu diketahui

- Folder foto klien hanya dibaca. Hasil OCR, koreksi, dan jejak audit disimpan di
  `Dokumen\Meja Vouching\<nama folder> - <kode>`.
- Folder bernama `Backup` dilewati.
- Kalau muncul pesan "Python tidak ditemukan" atau "vouchocr belum terpasang", ulangi langkah 5 di atas.
- Membuka di browser biasa (`npm run dev`, lalu http://localhost:1420) menampilkan **mode demo** dengan
  foto contoh buatan, bukan data klien.
