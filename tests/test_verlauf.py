"""Verlauf: frühere Fassungen und Papierkorb.

    .venv/bin/python tests/test_verlauf.py

Worauf es ankommt - beides sind Funktionen, bei denen ein Fehler teuer ist:

* Eine Fassung entsteht **nicht** bei jedem Speichern (sonst hunderte am Tag),
  aber vor jedem Überschreiben eine.
* Zurückholen darf nichts kosten: der jetzige Stand wird vorher weggelegt.
* Umbenennen und Löschen nehmen den Verlauf mit - sonst sind die Fassungen
  unerreichbar und die Seite sieht aus, als hätte sie nie welche gehabt.
* Der Papierkorb leert sich **nie** von allein, und Zurückholen findet den
  alten Platz wieder, auch wenn der Abschnitt darüber auch gelöscht wurde.
* Bei eingeschalteter Sperre sind auch die Fassungen verschlüsselt - sonst
  stünde der Text, den man gerade versteckt, in der Fassung daneben im Klartext.
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DATEN = Path(tempfile.mkdtemp(prefix="notizen-verlauf-"))
KONFIG = Path(tempfile.mkdtemp(prefix="notizen-verlauf-konfig-"))
os.environ["NOTIZEN_ORDNER"] = str(DATEN)
os.environ["NOTIZMAPPE_KONFIG"] = str(KONFIG)
os.environ["NOTIZMAPPE_OPTIONEN"] = str(KONFIG / "optionen.json")
os.environ["NOTIZMAPPE_QUELLE"] = "http://127.0.0.1:1"
sys.path.insert(0, str(WURZEL / "app"))

import bruecke as bruecke_modul
import speicher
import tresor

b = bruecke_modul.Bruecke()
fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


def schreiben(buch, absch, seite, text):
    stand = b.seite_lesen(buch, absch, seite)
    return b.seite_speichern({"notizbuch": buch, "abschnitt": absch, "name": seite,
                              "rev": stand["rev"], "titel": "Tagebuch",
                              "elemente": [{"typ": "text", "x": 10, "y": 10, "b": 300, "html": text}]})


buch = b.notizbuch_anlegen("Verlaufbuch")["name"]
absch = b.abschnitt_anlegen(buch, "Abschnitt")["name"]
seite = b.seite_anlegen(buch, absch, "Tagebuch")["name"]

# --- Wann entsteht eine Fassung? ---------------------------------------------
print("Fassungen entstehen")
schreiben(buch, absch, seite, "Erste Fassung")
pruefe("Beim ersten Speichern noch keine Fassung (nichts zu sichern)",
       len(b.versionen(buch, absch, seite)["versionen"]) <= 1)
schreiben(buch, absch, seite, "Zweite Fassung")
schreiben(buch, absch, seite, "Dritte Fassung")
anzahl = len(b.versionen(buch, absch, seite)["versionen"])
pruefe("Schnell hintereinander gibt nicht drei Fassungen", anzahl <= 1, anzahl)

speicher.VERLAUF_ABSTAND = 0           # so, als lägen Minuten dazwischen
# Eine Fassung je Sekunde: der Name ist auf die Sekunde genau. In echt liegen
# zehn Minuten dazwischen, hier muss der Test eben warten.
schreiben(buch, absch, seite, "Vierte Fassung")
time.sleep(1.1)
schreiben(buch, absch, seite, "Fünfte Fassung")
versionen = b.versionen(buch, absch, seite)["versionen"]
pruefe("Mit Abstand entstehen Fassungen", len(versionen) >= 2, len(versionen))
pruefe("Neueste zuerst", versionen == sorted(versionen, key=lambda v: v["marke"], reverse=True))

# --- Ansehen und Zurückholen -------------------------------------------------
print("\nZurückholen")
# Die neueste Fassung ist der Stand vor dem letzten Speichern. Die älteste ist
# die noch leere Seite von kurz nach dem Anlegen - die wäre zum Prüfen untauglich.
alt = b.version_lesen(buch, absch, seite, versionen[0]["marke"])
pruefe("Eine alte Fassung lässt sich lesen", alt.get("elemente"), alt)
alter_text = alt["elemente"][0]["html"]
jetzt_vorher = b.seite_lesen(buch, absch, seite)["elemente"][0]["html"]
pruefe("Sie ist nicht der jetzige Stand", alter_text != jetzt_vorher, (alter_text, jetzt_vorher))

vorher_anzahl = len(b.versionen(buch, absch, seite)["versionen"])
time.sleep(1.1)
zurueck = b.version_zurueck({"notizbuch": buch, "abschnitt": absch, "name": seite,
                             "marke": versionen[0]["marke"]})
pruefe("Zurückholen geht", "fehler" not in zurueck, zurueck)
pruefe("Der alte Text steht wieder da",
       b.seite_lesen(buch, absch, seite)["elemente"][0]["html"] == alter_text)
pruefe("Der vorherige Stand wurde als Fassung weggelegt",
       len(b.versionen(buch, absch, seite)["versionen"]) > vorher_anzahl)
pruefe("Die Zählung ist weitergelaufen (kein Konflikt beim nächsten Speichern)",
       b.seite_lesen(buch, absch, seite)["rev"] > 1)
pruefe("Nach dem Zurückholen lässt sich normal weiterschreiben",
       "fehler" not in schreiben(buch, absch, seite, "Danach"))
pruefe("Unbekannte Fassung wird gemeldet",
       "fehler" in b.version_lesen(buch, absch, seite, "20200101-000000"))
pruefe("Pfadtricks in der Marke prallen ab",
       "fehler" in b.version_lesen(buch, absch, seite, "../../../etc/passwd"))

# --- Ausdünnen ---------------------------------------------------------------
print("\nAusdünnen")
ordner = speicher.verlauf_ordner(DATEN / buch / absch / f"{seite}.json")
jetzt = time.time()
for tage, marke in ((200, "20250101-120000"), (120, "20250301-120000"), (5, "20260101-120000")):
    p = ordner / f"{marke}.json"
    p.write_text('{"titel": "alt", "elemente": [], "rev": 1}', encoding="utf-8")
    os.utime(p, (jetzt - tage * 86400, jetzt - tage * 86400))
weg = speicher._ausduennen(ordner)
namen = {p.stem for p in ordner.glob("*.json")}
pruefe("Fassungen älter als 90 Tage fliegen raus", "20250101-120000" not in namen, namen)
pruefe("Und die von vor 120 Tagen auch", "20250301-120000" not in namen, namen)
pruefe("Die von vor 5 Tagen bleibt", "20260101-120000" in namen, namen)

for i in range(80):
    p = ordner / f"2026021{i // 10}-1200{i % 10:02d}.json"
    p.write_text('{"titel": "x", "elemente": [], "rev": 1}', encoding="utf-8")
    os.utime(p, (jetzt - 3600, jetzt - 3600))
speicher._ausduennen(ordner)
pruefe(f"Nie mehr als {speicher.VERLAUF_ANZAHL} Fassungen je Seite",
       len(list(ordner.glob("*.json"))) <= speicher.VERLAUF_ANZAHL,
       len(list(ordner.glob("*.json"))))

# --- Umbenennen --------------------------------------------------------------
print("\nUmbenennen und Löschen")
neuer = b.seite_umbenennen(buch, absch, seite, "Anders benannt")["name"]
pruefe("Der Verlauf ist unter dem neuen Namen da",
       len(b.versionen(buch, absch, neuer)["versionen"]) > 0,
       b.versionen(buch, absch, neuer))
pruefe("Und nicht mehr unter dem alten",
       not (DATEN / buch / absch / speicher.VERLAUF / seite).exists())

# --- Papierkorb --------------------------------------------------------------
b.loeschen("seite", [buch, absch, neuer])
eintraege = b.papierkorb()["eintraege"]
pruefe("Die Seite liegt im Papierkorb", any(e["art"] == "seite" for e in eintraege), eintraege)
# Der Verlauf liegt mit im Papierkorb, bekommt aber keine eigene Zeile: er
# gehört zur Seite und kommt mit ihr zurück.
imkorb = [p.name for p in (DATEN / ".papierkorb").iterdir()]
pruefe("Der Verlauf ist mitgegangen",
       any(n.endswith(speicher.VERLAUF) for n in imkorb), imkorb)
pruefe("Und steht nicht als eigene Zeile da",
       not any(e["art"] == "verlauf" for e in eintraege), eintraege)
seiteneintrag = next(e for e in eintraege if e["art"] == "seite")
pruefe("Die Herkunft steht fest, wird nicht geraten", seiteneintrag["genau"] is True, seiteneintrag)

# Auch den Abschnitt löschen: Zurückholen muss ihn wieder anlegen
b.loeschen("abschnitt", [buch, absch])
pruefe("Der Abschnitt ist weg", not (DATEN / buch / absch).exists())
zurueck = b.papierkorb_zurueck({"eintrag": seiteneintrag["eintrag"]})
pruefe("Die Seite kommt zurück, obwohl der Abschnitt fehlte",
       "fehler" not in zurueck and (DATEN / buch / absch / f"{neuer}.json").is_file(), zurueck)
pruefe("Und sie steht wieder im Baum",
       any(s["name"] == neuer for bu in b.baum()["notizbuecher"]
           for a in bu["abschnitte"] for s in a["seiten"]))

uebrig = b.papierkorb()["eintraege"]
pruefe("Der zurückgeholte Eintrag ist aus dem Papierkorb verschwunden",
       all(e["eintrag"] != seiteneintrag["eintrag"] for e in uebrig), uebrig)
pruefe("Der Papierkorb leert sich nicht von allein", len(uebrig) > 0)

einer = uebrig[0]["eintrag"]
pruefe("Endgültig löschen geht", "fehler" not in b.papierkorb_weg({"eintrag": einer}))
pruefe("Und ist wirklich weg", all(e["eintrag"] != einer for e in b.papierkorb()["eintraege"]))
pruefe("Ausbrechen aus dem Papierkorb prallt ab",
       "fehler" in b.papierkorb_weg({"eintrag": "../../../etc/passwd"}))
geleert = b.papierkorb_leeren()
pruefe("Leeren räumt alles weg", "fehler" not in geleert and not b.papierkorb()["eintraege"], geleert)

# --- Eine Seite kommt vollständig zurück -------------------------------------
#
# Beim Löschen wandern Anhänge und Verlauf als eigene Einträge mit in den
# Papierkorb. Wer nur die Seite zurückholt, hat seine Bilder weggeworfen, ohne
# es zu merken - genau das ist beim Durchspielen eines ganzen Tagesablaufs
# herausgekommen.
print("\nZurückholen bringt alles mit")
import base64                                                       # noqa: E402

ganz = b.seite_anlegen(buch, absch, "Mit Bild")["name"]
bild = base64.b64encode(bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 40 + b"BILD").decode()
anhang = b.anhang_ablegen(buch, absch, ganz, "foto.png", bild)
for i in range(3):
    st = b.seite_lesen(buch, absch, ganz)
    b.seite_speichern({"notizbuch": buch, "abschnitt": absch, "name": ganz, "rev": st["rev"],
                       "titel": "Mit Bild", "elemente": [
                           {"typ": "text", "x": 10, "y": 10, "b": 300, "html": f"Stand {i}"},
                           {"typ": "bild", "x": 10, "y": 200, "b": 300,
                            "datei": anhang["datei"], "beschriftung": ""}]})
    time.sleep(1.05)
fassungen_vorher = len(b.versionen(buch, absch, ganz)["versionen"])
pruefe("Vorher gibt es Fassungen", fassungen_vorher >= 2, fassungen_vorher)

b.loeschen("seite", [buch, absch, ganz])
zeilen = b.papierkorb()["eintraege"]
pruefe("Der Papierkorb zeigt eine Zeile, nicht drei",
       len([z for z in zeilen if z["art"] in ("seite", "anhaenge", "verlauf")]) == 1, zeilen)
zurueck = b.papierkorb_zurueck({"eintrag": zeilen[0]["eintrag"]})
pruefe("Anhänge und Verlauf kommen mit", zurueck.get("mitgekommen") == 2, zurueck)
pruefe("Das Bild ist wieder da",
       "daten" in b.anhang_bild(buch, absch, ganz, anhang["datei"]))
pruefe("Die Fassungen sind wieder da",
       len(b.versionen(buch, absch, ganz)["versionen"]) == fassungen_vorher)
pruefe("Und nichts bleibt im Papierkorb liegen", b.papierkorb()["eintraege"] == [])

# Endgültig löschen muss das Beiwerk auch mitnehmen, sonst bleiben Reste.
b.loeschen("seite", [buch, absch, ganz])
eine = b.papierkorb()["eintraege"][0]["eintrag"]
b.papierkorb_weg({"eintrag": eine})
pruefe("Endgültig löschen lässt keine Reste zurück", b.papierkorb()["eintraege"] == [],
       b.papierkorb()["eintraege"])

# --- Mit Sperre --------------------------------------------------------------
print("\nMit eingeschalteter Sperre")
seite2 = b.seite_anlegen(buch, absch, "Geheimes")["name"]
schreiben(buch, absch, seite2, "Streng geheim")
b.sperre_einrichten({"passwort": "verlaufpasswort"})
schreiben(buch, absch, seite2, "Noch geheimer")
versionen2 = b.versionen(buch, absch, seite2)["versionen"]
pruefe("Auch mit Sperre entstehen Fassungen", len(versionen2) > 0, versionen2)
rohe = list((DATEN / buch / absch / speicher.VERLAUF / seite2).glob("*.json"))
pruefe("Keine Fassung steht im Klartext auf der Platte",
       all(b"geheim" not in p.read_bytes() for p in rohe), [p.name for p in rohe])
pruefe("Aufgeschlossen lässt sich die Fassung lesen",
       "elemente" in b.version_lesen(buch, absch, seite2, versionen2[0]["marke"]))
b.sperren()
pruefe("Zugesperrt kommt niemand an die Fassungen",
       b.versionen(buch, absch, seite2).get("art") == "zu"
       or b.version_lesen(buch, absch, seite2, versionen2[0]["marke"]).get("art") == "zu")

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
shutil.rmtree(DATEN, ignore_errors=True)
shutil.rmtree(KONFIG, ignore_errors=True)
sys.exit(1 if fehler else 0)
