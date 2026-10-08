"""Selbstupdate gegen einen nachgemachten GitHub-Server durchspielen.

    .venv/bin/python tests/test_update.py

Kein echtes Netz, kein Token - sonst hängt der Test an GitHubs Bremse und an der
Sichtbarkeit des Repos. Der Weg ist derselbe: Release abfragen, Paket laden,
Prüfsumme vergleichen, Installer abgekoppelt starten.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

QUELLE = Path(__file__).resolve().parent.parent
fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


PAKET = b"#!/usr/bin/env bash\necho 'Probe-Installer gelaufen'\nsleep 0.2\necho 'Fertig.'\n"
SUMME = hashlib.sha256(PAKET).hexdigest()
ZUSTAND = {"version": "v1.0.9", "paket": PAKET, "summe": SUMME, "assets": True}


class Hand(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _sende(self, inhalt, typ="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(inhalt)))
        self.end_headers()
        self.wfile.write(inhalt)

    def do_GET(self):
        basis = f"http://127.0.0.1:{self.server.server_port}"
        v = ZUSTAND["version"]
        if self.path.endswith("/releases/latest"):
            assets = []
            if ZUSTAND["assets"]:
                assets = [
                    {"name": f"notizmappe-{v}-installer.sh", "url": f"{basis}/asset/paket"},
                    {"name": f"notizmappe-{v}-installer.sh.sha256", "url": f"{basis}/asset/summe"},
                    {"name": "notizmappe-installer.sh", "url": f"{basis}/asset/paket"},
                ]
            self._sende(json.dumps({"tag_name": v, "body": "Probe-Release", "assets": assets}).encode())
        elif self.path == "/asset/paket":
            self._sende(ZUSTAND["paket"], "application/octet-stream")
        elif self.path == "/asset/summe":
            self._sende(f"{ZUSTAND['summe']}  notizmappe-{v}-installer.sh\n".encode(), "text/plain")
        else:
            self.send_error(404)


server = HTTPServer(("127.0.0.1", 0), Hand)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASIS = f"http://127.0.0.1:{server.server_port}"
ARBEIT = Path(tempfile.mkdtemp(prefix="notizmappe-update-test-"))


def modul_laden(ordner: Path, version: str, eingerichtet: bool, quelle: str = None):
    """aktualisieren.py arbeitet relativ zu seinem eigenen Ort - also eine echte
    Ordnerstruktur nachbauen statt Funktionen zu überschreiben."""
    shutil.rmtree(ordner, ignore_errors=True)
    (ordner / "app").mkdir(parents=True)
    shutil.copy(QUELLE / "app/aktualisieren.py", ordner / "app/aktualisieren.py")
    (ordner / "app/VERSION").write_text(version)
    if eingerichtet:
        (ordner / ".einrichtung").write_text(f"ZIEL={ordner}\n")
    os.environ["NOTIZMAPPE_QUELLE"] = quelle or BASIS
    os.environ.pop("NOTIZMAPPE_TOKEN", None)
    spec = importlib.util.spec_from_file_location(f"akt_{ordner.name}", ordner / "app/aktualisieren.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


m = modul_laden(ARBEIT / "a", "1.0.1", True)
pruefe("1.0.9 ist kleiner als 1.0.10", m.version_tupel("1.0.9") < m.version_tupel("1.0.10"))
pruefe("v-Vorsatz stoert nicht", m.version_tupel("v1.2.3") == (1, 2, 3))
pruefe("1.1.0 groesser als 1.0.99", m.version_tupel("1.1.0") > m.version_tupel("1.0.99"))
pruefe("Unsinn wird zu (0,)", m.version_tupel("kaputt") == (0,))

s = m.pruefen(frisch=True)
pruefe("findet die neuere Fassung", s["neuer"] and s["verfuegbar"] == "1.0.9", s)
pruefe("meldet die installierte", s["installiert"] == "1.0.1", s)
pruefe("meldet aktualisierbar", s["aktualisierbar"] is True, s)
pruefe("kein Fehler gemeldet", s["fehler"] is None, s)
pruefe("Release-Notizen dabei", s.get("notizen") == "Probe-Release", s)

ZUSTAND["version"] = "v9.9.9"
pruefe("Antwort kommt aus dem Zwischenspeicher", m.pruefen()["verfuegbar"] == "1.0.9")
pruefe("frisch=True fragt neu", m.pruefen(frisch=True)["verfuegbar"] == "9.9.9")
ZUSTAND["version"] = "v1.0.9"
m.pruefen(frisch=True)

pruefe("gleiche Version ist nicht neuer", modul_laden(ARBEIT / "b", "1.0.9", True).pruefen(frisch=True)["neuer"] is False)
pruefe("neuere Installation bleibt ruhig", modul_laden(ARBEIT / "c", "2.0.0", True).pruefen(frisch=True)["neuer"] is False)

ZUSTAND["assets"] = False
s = modul_laden(ARBEIT / "d", "1.0.1", True).pruefen(frisch=True)
pruefe("Release ohne Installationsdatei meldet Fehler", s["fehler"] and not s["neuer"], s)
ZUSTAND["assets"] = True

m5 = modul_laden(ARBEIT / "e", "1.0.1", False)
pruefe("Quellordner ist nicht aktualisierbar", m5.pruefen(frisch=True)["aktualisierbar"] is False)
try:
    m5.einspielen()
    pruefe("Quellordner verweigert Update", False)
except RuntimeError as f:
    pruefe("Quellordner verweigert Update", "git" in str(f).lower(), str(f))

m6 = modul_laden(ARBEIT / "f", "1.0.1", True)
r = m6.einspielen()
pruefe("Update gemeldet", r["von"] == "1.0.1" and r["nach"] == "1.0.9", r)
pruefe("Pruefsumme stimmt mit dem Paket", r["pruefsumme"] == SUMME, r)
for _ in range(40):
    if m6.protokoll().get("fertig"):
        break
    time.sleep(0.1)
p = m6.protokoll()
pruefe("Installer wurde ausgefuehrt", "Probe-Installer gelaufen" in p["text"], p["text"][:200])
pruefe("Protokoll meldet fertig", p["fertig"], p["text"][:200])
pruefe("Protokoll nennt die Versionen", "1.0.1 -> 1.0.9" in p["text"], p["text"][:200])

ZUSTAND["paket"] = PAKET + b"# verbogen\n"      # Summe bleibt die alte
m7 = modul_laden(ARBEIT / "g", "1.0.1", True)
try:
    m7.einspielen()
    pruefe("falsche Pruefsumme bricht ab", False)
except RuntimeError as f:
    pruefe("falsche Pruefsumme bricht ab", "summe" in str(f).lower(), str(f))
pruefe("nichts ausgefuehrt", not m7.protokoll()["laeuft"])
ZUSTAND["paket"] = PAKET

s = modul_laden(ARBEIT / "h", "1.0.1", True, quelle="http://127.0.0.1:1").pruefen(frisch=True)
pruefe("kein Netz: Fehler statt Absturz", s["fehler"] and not s["neuer"], s)
pruefe("kein Netz: Knopf bleibt aus", s["neuer"] is False)

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER: " + ", ".join(fehler))
server.shutdown()
shutil.rmtree(ARBEIT, ignore_errors=True)
sys.exit(1 if fehler else 0)
