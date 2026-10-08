"""Im echten Fenster nachspielen, was man als Erstes tut.

    .venv/bin/python tools/fenster_pruefen.py

Öffnet das Fenster, legt einen Kasten an, schreibt hinein, wartet auf das
Speichern und öffnet die Einstellungen - und meldet, was dabei herauskam. Dafür
da, dass "geht nicht" eine Antwort bekommt und nicht geraten werden muss: so kam
heraus, dass WebKitGTK gar kein localStorage hat und deshalb die ganze Oberfläche
stumm blieb.
"""
import json, os, sys, threading, time
from pathlib import Path

WURZEL = Path(__file__).resolve().parent
sys.path.insert(0, str(WURZEL / "app"))
os.environ.setdefault("NOTIZEN_ORDNER", str(Path.home() / "Notizen"))
os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
if os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("GDK_BACKEND", "wayland")

import uvicorn, main, webview

PORT = 8191
threading.Thread(target=lambda: uvicorn.run(main.app, host="127.0.0.1", port=PORT, log_level="error"),
                 daemon=True).start()
time.sleep(3)
fenster = webview.create_window("Diagnose", f"http://127.0.0.1:{PORT}/", width=1100, height=700)

LAGE = """JSON.stringify({
  fehler: window.__fehler,
  baumKinder: document.querySelector('#baum').children.length,
  seiten: document.querySelectorAll('.seite').length,
  titelGesperrt: document.querySelector('#titel').disabled,
  titel: document.querySelector('#titel').value,
  kaesten: document.querySelectorAll('.kasten').length
})"""

SCHREIBEN = """(function () {
  try {
    kastenNeu(120, 120);
    var t = document.querySelector('.kasten .text');
    t.focus();
    t.innerHTML = '<p>Vom Fenster aus geschrieben</p>';
    t.dispatchEvent(new Event('input', { bubbles: true }));
    return JSON.stringify({ kaesten: document.querySelectorAll('.kasten').length,
                            fokus: document.activeElement.className,
                            inhalt: t.textContent });
  } catch (f) { return JSON.stringify({ fehler: f.message, stapel: String(f.stack).slice(0, 300) }); }
})()"""

TAFEL = """(function () {
  try {
    document.querySelector('#zahnrad').click();
    return 'angeklickt';
  } catch (f) { return 'Fehler: ' + f.message; }
})()"""

TAFEL_LESEN = """JSON.stringify({
  offen: !document.querySelector('#einstellungen').hidden,
  version: document.querySelector('#e-version').textContent,
  ordner: document.querySelector('#e-ordner').textContent,
  seiten: document.querySelector('#e-seiten').textContent,
  verfuegbar: document.querySelector('#e-verfuegbar').textContent,
  hinweis: document.querySelector('#e-updatehinweis').textContent,
  lage: document.querySelector('#e-lage').textContent,
  fehler: window.__fehler
})"""


def nachsehen():
    try:
        time.sleep(6)
        print("LAGE " + fenster.evaluate_js(LAGE), flush=True)
        print("SCHREIBEN " + fenster.evaluate_js(SCHREIBEN), flush=True)
        time.sleep(3)                       # Autosave abwarten
        print("NACH DEM SPEICHERN " + fenster.evaluate_js(
            "JSON.stringify({zustand: document.querySelector('#zustand').textContent,"
            " kaesten: document.querySelectorAll('.kasten').length, fehler: window.__fehler})"), flush=True)
        fenster.evaluate_js(TAFEL)
        time.sleep(3)
        print("EINSTELLUNGEN " + fenster.evaluate_js(TAFEL_LESEN), flush=True)
    except Exception as f:
        print(f"Abfrage ging nicht: {f}", flush=True)
    time.sleep(1)
    fenster.destroy()


threading.Thread(target=nachsehen, daemon=True).start()
speicher = Path.home() / ".local/share/notizmappe/webansicht"
speicher.mkdir(parents=True, exist_ok=True)
webview.start(private_mode=False, storage_path=str(speicher))
