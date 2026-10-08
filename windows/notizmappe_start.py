"""Einstieg fuer die Windows-Fassung (von PyInstaller zu einer .exe gebuendelt).

Auf Windows gibt es keinen systemd-Dienst: die .exe ist das Programm. Sie startet
den Server im eigenen Prozess, oeffnet den Browser und laeuft, solange das Fenster
offen ist. Die Notizen liegen in %USERPROFILE%\\Notizen - also im selben Ordner,
den auch der Nextcloud-Client synchronisiert, wenn man ihn dort hinlegt.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def basis() -> Path:
    """Im Buendel liegen die Dateien im Entpackordner, sonst neben dieser Datei."""
    gebuendelt = getattr(sys, "_MEIPASS", None)
    return Path(gebuendelt) if gebuendelt else Path(__file__).resolve().parent.parent


def freier_port(wunsch: int) -> int:
    """Ist der Port belegt (zweiter Start, anderes Programm), nimm den naechsten."""
    for port in range(wunsch, wunsch + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return wunsch


def main() -> int:
    ordner = basis() / "app"
    sys.path.insert(0, str(ordner))
    os.environ.setdefault("NOTIZEN_ORDNER", str(Path.home() / "Notizen"))
    Path(os.environ["NOTIZEN_ORDNER"]).mkdir(parents=True, exist_ok=True)

    port = freier_port(int(os.environ.get("PORT", "8099")))
    adresse = f"http://127.0.0.1:{port}/"

    import uvicorn  # erst hier, damit ein Fehler eine lesbare Meldung gibt
    import main as programm

    version = (ordner / "VERSION").read_text(encoding="utf-8").strip()
    print(f"Notizmappe {version}")
    print(f"  Notizen:  {os.environ['NOTIZEN_ORDNER']}")
    print(f"  Adresse:  {adresse}")
    print("  Dieses Fenster offen lassen. Schliessen beendet die Notizmappe.")

    threading.Timer(1.5, lambda: webbrowser.open(adresse)).start()
    uvicorn.run(programm.app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as fehler:        # Fenster nicht einfach zuklappen lassen
        import traceback
        traceback.print_exc()
        print(f"\nFehler: {fehler}", flush=True)
        # Nur warten, wenn ueberhaupt jemand Enter druecken kann - im Buildlauf
        # haengt das Fenster sonst hier und der Fehler faellt als Zeitueberschreitung auf.
        if sys.stdin is not None and sys.stdin.isatty():
            try:
                input("Enter zum Schliessen ")
            except EOFError:
                pass
        sys.exit(1)
