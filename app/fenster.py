"""Die Notizmappe als Programm im eigenen Fenster.

Die Oberflaeche ist HTML und laeuft in der Webansicht des Systems; sie wird als
Datei geladen, nicht ueber eine Adresse. Zwischen Fenster und Programm liegt
bruecke.py - ein Funktionsaufruf, kein Netz. Kein Port, keine IP, kein HTTP, und
deshalb auch keine Frage der Firewall.

Traegt die Webansicht nicht, geht kein Fenster auf. Dann wird gesagt, woran es
liegt - frueher ging ersatzweise ein Browser auf, aber ein Browser braucht eine
Adresse, und genau die gibt es hier nicht mehr.
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


def _oberflaeche() -> Path:
    return Path(__file__).resolve().parent / "oberflaeche/index.html"


def _datenort() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "notizmappe"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "notizmappe"


PROTOKOLL = _datenort() / "fenster.log"
BEGONNEN = time.monotonic()


def seit_start() -> str:
    return f"[{time.monotonic() - BEGONNEN:5.1f}s]"


def notieren(zeile: str) -> None:
    """Jeder Versuch kommt ins Protokoll. Beim Klick aus dem Menue gibt es kein
    Terminal - ohne Datei weiss hinterher niemand, welcher Weg genommen wurde und
    warum er nicht trug."""
    stempel = time.strftime("%d.%m.%Y %H:%M:%S")
    zeile = f"{seit_start()} {zeile}"
    print(zeile, file=sys.stderr, flush=True)
    try:
        PROTOKOLL.parent.mkdir(parents=True, exist_ok=True)
        with PROTOKOLL.open("a", encoding="utf-8") as f:
            f.write(f"{stempel}  {zeile}\n")
    except OSError:
        pass


def meldung_zeigen(text: str) -> None:
    """Ohne Terminal und ohne Fenster bliebe sonst gar nichts uebrig - dann wenigstens
    ein Hinweisfenster der Arbeitsumgebung."""
    from shutil import which
    if sys.platform == "win32":
        # Ohne Konsole landet print() im Nichts - das Fenster von Windows selbst
        # ist hier die einzige Moeglichkeit, ueberhaupt etwas zu sagen.
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, TITEL, 0x10)
            return
        except Exception:
            pass
    hat_anzeige = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    for werkzeug, befehl in (("kdialog", ["kdialog", "--title", TITEL, "--error", text]),
                             ("zenity", ["zenity", "--error", f"--title={TITEL}", f"--text={text}"])):
        if hat_anzeige and which(werkzeug):
            try:
                subprocess.run(befehl, timeout=120)
                return
            except (OSError, subprocess.TimeoutExpired):
                continue
    print(text, file=sys.stderr, flush=True)


def webview2_lage() -> str:
    """Das Fenster kommt auf Windows von der Edge-WebView2-Laufzeit. Fehlt die,
    geht nichts auf - und das muss dastehen, statt dass man raet."""
    if sys.platform != "win32":
        return ""
    teile = []
    try:
        import winreg
        gefunden = None
        for wurzel, pfad in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        ):
            try:
                with winreg.OpenKey(wurzel, pfad) as k:
                    gefunden = winreg.QueryValueEx(k, "pv")[0]
                    break
            except OSError:
                continue
        teile.append(f"WebView2-Laufzeit: {gefunden}" if gefunden
                     else "WebView2-Laufzeit: FEHLT - zu holen bei Microsoft "
                          "(\"Evergreen Standalone Installer\")")
    except Exception as f:
        teile.append(f"WebView2-Laufzeit: nicht feststellbar ({f})")
    try:
        import clr  # noqa: F401  - pywebview spricht ueber pythonnet mit WebView2
        teile.append("pythonnet: da")
    except Exception as f:
        teile.append(f"pythonnet: FEHLT ({f})")
    return "  ".join(teile)


def unter_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def webkit_zurechtruecken() -> None:
    """Zwei Dinge, ohne die das Fenster nicht oder nicht richtig aufgeht.

    WebKitGTK rendert standardmaessig ueber DMABUF. Mit NVIDIA unter Wayland bricht
    das die Verbindung zum Display ab ("Error 71, Protokollfehler") - und zwar so
    hart, dass Gdk den Prozess beendet, bevor Python etwas davon mitbekommt. Ohne
    diesen Renderer geht das Fenster auf; die Beschleunigung bleibt an, nur der
    Pufferweg ist ein anderer.

    Und: liegt eine Wayland-Sitzung an, soll GTK auch Wayland sprechen. Sonst nimmt
    es bei gesetztem DISPLAY den Umweg ueber XWayland - mit unscharfer Darstellung
    auf skalierten Bildschirmen und eigenen Eingabe-Macken.
    """
    if not sys.platform.startswith("linux"):
        return
    os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
    if unter_wayland():
        os.environ.setdefault("GDK_BACKEND", "wayland")
        os.environ.setdefault("QT_QPA_PLATFORM", "wayland")   # falls pywebview Qt nimmt
        os.environ.setdefault("MOZ_ENABLE_WAYLAND", "1")


def fenster_zeigen() -> bool:
    """Das Fenster aufmachen. True, wenn es wirklich offen war."""
    webkit_zurechtruecken()
    try:
        import webview
    except ImportError:
        meldung_zeigen("pywebview fehlt - ohne das geht kein Fenster auf.\n"
                       "Unter Linux: python-gobject und webkit2gtk-4.1 installieren.")
        return False

    import bruecke as bruecke_modul
    verbindung = bruecke_modul.Bruecke()

    seite = _oberflaeche()
    if not seite.is_file():
        meldung_zeigen(f"Die Oberfläche fehlt: {seite}")
        return False

    notieren(f"Oberfläche: {seite}")
    if sys.platform == "win32":
        notieren(f"Windows: {webview2_lage()}")

    fenster = webview.create_window(
        TITEL, url=seite.as_uri(), js_api=verbindung,
        width=1280, height=840, min_size=(640, 480),
    )
    verbindung.fenster = fenster       # fuer die Ordner- und Speichern-Dialoge

    speicher = _datenort() / "webansicht"
    speicher.mkdir(parents=True, exist_ok=True)

    # Das Symbol nur dort mitgeben, wo ein PNG auch eines sein darf. Windows
    # verlangt eine .ico und wirft sonst mitten im Fensterbau
    # "Argument 'picture' must be a picture that can be used as a Icon" - in einem
    # .NET-Thread, der das ganze Programm mitnimmt.
    zusatz = {}
    if sys.platform != "win32":
        symbol = Path(__file__).resolve().parent / "oberflaeche/icon.png"
        if symbol.is_file():
            zusatz["icon"] = str(symbol)

    begonnen = time.monotonic()
    try:
        # private_mode=False: sonst stellt WebKitGTK gar kein localStorage bereit.
        webview.start(private_mode=False, storage_path=str(speicher), **zusatz)
    except TypeError:
        webview.start(private_mode=False, storage_path=str(speicher))
    dauer = time.monotonic() - begonnen

    if dauer < 2.0:
        # Kam zurueck, ohne dass jemand etwas schliessen konnte: dann ist nie ein
        # Fenster aufgegangen. Ohne diese Pruefung beendet sich das Programm
        # kommentarlos und niemand weiss, warum.
        notieren(f"Das Fenster war nach {dauer:.1f}s schon wieder zu.")
        return False
    notieren(f"Fenster war {dauer:.0f}s offen.")
    return True


def oeffnen() -> int:
    if os.environ.get("NOTIZMAPPE_OHNE_FENSTER") == "1":
        # Fuer Buildlaeufe: dort gibt es keinen Bildschirm. Nur nachsehen, ob sich
        # alles laden laesst - das Fenster faellt weg.
        import bruecke as bruecke_modul
        b = bruecke_modul.Bruecke()
        e = b.einstellungen()
        print(f"Ohne Fenster. Version {e.get('version')}, Ordner {e.get('ordner')}", flush=True)
        return 0

    if fenster_zeigen():
        return 0

    meldung_zeigen(
        "Das Fenster ließ sich nicht öffnen.\n\n"
        + (webview2_lage() if sys.platform == "win32"
           else "Die Webansicht des Systems steht nicht zur Verfügung.")
        + f"\n\nProtokoll: {PROTOKOLL}"
    )
    return 1


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

    if sys.platform.startswith("linux"):
        gesetzt = os.environ.get("WEBKIT_DISABLE_DMABUF_RENDERER")
        print(f"  WEBKIT_DISABLE_DMABUF_RENDERER: {gesetzt or 'wird beim Start auf 1 gesetzt'}"
              f"   (ohne das bricht WebKitGTK mit NVIDIA unter Wayland ab)")
        if unter_wayland():
            print(f"  Sitzung: Wayland ({os.environ['WAYLAND_DISPLAY']}) -> GDK_BACKEND=wayland, "
                  f"kein Umweg über XWayland")
        else:
            print("  Sitzung: kein WAYLAND_DISPLAY gesetzt - es läuft über X11")

    if sys.platform == "win32":
        print(f"  {webview2_lage()}")

    print("\nOhne eine Webansicht geht kein Fenster auf. Es wird dann auch nichts im"
          "\nBrowser geöffnet - dafür gäbe es keine Adresse mehr, das Programm redet"
          "\ndirekt mit seinem Fenster.")
    print(f"\nOberfläche: {_oberflaeche()}  {'da' if _oberflaeche().is_file() else 'FEHLT'}")
    try:
        import bruecke as bruecke_modul
        e = bruecke_modul.Bruecke().einstellungen()
        print(f"Daten:      {e.get('ordner')}  ({e.get('seiten')} Seiten)")
    except Exception as f:
        print(f"Daten:      nicht lesbar ({f})")
    return 0


def update_anstossen() -> int:
    """Update ohne Fenster anstossen - fuer Buildlaeufe und fuer den Fall, dass
    die Oberflaeche nicht mehr aufgeht."""
    import json
    import bruecke as bruecke_modul
    ergebnis = bruecke_modul.Bruecke().update()
    print(json.dumps(ergebnis, ensure_ascii=False))
    return 1 if ergebnis.get("fehler") else 0


if __name__ == "__main__":
    if "--pruefen" in sys.argv:
        sys.exit(pruefen())
    if "--update" in sys.argv:
        sys.exit(update_anstossen())
    sys.exit(oeffnen())
