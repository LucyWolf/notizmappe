"""Anmeldung, Sperre und Projekte durchfahren - lokal und im Server-Betrieb.

    .venv/bin/python tests/test_konten.py

Läuft gegen Wegwerf-Ordner unter /tmp, fasst echte Notizen und Einstellungen nicht an.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DATEN = Path(tempfile.mkdtemp(prefix="notizen-konten-"))
KONFIG = Path(tempfile.mkdtemp(prefix="notizen-konfig-"))
os.environ["NOTIZEN_ORDNER"] = str(DATEN)
os.environ["NOTIZMAPPE_KONFIG"] = str(KONFIG)
os.environ["NOTIZMAPPE_QUELLE"] = "http://127.0.0.1:1"
os.environ.pop("NOTIZMAPPE_SERVER", None)
sys.path.insert(0, str(WURZEL / "app"))

from fastapi.testclient import TestClient
import konten
import main

fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


def neu(hier=True):
    return TestClient(main.app, client=("127.0.0.1" if hier else "10.0.0.9", 50000))


# --- Eigener Rechner, ohne Sperre -------------------------------------------------
print("--- Eigener Rechner ---")
a = neu()
pruefe("Ohne Sperre offen", a.get("/api/baum").status_code == 200)
pruefe("Status sagt: keine Anmeldung", a.get("/api/status").json()["anmeldung"] is False)
pruefe("Sperre von fremder Adresse nicht einschaltbar",
       neu(False).post("/api/sperre", json={"passwort": "geheim123"}).status_code == 403)
pruefe("Zu kurzes Passwort abgelehnt", a.post("/api/sperre", json={"passwort": "kurz"}).status_code == 400)
r = a.post("/api/sperre", json={"passwort": "geheim123"})
pruefe("Sperre eingeschaltet", r.status_code == 200, r.text)
pruefe("Sitzungskeks gesetzt", "notizmappe" in a.cookies)
pruefe("Keks ist HttpOnly und SameSite=Strict",
       "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower(),
       r.headers["set-cookie"])
pruefe("Lokaler Keks endet mit dem Fenster", "max-age" not in r.headers["set-cookie"].lower())
pruefe("Mit Keks weiter offen", a.get("/api/baum").status_code == 200)
b = neu()
pruefe("Ohne Keks gesperrt (401)", b.get("/api/baum").status_code == 401)
pruefe("Startseite leitet zur Anmeldung", b.get("/", follow_redirects=False).headers.get("location") == "/anmelden")
pruefe("Anmeldeseite fragt nur nach dem Passwort",
       'name="name"' not in b.get("/anmelden").text and 'name="passwort"' in b.get("/anmelden").text)
pruefe("Status antwortet auch gesperrt", b.get("/api/status").status_code == 200)
pruefe("Statik bleibt erreichbar", b.get("/static/stil.css").status_code == 200)
pruefe("Falsches Passwort abgelehnt", b.post("/api/anmelden", json={"passwort": "falsch!!"}).status_code == 400)
pruefe("Richtiges Passwort ohne Namen genuegt",
       b.post("/api/anmelden", json={"passwort": "geheim123"}).status_code == 200)
pruefe("Danach offen", b.get("/api/baum").status_code == 200)
b.post("/api/abmelden")
pruefe("Abmelden sperrt wieder", b.get("/api/baum").status_code == 401)

# Bremse gegen Raten
c = neu()
for _ in range(5):
    c.post("/api/anmelden", json={"passwort": "falsch!!"})
r = c.post("/api/anmelden", json={"passwort": "geheim123"})
pruefe("Nach 5 Fehlversuchen gebremst - auch mit richtigem Passwort", r.status_code == 400 and "warten" in r.text, r.text)
konten._fehlversuche.clear()
for i in range(16):
    TestClient(main.app, client=(f"10.1.0.{i}", 1)).post("/api/anmelden", json={"passwort": "falsch!!"})
r = neu().post("/api/anmelden", json={"passwort": "geheim123"})
pruefe("Wechselnde Absender helfen beim Raten nicht", r.status_code == 400 and "warten" in r.text, r.text)
konten._fehlversuche.clear()

pruefe("Sperrzeit einstellbar", a.post("/api/sperre/zeit", json={"minuten": 5}).json()["sperre_minuten"] == 5)
pruefe("Ich-Abfrage kennt die Sperrzeit", a.get("/api/ich").json()["sperre_minuten"] == 5)
pruefe("Fremde Seite kann nichts aendern (Origin)",
       a.post("/api/notizbuch", json={"name": "X"}, headers={"origin": "https://boese.example"}).status_code == 403)
pruefe("Eigene Herkunft darf", a.post("/api/notizbuch", json={"name": "Privat"},
                                      headers={"origin": "http://testserver"}).status_code == 200)
pruefe("Konten liegen nicht im Datenordner", not list(DATEN.rglob("konten.json")))
pruefe("Konten-Datei nur fuer den Besitzer lesbar", (KONFIG / "konten.json").stat().st_mode & 0o077 == 0)
pruefe("Kein Klartext-Passwort in der Datei", "geheim123" not in (KONFIG / "konten.json").read_text())
pruefe("Sperre aus braucht das Passwort",
       a.post("/api/sperre/aus", json={"passwort": "falsch!!"}).status_code == 400)
pruefe("Sperre aus", a.post("/api/sperre/aus", json={"passwort": "geheim123"}).status_code == 200)
pruefe("Danach wieder offen", neu().get("/api/baum").status_code == 200)

# --- Server-Betrieb -------------------------------------------------------------
print("--- Server-Betrieb ---")
os.environ["NOTIZMAPPE_SERVER"] = "1"
gast = neu(False)
pruefe("Ohne Konto trotzdem gesperrt", gast.get("/api/baum").status_code == 401)
seite = gast.get("/anmelden").text
pruefe("Anmeldeseite zeigt die Einrichtung", 'name="code"' in seite)
code = konten.einrichtungscode()
pruefe("Einrichtungscode erzeugt", bool(code))
pruefe("Falscher Code abgelehnt", gast.post("/api/einrichten", json={
    "code": "falsch", "name": "admin", "passwort": "adminpass1"}).status_code == 400)
konten._fehlversuche.clear()
r = gast.post("/api/einrichten", json={"code": code, "name": "Lucy", "passwort": "adminpass1"})
pruefe("Erstes Konto mit Code angelegt", r.status_code == 200, r.text)
pruefe("Server-Keks bleibt 30 Tage", "max-age=2592000" in r.headers["set-cookie"].lower(), r.headers["set-cookie"])
pruefe("Code danach verbraucht", konten.einrichtungscode() is None)
pruefe("Zweite Einrichtung abgelehnt", neu(False).post("/api/einrichten", json={
    "code": code, "name": "boese", "passwort": "boesepass1"}).status_code == 400)
admin = gast
pruefe("Updates im Server-Betrieb gesperrt", admin.post("/api/update").status_code == 403)
pruefe("Ordner im Server-Betrieb nicht umstellbar", neu(True).post("/api/ordner", json={"ordner": "/tmp"}).status_code in (401, 403))
pruefe("Ordner-Dialog im Server-Betrieb gesperrt", admin.post("/api/ordner/waehlen").status_code == 403)

pruefe("Admin legt Konto an", admin.post("/api/konten", json={"name": "Ben", "passwort": "benpass12"}).status_code == 200)
pruefe("Doppelter Name abgelehnt", admin.post("/api/konten", json={"name": "ben", "passwort": "benpass12"}).status_code == 400)
pruefe("Unsinniger Name abgelehnt", admin.post("/api/konten", json={"name": "../x", "passwort": "benpass12"}).status_code == 400)
admin.post("/api/notizbuch", json={"name": "Projekt A"})
admin.post("/api/notizbuch", json={"name": "Projekt B"})
admin.post("/api/abschnitt", json={"notizbuch": "Projekt B", "name": "Intern"})
seite_b = admin.post("/api/seite", json={"notizbuch": "Projekt B", "abschnitt": "Intern", "titel": "Geheim"}).json()["name"]

ben = neu(False)
pruefe("Ben meldet sich an", ben.post("/api/anmelden", json={"name": "Ben", "passwort": "benpass12"}).status_code == 200)
pruefe("Ben sieht ohne Freigabe nichts",
       [b["name"] for b in ben.get("/api/baum").json()["notizbuecher"]] == [])
pruefe("Ben darf keine Konten verwalten", ben.get("/api/konten").status_code == 403)
r = admin.post("/api/zugriff", json={"notizbuch": "Projekt A", "mitglieder": ["Ben", "Gibtsnicht"]})
pruefe("Freigabe gesetzt, Unbekannte verworfen", r.json()["mitglieder"] == ["Ben"], r.text)
pruefe("Ben sieht genau Projekt A",
       [b["name"] for b in ben.get("/api/baum").json()["notizbuecher"]] == ["Projekt A"])
pruefe("Ben kann Projekt B nicht lesen (404)", ben.get("/api/seite", params={
    "notizbuch": "Projekt B", "abschnitt": "Intern", "name": seite_b}).status_code == 404)
pruefe("Ben kann in Projekt B nichts anlegen",
       ben.post("/api/abschnitt", json={"notizbuch": "Projekt B", "name": "X"}).status_code == 404)
pruefe("Ben kann Projekt B nicht beschreiben", ben.put("/api/seite", json={
    "notizbuch": "Projekt B", "abschnitt": "Intern", "name": seite_b, "rev": 1, "elemente": []}).status_code == 404)
pruefe("Ben kann nichts in Projekt B hochladen", ben.post("/api/anhang", data={
    "notizbuch": "Projekt B", "abschnitt": "Intern", "name": seite_b},
    files={"datei": ("a.txt", b"x", "text/plain")}).status_code == 404)
pruefe("Ben kann Projekt B nicht loeschen",
       ben.post("/api/loeschen", json={"art": "notizbuch", "pfad": ["Projekt B"]}).status_code == 404)
pruefe("Ben darf ein ganzes Projekt nicht loeschen",
       ben.post("/api/loeschen", json={"art": "notizbuch", "pfad": ["Projekt A"]}).status_code == 403)
pruefe("Ben arbeitet in Projekt A",
       ben.post("/api/abschnitt", json={"notizbuch": "Projekt A", "name": "Ideen"}).status_code == 200)
r = ben.post("/api/notizbuch", json={"name": "Bens Buch"})
pruefe("Eigenes Notizbuch: Ben ist Mitglied",
       "Bens Buch" in [b["name"] for b in ben.get("/api/baum").json()["notizbuecher"]], r.text)
pruefe("Ben sieht keinen Datenordner-Pfad", ben.get("/api/einstellungen").json()["ordner"] == "")

g = neu(False)
r = g.post("/api/geraet", json={"name": "Ben", "passwort": "benpass12", "geraet": "Laptop"})
pruefe("Geraeteschluessel ausgegeben", r.status_code == 200 and r.json().get("token"), r.text)
token = r.json()["token"]
pruefe("Geraeteschluessel allein oeffnet die API nicht", g.get("/api/baum").status_code == 401)
r = g.post("/geraet/anmelden", data={"token": token}, headers={"origin": "http://127.0.0.1:8099"})
pruefe("Geraeteschluessel gibt Sitzung im Fenster", r.status_code == 200 and "notizmappe" in g.cookies, r.text[:200])
pruefe("Fenster sieht Bens Projekte", g.get("/api/baum").status_code == 200)
pruefe("Normale Sitzung taugt nicht als Geraeteschluessel",
       neu(False).post("/geraet/anmelden", data={"token": g.cookies.get("notizmappe")}).status_code == 401)
pruefe("Geraet in der Liste", [d["geraet"] for d in ben.get("/api/ich").json()["geraete"]] == ["Laptop"])

admin.post("/api/konten/passwort", json={"name": "Ben", "passwort": "neuespass1"})
pruefe("Passwort neu: Bens Sitzungen enden", ben.get("/api/baum").status_code == 401)
pruefe("Passwort neu: Geraeteschluessel ungueltig",
       neu(False).post("/geraet/anmelden", data={"token": token}).status_code == 401)
pruefe("Letzter Admin kann nicht weg", admin.post("/api/konten/admin", json={"name": "Lucy", "admin": False}).status_code == 400)
pruefe("Eigenes Konto nicht loeschbar", admin.post("/api/konten/loeschen", json={"name": "Lucy"}).status_code == 400)
pruefe("Konto loeschen", admin.post("/api/konten/loeschen", json={"name": "Ben"}).status_code == 200)
pruefe("Geloeschtes Konto kommt nicht rein",
       neu(False).post("/api/anmelden", json={"name": "Ben", "passwort": "neuespass1"}).status_code == 400)

os.environ.pop("NOTIZMAPPE_SERVER")
print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
shutil.rmtree(DATEN, ignore_errors=True)
shutil.rmtree(KONFIG, ignore_errors=True)
sys.exit(1 if fehler else 0)
