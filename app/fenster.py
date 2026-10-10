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
    # /api/status antwortet auch, wenn die Notizmappe gesperrt ist; /api/baum fuer
    # aeltere Fassungen, die es noch nicht kennen.
    for weg, marke in (("/api/status", b'"notizmappe"'), ("/api/baum", b"notizbuecher")):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{weg}", timeout=1.5) as a:
                if marke in a.read(400):
                    return True
        except (urllib.error.URLError, OSError, TimeoutError):
            continue
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
    notieren(f"Server gestartet auf Port {port} (Importe sind damit durch).")
    return faden


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


def browserfenster_erlaubt() -> bool:
    """Auf Windows ja, sonst nur auf Ansage.

    Ein Fenster mit --app hat keine Adresszeile, keine Lesezeichen und einen
    eigenen Eintrag in der Taskleiste - es sieht aus und verhaelt sich wie ein
    Programm, auch wenn innen ein Browser steckt. Auf Windows ist Edge immer
    vorhanden, also gibt es damit immer ein Fenster, auch wenn die WebView2-
    Laufzeit fehlt. Unter Linux bleibt es abgeschaltet: dort ist die Webansicht
    des Systems der richtige Weg, und ein Browserfenster wuerde nur verdecken,
    dass etwas fehlt."""
    if os.environ.get("NOTIZMAPPE_BROWSERFENSTER") == "0":
        return False
    return sys.platform == "win32" or os.environ.get("NOTIZMAPPE_BROWSERFENSTER") == "1"


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


def eltern_wache(webview) -> None:
    """Das Hauptfenster gehoert zu seinem Server. Stirbt der Elternprozess (Absturz,
    kill, Abmelden), blieb das Fenster sonst offen und zeigte auf einen toten
    Server. Unter Linux/macOS merkt man das daran, dass sich getppid() aendert -
    der Prozess wird an init oder einen Subreaper weitergereicht."""
    roh = os.environ.get("NOTIZMAPPE_ELTERN")
    if not roh or os.name != "posix":
        return
    eltern = int(roh)

    def wachen():
        while os.getppid() == eltern:
            time.sleep(1.5)
        for w in list(getattr(webview, "windows", [])):
            try:
                w.destroy()
            except Exception:
                pass
        os._exit(0)

    threading.Thread(target=wachen, daemon=True).start()


