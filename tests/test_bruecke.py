"""Die Brücke am Stück durchfahren: anlegen, schreiben, Anhänge, Konflikt, Angriffe.

    .venv/bin/python tests/test_bruecke.py

Läuft gegen eine Wegwerf-Ablage unter /tmp, fasst echte Notizen nicht an. Es gibt
keinen Server mehr - die Oberfläche ruft genau diese Methoden auf.
"""
import base64
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DATEN = Path(tempfile.mkdtemp(prefix="notizen-test-"))
KONFIG = Path(tempfile.mkdtemp(prefix="notizen-konfig-"))
os.environ["NOTIZEN_ORDNER"] = str(DATEN)
os.environ["NOTIZMAPPE_KONFIG"] = str(KONFIG)
os.environ["NOTIZMAPPE_OPTIONEN"] = str(KONFIG / "optionen.json")
os.environ["NOTIZMAPPE_QUELLE"] = "http://127.0.0.1:1"      # kein echtes GitHub im Test
sys.path.insert(0, str(WURZEL / "app"))

import bruecke as bruecke_modul
import speicher

b = bruecke_modul.Bruecke()
fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


def b64(daten: bytes) -> str:
    return base64.b64encode(daten).decode("ascii")


# --- Die Oberfläche liegt als Datei bereit, nicht hinter einer Adresse -------
seite = WURZEL / "app/oberflaeche/index.html"
pruefe("Oberflaeche vorhanden", seite.is_file(), seite)
html = seite.read_text(encoding="utf-8")
for stueck in ['id="flaeche"', 'id="baum"', 'mappe.js', 'stil.css', 'id="titel"', 'id="anhang"']:
    pruefe(f"Oberflaeche enthaelt {stueck}", stueck in html)
pruefe("keine Jinja-Platzhalter mehr", "{{" not in html and "{%" not in html)
pruefe("keine Serveradressen in der Seite", "/static/" not in html and "127.0.0.1" not in html)
js = (WURZEL / "app/oberflaeche/mappe.js").read_text(encoding="utf-8")
pruefe("Oberflaeche ruft die Bruecke", "pywebview.api" in js)
pruefe("kein fetch mehr in der Oberflaeche", "fetch(" not in js)

# --- Baum --------------------------------------------------------------------
pruefe("Baum anfangs leer", b.baum()["notizbuecher"] == [])
buch = b.notizbuch_anlegen("Arbeit")["name"]
absch = b.abschnitt_anlegen(buch, "Projekte")["name"]
s1 = b.seite_anlegen(buch, absch, "Phobos")["name"]
pruefe("Namen sauber", (buch, absch, s1) == ("Arbeit", "Projekte", "Phobos"), (buch, absch, s1))
pruefe("Datei liegt am richtigen Platz", (DATEN / "Arbeit/Projekte/Phobos.json").is_file())
baum = b.baum()["notizbuecher"]
pruefe("Baum zeigt die Seite", baum[0]["abschnitte"][0]["seiten"][0]["titel"] == "Phobos", baum)
pruefe("Zweite Seite gleichen Titels bekommt eigenen Dateinamen",
       b.seite_anlegen(buch, absch, "Phobos")["name"] == "Phobos (2)")
pruefe("Name fehlt wird gemeldet", "fehler" in b.notizbuch_anlegen(""))

# --- Schreiben ---------------------------------------------------------------
s = b.seite_lesen(buch, absch, s1)
pruefe("Neue Seite hat rev 1 und keine Elemente", s["rev"] == 1 and s["elemente"] == [], s)

r = b.seite_speichern({
    "notizbuch": buch, "abschnitt": absch, "name": s1, "rev": 1, "titel": "Phobos", "geraet": "pc1",
    "elemente": [
        {"id": "a1", "typ": "text", "x": 40, "y": 60, "b": 400, "html": "<p>Hallo <b>Welt</b></p>"},
        {"id": "a2", "typ": "text", "x": 500, "y": 60, "b": 300,
         "html": '<p onclick="boese()">Text</p><script>alert(1)</script><img src=x onerror=alert(1)>'},
    ]})
pruefe("Speichern geht", "fehler" not in r, r)
pruefe("rev zaehlt hoch", r["rev"] == 2, r)

