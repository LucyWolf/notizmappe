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
# Die Versionspruefung legt ihre letzte Antwort im Quellordner ab. Wer das
# Programm vorher von Hand laufen liess, hat dort eine echte Antwort von GitHub
# stehen - und der Test prueft dann die statt seiner eigenen. Genau das ist mir
# passiert, also vorher weg damit.
(QUELLE / ".update-stand.json").unlink(missing_ok=True)
fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


PAKET = b"#!/usr/bin/env bash\necho 'Probe-Installer gelaufen'\nsleep 0.2\necho 'Fertig.'\n"
SUMME = hashlib.sha256(PAKET).hexdigest()
ZUSTAND = {"version": "v1.0.9", "paket": PAKET, "summe": SUMME, "assets": True,
           # Wie GitHub antwortet, wenn das Stundenlimit aufgebraucht ist.
           "bremse": 0, "anfragen": 0}


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
            ZUSTAND["anfragen"] += 1
            if ZUSTAND["bremse"]:
                roh = b'{"message": "API rate limit exceeded"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("x-ratelimit-remaining", "0")
                self.send_header("x-ratelimit-reset", str(int(ZUSTAND["bremse"])))
                self.send_header("Content-Length", str(len(roh)))
                self.end_headers()
                self.wfile.write(roh)
                return
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

# --- Die Bremse von GitHub ---------------------------------------------------
#
# 60 Anfragen je Stunde und je Adresse, ohne Anmeldung - und die teilen sich
# alle Programme im selben Netz. Dann steht da ein 403, und "GitHub antwortet
# mit 403" hilft niemandem weiter: man sieht weder, dass es eine Bremse ist,
# noch wann sie aufhoert, noch was man dagegen tun kann.
print("\nWenn GitHub bremst")
import time as _zeit                                        # noqa: E402

ZUSTAND["bremse"] = _zeit.time() + 1800
ZUSTAND["anfragen"] = 0
mb = modul_laden(ARBEIT / "bremse", "1.0.1", True)
s = mb.pruefen(frisch=True)
pruefe("die Meldung sagt, dass es eine Bremse ist",
       s["fehler"] and "keine Anfragen mehr" in s["fehler"], s["fehler"])
pruefe("und wann es wieder geht",
       _zeit.strftime("%H:%M", _zeit.localtime(ZUSTAND["bremse"])) in s["fehler"], s["fehler"])
pruefe("und was man dagegen tun kann", "Token" in s["fehler"], s["fehler"])
pruefe("gefragt wurde genau einmal", ZUSTAND["anfragen"] == 1, ZUSTAND["anfragen"])

# Und jetzt das Eigentliche: nicht gegen die zugehaltene Tuer rennen. Auch der
# Knopf "Nach Updates suchen" darf bis dahin nicht noch einmal anklopfen.
mb.pruefen()
mb.pruefen(frisch=True)
pruefe("bis zur Freigabe wird nicht wieder gefragt", ZUSTAND["anfragen"] == 1, ZUSTAND["anfragen"])
pruefe("und die Meldung bleibt stehen", "keine Anfragen mehr" in mb.pruefen()["fehler"])

# Ist die Sperrzeit vorbei, geht es von selbst weiter.
ZUSTAND["bremse"] = 0
notiz = json.loads(mb.NOTIZ.read_text(encoding="utf-8"))
notiz["wieder"] = _zeit.time() - 1
mb.NOTIZ.write_text(json.dumps(notiz), encoding="utf-8")
s = mb.pruefen(frisch=True)
pruefe("danach fragt es wieder", ZUSTAND["anfragen"] == 2 and s["fehler"] is None, (ZUSTAND["anfragen"], s))

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

# --- Ohne Konsole (so ist die Windows-Fassung gebaut) ------------------------
#
# Dort ist sys.stdout leer. Eine Funktion, die ihr Ergebnis druckt, faellt damit
# um - und von aussen sieht das aus wie "Update ging nicht": Rueckgabe 1, keine
# Zeile Text. Genau das hat im Buildlauf eine Weile gekostet.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import fenster                                                      # noqa: E402

