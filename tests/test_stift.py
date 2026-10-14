"""Striche vom Stift: was gespeichert wird und was nicht.

    .venv/bin/python tests/test_stift.py

Eine Zeichnung geht denselben Weg wie ein Textkasten - durch _elemente() in die
Seite. Hier wird geprüft, dass dabei nichts durchrutscht, was die Datei
aufbläht oder beim nächsten Öffnen Unsinn zeichnet, und dass eine gemalte Seite
das Speichern und Wiederöffnen heil übersteht.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DATEN = Path(tempfile.mkdtemp(prefix="notizen-stift-"))
KONFIG = Path(tempfile.mkdtemp(prefix="notizen-stift-konfig-"))
os.environ["NOTIZEN_ORDNER"] = str(DATEN)
os.environ["NOTIZMAPPE_KONFIG"] = str(KONFIG)
os.environ["NOTIZMAPPE_OPTIONEN"] = str(KONFIG / "optionen.json")
os.environ["NOTIZMAPPE_QUELLE"] = "http://127.0.0.1:1"
sys.path.insert(0, str(WURZEL / "app"))

import bruecke as bruecke_modul
import reinigen

b = bruecke_modul.Bruecke()
fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


# --- Die Prüfung der Striche -------------------------------------------------
print("Striche prüfen")
ein = reinigen.striche([{"f": "#AABBCC", "d": 3, "a": "marker", "p": [1.234, 2.345, 0.5, 9, 9, 1]}])
pruefe("Ein sauberer Strich kommt durch", len(ein) == 1, ein)
pruefe("Farbe kleingeschrieben", ein[0]["f"] == "#aabbcc", ein)
pruefe("Koordinaten auf eine Stelle gerundet", ein[0]["p"][0] == 1.2, ein)
pruefe("Marker bleibt Marker", ein[0]["a"] == "marker")

pruefe("Unsinnige Farbe wird ersetzt",
       reinigen.striche([{"f": "javascript:boese", "p": [0, 0, 1]}])[0]["f"] == "#1d1d1f")
pruefe("Farbe mit Klammern wird ersetzt",
       reinigen.striche([{"f": "url(x)", "p": [0, 0, 1]}])[0]["f"] == "#1d1d1f")
pruefe("Unbekannte Art wird zum Stift",
       reinigen.striche([{"a": "laser", "p": [0, 0, 1]}])[0]["a"] == "stift")
pruefe("Dicke wird gedeckelt",
       reinigen.striche([{"d": 9999, "p": [0, 0, 1]}])[0]["d"] == 60.0)
pruefe("Dicke als Unsinn gibt den Standard",
       reinigen.striche([{"d": "dick", "p": [0, 0, 1]}])[0]["d"] == 4.0)
pruefe("Druck wird auf 0 bis 1 begrenzt",
       reinigen.striche([{"p": [0, 0, 77]}])[0]["p"][2] == 1.0)
pruefe("Weit entfernte Punkte werden hereingeholt",
       reinigen.striche([{"p": [10 ** 9, 0, 1]}])[0]["p"][0] == reinigen.WEIT)

viel = {"p": [i % 100 for i in range(reinigen.MAX_PUNKTE * 3 + 3000)]}
pruefe("Zu viele Punkte werden abgeschnitten",
       len(reinigen.striche([viel])[0]["p"]) == reinigen.MAX_PUNKTE * 3)
pruefe("Zu viele Striche werden abgeschnitten",
       len(reinigen.striche([{"p": [1, 2, 1]}] * (reinigen.MAX_STRICHE + 50))) == reinigen.MAX_STRICHE)
pruefe("Ein Strich ohne Punkte faellt weg", reinigen.striche([{"p": []}]) == [])
pruefe("Kein Strich ist auch kein Fehler", reinigen.striche("kein Strich") == [])
pruefe("Text statt Zahl faellt weg, der Rest bleibt",
       reinigen.striche([{"p": [1, 2, 1, "x", "y", "z", 3, 4, 1]}])[0]["p"] == [1.0, 2.0, 1.0, 3.0, 4.0, 1.0])
pruefe("Zusaetzliche Felder werden nicht uebernommen",
       set(reinigen.striche([{"p": [0, 0, 1], "boese": "<script>"}])[0]) == {"f", "d", "a", "p"})

# --- Durch die Bruecke und zurueck -------------------------------------------
print("\nGemalte Seite speichern und wieder öffnen")
buch = b.notizbuch_anlegen("Malbuch")["name"]
absch = b.abschnitt_anlegen(buch, "Skizzen")["name"]
seite = b.seite_anlegen(buch, absch, "Gekritzel")["name"]
gelesen = b.seite_lesen(buch, absch, seite)

antwort = b.seite_speichern({
    "notizbuch": buch, "abschnitt": absch, "name": seite, "rev": gelesen["rev"],
    "titel": "Gekritzel",
    "elemente": [
        {"typ": "text", "x": 10, "y": 10, "b": 200, "html": "Dazu geschrieben"},
        {"typ": "stift", "id": "zeichnung", "x": 0, "y": 0, "b": 0, "striche": [
            {"f": "#d13232", "d": 4, "a": "stift", "p": [10, 10, 0.5, 20, 30, 0.8]},
            {"f": "#ffd84d", "d": 22, "a": "marker", "p": [5, 5, 0.5, 60, 5, 0.5]},
        ]},
    ]})
pruefe("Speichern geht", "fehler" not in antwort, antwort)
zurueck = b.seite_lesen(buch, absch, seite)
gemalt = [e for e in zurueck["elemente"] if e["typ"] == "stift"]
pruefe("Die Zeichnung ist wieder da", len(gemalt) == 1, zurueck["elemente"])
pruefe("Beide Striche sind heil", len(gemalt[0]["striche"]) == 2, gemalt)
pruefe("Der Marker ist noch Marker", gemalt[0]["striche"][1]["a"] == "marker")
pruefe("Der Text daneben ist auch noch da",
       any(e["typ"] == "text" and "Dazu" in e["html"] for e in zurueck["elemente"]))

# Eine leere Zeichnung hat in der Datei nichts zu suchen - sonst bekommt jede
# Seite, die man nur anschaut, ein Element dazu.
antwort = b.seite_speichern({
    "notizbuch": buch, "abschnitt": absch, "name": seite, "rev": zurueck["rev"],
    "titel": "Gekritzel",
    "elemente": [{"typ": "stift", "id": "zeichnung", "x": 0, "y": 0, "b": 0, "striche": []}]})
leer = b.seite_lesen(buch, absch, seite)
pruefe("Eine leere Zeichnung wird nicht mitgeschleppt",
       all(e["typ"] != "stift" for e in leer["elemente"]), leer["elemente"])

# --- Die Oberflaeche ---------------------------------------------------------
print("\nOberfläche")
html = (WURZEL / "app/oberflaeche/index.html").read_text(encoding="utf-8")
js = (WURZEL / "app/oberflaeche/mappe.js").read_text(encoding="utf-8")
pruefe("Es gibt einen Reiter Zeichnen", 'data-reiter="zeichnen"' in html)
pruefe("Und einen Reiter Start", 'data-reiter="start"' in html)
for was, kennung in (("Rueckgaengig", "m-zurueck"), ("Wiederholen", "m-vor"),
                     ("Farbe", "m-farbe"), ("Dicke", "m-dicke"), ("nur Stift", "m-nurstift")):
    pruefe(f"Knopf/Feld {was} ist da", f'id="{kennung}"' in html)
for werkzeug in ("auswahl", "lasso", "radierer", "hand"):
    pruefe(f"Werkzeug {werkzeug} ist da", f'data-werkzeug="{werkzeug}"' in html)
pruefe("Striche werden nicht als Kasten gebaut", "e.typ !== 'stift'" in js)
pruefe("Die Zeichenebene liegt ueber den Kaesten",
       "#malblatt" in (WURZEL / "app/oberflaeche/stil.css").read_text(encoding="utf-8"))

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
shutil.rmtree(DATEN, ignore_errors=True)
shutil.rmtree(KONFIG, ignore_errors=True)
sys.exit(1 if fehler else 0)