s = b.seite_lesen(buch, absch, s1)
pruefe("Zwei Elemente gespeichert", len(s["elemente"]) == 2, s["elemente"])
pruefe("Formatierung bleibt", s["elemente"][0]["html"] == "<p>Hallo <b>Welt</b></p>", s["elemente"][0])
boese = s["elemente"][1]["html"]
for was, bedingung in [("script weg", "<script" not in boese), ("onclick weg", "onclick" not in boese),
                       ("img ohne Anhang weg", "<img" not in boese), ("Text bleibt", "Text" in boese)]:
    pruefe(was, bedingung, boese)
pruefe("Nichts Boeses in der Datei", "onerror" not in (DATEN / "Arbeit/Projekte/Phobos.json").read_text())

# --- Konflikt ----------------------------------------------------------------
r = b.seite_speichern({"notizbuch": buch, "abschnitt": absch, "name": s1, "rev": 1,
                       "titel": "Phobos", "geraet": "handy", "elemente": []})
pruefe("Alte rev wird abgelehnt", r.get("art") == "konflikt", r)
pruefe("Konflikt liefert die aktuelle Fassung mit", r.get("aktuell", {}).get("rev") == 2, r)
pruefe("Nichts ueberschrieben", len(b.seite_lesen(buch, absch, s1)["elemente"]) == 2)

st = b.stand(buch, absch, s1)
pruefe("Stand meldet rev und Geraet", st["da"] and st["rev"] == 2 and st["geraet"] == "pc1", st)
pruefe("Stand bei unbekannter Seite", b.stand(buch, absch, "gibtsnicht") == {"da": False})

# --- Grenzen und Angriffe ----------------------------------------------------
for schlecht in ["../../etc", "..", ".versteckt", "a/b", "a\\b", ""]:
    pruefe(f"Pfad {schlecht!r} abgelehnt", "fehler" in b.seite_lesen(schlecht, absch, s1))
pruefe("Anlegen ausserhalb abgelehnt", "fehler" in b.seite_anlegen("../..", "x", "y"))
r = b.notizbuch_anlegen("../flucht")
pruefe("Notizbuch '../flucht' landet im Datenordner", "fehler" not in r and "/" not in r["name"], r)
pruefe("Kein Ordner ausserhalb entstanden", not (DATEN.parent / "flucht").exists())

r = b.seite_speichern({"notizbuch": buch, "abschnitt": absch, "name": s1, "rev": 2, "titel": "Phobos",
                       "elemente": [{"id": str(i), "typ": "text", "html": "x"} for i in range(600)]})
pruefe("Zu viele Elemente abgelehnt", "fehler" in r, r)
r = b.seite_speichern({"notizbuch": buch, "abschnitt": absch, "name": s1, "rev": 2, "titel": "Phobos",
                       "elemente": [{"id": "z", "typ": "text", "x": "NaN", "y": 1e30, "b": -5, "html": "x"}]})
pruefe("Unsinnige Koordinaten werden gerade gebogen", "fehler" not in r, r)
e = b.seite_lesen(buch, absch, s1)["elemente"][0]
pruefe("x/y/b in sinnvollen Grenzen", e["x"] >= 0 and e["y"] <= 200000 and e["b"] >= 40, e)

# --- Umbenennen --------------------------------------------------------------
neu = b.seite_umbenennen(buch, absch, s1, "Phobos v2")["name"]
pruefe("Datei umbenannt", neu == "Phobos v2" and (DATEN / "Arbeit/Projekte/Phobos v2.json").is_file(), neu)
pruefe("Alte Datei weg", not (DATEN / "Arbeit/Projekte/Phobos.json").exists())
pruefe("Inhalt nach Umbenennen noch da", len(b.seite_lesen(buch, absch, neu)["elemente"]) == 1)

# --- Schrift, Farben, Hervorhebung ------------------------------------------
s2 = b.seite_lesen(buch, absch, neu)
r = b.seite_speichern({
    "notizbuch": buch, "abschnitt": absch, "name": neu, "rev": s2["rev"], "titel": s2["titel"],
    "elemente": [{"id": "f1", "typ": "text", "x": 0, "y": 0, "b": 400,
                  "html": '<font size="5" face="Georgia, serif">gross und serif</font>'
                          '<font size="99">unsinnige Groesse</font>'
                          '<font face="boese; position:fixed">fremde Schrift</font>'
                          '<font color="#b23b2e">rot</font><mark>wichtig</mark>'
                          '<font color="#123456">fremde Farbe</font>'
                          '<mark onclick="boese()">mit Angriff</mark>'}]})
