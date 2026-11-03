"""Wird aus einem Gerber-Paket wirklich diese Platine?

    .venv/bin/python tests/test_platine.py

Ein Gerber-Paket ist ein ZIP mit einem Dutzend Textdateien, von denen jede
eine Lage zeichnet. Dabei kann vieles leise schiefgehen, und nichts davon
sieht man dem Bild an: ein falsch gelesenes Koordinatenformat macht die
Platine tausendmal zu groß, eine nicht erkannte Endung lässt eine ganze Lage
verschwinden, und die Bohrdatei rechnet in anderen Einheiten als der Rest.

Deshalb wird hier an einer von Hand geschriebenen Platine gemessen, von der
jede Zahl bekannt ist: 20 × 15 mm, eine Leiterbahn, ein Lötauge, zwei Löcher.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
mappe = (WURZEL / "app/oberflaeche/mappe.js").read_text(encoding="utf-8")
fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was
          + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


teile = []
for muster, name in ((r"^const PCB_MAX_EINTRAEGE = [^;]*;", "PCB_MAX_EINTRAEGE"),
                     (r"^const PCB_MAX_ENTPACKT = [^;]*;", "PCB_MAX_ENTPACKT"),
                     (r"^const PCB_MAX_STUECKE = [^;]*;", "PCB_MAX_STUECKE"),
                     (r"^const PCB_BOGEN = [^;]*;", "PCB_BOGEN"),
                     (r"^async function entpacken\(.*?^\}", "entpacken"),
                     (r"^async function zipLesen\(.*?^\}", "zipLesen"),
                     (r"^const PCB_LAGEN = \[.*?^\];", "PCB_LAGEN"),
                     (r"^function lageVon\(.*?^\}", "lageVon"),
                     (r"^function gerberLesen\(.*?^\}", "gerberLesen"),
                     (r"^function bohrLesen\(.*?^\}", "bohrLesen"),
                     (r"^function istBohrdatei\(.*?^\}", "istBohrdatei"),
                     (r"^const PCB_SEITEN = \{.*?^\};", "PCB_SEITEN"),
                     (r"^function textVon\(.*?^\}", "textVon"),
                     (r"^function platinePacken\(.*?^\}", "platinePacken"),
                     (r"^function umrissNaehen\(.*?^\}", "umrissNaehen"),
                     (r"^function pcbRahmen\(.*?^\}", "pcbRahmen")):
    treffer = re.search(muster, mappe, re.S | re.M)
    pruefe(f"{name} steht in mappe.js", bool(treffer))
    if treffer:
        teile.append(treffer.group(0))
if fehler:
    sys.exit(1)

# --- Die Platine, von der wir jede Zahl kennen -------------------------------
#
# Format 4.6, Millimeter: 20 mm stehen als 20000000 da.
UMRISS = """%FSLAX46Y46*%
%MOMM*%
%ADD10C,0.100000*%
G04 Umriss der Platine*
D10*
X0Y0D02*
X20000000Y0D01*
X20000000Y15000000D01*
X0Y15000000D01*
X0Y0D01*
M02*
"""
KUPFER = """%FSLAX46Y46*%
%MOMM*%
%ADD10C,0.250000*%
%ADD11R,1.600000X1.600000*%
D10*
X2000000Y2000000D02*
X10000000Y2000000D01*
D11*
X5000000Y8000000D03*
M02*
"""
DRUCK = """%FSLAX46Y46*%
%MOMM*%
%ADD10C,0.150000*%
D10*
X1000000Y14000000D02*
X6000000Y14000000D01*
M02*
"""
# Zoll und Format 2.4: X10000 ist genau ein Zoll, also 25,4 mm. Steht das
# Maß falsch, ist die Platine um den Faktor 25 daneben.
ZOLL = """%FSLAX24Y24*%
%MOIN*%
%ADD10C,0.010000*%
D10*
X0Y0D02*
X10000Y0D01*
M02*
"""
BOHREN = """M48
METRIC
T1C0.800
%
T1
X5.0Y8.0
X17.0Y8.0
M30
"""

ordner = Path(tempfile.mkdtemp(prefix="platine-"))
with zipfile.ZipFile(ordner / "gerber.zip", "w") as z:
    # Gemischt gepackt und ungepackt: beides kommt in echten Paketen vor.
    z.writestr("Gerber_BoardOutlineLayer.GKO", UMRISS, zipfile.ZIP_DEFLATED)
    z.writestr("Gerber_TopLayer.GTL", KUPFER, zipfile.ZIP_DEFLATED)
    z.writestr("Gerber_TopSilkLayer.GTO", DRUCK, zipfile.ZIP_STORED)
    z.writestr("Drill_PTH_Through.DRL", BOHREN, zipfile.ZIP_DEFLATED)
    z.writestr("liesmich.txt", "nur Text, keine Bohrdatei\n", zipfile.ZIP_STORED)

HARNISCH = r"""
const fs = require('fs');
const window = { DecompressionStream: globalThis.DecompressionStream };
""" + "\n".join(teile) + r"""

