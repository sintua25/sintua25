from .cli import main

# Dijaga: proses OCR paralel (multiprocessing "spawn" di Windows) mengimpor modul ini lagi.
if __name__ == "__main__":
    raise SystemExit(main())
