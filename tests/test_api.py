"""API am Stück durchfahren: anlegen, schreiben, Anhänge, Konflikt, Angriffe.

    .venv/bin/python tests/test_api.py

Läuft gegen eine Wegwerf-Ablage unter /tmp, fasst echte Notizen nicht an.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DATEN = Path(tempfile.mkdtemp(prefix="notizen-test-"))
os.environ["NOTIZEN_ORDNER"] = str(DATEN)
os.environ["NOTIZMAPPE_QUELLE"] = "http://127.0.0.1:1"      # kein echtes GitHub im Test
sys.path.insert(0, str(WURZEL / "app"))

from fastapi.testclient import TestClient
import main

k = TestClient(main.app)
fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


# --- Oberfläche wirklich rendern, nicht nur die Vorlage parsen ---------------
a = k.get("/")
pruefe("Startseite rendert", a.status_code == 200, a.text[:300])
for stueck in ['id="flaeche"', 'id="baum"', '/static/mappe.js', '/static/stil.css', 'id="titel"', 'id="anhang"']:
    pruefe(f"Startseite enthaelt {stueck}", stueck in a.text)
pruefe("stil.css wird geliefert", k.get("/static/stil.css").status_code == 200)
pruefe("mappe.js wird geliefert", k.get("/static/mappe.js").status_code == 200)

# --- Baum --------------------------------------------------------------------
pruefe("Baum anfangs leer", k.get("/api/baum").json()["notizbuecher"] == [])
buch = k.post("/api/notizbuch", json={"name": "Arbeit"}).json()["name"]
absch = k.post("/api/abschnitt", json={"notizbuch": buch, "name": "Projekte"}).json()["name"]
seite = k.post("/api/seite", json={"notizbuch": buch, "abschnitt": absch, "titel": "Phobos"}).json()["name"]
pruefe("Namen sauber", (buch, absch, seite) == ("Arbeit", "Projekte", "Phobos"), (buch, absch, seite))
pruefe("Datei liegt am richtigen Platz", (DATEN / "Arbeit/Projekte/Phobos.json").is_file())
baum = k.get("/api/baum").json()["notizbuecher"]
pruefe("Baum zeigt die Seite", baum[0]["abschnitte"][0]["seiten"][0]["titel"] == "Phobos", baum)
z = k.post("/api/seite", json={"notizbuch": buch, "abschnitt": absch, "titel": "Phobos"}).json()["name"]
pruefe("Zweite Seite gleichen Titels bekommt eigenen Dateinamen", z == "Phobos (2)", z)

# --- Schreiben ---------------------------------------------------------------
s = k.get("/api/seite", params={"notizbuch": buch, "abschnitt": absch, "name": seite}).json()
pruefe("Neue Seite hat rev 1 und keine Elemente", s["rev"] == 1 and s["elemente"] == [], s)

r = k.put("/api/seite", json={
    "notizbuch": buch, "abschnitt": absch, "name": seite, "rev": 1, "titel": "Phobos", "geraet": "pc1",
    "elemente": [
        {"id": "a1", "typ": "text", "x": 40, "y": 60, "b": 400, "html": "<p>Hallo <b>Welt</b></p>"},
        {"id": "a2", "typ": "text", "x": 500, "y": 60, "b": 300,
         "html": '<p onclick="boese()">Text</p><script>alert(1)</script><img src=x onerror=alert(1)>'},
    ]})
pruefe("Speichern geht", r.status_code == 200, r.text)
pruefe("rev zaehlt hoch", r.json()["rev"] == 2, r.json())

s = k.get("/api/seite", params={"notizbuch": buch, "abschnitt": absch, "name": seite}).json()
pruefe("Zwei Elemente gespeichert", len(s["elemente"]) == 2, s["elemente"])
pruefe("Formatierung bleibt", s["elemente"][0]["html"] == "<p>Hallo <b>Welt</b></p>", s["elemente"][0])
boese = s["elemente"][1]["html"]
pruefe("script weg", "<script" not in boese, boese)
pruefe("onclick weg", "onclick" not in boese, boese)
pruefe("img weg", "<img" not in boese, boese)
pruefe("Text bleibt", "Text" in boese, boese)
pruefe("Nichts Boeses in der Datei", "onerror" not in (DATEN / "Arbeit/Projekte/Phobos.json").read_text())

# --- Konflikt ----------------------------------------------------------------
r = k.put("/api/seite", json={"notizbuch": buch, "abschnitt": absch, "name": seite, "rev": 1,
                              "titel": "Phobos", "geraet": "handy", "elemente": []})
pruefe("Alte rev wird abgelehnt (409)", r.status_code == 409, r.status_code)
pruefe("409 liefert die aktuelle Fassung mit", r.json().get("aktuell", {}).get("rev") == 2, r.json())
s = k.get("/api/seite", params={"notizbuch": buch, "abschnitt": absch, "name": seite}).json()
pruefe("Nichts ueberschrieben", len(s["elemente"]) == 2, s["elemente"])

st = k.get("/api/stand", params={"notizbuch": buch, "abschnitt": absch, "name": seite}).json()
pruefe("Stand meldet rev und Geraet", st["da"] and st["rev"] == 2 and st["geraet"] == "pc1", st)
pruefe("Stand bei unbekannter Seite",
       k.get("/api/stand", params={"notizbuch": buch, "abschnitt": absch, "name": "gibtsnicht"}).json() == {"da": False})

# --- Grenzen und Angriffe ----------------------------------------------------
for schlecht in ["../../etc", "..", ".versteckt", "a/b", "a\\b", ""]:
    r = k.get("/api/seite", params={"notizbuch": schlecht, "abschnitt": absch, "name": seite})
    pruefe(f"Pfad {schlecht!r} abgelehnt", r.status_code in (400, 422), r.status_code)
pruefe("Anlegen ausserhalb abgelehnt",
       k.post("/api/seite", json={"notizbuch": "../..", "abschnitt": "x", "titel": "y"}).status_code == 400)
r = k.post("/api/notizbuch", json={"name": "../flucht"})
pruefe("Notizbuch '../flucht' landet im Datenordner", r.status_code == 200 and "/" not in r.json()["name"], r.text)
pruefe("Kein Ordner ausserhalb entstanden", not (DATEN.parent / "flucht").exists())

r = k.put("/api/seite", json={"notizbuch": buch, "abschnitt": absch, "name": seite, "rev": 2, "titel": "Phobos",
                              "elemente": [{"id": str(i), "typ": "text", "html": "x"} for i in range(600)]})
pruefe("Zu viele Elemente abgelehnt", r.status_code == 400, r.status_code)
r = k.put("/api/seite", json={"notizbuch": buch, "abschnitt": absch, "name": seite, "rev": 2, "titel": "Phobos",
                              "elemente": [{"id": "z", "typ": "text", "x": "NaN", "y": 1e30, "b": -5, "html": "x"}]})
pruefe("Unsinnige Koordinaten werden gerade gebogen", r.status_code == 200, r.text)
e = k.get("/api/seite", params={"notizbuch": buch, "abschnitt": absch, "name": seite}).json()["elemente"][0]
pruefe("x/y/b in sinnvollen Grenzen", e["x"] >= 0 and e["y"] <= 200000 and e["b"] >= 40, e)

# --- Umbenennen --------------------------------------------------------------
neu = k.post("/api/seite/titel", json={"notizbuch": buch, "abschnitt": absch, "name": seite,
                                       "titel": "Phobos v2"}).json()["name"]
pruefe("Datei umbenannt", neu == "Phobos v2" and (DATEN / "Arbeit/Projekte/Phobos v2.json").is_file(), neu)
pruefe("Alte Datei weg", not (DATEN / "Arbeit/Projekte/Phobos.json").exists())
s = k.get("/api/seite", params={"notizbuch": buch, "abschnitt": absch, "name": neu}).json()
pruefe("Inhalt nach Umbenennen noch da", len(s["elemente"]) == 1, s["elemente"])

# --- Konfliktkopie vom Sync --------------------------------------------------
shutil.copy(DATEN / "Arbeit/Projekte/Phobos v2.json",
            DATEN / "Arbeit/Projekte/Phobos v2 (Konflikt-Kopie 2026-10-08).json")
seiten = [p for b in k.get("/api/baum").json()["notizbuecher"] for a in b["abschnitte"] for p in a["seiten"]]
pruefe("Konfliktkopie ist als solche markiert", any(p["konflikt"] for p in seiten), seiten)
pruefe("Normale Seite nicht markiert", any(not p["konflikt"] for p in seiten))

# --- Anhänge -----------------------------------------------------------------
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(2)</script></svg>'


def hoch(dateiname, inhalt, seite_=None):
    return k.post("/api/anhang", data={"notizbuch": buch, "abschnitt": absch, "name": seite_ or neu},
                  files={"datei": (dateiname, inhalt, "application/octet-stream")})


r = hoch("Bild.png", PNG)
pruefe("Bild hochgeladen", r.status_code == 200, r.text)
pruefe("als Bild erkannt", r.json()["art"] == "bild" and r.json()["medientyp"] == "image/png", r.json())
pruefe("Datei liegt neben der Seite", (DATEN / f"Arbeit/Projekte/{neu}.anhang/Bild.png").is_file())

r = hoch("Zeichnung.svg", SVG)
pruefe("SVG gilt als Datei, nicht als Bild", r.status_code == 200 and r.json()["art"] == "datei", r.text)
svgname = r.json()["datei"]
pruefe("Zweites Bild gleichen Namens bekommt eigenen", hoch("Bild.png", PNG).json()["datei"] == "Bild (2).png")

a = k.get("/api/anhang", params={"notizbuch": buch, "abschnitt": absch, "name": neu, "datei": "Bild.png"})
pruefe("Bild kommt zurueck", a.status_code == 200 and a.content == PNG, a.status_code)
pruefe("Bild wird angezeigt (inline)", "inline" in a.headers.get("content-disposition", ""), dict(a.headers))
pruefe("Bild hat den echten Medientyp", a.headers["content-type"].startswith("image/png"), dict(a.headers))
pruefe("nosniff gesetzt", a.headers.get("x-content-type-options") == "nosniff", dict(a.headers))

a = k.get("/api/anhang", params={"notizbuch": buch, "abschnitt": absch, "name": neu, "datei": svgname})
pruefe("SVG wird heruntergeladen, nicht angezeigt", "attachment" in a.headers.get("content-disposition", ""), dict(a.headers))
pruefe("SVG nicht als image/svg ausgeliefert", "svg" not in a.headers["content-type"], dict(a.headers))

r = hoch("../../flucht.png", PNG)
pruefe("Pfad im Dateinamen entschaerft", r.status_code == 200 and "/" not in r.json()["datei"], r.text)
pruefe("Nichts ausserhalb gelandet", not (DATEN / "Arbeit/flucht.png").exists() and not (DATEN / "flucht.png").exists())
pruefe("Ausbruch beim Abruf abgelehnt",
       k.get("/api/anhang", params={"notizbuch": buch, "abschnitt": absch, "name": neu,
                                    "datei": "../../../etc/passwd"}).status_code == 400)
pruefe("Leere Datei abgelehnt", hoch("leer.txt", b"").status_code == 400)
pruefe("Zu grosse Datei abgelehnt (413)", hoch("riesig.bin", b"x" * (26 * 1024 * 1024)).status_code == 413)

s = k.get("/api/seite", params={"notizbuch": buch, "abschnitt": absch, "name": neu}).json()
r = k.put("/api/seite", json={
    "notizbuch": buch, "abschnitt": absch, "name": neu, "rev": s["rev"], "titel": s["titel"],
    "elemente": [
        {"id": "b1", "typ": "bild", "x": 10, "y": 10, "b": 300, "datei": "Bild.png", "beschriftung": "Bild.png"},
        {"id": "d1", "typ": "datei", "x": 10, "y": 400, "b": 280, "datei": svgname, "groesse": len(SVG)},
        {"id": "x1", "typ": "bild", "x": 0, "y": 0, "b": 100, "datei": "../../../etc/passwd"},
        {"id": "y1", "typ": "unsinn", "x": 0, "y": 0, "b": 100},
    ]})
pruefe("Seite mit Anhaengen gespeichert", r.status_code == 200, r.text)
arten = [(e["typ"], e.get("datei")) for e in
         k.get("/api/seite", params={"notizbuch": buch, "abschnitt": absch, "name": neu}).json()["elemente"]]
pruefe("Bild- und Dateielement bleiben", ("bild", "Bild.png") in arten and ("datei", svgname) in arten, arten)
pruefe("Ausbruchspfad im Element verworfen", not any("passwd" in str(d) for _, d in arten), arten)
pruefe("Unbekannte Art verworfen", all(t in {"bild", "datei", "text"} for t, _ in arten), arten)
pruefe("Verwaiste Dateien aufgeraeumt", r.json()["aufgeraeumt"] == 2, r.json())
pruefe("Benutzte Datei ist noch da", (DATEN / f"Arbeit/Projekte/{neu}.anhang/Bild.png").is_file())
pruefe("Unbenutzte im Papierkorb", any("Bild (2)" in p.name for p in (DATEN / ".papierkorb").glob("*")))

neu2 = k.post("/api/seite/titel", json={"notizbuch": buch, "abschnitt": absch, "name": neu,
                                        "titel": "Mit Bildern"}).json()["name"]
pruefe("Anhangsordner umbenannt", (DATEN / f"Arbeit/Projekte/{neu2}.anhang/Bild.png").is_file(), neu2)
pruefe("Alter Anhangsordner weg", not (DATEN / f"Arbeit/Projekte/{neu}.anhang").exists())
pruefe("Bild nach dem Umbenennen abrufbar",
       k.get("/api/anhang", params={"notizbuch": buch, "abschnitt": absch, "name": neu2,
                                    "datei": "Bild.png"}).status_code == 200)
neu = neu2

# --- Update-Routen: lesen darf jeder, anstossen nur von diesem Rechner --------
# Der Testclient meldet sich als "testclient", nicht als 127.0.0.1 - genau wie ein
# fremder Rechner im Netz. Dass er abgewiesen wird, ist der Sinn der Pruefung.
v = k.get("/api/version")
pruefe("Version abfragbar", v.status_code == 200 and "installiert" in v.json(), v.text)
pruefe("ohne GitHub kein Update angeboten", v.json()["neuer"] is False, v.json())
pruefe("Quellordner meldet nicht aktualisierbar", v.json()["aktualisierbar"] is False, v.json())
pruefe("Update von fremder Adresse abgelehnt (403)", k.post("/api/update").status_code == 403)
pruefe("Update-Protokoll von fremder Adresse abgelehnt", k.get("/api/update/stand").status_code == 403)

# --- Einstellungen zum Update ------------------------------------------------
e = k.get("/api/einstellungen")
pruefe("Einstellungen abfragbar", e.status_code == 200 and "ordner" in e.json(), e.text)
pruefe("Optionen dabei", e.json()["optionen"]["beim_start_pruefen"] is True, e.json())
pruefe("automatisch einspielen ist aus", e.json()["optionen"]["automatisch_einspielen"] is False, e.json())
pruefe("fremde Adresse darf Optionen nicht setzen",
       k.post("/api/einstellungen", json={"automatisch_einspielen": True}).status_code == 403)
pruefe("Optionen danach unveraendert",
       k.get("/api/einstellungen").json()["optionen"]["automatisch_einspielen"] is False)

# --- Löschen -----------------------------------------------------------------
r = k.post("/api/loeschen", json={"art": "seite", "pfad": [buch, absch, neu]})
pruefe("Seite geloescht", r.status_code == 200, r.text)
pruefe("Seite wirklich weg", not (DATEN / f"Arbeit/Projekte/{neu}.json").exists())
korb = list((DATEN / ".papierkorb").glob("*"))
pruefe("Im Papierkorb angekommen", any(p.name.endswith(".json") for p in korb), [p.name for p in korb])
pruefe("Anhangsordner mit in den Papierkorb", any(p.name.endswith(".anhang") and p.is_dir() for p in korb),
       [p.name for p in korb])
pruefe("Anhangsordner nicht mehr beim Abschnitt", not list((DATEN / "Arbeit/Projekte").glob("*.anhang")))
pruefe("Papierkorb taucht nicht im Baum auf",
       all(b["name"] != ".papierkorb" for b in k.get("/api/baum").json()["notizbuecher"]))
pruefe("Loeschen mit falscher Pfadlaenge abgelehnt",
       k.post("/api/loeschen", json={"art": "seite", "pfad": [buch, absch]}).status_code == 400)
pruefe("Notizbuch geloescht",
       k.post("/api/loeschen", json={"art": "notizbuch", "pfad": [buch]}).status_code == 200
       and not (DATEN / "Arbeit").exists())

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
shutil.rmtree(DATEN, ignore_errors=True)
sys.exit(1 if fehler else 0)
