"""Die Notizmappe als Programm im eigenen Fenster.

Innen drin bleibt es ein kleiner Webserver - die Oberflaeche ist HTML. Nach aussen
ist es ein Fenster wie jedes andere: eigener Eintrag in der Fensterleiste, kein
Browser, keine Adresszeile.

Drei Wege, in dieser Reihenfolge:
  1. pywebview - benutzt die Webansicht des Systems (WebKit2GTK oder Qt). Das ist
     ein echtes Fenster mit eigenem Prozess.
  2. Ein Chromium-artiger Browser mit --app= - sieht genauso aus (eigenes Fenster,
     keine Adresszeile), braucht aber einen installierten Browser.
  3. Normaler Browser. Nicht schoen, aber immer noch besser als gar nichts.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

TITEL = "Notizmappe"
# Browser, die --app= koennen. Firefox kann es nicht, deshalb steht er nicht hier.
APP_BROWSER = [
    "chromium", "chromium-browser", "google-chrome-stable", "google-chrome",
    "brave", "brave-browser", "vivaldi-stable", "vivaldi", "microsoft-edge-stable",
]


def freier_port(wunsch: int = 8099) -> int:
    for port in range(wunsch, wunsch + 30):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return wunsch


def laeuft_schon(port: int) -> bool:
    """Laeuft dort bereits eine Notizmappe (z.B. als Dienst)? Dann docken wir an,
    statt einen zweiten Server auf dieselben Dateien zu setzen."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/baum", timeout=1.5) as a:
            return b"notizbuecher" in a.read(400)
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def server_starten(port: int) -> threading.Thread:
    """Server im eigenen Prozess, in einem Nebenlaeufer. Schliesst man das Fenster,
    geht der Prozess - und der Server mit ihm."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import uvicorn
    import main

    config = uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    faden = threading.Thread(target=server.run, daemon=True)
    faden.start()
    for _ in range(100):               # bis zu 10 Sekunden auf "antwortet" warten
        if laeuft_schon(port):
            return faden
        time.sleep(0.1)
    return faden


def mit_pywebview(adresse: str) -> bool:
    try:
        import webview
    except ImportError:
        return False
    try:
        webview.create_window(TITEL, adresse, width=1280, height=840,
                              min_size=(640, 480), text_select=True)
        webview.start()
        return True
    except Exception as f:
        print(f"Fenster über pywebview ging nicht: {f}", file=sys.stderr)
        return False


def mit_browserfenster(adresse: str, profil: Path) -> bool:
    """--app= gibt ein Fenster ohne Adresszeile. Ein eigenes Profil, damit das
    Fenster nicht in einer laufenden Browsersitzung aufgeht und mit ihr stirbt."""
    for browser in APP_BROWSER:
        from shutil import which
        if not which(browser):
            continue
        profil.mkdir(parents=True, exist_ok=True)
        try:
            lauf = subprocess.run([
                browser, f"--app={adresse}", f"--user-data-dir={profil}",
                "--no-first-run", "--no-default-browser-check",
                f"--class={TITEL}", f"--window-size=1280,840",
            ])
            return lauf.returncode == 0
        except OSError:
            continue
    return False


def oeffnen(port: int | None = None, eigener_server: bool = True) -> int:
    port = port or int(os.environ.get("PORT", "8099"))
    if laeuft_schon(port):
        eigener_server = False         # Dienst ist schon da, nur das Fenster fehlt
    elif eigener_server:
        port = freier_port(port)
        server_starten(port)

    adresse = f"http://127.0.0.1:{port}/"
    daten = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "notizmappe"

    if os.environ.get("NOTIZMAPPE_NUR_SERVER") == "1":
        # Fuer Buildlaeufe: es gibt keinen Desktop, an dem ein Fenster aufgehen
        # koennte. Server laeuft, Fenster faellt weg.
        print(f"Nur-Server-Betrieb: {adresse}", flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return 0

    if mit_pywebview(adresse):
        return 0
    if mit_browserfenster(adresse, daten / "fensterprofil"):
        return 0

    import webbrowser
    print(f"Kein Fenster möglich - weder pywebview noch ein Browser mit Fenstermodus.\n"
          f"Es geht im normalen Browser auf: {adresse}", file=sys.stderr)
    webbrowser.open(adresse)
    if eigener_server:
        print("Dieses Fenster offen lassen, sonst ist die Notizmappe weg.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return 0


def pruefen() -> int:
    """Sagt, womit das Fenster aufgehen wuerde. Bei "geht nicht" soll man nicht
    raten muessen, woran es liegt."""
    from shutil import which
    print("Notizmappe - was ist fürs Fenster da?\n")

    try:
        import webview
        print(f"  pywebview {getattr(webview, '__version__', '?')}: da")
    except ImportError:
        print("  pywebview: FEHLT (pip install pywebview)")
        webview = None

    try:
        import gi
        gi.require_version("Gtk", "3.0")
        print("  PyGObject (gi): da")
        for fassung in ("4.1", "4.0"):
            try:
                gi.require_version("WebKit2", fassung)
                print(f"  WebKit2 {fassung}: da  -> das Fenster geht hiermit auf")
                break
            except ValueError:
                continue
        else:
            print("  WebKit2: FEHLT  (Arch: webkit2gtk-4.1, Debian: gir1.2-webkit2-4.1)")
    except (ImportError, ValueError) as f:
        print(f"  PyGObject (gi): FEHLT  (Arch: python-gobject, Debian: python3-gi)  [{f}]")

    for name, modul in (("PyQt6 WebEngine", "PyQt6.QtWebEngineWidgets"),
                        ("PySide6 WebEngine", "PySide6.QtWebEngineWidgets")):
        try:
            __import__(modul)
            print(f"  {name}: da  -> taugt auch als Fenster")
        except ImportError:
            pass

    gefunden = [b for b in APP_BROWSER if which(b)]
    print(f"  Browser mit Fenstermodus: {', '.join(gefunden) if gefunden else 'keiner'}")
    print("\nOhne eines davon läuft es im normalen Browser - das ist der Notnagel.")
    return 0


if __name__ == "__main__":
    if "--pruefen" in sys.argv:
        sys.exit(pruefen())
    sys.exit(oeffnen())