ohne_konsole = Path(tempfile.mkdtemp(prefix="notizen-ohne-konsole-"))
os.environ["LOCALAPPDATA"] = str(ohne_konsole)
echt, sys.stdout = sys.stdout, None
try:
    rueckgabe = fenster.update_anstossen()
except Exception as f:                                              # noqa: BLE001
    sys.stdout = echt
    rueckgabe = f"Absturz: {type(f).__name__}"
finally:
    sys.stdout = echt
pruefe("--update faellt ohne Konsole nicht um", rueckgabe in (0, 1), rueckgabe)

import aktualisieren as akt_fuer_protokoll                          # noqa: E402

pruefe("und schreibt seine Antwort ins Protokoll",
       akt_fuer_protokoll.PROTOKOLL.exists()
       and "--update:" in akt_fuer_protokoll.PROTOKOLL.read_text(encoding="utf-8"),
       str(akt_fuer_protokoll.PROTOKOLL))
shutil.rmtree(ohne_konsole, ignore_errors=True)
(QUELLE / ".update-stand.json").unlink(missing_ok=True)

# --- Wird das Ergebnis ueberhaupt angezeigt? --------------------------------
#
# Der Mechanismus kann tadellos laufen und trotzdem sieht man nichts: Balken
# und Knopf im Band hingen frueher an zwei verschiedenen Wegen. Der Knopf kam
# nur ueber updateBeimStart(), und das steigt aus, wenn "beim Start nachsehen"
# aus ist - dann blieb das Band stumm, egal was GitHub sagte.
import re as _re                                                    # noqa: E402

_mappe = (QUELLE / "app/oberflaeche/mappe.js").read_text(encoding="utf-8")
_hinweis = _re.search(r"^function updateHinweisBauen\(.*?^\}", _mappe, _re.S | _re.M)
pruefe("updateHinweisBauen steht in mappe.js", bool(_hinweis))
if _hinweis:
    _text = _hinweis.group(0)
    pruefe("und geht ueber versionPruefen - so wird auch der Knopf im Band gesetzt",
           "versionPruefen(" in _text and "api('/api/version'" not in _text, _text[:200])
    # Vier Sekunden nach dem Start steht die Bruecke manchmal noch nicht.
    pruefe("und versucht es nach einem Fehlschlag frueher noch einmal",
           "versuche" in _text, _text[:200])
    # Der Unterschied zur Serverfassung, der dafuer gesorgt hat, dass im
    # Fenster nie etwas kam: dort steht der Balken da, sobald es etwas
    # Neues gibt. Hier hing er zusaetzlich an aktualisierbar - und das ist
    # aus, sobald das Fenster nicht aus einer Installation laeuft.
    pruefe("der Balken haengt nur an neuer, so wie in der Serverfassung",
           "!v.neuer) return;" in _text and "!v.aktualisierbar) return;" not in _text,
           _text[-300:])
_balken = _re.search(r"^function updateBalken\(.*?^\}", _mappe, _re.S | _re.M)
pruefe("updateBalken steht in mappe.js", bool(_balken))
if _balken:
    # Ein Knopf, der nichts tun kann, gehoert weg - der Satz daneben sagt
    # dann, warum.
    pruefe("und laesst 'Jetzt aktualisieren' weg, wenn sich nichts einspielen laesst",
           "hidden: !geht" in _balken.group(0), _balken.group(0)[:200])
    pruefe("sagt aber trotzdem, dass es etwas Neues gibt",
           "nicht aus einer Installation" in _balken.group(0))
pruefe("der Reiter Hilfe zeigt den Stand",
       bool(_re.search(r"^function hilfeStandZeigen\(.*?^\}", _mappe, _re.S | _re.M)))
# Der Fall, der sonst stumm bleibt: neuer waere da, aber das Fenster laeuft
# aus dem Quellordner - dann gibt es weder Knopf noch Balken.
pruefe("und nennt den Grund, wenn sich hier nichts einspielen laesst",
       "nicht aus einer Installation" in _mappe)

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER: " + ", ".join(fehler))
server.shutdown()
shutil.rmtree(ARBEIT, ignore_errors=True)
sys.exit(1 if fehler else 0)