(async function () {
  const ergebnis = {};
  const roh = fs.readFileSync('/p/gerber.zip');
  const puffer = roh.buffer.slice(roh.byteOffset, roh.byteOffset + roh.byteLength);
  const dateien = await zipLesen(puffer);
  ergebnis.namen = dateien.map((d) => d.name);
  ergebnis.lagen = dateien.map((d) => lageVon(d.name));
  ergebnis.laengen = dateien.map((d) => d.daten.length);

  const umriss = gerberLesen(textVon(dateien[0].daten));
  ergebnis.umriss_stuecke = umriss.length;
  ergebnis.umriss_punkte = umriss[0].punkte;
  ergebnis.umriss_breite = umriss[0].breite;

  const kupfer = gerberLesen(textVon(dateien[1].daten));
  ergebnis.kupfer = kupfer.map((s) => s.t);
  ergebnis.bahn = kupfer[0].punkte;
  ergebnis.bahn_breite = kupfer[0].breite;
  ergebnis.auge = { x: kupfer[1].x, y: kupfer[1].y,
                    form: kupfer[1].blende.form, werte: kupfer[1].blende.werte };

  const zoll = gerberLesen(ZOLL);
  ergebnis.zoll = zoll[0].punkte[1];

  const loecher = bohrLesen(textVon(dateien[3].daten));
  ergebnis.loecher = loecher;
  ergebnis.text_ist_bohrdatei = istBohrdatei(textVon(dateien[4].daten));

  const platine = platinePacken(dateien);
  ergebnis.pakete = Object.keys(platine.lagen).sort();
  ergebnis.pakete_namen = platine.namen;
  ergebnis.ringe = platine.umriss.length;
  ergebnis.ring_punkte = platine.umriss[0] ? platine.umriss[0].length : 0;
  const r = pcbRahmen(platine);
  ergebnis.rahmen = [r.x0, r.y0, r.breit, r.hoch];
  ergebnis.bohrzahl = platine.loecher.length;

  process.stdout.write(JSON.stringify(ergebnis) + '\n');
})().catch((f) => { process.stderr.write(String(f.stack || f) + '\n'); process.exit(1); });
""".replace("ZOLL", json.dumps(ZOLL))

(ordner / "pruef.js").write_text(HARNISCH, encoding="utf-8")
if shutil.which("node"):
    befehl = ["node", str(ordner / "pruef.js")]
    HARNISCH = HARNISCH.replace("'/p/gerber.zip'", repr(str(ordner / "gerber.zip")))
    (ordner / "pruef.js").write_text(HARNISCH, encoding="utf-8")
elif shutil.which("docker"):
    befehl = ["docker", "run", "--rm", "-v", f"{ordner}:/p:ro", "node:alpine",
              "node", "/p/pruef.js"]
else:
    print("  --  weder node noch docker da, die Platine ist ungeprueft")
    sys.exit(0)

lauf = subprocess.run(befehl, capture_output=True, text=True)
if lauf.returncode != 0:
    print(lauf.stdout)
    print(lauf.stderr)
    sys.exit(1)
d = json.loads(lauf.stdout.strip().splitlines()[-1])


def gleich(a, b, genau=1e-6):
    if isinstance(a, list):
        return len(a) == len(b) and all(gleich(x, y, genau) for x, y in zip(a, b))
    return abs(a - b) < genau


print("\nDas ZIP")
pruefe("alle fünf Dateien kommen heraus", len(d["namen"]) == 5, d["namen"])
pruefe("gepackt und ungepackt gleichermaßen",
       d["laengen"] == [len(UMRISS), len(KUPFER), len(DRUCK), len(BOHREN), 26],
       d["laengen"])

print("\nWelche Datei ist welche Lage")
pruefe("Endungen werden erkannt",
       d["lagen"] == ["umriss", "kupfer-oben", "druck-oben", "bohren", "unklar"],
       d["lagen"])

print("\nDer Umriss")
pruefe("ein Zug mit fünf Punkten", d["umriss_stuecke"] == 1 and len(d["umriss_punkte"]) == 5,
       (d["umriss_stuecke"], d["umriss_punkte"]))
pruefe("und zwar in Millimetern, nicht in Gerber-Einheiten",
       gleich(d["umriss_punkte"], [[0, 0], [20, 0], [20, 15], [0, 15], [0, 0]]),
       d["umriss_punkte"])

print("\nDas Kupfer")
pruefe("eine Bahn und ein Lötauge", d["kupfer"] == ["zug", "abdruck"], d["kupfer"])
pruefe("die Bahn läuft von 2,2 nach 10,2",
       gleich(d["bahn"], [[2, 2], [10, 2]]), d["bahn"])
pruefe("und ist 0,25 mm breit", gleich(d["bahn_breite"], 0.25), d["bahn_breite"])
pruefe("das Lötauge sitzt auf 5,8 und ist 1,6 mm im Quadrat",
       gleich([d["auge"]["x"], d["auge"]["y"]], [5, 8]) and d["auge"]["form"] == "R"
       and gleich(d["auge"]["werte"], [1.6, 1.6]), d["auge"])

print("\nZoll und ein anderes Zahlenformat")
# Eine Zeichnung in Zoll mit Format 2.4: X10000 ist ein Zoll.
pruefe("ein Zoll sind 25,4 mm", gleich(d["zoll"], [25.4, 0], 1e-9), d["zoll"])

print("\nDie Bohrdatei")
pruefe("zwei Löcher, 0,8 mm",
       len(d["loecher"]) == 2 and gleich([d["loecher"][0]["x"], d["loecher"][0]["y"],
                                          d["loecher"][0]["d"]], [5.0, 8.0, 0.8]),
       d["loecher"])
pruefe("eine gewöhnliche .txt ist keine Bohrdatei", d["text_ist_bohrdatei"] is False,
       d["text_ist_bohrdatei"])

print("\nDie ganze Platine")
pruefe("drei Lagen", d["pakete"] == ["druck-oben", "kupfer-oben", "umriss"], d["pakete"])
pruefe("die liesmich.txt zählt nicht mit", len(d["pakete_namen"]) == 4, d["pakete_namen"])
# Vier Striche ergeben einen Ring - sonst bliebe der Träger ungefüllt.
pruefe("der Umriss wird zu einem geschlossenen Ring",
       d["ringe"] == 1 and d["ring_punkte"] == 5, (d["ringe"], d["ring_punkte"]))
pruefe("und die Platine ist 20 × 15 mm groß",
       gleich(d["rahmen"], [0, 0, 20, 15]), d["rahmen"])
pruefe("zwei Bohrungen sind angekommen", d["bohrzahl"] == 2, d["bohrzahl"])

# --- Und landet sie auch im Bild? --------------------------------------------
#
# Alles richtig gelesen und trotzdem nichts zu sehen: das ist der Fehler, den
# ein Lesetest nicht findet. Gemalt wird hier auf eine Zeichenfläche, die
# mitschreibt, und nachgerechnet, wo die Ecken der Platine landen.
print("\nWo die Platine auf der Fläche landet")
teile2 = []
for muster, name in ((r"^function pcbFenster\(.*?^\}", "pcbFenster"),
                     (r"^function pcbPfad\(.*?^\}", "pcbPfad"),
                     (r"^function abdruckMalen\(.*?^\}", "abdruckMalen"),
                     (r"^function lageMalen\(.*?^\}", "lageMalen"),
                     (r"^const PCB_FARBEN = \{.*?^\};", "PCB_FARBEN"),
                     (r"^function platineZeichnen\(.*?^\}", "platineZeichnen")):
    treffer = re.search(muster, mappe, re.S | re.M)
    pruefe(f"{name} steht in mappe.js", bool(treffer))
    if treffer:
        teile2.append(treffer.group(0))

MALEN = r"""
const fs = require('fs');
const window = { DecompressionStream: globalThis.DecompressionStream,
                 devicePixelRatio: 1 };