WARTESEITE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<style>
 html,body{height:100%;margin:0;display:flex;align-items:center;justify-content:center;
   background:#fffefb;color:#78736a;font:15px system-ui,sans-serif}
 @media (prefers-color-scheme:dark){html,body{background:#1b1a18;color:#938d83}}
 .p{width:180px;height:3px;background:#e3e0d8;border-radius:2px;overflow:hidden}
 @media (prefers-color-scheme:dark){.p{background:#332f2a}}
 .p i{display:block;height:100%;width:40%;background:#7a5cff;border-radius:2px;
   animation:l 1.1s ease-in-out infinite}
 @keyframes l{0%{margin-left:-40%}100%{margin-left:100%}}
 div{text-align:center}
</style></head><body><div>
 <p>Notizmappe wird geöffnet …</p><div class="p"><i></i></div>
</div></body></html>"""


def fenster_zeigen(adresse: str) -> None:
    """Laeuft im Kindprozess - siehe mit_pywebview()."""
    webkit_zurechtruecken()
    import webview
    eltern_wache(webview)
    # Erst eine Warteseite, dann die Oberflaeche. Sonst steht das Fenster so lange
    # aus, bis der Server antwortet - und in der Zeit sieht man gar nichts und
    # haelt das Programm fuer kaputt.
    fenster = webview.create_window(TITEL, html=WARTESEITE,
                                    width=1280, height=840, min_size=(640, 480))

    def wenn_bereit():
        port = int(adresse.rstrip("/").rsplit(":", 1)[-1])
        for _ in range(600):           # bis zu einer Minute
            if laeuft_schon(port):
                notieren("Oberfläche geladen.")
                fenster.load_url(adresse)
                return
            time.sleep(0.1)
        notieren("Der Server ist nicht hochgekommen - das Fenster bleibt bei der Warteseite.")
    # private_mode=False: im Privatmodus stellt WebKitGTK gar kein localStorage
    # bereit - die Variable fehlt dann komplett. Die Oberflaeche kommt inzwischen
    # auch ohne aus, aber so bleiben Zoom, aufgeklappte Abschnitte und die zuletzt
    # offene Seite ueber einen Neustart hinweg erhalten.
    speicher = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "notizmappe/webansicht"
    speicher.mkdir(parents=True, exist_ok=True)
    # Das Symbol nur dort mitgeben, wo ein PNG auch eines sein darf. Windows
    # verlangt eine .ico-Datei und wirft sonst mitten im Fensterbau
    # "Argument 'picture' must be a picture that can be used as a Icon" - in einem
    # .NET-Thread, der das ganze Programm mitnimmt. Kein Fenster, keine Meldung,
    # nichts. Die Windows-Fassung hat ihr Symbol ohnehin aus der exe selbst.
    zusatz = {}
    if sys.platform != "win32":
        symbol = Path(__file__).resolve().parent / "static/icon.png"
        if symbol.is_file():
            zusatz["icon"] = str(symbol)
    try:
        webview.start(wenn_bereit, private_mode=False, storage_path=str(speicher), **zusatz)
    except TypeError:
        # Aeltere pywebview-Fassungen kennen den Parameter nicht.
        webview.start(wenn_bereit, private_mode=False, storage_path=str(speicher))


def fenster_befehl(adresse: str) -> list[str]:
    """Befehl fuer einen Fensterprozess. Im Windows-Buendel (PyInstaller) ist
    sys.executable die exe selbst und versteht --nur-fenster direkt."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--nur-fenster", adresse]
    return [sys.executable, str(Path(__file__).resolve()), "--nur-fenster", adresse]


def weiteres_fenster(adresse: str) -> bool:
    """Ein zusaetzliches Fenster, ohne darauf zu warten - fuer die Verbindung zu
    einem Server neben der lokalen Mappe. False, wenn es kein pywebview gibt."""
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    try:
        subprocess.Popen(fenster_befehl(adresse))
    except OSError:
        return False
    return True


def mit_pywebview(adresse: str) -> bool:
    """Das Fenster laeuft in einem eigenen Prozess - ausser auf Windows.

    Nicht aus Ordnungsliebe: stirbt die Webansicht am Display, reisst sie den
    ganzen Prozess mit, ohne eine Ausnahme auszuloesen - ein try/except im selben
    Prozess sieht davon nichts und der Rueckfall auf den naechsten Weg kaeme nie.
    Als Kindprozess merkt man es am Rueckgabewert und daran, wie schnell er weg war.
    """
    try:
        import webview  # noqa: F401  - nur nachsehen, ob es ueberhaupt da ist
    except ImportError:
        mit_pywebview.grund = "pywebview fehlt"
        notieren(mit_pywebview.grund)
        return False

    if sys.platform == "win32":
        # Auf Windows im selben Prozess. Der Grund fuer den Kindprozess ist, dass
        # WebKitGTK bei einem Display-Fehler den ganzen Prozess mitreisst, ohne
        # eine Ausnahme auszuloesen - das ist ein Linux-Problem. Hier wuerde der
        # zweite Prozess dagegen das ganze Buendel ein zweites Mal auspacken
        # (PyInstaller --onefile), und der Start dauert doppelt so lange.
        notieren(f"Windows: {webview2_lage()}")
        begonnen = time.monotonic()
        try:
            fenster_zeigen(adresse)
        except Exception as f:
            import traceback
            mit_pywebview.grund = f"Die Webansicht von Windows hat nicht getragen: {f}"
            notieren(mit_pywebview.grund + "\n" + traceback.format_exc()[-800:])
            return False
        dauer = time.monotonic() - begonnen
        if dauer < 2.0:
            # Kam zurueck, ohne dass jemand etwas schliessen konnte: dann ist nie
            # ein Fenster aufgegangen. Ohne diese Pruefung sieht man nur, wie das
            # Programm sich kommentarlos beendet.
            mit_pywebview.grund = (f"Das Fenster war nach {dauer:.1f}s schon wieder zu - "
                                   f"es ist wohl nie aufgegangen.\n{webview2_lage()}")
            notieren(mit_pywebview.grund)
            return False
        notieren(f"Fenster war {dauer:.0f}s offen.")
        return True

    begonnen = time.monotonic()
    try:
        # Mit Eltern-PID: das Fenster soll mit dem Server gehen (eltern_wache).
        # Die Ausgabe wird eingefangen, damit der Grund im Protokoll landet und
        # nicht im Nichts verschwindet, wenn niemand ein Terminal offen hat.
        lauf = subprocess.run(fenster_befehl(adresse),
                              env=dict(os.environ, NOTIZMAPPE_ELTERN=str(os.getpid())),
                              capture_output=True, text=True)
    except OSError as f:
        mit_pywebview.grund = f"pywebview liess sich nicht starten: {f}"
        notieren(mit_pywebview.grund)
        return False
    dauer = time.monotonic() - begonnen

    gemeckert = "\n".join(z for z in (lauf.stderr or "").splitlines()[-6:] if z.strip())
    if lauf.returncode == 0 and dauer >= 2.0:
        notieren(f"Fenster über die Webansicht des Systems, {dauer:.0f}s offen gewesen.")
        return True

    mit_pywebview.grund = (f"Die Webansicht des Systems hat nicht getragen: nach {dauer:.1f}s "
                           f"beendet, Rückgabe {lauf.returncode}."
                           + (f"\n{gemeckert}" if gemeckert else ""))
    notieren(mit_pywebview.grund)
    return False


mit_pywebview.grund = ""


def app_fenster_programme() -> list[str]:
    """Was auf diesem Rechner ein Fenster ohne Adresszeile aufmachen kann."""
    from shutil import which
    if sys.platform == "win32":
        # Edge gehoert zu Windows, ist also immer da. Mit --app ist das ein
        # eigenes Fenster mit eigenem Eintrag in der Taskleiste - kein Browsertab.
        kandidaten = []
        for ordner in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                       os.environ.get("ProgramFiles", r"C:\Program Files"),
                       os.environ.get("LOCALAPPDATA", "")):
            if not ordner:
                continue
            for weg in (r"Microsoft\Edge\Application\msedge.exe",
                        r"Google\Chrome\Application\chrome.exe",
                        r"BraveSoftware\Brave-Browser\Application\brave.exe"):
                voll = Path(ordner) / weg
                if voll.is_file():
                    kandidaten.append(str(voll))
        return kandidaten
    return [b for b in APP_BROWSER if which(b)]


def mit_browserfenster(adresse: str, profil: Path) -> bool:
    """--app= gibt ein Fenster ohne Adresszeile. Ein eigenes Profil, damit das
    Fenster nicht in einer laufenden Browsersitzung aufgeht und mit ihr stirbt."""
    for browser in app_fenster_programme():
        profil.mkdir(parents=True, exist_ok=True)
        befehl = [
            browser, f"--app={adresse}", f"--user-data-dir={profil}",
            "--no-first-run", "--no-default-browser-check",
            f"--class={TITEL}", "--window-size=1280,840",
        ]
        if unter_wayland():
            # Sonst laeuft auch dieses Fenster ueber XWayland.
            befehl += ["--ozone-platform=wayland", "--enable-features=UseOzonePlatform"]
        try:
            notieren(f"Fenster über {Path(browser).name} (--app, ohne Adresszeile).")
            begonnen = time.monotonic()
            lauf = subprocess.run(befehl)
            dauer = time.monotonic() - begonnen
            if lauf.returncode == 0 and dauer >= 2.0:
                return True
            notieren(f"{Path(browser).name} war nach {dauer:.1f}s wieder weg "
                     f"(Rückgabe {lauf.returncode}).")
        except OSError as f:
            notieren(f"{browser} liess sich nicht starten: {f}")
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

    if browserfenster_erlaubt():
        notieren("Webansicht ging nicht - jetzt ein Fenster ohne Adresszeile.")
        if mit_browserfenster(adresse, daten / "fensterprofil"):
            return 0

    # Hier wird bewusst nichts im Browser geöffnet. Die Notizmappe soll ein
    # Programm im eigenen Fenster sein; ein Tab im Browser ist kein Ersatz, und
    # stillschweigend einen aufzumachen verdeckt nur, dass etwas kaputt ist.
    meldung_zeigen(
        "Das Fenster ließ sich nicht öffnen.\n\n"
        + (mit_pywebview.grund or "Die Webansicht des Systems steht nicht zur Verfügung.")
        + f"\n\nProtokoll: {PROTOKOLL}\n"
        + ("" if sys.platform == "win32" else
           f"Was fehlt, sagt:\n    {Path(sys.argv[0]).resolve().parent}/notizmappe --pruefen\n")
        + "Notfalls im Browser: NOTIZMAPPE_BROWSERFENSTER=1 davor setzen."
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

    gefunden = app_fenster_programme()
    print("  Fenster ohne Adresszeile möglich über: "
          + (", ".join(Path(g).name for g in gefunden) if gefunden else "nichts gefunden"))
    if sys.platform == "win32":
        print("\nReihenfolge: Webansicht von Windows (WebView2), sonst ein Fenster über"
              "\nEdge oder Chrome mit --app - ohne Adresszeile, eigener Eintrag in der"
              "\nTaskleiste. Abschalten mit NOTIZMAPPE_BROWSERFENSTER=0.")
    else:
        print("\nOhne pywebview mit WebKit2 oder Qt geht hier kein Fenster auf. Es wird dann"
              "\nauch nichts im Browser geöffnet - nur gemeldet. Wer das doch will:"
              "\n    NOTIZMAPPE_BROWSERFENSTER=1 notizmappe")
    return 0


if __name__ == "__main__":
    if "--pruefen" in sys.argv:
        sys.exit(pruefen())
    if "--nur-fenster" in sys.argv:
        fenster_zeigen(sys.argv[sys.argv.index("--nur-fenster") + 1])
        sys.exit(0)
    sys.exit(oeffnen())
