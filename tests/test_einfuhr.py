"""Aus OneNote übernehmen: was ankommt und was gemeldet wird.

    .venv/bin/python tests/test_einfuhr.py

Eine echte .one-Datei lässt sich hier nicht herstellen - das Format ist zu
verwickelt, um es für einen Test nachzubauen. Geprüft wird deshalb alles
drumherum, und das ist der Teil, der schiefgehen kann:

* Erkennt das Programm, was es vor sich hat? (Kennung am Dateianfang)
* Wird aus Gelesenem ein richtiges Notizbuch - mit Seiten, Text und Anhängen?
* Bleiben vorhandene Notizen unangetastet?
* Und vor allem: wird gemeldet, was **nicht** gelesen werden konnte, statt es
  still zu verschlucken? Beim Umstieg darf nichts unbemerkt verloren gehen.

Das Auspacken von .onepkg wird an einem echten CAB-Archiv geprüft.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DATEN = Path(tempfile.mkdtemp(prefix="notizen-einfuhr-"))
KONFIG = Path(tempfile.mkdtemp(prefix="notizen-einfuhr-konfig-"))
os.environ["NOTIZEN_ORDNER"] = str(DATEN)
os.environ["NOTIZMAPPE_KONFIG"] = str(KONFIG)
os.environ["NOTIZMAPPE_OPTIONEN"] = str(KONFIG / "optionen.json")
os.environ["NOTIZMAPPE_QUELLE"] = "http://127.0.0.1:1"
sys.path.insert(0, str(WURZEL / "app"))

import bruecke as bruecke_modul
import einfuhr
import speicher

b = bruecke_modul.Bruecke()
fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


# --- Was ist das für eine Datei? ---------------------------------------------
print("Dateien erkennen")
tmp = Path(tempfile.mkdtemp(prefix="einfuhr-dateien-"))
(tmp / "text.one").write_bytes(b"nur Text, keine OneNote-Datei")
(tmp / "echt.one").write_bytes(einfuhr.KENNUNG_ONE + b"\x00" * 100)
(tmp / "inhalt.onetoc2").write_bytes(einfuhr.KENNUNG_TOC + b"\x00" * 100)
pruefe("Fremde Datei wird erkannt", einfuhr.art_von(tmp / "text.one") == "unbekannt")
pruefe("Abschnitt wird erkannt", einfuhr.art_von(tmp / "echt.one") == "one")
pruefe("Inhaltsverzeichnis wird erkannt", einfuhr.art_von(tmp / "inhalt.onetoc2") == "onetoc2")
pruefe("Paket wird an der Endung erkannt", einfuhr.art_von(tmp / "x.onepkg") == "onepkg")

for datei, erwartet in (("text.one", "keine OneNote-Datei"),
                        ("inhalt.onetoc2", "Inhaltsverzeichnis"),
                        ("echt.one", "kommt mit der Datei nicht zurecht")):
    try:
        einfuhr.abschnitt_lesen(tmp / datei)
        pruefe(f"{datei}: klare Meldung", False, "kein Fehler geworfen")
    except einfuhr.EinfuhrFehler as f:
        pruefe(f"{datei}: klare Meldung", erwartet in str(f), str(f))

# --- Ein echtes CAB-Paket ----------------------------------------------------
print("\n.onepkg auspacken")
try:
    import cabarchive
    archiv = cabarchive.CabArchive()
    archiv["Abschnitt A.one"] = cabarchive.CabFile(einfuhr.KENNUNG_ONE + b"\x00" * 64)
    archiv["Inhalt.onetoc2"] = cabarchive.CabFile(einfuhr.KENNUNG_TOC + b"\x00" * 64)
    (tmp / "buch.onepkg").write_bytes(archiv.save())
    teile = einfuhr.paket_lesen(tmp / "buch.onepkg")
    pruefe("Nur die Abschnitte werden herausgeholt", len(teile) == 1, [t["name"] for t in teile])
    pruefe("Ein klemmender Abschnitt kostet nicht das Paket",
           "fehler" in teile[0] and teile[0]["seiten"] == [], teile[0])
except ImportError:
    pruefe("cabarchive ist da", False, "fehlt")

leer = cabarchive.CabArchive()
leer["nichts.txt"] = cabarchive.CabFile(b"x")
(tmp / "leer.onepkg").write_bytes(leer.save())
try:
    einfuhr.paket_lesen(tmp / "leer.onepkg")
    pruefe("Paket ohne Abschnitt wird gemeldet", False)
except einfuhr.EinfuhrFehler as f:
    pruefe("Paket ohne Abschnitt wird gemeldet", "kein Abschnitt" in str(f), str(f))

# --- Aus Gelesenem ein Notizbuch ---------------------------------------------
print("\nNotizbuch anlegen")
vorher_buch = b.notizbuch_anlegen("Meins")["name"]
b.abschnitt_anlegen(vorher_buch, "Bleibt")

bild = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 40 + b"BILD"
gelesen = [
    {"name": "Arbeit", "anhaenge": [{"name": "abc.png", "inhalt": bild}],
     "seiten": [{"titel": "Montag", "texte": ["Erste Zeile\nZweite Zeile", "Zweiter Kasten"]},
                {"titel": "", "texte": ["Ohne Titel, erste Zeile wird genommen"]}]},
    {"name": "Kaputt", "anhaenge": [], "seiten": [], "fehler": "mit Passwort geschützt"},
]
bericht = einfuhr.anlegen("Aus OneNote", gelesen)
pruefe("Notizbuch angelegt", bericht["notizbuch"].startswith("Aus OneNote"), bericht)
pruefe("Beide Abschnitte angelegt", bericht["abschnitte"] == 2, bericht)
pruefe("Seiten angelegt (2 plus die Sammelseite)", bericht["seiten"] == 3, bericht)
pruefe("Anhang abgelegt", bericht["anhaenge"] == 1, bericht)
pruefe("Nicht Lesbares wird gemeldet, nicht verschluckt",
       any("Passwort" in u for u in bericht["uebersprungen"]), bericht)

buch = bericht["notizbuch"]
baum = {bu["name"]: bu for bu in b.baum()["notizbuecher"]}
pruefe("Das alte Notizbuch ist unangetastet", vorher_buch in baum)
seiten = {s["titel"] for a in baum[buch]["abschnitte"] for s in a["seiten"]}
pruefe("Seite mit Titel ist da", "Montag" in seiten, seiten)
pruefe("Seite ohne Titel bekam ihre erste Zeile",
       any(t.startswith("Ohne Titel") for t in seiten), seiten)
pruefe("Sammelseite für Dateien ist da", "Dateien aus OneNote" in seiten, seiten)

montag = next(s for a in baum[buch]["abschnitte"] for s in a["seiten"] if s["titel"] == "Montag")
abschnitt = next(a["name"] for a in baum[buch]["abschnitte"] for s in a["seiten"] if s["titel"] == "Montag")
inhalt = b.seite_lesen(buch, abschnitt, montag["name"])
pruefe("Zwei Textkästen auf der Seite", len(inhalt["elemente"]) == 2, inhalt["elemente"])
pruefe("Der Text ist angekommen", "Erste Zeile" in inhalt["elemente"][0]["html"], inhalt["elemente"][0])
pruefe("Zeilenumbruch wurde übernommen", "<br>" in inhalt["elemente"][0]["html"])
pruefe("Die Kästen überdecken sich nicht",
       inhalt["elemente"][1]["y"] > inhalt["elemente"][0]["y"] + 40, inhalt["elemente"])

# --- Text bleibt Text --------------------------------------------------------
print("\nSpitze Klammern im Text")
for roh, muss_drin in (("Die Klammer <b> in HTML", "&lt;b&gt;"),
                       ("<script>wichtig</script> Notiz", "wichtig"),
                       ("Preis < 5 & mehr", "&lt; 5 &amp; mehr")):
    html = einfuhr._elemente([roh])[0]["html"]
    pruefe("Text bleibt erhalten: " + roh[:24], muss_drin in html, html)
pruefe("Zeilenumbrüche werden zu <br>", "<br>" in einfuhr._elemente(["a\nb"])[0]["html"])
pruefe("Und es wird kein Markup daraus",
       "<b>" not in einfuhr._elemente(["Die Klammer <b> in HTML"])[0]["html"])

# --- Durch die Brücke --------------------------------------------------------
print("\nDurch die Brücke")
antwort = b.onenote_einlesen({"pfad": str(tmp / "text.one")})
pruefe("Fremde Datei: Meldung statt Absturz",
       "fehler" in antwort and "OneNote" in antwort["fehler"], antwort)
antwort = b.onenote_einlesen({"pfad": str(tmp / "gibtsnicht.one")})
pruefe("Fehlende Datei wird gemeldet", "fehler" in antwort, antwort)
antwort = b.onenote_einlesen({"pfad": str(tmp / "echt.one")})
pruefe("Unlesbare Datei: Meldung statt halbes Notizbuch", "fehler" in antwort, antwort)
pruefe("Und es wurde nichts angelegt",
       sum(1 for bu in b.baum()["notizbuecher"] if bu["name"].startswith("echt")) == 0)

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
shutil.rmtree(DATEN, ignore_errors=True)
shutil.rmtree(KONFIG, ignore_errors=True)
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fehler else 0)