/* Eine Zeichenflaeche, die nur mitschreibt - mit echter Matrix, denn genau
   dort steckt der Fehler, den man sucht. */
function Mitschrift(breit, hoch) {
  this.m = [1, 0, 0, 1, 0, 0];
  this.stapel = [];
  this.punkte = [];
  this.fillStyle = '#000';
  this.strokeStyle = '#000';
  this.lineWidth = 1;
  this.farben = {};
}
Mitschrift.prototype.hin = function (x, y, farbe) {
  const m = this.m;
  this.punkte.push([m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5],
                    farbe || this.fillStyle]);
};
Mitschrift.prototype.setTransform = function (a, b, c, d, e, f) { this.m = [a, b, c, d, e, f]; };
Mitschrift.prototype.translate = function (tx, ty) {
  const m = this.m;
  m[4] += m[0] * tx + m[2] * ty;
  m[5] += m[1] * tx + m[3] * ty;
};
Mitschrift.prototype.save = function () { this.stapel.push(this.m.slice()); };
Mitschrift.prototype.restore = function () { this.m = this.stapel.pop() || this.m; };
Mitschrift.prototype.beginPath = function () {};
Mitschrift.prototype.closePath = function () {};
Mitschrift.prototype.moveTo = function (x, y) { this.hin(x, y); };
Mitschrift.prototype.lineTo = function (x, y) { this.hin(x, y); };
Mitschrift.prototype.arc = function (x, y, r) { this.hin(x, y); };
Mitschrift.prototype.fillRect = function (x, y, b, h) { this.hin(x, y); this.hin(x + b, y + h); };
Mitschrift.prototype.clearRect = function () {};
Mitschrift.prototype.fill = function () { this.farben[this.fillStyle] = 1; };
Mitschrift.prototype.stroke = function () { this.farben[this.strokeStyle] = 1; };
Mitschrift.prototype.clip = function () {};
""" + "\n".join(teile) + "\n" + "\n".join(teile2) + r"""