pruefe("Mit Auszeichnung gespeichert", "fehler" not in r, r)
h = b.seite_lesen(buch, absch, neu)["elemente"][0]["html"]
for was, bedingung in [
    ("Groesse bleibt", 'size="5"' in h), ("Schriftart bleibt", 'face="Georgia, serif"' in h),
    ("Farbe aus der Palette bleibt", 'color="#b23b2e"' in h),
    ("Hervorhebung bleibt", "<mark>wichtig</mark>" in h),
    ("Unsinnige Groesse weg", 'size="99"' not in h), ("Fremde Schriftart weg", "position:fixed" not in h),
    ("Fremde Farbe weg", "#123456" not in h), ("onclick an der Hervorhebung weg", "onclick" not in h),
    ("Text bleibt trotzdem stehen", "gross und serif" in h and "fremde Schrift" in h),
]:
    pruefe(was, bedingung, h)

# --- Konfliktkopie vom Sync --------------------------------------------------
shutil.copy(DATEN / "Arbeit/Projekte/Phobos v2.json",
            DATEN / "Arbeit/Projekte/Phobos v2 (Konflikt-Kopie 2026-10-08).json")
seiten = [p for bu in b.baum()["notizbuecher"] for a in bu["abschnitte"] for p in a["seiten"]]
pruefe("Konfliktkopie ist als solche markiert", any(p["konflikt"] for p in seiten), seiten)
pruefe("Normale Seite nicht markiert", any(not p["konflikt"] for p in seiten))

# --- Anhänge -----------------------------------------------------------------
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(2)</script></svg>'

r = b.anhang_ablegen(buch, absch, neu, "Bild.png", b64(PNG))
pruefe("Bild abgelegt", "fehler" not in r and r["art"] == "bild", r)
pruefe("Datei liegt neben der Seite", (DATEN / f"Arbeit/Projekte/{neu}.anhang/Bild.png").is_file())
r2 = b.anhang_ablegen(buch, absch, neu, "Zeichnung.svg", b64(SVG))
pruefe("SVG gilt als Datei, nicht als Bild", r2["art"] == "datei", r2)
svgname = r2["datei"]
pruefe("Zweites Bild gleichen Namens bekommt eigenen",
       b.anhang_ablegen(buch, absch, neu, "Bild.png", b64(PNG))["datei"] == "Bild (2).png")

r = b.anhang_bild(buch, absch, neu, "Bild.png")
pruefe("Bilddaten kommen zurueck", r.get("medientyp") == "image/png" and base64.b64decode(r["daten"]) == PNG, r)
pruefe("SVG wird nicht als Bild ausgeliefert", "fehler" in b.anhang_bild(buch, absch, neu, svgname))

r = b.anhang_ablegen(buch, absch, neu, "../../flucht.png", b64(PNG))
pruefe("Pfad im Dateinamen entschaerft", "fehler" not in r and "/" not in r["datei"], r)
pruefe("Nichts ausserhalb gelandet", not (DATEN / "Arbeit/flucht.png").exists())
pruefe("Ausbruch beim Lesen abgelehnt", "fehler" in b.anhang_bild(buch, absch, neu, "../../../etc/passwd"))
pruefe("Leere Datei abgelehnt", "fehler" in b.anhang_ablegen(buch, absch, neu, "leer.txt", ""))
pruefe("Zu grosse Datei abgelehnt",
       "fehler" in b.anhang_ablegen(buch, absch, neu, "riesig.bin", b64(b"x" * (26 * 1024 * 1024))))

s3 = b.seite_lesen(buch, absch, neu)
r = b.seite_speichern({
    "notizbuch": buch, "abschnitt": absch, "name": neu, "rev": s3["rev"], "titel": s3["titel"],
    "elemente": [
        {"id": "b1", "typ": "bild", "x": 10, "y": 10, "b": 300, "datei": "Bild.png", "beschriftung": "Bild.png"},
        {"id": "d1", "typ": "datei", "x": 10, "y": 400, "b": 280, "datei": svgname, "groesse": len(SVG)},
        {"id": "x1", "typ": "bild", "x": 0, "y": 0, "b": 100, "datei": "../../../etc/passwd"},
        {"id": "y1", "typ": "unsinn", "x": 0, "y": 0, "b": 100},
    ]})
