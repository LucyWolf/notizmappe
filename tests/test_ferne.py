"""Verbindung zu einer Notizmappe auf einem Server.

    .venv/bin/python tests/test_ferne.py

Geprüft wird gegen einen kleinen Gegenserver im Test selbst - er tut so, als
wäre er die Serverfassung. Worauf es ankommt:

* Angemeldet wird mit Adresse, Name und Passwort; gemerkt wird das
  Sitzungs-Kennzeichen, **nicht das Passwort**.
* Verbunden gehen die Aufrufe wirklich dorthin und nicht in den eigenen Ordner.
  Das ist der Punkt, an dem man Notizen am falschen Ort anlegt, ohne es zu
  merken.
* Läuft die Anmeldung ab, wird das gesagt - nicht stillschweigend weiter in den
  eigenen Ordner geschrieben.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

WURZEL = Path(__file__).resolve().parent.parent
DATEN = Path(tempfile.mkdtemp(prefix="notizen-ferne-"))
KONFIG = Path(tempfile.mkdtemp(prefix="notizen-ferne-konfig-"))
os.environ["NOTIZEN_ORDNER"] = str(DATEN)
os.environ["NOTIZMAPPE_KONFIG"] = str(KONFIG)
os.environ["NOTIZMAPPE_OPTIONEN"] = str(KONFIG / "optionen.json")
os.environ["NOTIZMAPPE_QUELLE"] = "http://127.0.0.1:1"
os.environ["LOCALAPPDATA"] = str(KONFIG)
sys.path.insert(0, str(WURZEL / "app"))

import bruecke as bruecke_modul                                     # noqa: E402
import ferne                                                        # noqa: E402

b = bruecke_modul.Bruecke()
fehler = []
gerufen = []
GUELTIG = "lucy:99999999999:abc123:unterschrift"


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


class Gegenserver(BaseHTTPRequestHandler):
    """Tut so, als wäre er die Serverfassung - gerade so viel wie nötig."""

    abgelaufen = False

    def log_message(self, *args):
        pass

    def _antwort(self, lage, rumpf=b"", kopf=None):
        self.send_response(lage)
        for k, v in (kopf or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(rumpf)))
        self.end_headers()
        if rumpf:
            self.wfile.write(rumpf)

    def do_POST(self):
        laenge = int(self.headers.get("Content-Length") or 0)
        rumpf = self.rfile.read(laenge)
        if self.path == "/anmelden":
            felder = parse_qs(rumpf.decode("utf-8"))
            name = (felder.get("name") or [""])[0]
            passwort = (felder.get("passwort") or [""])[0]
            if name == "lucy" and passwort == "richtigespasswort":
                self._antwort(303, b"", {"Location": "/",
                                         "Set-Cookie": f"notizmappe={GUELTIG}; HttpOnly; Path=/"})
            else:
                self._antwort(303, b"", {"Location": "/anmelden?fehler=Name+oder+Passwort+stimmt+nicht."})
            return
        if self.path.startswith("/bruecke/"):
            methode = self.path[len("/bruecke/"):]
            keks = self.headers.get("Cookie") or ""
            if Gegenserver.abgelaufen or GUELTIG not in keks:
                self._antwort(401, json.dumps({"fehler": "Nicht angemeldet"}).encode())
                return
            if self.headers.get("X-Notizmappe") != "1":
                self._antwort(400, json.dumps({"fehler": "Falscher Aufruf"}).encode())
                return
            gerufen.append((methode, json.loads(rumpf or b"{}").get("args")))
            if methode == "baum":
                antwort = {"notizbuecher": [{"name": "Vom Server", "abschnitte": []}]}
            elif methode == "notizbuch_anlegen":
                antwort = {"name": "Vom Server angelegt"}
            else:
                antwort = {"ok": True, "methode": methode}
            self._antwort(200, json.dumps(antwort).encode())
            return
        self._antwort(404)

    def do_GET(self):
        if self.path.startswith("/anhang"):
            keks = self.headers.get("Cookie") or ""
            if GUELTIG not in keks:
                self._antwort(401, b'{"fehler": "Nicht angemeldet"}')
                return
            self._antwort(200, b"DATEIINHALT", {"Content-Type": "application/octet-stream"})
            return
        self._antwort(404)


server = ThreadingHTTPServer(("127.0.0.1", 0), Gegenserver)
threading.Thread(target=server.serve_forever, daemon=True).start()
ADRESSE = f"http://127.0.0.1:{server.server_port}"

# --- Anmelden ----------------------------------------------------------------
print("Anmelden")
pruefe("Vorher nicht verbunden", ferne.stand()["aktiv"] is False)
a = b.ferne_anmelden({"adresse": ADRESSE, "benutzer": "lucy", "passwort": "falsch"})
pruefe("Falsches Passwort wird gemeldet", "fehler" in a and "stimmt nicht" in a["fehler"], a)
pruefe("Und nichts gemerkt", not ferne.stand()["angemeldet"])
a = b.ferne_anmelden({"adresse": ADRESSE, "benutzer": "Lucy", "passwort": "richtigespasswort"})
pruefe("Richtiges Passwort meldet an", "fehler" not in a, a)
pruefe("Jetzt angemeldet und verbunden", ferne.stand()["aktiv"] is True, ferne.stand())

import konfig                                                       # noqa: E402

gemerkt = konfig.lesen()
pruefe("Das Passwort wird NICHT gemerkt",
       "richtigespasswort" not in json.dumps(gemerkt), list(gemerkt))
pruefe("Das Sitzungs-Kennzeichen schon", gemerkt.get("ferne_keks") == GUELTIG)
pruefe("Adresse und Name auch",
       gemerkt.get("ferne_adresse") == ADRESSE and gemerkt.get("ferne_benutzer") == "lucy")
pruefe("Unsinn als Adresse wird abgelehnt",
       "fehler" in b.ferne_anmelden({"adresse": "ftp://x", "benutzer": "a", "passwort": "b"}))

# --- Verbunden geht alles dorthin --------------------------------------------
print("\nVerbunden")
baum = b.baum()
pruefe("Der Baum kommt vom Server",
       baum.get("notizbuecher", [{}])[0].get("name") == "Vom Server", baum)
pruefe("Und nicht aus dem eigenen Ordner", not list(DATEN.glob("*")), list(DATEN.glob("*")))
angelegt = b.notizbuch_anlegen("Neues Buch")
pruefe("Anlegen passiert auf dem Server", angelegt.get("name") == "Vom Server angelegt", angelegt)
pruefe("Im eigenen Ordner entsteht dabei nichts", not list(DATEN.glob("*")), list(DATEN.glob("*")))
pruefe("Die Werte kommen mit", ("notizbuch_anlegen", ["Neues Buch"]) in gerufen, gerufen[-3:])
e = b.einstellungen()
pruefe("Die Leiste zeigt den Server statt eines Pfads",
       e["ordner"].startswith("Server: "), e["ordner"])
pruefe("Und die Einstellungen kennen den Zustand", e["ferne"]["aktiv"] is True)

# Was oertlich bleiben muss, bleibt oertlich
pruefe("Die Schriften bleiben die eigenen", "schriften" in b.schriften())
pruefe("Die Sperre gilt weiter den eigenen Notizen", "eingerichtet" in b.sperre_stand())
pruefe("Nur bekannte Methoden gehen hinaus",
       all(m in bruecke_modul.FERN for m, _ in gerufen), {m for m, _ in gerufen})

# --- Umschalten --------------------------------------------------------------
print("\nUmschalten")
b.ferne_umschalten({"an": False})
pruefe("Zurück bei den eigenen Notizen", ferne.stand()["aktiv"] is False)
eigenes = b.notizbuch_anlegen("Hier zuhause")
pruefe("Jetzt entsteht es wieder hier", (DATEN / eigenes["name"]).is_dir(), eigenes)
pruefe("Angemeldet bleibt man trotzdem", ferne.stand()["angemeldet"] is True)
b.ferne_umschalten({"an": True})
pruefe("Und wieder hinüber", ferne.stand()["aktiv"] is True)

# --- Abgelaufene Anmeldung ---------------------------------------------------
print("\nWenn die Anmeldung abläuft")
Gegenserver.abgelaufen = True
antwort = b.baum()
pruefe("Das wird gesagt", antwort.get("art") == "ferne" and "neu anmelden" in antwort.get("fehler", ""),
       antwort)
pruefe("Und das Kennzeichen weggeworfen", not konfig.lesen().get("ferne_keks"))
pruefe("Nicht stillschweigend in den eigenen Ordner geschrieben",
       not (DATEN / "Vom Server").exists())
Gegenserver.abgelaufen = False

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
server.shutdown()
shutil.rmtree(DATEN, ignore_errors=True)
shutil.rmtree(KONFIG, ignore_errors=True)
sys.exit(1 if fehler else 0)