(async function () {
  const roh = fs.readFileSync('/p/gerber.zip');
  const puffer = roh.buffer.slice(roh.byteOffset, roh.byteOffset + roh.byteLength);
  const platine = platinePacken(await zipLesen(puffer));
  const ergebnis = {};

  function malen(seite) {
    const ctx = new Mitschrift();
    const bild = { width: 0, height: 0, getContext: () => ctx };
    const z = { bild: bild, wo: { getBoundingClientRect: () => ({ width: 400, height: 300 }) },
                platine: platine, rahmen: pcbRahmen(platine), seite: seite,
                zoom: 1, ox: 0, oy: 0 };
    platineZeichnen(z);
    return { ctx: ctx, breit: bild.width, hoch: bild.height };
  }

  const oben = malen('oben');
  const xs = oben.ctx.punkte.map((p) => p[0]);
  const ys = oben.ctx.punkte.map((p) => p[1]);
  ergebnis.flaeche = [oben.breit, oben.hoch];
  ergebnis.kasten = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  ergebnis.farben = Object.keys(oben.ctx.farben).sort();
  // Dieselben Loecher von unten: sie muessen spiegelbildlich liegen.
  const unten = malen('unten');
  function loch(c) {
    return c.punkte.filter((p) => p[2] === PCB_FARBEN.loch).map((p) => Math.round(p[0]));
  }
  ergebnis.loch_oben = loch(oben.ctx);
  ergebnis.loch_unten = loch(unten.ctx);
  // Das Fenster, in dem die Platine steht: 435 px ist ein gewoehnlicher Kasten.
  ergebnis.fenster = { schmal: pcbFenster({ breit: 17.8, hoch: 42.5 }, 435),
                       quer: pcbFenster({ breit: 100, hoch: 20 }, 435),
                       streifen: pcbFenster({ breit: 200, hoch: 2 }, 435),
                       quadrat: pcbFenster({ breit: 20, hoch: 15 }, 435) };
  process.stdout.write(JSON.stringify(ergebnis) + '\n');
})().catch((f) => { process.stderr.write(String(f.stack || f) + '\n'); process.exit(1); });
"""

(ordner / "malen.js").write_text(MALEN, encoding="utf-8")
befehl2 = list(befehl)
befehl2[-1] = befehl2[-1].replace("pruef.js", "malen.js")
if befehl2[0] != "docker":
    befehl2[-1] = str(ordner / "malen.js")
    MALEN = MALEN.replace("'/p/gerber.zip'", repr(str(ordner / "gerber.zip")))
    (ordner / "malen.js").write_text(MALEN, encoding="utf-8")
lauf2 = subprocess.run(befehl2, capture_output=True, text=True)
if lauf2.returncode != 0:
    print(lauf2.stdout)
    print(lauf2.stderr)
    sys.exit(1)
m = json.loads(lauf2.stdout.strip().splitlines()[-1])

pruefe("die Fläche bekommt die Größe des Kastens", m["flaeche"] == [400, 300], m["flaeche"])
x0, y0, x1, y1 = m["kasten"]
pruefe("nichts wird außerhalb gezeichnet",
       -1 <= x0 and x1 <= 401 and -1 <= y0 and y1 <= 301, m["kasten"])
# 20 mm auf 400 px: mit einem Millimeter Luft ringsum bleiben gut 350 px.
pruefe("und die Platine füllt das Bild aus", (x1 - x0) > 340, m["kasten"])
pruefe("Träger, Kupfer, Bohrung und Aufdruck sind dabei",
       sorted(m["farben"]) == sorted(["#0d5c38", "#0a3f27", "#d8a93c", "#f2f4f5",
                                      "#0b0c0d"]), m["farben"])
# Von unten gesehen liegt dasselbe Loch spiegelbildlich - sonst loetet man
# nach dem Bild auf der falschen Seite.
pruefe("von unten liegen die Löcher gespiegelt",
       len(m["loch_oben"]) == 2
       and sorted(m["loch_unten"]) == sorted(400 - x for x in m["loch_oben"])
       and m["loch_oben"] != m["loch_unten"],
       (m["loch_oben"], m["loch_unten"]))

# --- Und wie gross ist das Fenster, in dem sie steht? ------------------------
#
# Das Fenster ist immer so breit wie der Kasten - also so breit wie die Zeile
# darunter. Nur die Hoehe richtet sich nach der Platine: ein festes 4:3 waere
# fuer ein langes schmales Brett zu flach und fuer ein flaches zu hoch.
print("\nDas Fenster um die Platine")
f = m["fenster"]
pruefe("jedes Fenster ist so breit wie der Kasten",
       all(w["breit"] == 435 for w in f.values()), f)
pruefe("eine lange schmale Platine bekommt das hoechste Fenster",
       f["schmal"]["hoch"] == 340, f["schmal"])
pruefe("eine flache Platine bekommt ein flaches",
       f["quer"]["hoch"] < 120 and f["streifen"]["hoch"] < 120,
       (f["quer"], f["streifen"]))
pruefe("und keines ist hoeher als 340 oder flacher als 90",
       all(90 <= w["hoch"] <= 340 for w in f.values()), f)

# --- Haengt die Zeichenflaeche auch am Fenster? ------------------------------
#
# Die Zeichenflaeche liegt mit position: absolute; inset: 0 im Fenster. Ist das
# Fenster selbst nicht positioniert, sucht sie sich den naechsten positionierten
# Vorfahren - den Kasten - und wird ueber dessen ganze Breite gezerrt. Das Bild
# ist dann vollstaendig da, nur in die Breite gezogen: ein Fehler, den kein
# Rechentest sieht, weil gezeichnet wird in die richtige Groesse.
print("\nDas Fenster traegt die Zeichenfläche")
# Nur der Stilblock, nicht die ganze Datei: in JavaScript stehen auch
# geschweifte Klammern, und die bringen die Regelsuche durcheinander.
# Im Fenster stehen die festen Regeln in der Stildatei, nicht im Skript.
stilblock = (WURZEL / "app/oberflaeche/stil.css").read_text(encoding="utf-8")
pruefe("die Stildatei kennt die Kästen", ".modell" in stilblock)
for fenster in (".kasten-3d .modell", ".kasten-pcb .modell"):
    # Die Regel darf auch mit anderen Wählern zusammenstehen. Kommentare
    # fliegen vorher heraus - vor dem Wähler wie in der Regel.
    def ohne(text):
        return re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    regel = next((t for t in re.finditer(r"([^{}]+)\{([^{}]*)\}", stilblock)
                  if fenster in [w.strip() for w in ohne(t.group(1)).split(",")]), None)
    # Ohne die Kommentare: sonst genuegt es, dass im Kommentar darueber steht,
    # was fehlt. Genau so ist diese Prüfung beim ersten Versuch grün geblieben.
    inhalt = ohne(regel.group(2)) if regel else ""
    pruefe(f"{fenster} ist positioniert", "position: relative" in inhalt,
           inhalt.strip() or "keine Regel")
    pruefe(f"{fenster} schneidet ab", "overflow: hidden" in inhalt,
           inhalt.strip() or "keine Regel")

shutil.rmtree(ordner, ignore_errors=True)
print()
if fehler:
    print(f"{len(fehler)} Prüfungen gescheitert")
    sys.exit(1)
print("Aus dem Gerber-Paket wird diese Platine")