pruefe("Seite mit Anhaengen gespeichert", "fehler" not in r, r)
arten = [(e["typ"], e.get("datei")) for e in b.seite_lesen(buch, absch, neu)["elemente"]]
pruefe("Bild- und Dateielement bleiben", ("bild", "Bild.png") in arten and ("datei", svgname) in arten, arten)
pruefe("Ausbruchspfad im Element verworfen", not any("passwd" in str(d) for _, d in arten), arten)
pruefe("Unbekannte Art verworfen", all(t in {"bild", "datei", "text"} for t, _ in arten), arten)
# Frisch Hochgeladenes bleibt zunaechst liegen: waehrend ein Bild hochlaedt, kann
# schon ein Speichern mit dem Stand davor unterwegs sein. Erst danach wird geraeumt.
pruefe("Frisches bleibt erst einmal liegen", r["aufgeraeumt"] == 0, r)
pruefe("Unbenutzte Datei noch da", (DATEN / f"Arbeit/Projekte/{neu}.anhang/Bild (2).png").is_file())

import time as _zeit
alt_genug = _zeit.time() - speicher.SCHONFRIST - 60
for datei in (DATEN / f"Arbeit/Projekte/{neu}.anhang").iterdir():
    os.utime(datei, (alt_genug, alt_genug))
s4 = b.seite_lesen(buch, absch, neu)
r = b.seite_speichern({"notizbuch": buch, "abschnitt": absch, "name": neu, "rev": s4["rev"],
                       "titel": s4["titel"], "elemente": s4["elemente"]})
pruefe("Verwaiste Dateien aufgeraeumt", r["aufgeraeumt"] == 2, r)
pruefe("Benutzte Datei ist noch da", (DATEN / f"Arbeit/Projekte/{neu}.anhang/Bild.png").is_file())
pruefe("Unbenutzte im Papierkorb", any("Bild (2)" in p.name for p in (DATEN / ".papierkorb").glob("*")))

neu2 = b.seite_umbenennen(buch, absch, neu, "Mit Bildern")["name"]
pruefe("Anhangsordner umbenannt", (DATEN / f"Arbeit/Projekte/{neu2}.anhang/Bild.png").is_file(), neu2)
pruefe("Bild nach dem Umbenennen abrufbar", "fehler" not in b.anhang_bild(buch, absch, neu2, "Bild.png"))
neu = neu2

# --- Einstellungen und Updates ----------------------------------------------
e = b.einstellungen()
pruefe("Einstellungen abfragbar", "ordner" in e and e["version"], e)
pruefe("Seitenzahl zaehlt nur Seiten", e["seiten"] == sum(
    len(a["seiten"]) for bu in b.baum()["notizbuecher"] for a in bu["abschnitte"]), e["seiten"])
pruefe("Optionen dabei", e["optionen"]["beim_start_pruefen"] is True, e)
pruefe("automatisch installieren ist aus", e["optionen"]["automatisch_einspielen"] is False, e)
pruefe("Optionen lassen sich setzen",
       b.optionen_setzen({"automatisch_einspielen": True})["automatisch_einspielen"] is True)
pruefe("und bleiben stehen", b.einstellungen()["optionen"]["automatisch_einspielen"] is True)
b.optionen_setzen({"automatisch_einspielen": False})

v = b.version()
pruefe("Version abfragbar", v["installiert"] == e["version"], v)
pruefe("ohne GitHub kein Update angeboten", v["neuer"] is False, v)
pruefe("Quellordner meldet nicht aktualisierbar", v["aktualisierbar"] is False, v)
pruefe("Update verweigert sich im Quellordner", "fehler" in b.update())

# --- Löschen -----------------------------------------------------------------
pruefe("Seite geloescht", "fehler" not in b.loeschen("seite", [buch, absch, neu]))
pruefe("Seite wirklich weg", not (DATEN / f"Arbeit/Projekte/{neu}.json").exists())
korb = list((DATEN / ".papierkorb").glob("*"))
pruefe("Im Papierkorb angekommen", any(p.name.endswith(".json") for p in korb), [p.name for p in korb])
pruefe("Anhangsordner mit in den Papierkorb", any(p.name.endswith(".anhang") and p.is_dir() for p in korb))
pruefe("Papierkorb taucht nicht im Baum auf",
       all(bu["name"] != ".papierkorb" for bu in b.baum()["notizbuecher"]))
pruefe("Loeschen mit falscher Pfadlaenge abgelehnt", "fehler" in b.loeschen("seite", [buch, absch]))
pruefe("Notizbuch geloescht",
       "fehler" not in b.loeschen("notizbuch", [buch]) and not (DATEN / "Arbeit").exists())

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
shutil.rmtree(DATEN, ignore_errors=True)
shutil.rmtree(KONFIG, ignore_errors=True)
sys.exit(1 if fehler else 0)
