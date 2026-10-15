"""Jede Methode der Brücke mit Unsinn füttern.

    .venv/bin/python tests/test_robust.py

Die Oberfläche schickt normalerweise brauchbare Werte. Fehlt aber ein Feld,
heißt zwei Wege gleich oder tippt sich jemand vertan, kommt None, eine Zahl
oder eine Liste an - und dann soll eine **Meldung** zurückkommen, kein roher
Programmfehler.

Warum das einen eigenen Test wert ist: genau so ist der Update-Knopf gestorben.
Zwei Wege hießen gleich, die Updateprüfung bekam plötzlich die Werte der
Seitenfassung, und im Fenster stand "TypeError: normalize() argument 2 must be
str, not None". Das sah nach einem kaputten Programm aus und war nur ein
fehlender Wert.

Erkannt wird das am Feld "wo" in der Antwort: das setzt die Brücke genau dann,
wenn eine Ausnahme durchgefallen ist, die niemand erwartet hat.
"""
import inspect
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DATEN = Path(tempfile.mkdtemp(prefix="notizen-robust-"))
KONFIG = Path(tempfile.mkdtemp(prefix="notizen-robust-konfig-"))
os.environ["NOTIZEN_ORDNER"] = str(DATEN)
os.environ["NOTIZMAPPE_KONFIG"] = str(KONFIG)
os.environ["NOTIZMAPPE_OPTIONEN"] = str(KONFIG / "optionen.json")
os.environ["NOTIZMAPPE_QUELLE"] = "http://127.0.0.1:1"
os.environ["LOCALAPPDATA"] = str(KONFIG)
sys.path.insert(0, str(WURZEL / "app"))

import bruecke as bruecke_modul

b = bruecke_modul.Bruecke()
fehler = []

FAELLE = (
    ("None", lambda p: None),
    ("leer", lambda p: {} if p.name == "rumpf" else ""),
    ("Zahl", lambda p: 42),
    ("Liste", lambda p: [1, 2]),
    ("Wörterbuch", lambda p: {"a": 1}),
    ("langer Text", lambda p: "x" * 5000),
    ("Pfadtrick", lambda p: "../../etc/passwd"),
    ("Punkt", lambda p: "."),
    ("Null-Byte", lambda p: "a\x00b"),
    ("Zeilenumbruch", lambda p: "a\nb"),
    ("Windows-Pfad", lambda p: "C:\\Windows\\x"),
    ("Emoji", lambda p: "📓"),
    ("nur Leerzeichen", lambda p: "   "),
)

# Diese fassen das Fenster an (Dateidialoge) - ohne Fenster tun sie nichts,
# aber mitgeprueft werden sie trotzdem.
methoden = sorted(n for n in dir(b) if not n.startswith("_") and callable(getattr(b, n)))
roh = []
aufrufe = 0
for name in methoden:
    m = getattr(b, name)
    for fall, mach in FAELLE:
        aufrufe += 1
        args = [mach(p) for p in inspect.signature(m).parameters.values()
                if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        try:
            antwort = m(*args)
        except Exception as f:                      # noqa: BLE001
            roh.append(f"{name}({fall}) wirft {type(f).__name__}: {f}")
            continue
        if not isinstance(antwort, dict):
            roh.append(f"{name}({fall}) gibt kein Wörterbuch zurück: {type(antwort).__name__}")
        elif "wo" in antwort:
            roh.append(f"{name}({fall}): {antwort['fehler']}")

print(f"  {len(methoden)} Methoden × {len(FAELLE)} Fälle = {aufrufe} Aufrufe")
for z in roh[:20]:
    print("FEHLER  " + z)
if roh:
    fehler.append(f"{len(roh)} rohe Programmfehler")
else:
    print("  ok    keine Methode fällt bei Unsinn um")

# Anlegen ist erlaubt - "notizbuch_anlegen" tut genau das, auch mit einem
# seltsamen Namen. Verboten ist, dabei aus dem Datenordner auszubrechen: aus
# "../../etc/passwd" muss ein harmloser Name im Ordner werden, kein Pfad.
entstanden = [p for p in DATEN.rglob("*")] if DATEN.is_dir() else []
ausgebrochen = [str(p) for p in entstanden if not str(p.resolve()).startswith(str(DATEN.resolve()))]
print(("  ok    " if not ausgebrochen else "FEHLER  ")
      + f"nichts bricht aus dem Datenordner aus ({len(entstanden)} Einträge entstanden)"
      + ("" if not ausgebrochen else f"   {ausgebrochen}"))
if ausgebrochen:
    fehler.append("Etwas ist aus dem Datenordner ausgebrochen")

tiefer = [p.name for p in DATEN.iterdir() if "/" in p.name or "\\" in p.name]
print(("  ok    " if not tiefer else "FEHLER  ") + "kein angelegter Name enthält einen Pfadtrenner"
      + ("" if not tiefer else f"   {tiefer}"))
if tiefer:
    fehler.append("Pfadtrenner im Namen")

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
shutil.rmtree(DATEN, ignore_errors=True)
shutil.rmtree(KONFIG, ignore_errors=True)
sys.exit(1 if fehler else 0)
