"""Einstieg fuer die Windows-Fassung (von PyInstaller zu einer .exe gebuendelt).

Das Fenster selbst macht app/fenster.py - hier steht nur, was auf Windows anders
ist: die Notizen liegen unter %USERPROFILE%\\Notizen, und ein Fehler darf das
Fenster nicht wortlos zuklappen lassen.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def ausgabe_absichern() -> None:
    """Mit --windowed gibt PyInstaller der exe keine Konsole: sys.stdout und
    sys.stderr sind dann None, und jedes print() wirft einen Fehler."""
    import io
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, io.TextIOWrapper(io.BytesIO(), errors="ignore"))


def basis() -> Path:
    """Im Buendel liegen die Dateien im Entpackordner, sonst neben dieser Datei."""
    gebuendelt = getattr(sys, "_MEIPASS", None)
    return Path(gebuendelt) if gebuendelt else Path(__file__).resolve().parent.parent


def main() -> int:
    ausgabe_absichern()
    ordner = basis() / "app"
    sys.path.insert(0, str(ordner))

    import fenster
    if "--pruefen" in sys.argv:
        return fenster.pruefen()
    if "--update" in sys.argv:
        return fenster.update_anstossen()
    return fenster.oeffnen()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as fehler:
        import traceback
        traceback.print_exc()
        print(f"\nFehler: {fehler}", flush=True)
        # Ohne Konsole (--windowed) sieht das niemand, deshalb zusaetzlich ein Fenster.
        if os.environ.get("NOTIZMAPPE_OHNE_FENSTER") != "1":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, str(fehler), "Notizmappe", 0x10)
            except Exception:
                pass
        if sys.stdin is not None and sys.stdin.isatty():
            try:
                input("Enter zum Schliessen ")
            except EOFError:
                pass
        sys.exit(1)
