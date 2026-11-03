"""Liest mappe.js STL und OBJ richtig - und liegt das Modell dann im Bild?

    .venv/bin/python tests/test_modell.py

Hier laeuft kein Browser, also ist das Zeichnen selbst nicht zu pruefen - wie
es aussieht, sieht Lucy zuerst. Pruefbar ist aber alles, was davor schiefgehen
kann, und das ist das meiste:

  * binaer oder Text? Viele binaere STL fangen ebenfalls mit "solid" an - wer
    danach entscheidet, liest Muell.
  * Normalen: die in der Datei stehen oft auf 0 oder zeigen falsch, deshalb
    werden sie neu gerechnet. Steht hier eine falsche drin, muss sie ignoriert
    werden.
  * OBJ: Vielecke, Schraegstrich-Formen (7/3/2) und negative Nummern.
  * und die Matrizen: ein Vorzeichen daneben und das Teil steht hinter der
    Kamera. Darum wandern die Ecken des Wuerfels durch die echte Matrix aus
    modellZeichnen und muessen im Bild liegen - in jeder Drehung.
"""
import base64
import json
import re
import shutil
import struct
import zlib
import subprocess
import sys
import tempfile
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
for muster, name in ((r"^const MODELL_ARTEN = [^\n]*$", "MODELL_ARTEN"),
                     (r"^const MODELL_MAX_DREIECKE = [^\n]*$", "MODELL_MAX_DREIECKE"),
                     (r"^const MODELL_WEG = [^\n]*$", "MODELL_WEG"),
                     (r"^function modellArt\(.*?^\}", "modellArt"),
                     (r"^function stlLesen\(.*?^\}", "stlLesen"),
                     (r"^function stlBinaer\(.*?^\}", "stlBinaer"),
                     (r"^function stlText\(.*?^\}", "stlText"),
                     (r"^function objLesen\(.*?^\}", "objLesen"),
                     (r"^const FBX_MAGIE = [^\n]*$", "FBX_MAGIE"),
                     (r"^async function fbxLesen\(.*?^\}", "fbxLesen"),
                     (r"^async function auspacken\(.*?^\}", "auspacken"),
                     (r"^async function fbxBinaer\(.*?^\}", "fbxBinaer"),
                     (r"^async function fbxKnoten\(.*?^\}", "fbxKnoten"),
                     (r"^async function fbxWert\(.*?^\}", "fbxWert"),
                     (r"^function fbxFeld\(.*?^\}", "fbxFeld"),
                     (r"^function fbxText\(.*?^\}", "fbxText"),
                     (r"^function fbxWerteText\(.*?^\}", "fbxWerteText"),
                     (r"^function fbxKind\(.*?^\}", "fbxKind"),
                     (r"^function fbxFeldVon\(.*?^\}", "fbxFeldVon"),
                     (r"^function fbxEigenschaft\(.*?^\}", "fbxEigenschaft"),
                     (r"^function matDrehZ\(.*?^\}", "matDrehZ"),
                     (r"^function matSkalaXYZ\(.*?^\}", "matSkalaXYZ"),
                     (r"^function matDrehGrad\(.*?^\}", "matDrehGrad"),
                     (r"^function fbxModellLage\(.*?^\}", "fbxModellLage"),
                     (r"^function fbxGeoLage\(.*?^\}", "fbxGeoLage"),
                     (r"^function fbxLage\(.*?^\}", "fbxLage"),
                     (r"^function punkteWandeln\(.*?^\}", "punkteWandeln"),
                     (r"^function fbxGeometrie\(.*?^\}", "fbxGeometrie"),
                     (r"^function fbxNetz\(.*?^\}", "fbxNetz"),
                     (r"^function netzBauen\(.*?^\}", "netzBauen"),
                     (r"^function matEinheit\(.*?^\}", "matEinheit"),
                     (r"^function matMal\(.*?^\}", "matMal"),
                     (r"^function matPerspektive\(.*?^\}", "matPerspektive"),
                     (r"^function matSchieben\(.*?^\}", "matSchieben"),
                     (r"^function matSkala\(.*?^\}", "matSkala"),
                     (r"^function matDrehX\(.*?^\}", "matDrehX"),
                     (r"^function matDrehY\(.*?^\}", "matDrehY"),
                     (r"^function mat3Von\(.*?^\}", "mat3Von"),
                     (r"^const MODELL_WINKEL = [^\n]*$", "MODELL_WINKEL"),
                     (r"^const MODELL_SCHIEB_MAX = [^\n]*$", "MODELL_SCHIEB_MAX"),
                     (r"^function punktSchieben\(.*?^\}", "punktSchieben"),
                     (r"^const MODELL_LEBENDIG = [^\n]*$", "MODELL_LEBENDIG"),
                     (r"^const MODELL_MAX_LEBENDIG = [^\n]*$", "MODELL_MAX_LEBENDIG"),
                     (r"^function platzSchaffen\(.*?^\}", "platzSchaffen"),
                     (r"^function modellZeichnen\(.*?^\}", "modellZeichnen")):
    treffer = re.search(muster, mappe, re.S | re.M)
    pruefe(f"{name} steht in mappe.js", bool(treffer))
    if treffer:
        teile.append(treffer.group(0))
if fehler:
    sys.exit(1)


# --- Dateien bauen -----------------------------------------------------------
def stl_binaer(dreiecke, kopf=b"solid aus einem Programm, das luegt"):
    # Der Kopf fangt absichtlich mit "solid" an: genau daran scheitern Leser,
    # die nach dem ersten Wort entscheiden.
    daten = kopf.ljust(80, b" ")[:80] + struct.pack("<I", len(dreiecke))
    for ecken in dreiecke:
        daten += struct.pack("<3f", 9.0, 9.0, 9.0)          # falsche Normale
        for e in ecken:
            daten += struct.pack("<3f", *e)
        daten += struct.pack("<H", 0)
    return daten


ZWEI = stl_binaer([
    [(0, 0, 0), (1, 0, 0), (0, 1, 0)],     # Normale muss (0,0,1) werden
    [(0, 0, 0), (0, 1, 0), (1, 0, 0)],     # verkehrt herum -> (0,0,-1)
])

TEXT_STL = """solid eins
  facet normal 0 0 0
    outer loop
      vertex 0 0 0
      vertex 2e0 0 0
      vertex 0 2 0
    endloop
  endfacet
endsolid eins
""".encode()

OBJ = """# ein Viereck und zweimal dasselbe Dreieck anders geschrieben
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
f 1 2 3 4
f 1/1/1 2/2/2 3/3/3
f -4 -3 -2
""".encode()

# Zwei Faelle aus dem echten Leben: hinten haengt noch etwas dran, und der
# Kopf zaehlt mehr Dreiecke, als wirklich in der Datei stehen. Beides ist
# haeufig - wer nur auf die genaue Laenge prueft, landet im Textzweig und
# findet dort kein einziges "vertex".
ANHANG = stl_binaer([[(0, 0, 0), (1, 0, 0), (0, 1, 0)]]) + b"Kommentar vom Slicer"
ZU_VIEL = bytearray(stl_binaer([[(0, 0, 0), (1, 0, 0), (0, 1, 0)]]))
ZU_VIEL[80:84] = struct.pack("<I", 99)

# --- FBX: Szenen zum Prüfen selbst bauen -------------------------------------
#
# Es gibt hier keine echte FBX zum Mitliefern, und eine aus dem Netz zu holen
# hieße, gegen etwas zu prüfen, das sich ändern kann. Also werden die Dateien
# hier geschrieben - binär (mit zlib-gepackten Feldern, 32- und 64-Bit-Zeiger)
# und als Text.
def fbx_prop_l(v):
    return b"L" + struct.pack("<q", v)


def fbx_prop_s(s):
    b = s.encode("utf-8")
    return b"S" + struct.pack("<I", len(b)) + b


def fbx_prop_d(v):
    return b"D" + struct.pack("<d", v)


def fbx_feld_d(werte, packen=True):
    roh = struct.pack("<%dd" % len(werte), *werte)
    daten = zlib.compress(roh) if packen else roh
    return b"d" + struct.pack("<III", len(werte), 1 if packen else 0, len(daten)) + daten


def fbx_feld_i(werte, packen=False):
    roh = struct.pack("<%di" % len(werte), *werte)
    daten = zlib.compress(roh) if packen else roh
    return b"i" + struct.pack("<III", len(werte), 1 if packen else 0, len(daten)) + daten


def fbx_knoten(name, props=(), kinder=(), breit=False):
    """Gibt eine Funktion zurück: der Datensatz kennt seine Endstelle erst,
    wenn er weiß, wo er anfängt."""
    def schreiben(start):
        nameb = name.encode("utf-8")
        pb = b"".join(props)
        kopf = 25 if breit else 13
        pos = start + kopf + len(nameb) + len(pb)
        kb = b""
        for k in kinder:
            stueck = k(pos)
            kb += stueck
            pos += len(stueck)
        if kinder:
            kb += b"\0" * kopf
            pos += kopf
        marke = (struct.pack("<QQQ", pos, len(props), len(pb)) if breit
                 else struct.pack("<III", pos, len(props), len(pb)))
        return marke + bytes([len(nameb)]) + nameb + pb + kb
    return schreiben


def fbx_datei(knoten, fassung=7400):
    breit = fassung >= 7500
    daten = b"Kaydara FBX Binary  \x00\x1a\x00" + struct.pack("<I", fassung)
    pos = len(daten)
    for k in knoten:
        stueck = k(pos)
        daten += stueck
        pos += len(stueck)
    return daten + b"\0" * (25 if breit else 13)


def fbx_modell(nummer, name, eigenschaften, breit=False):
    p70 = []
    for wie, werte in eigenschaften:
        p70.append(fbx_knoten("P", [fbx_prop_s(wie), fbx_prop_s(wie), fbx_prop_s(""),
                                    fbx_prop_s("A")] + [fbx_prop_d(w) for w in werte],
                              breit=breit))
    return fbx_knoten("Model", [fbx_prop_l(nummer), fbx_prop_s(name), fbx_prop_s("Mesh")],
                      [fbx_knoten("Properties70", [], p70, breit=breit)], breit=breit)


VIERECK = [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0]
STREIFEN = [0, 1, 2, -4]


def fbx_geometrie(nummer, ecken=None, breit=False, packen=True):
    return fbx_knoten("Geometry", [fbx_prop_l(nummer), fbx_prop_s("Geometry::"),
                                   fbx_prop_s("Mesh")],
                      [fbx_knoten("Vertices", [fbx_feld_d(ecken or VIERECK, packen)], breit=breit),
                       fbx_knoten("PolygonVertexIndex", [fbx_feld_i(STREIFEN)], breit=breit)],
                      breit=breit)


def fbx_c(kind, eltern, breit=False):
    return fbx_knoten("C", [fbx_prop_s("OO"), fbx_prop_l(kind), fbx_prop_l(eltern)], breit=breit)


# Szene A, 32-Bit-Zeiger: ein Viereck, verschoben um 10 in x. Die Ecken sind
# gepackt, die Nummern nicht - beide Wege kommen vor.
FBX_A = fbx_datei([
    fbx_knoten("Objects", [], [
        fbx_geometrie(100),
        fbx_modell(200, "Model::teil", [("Lcl Translation", [10, 0, 0])]),
    ]),
    fbx_knoten("Connections", [], [fbx_c(100, 200)]),
])

# Szene B, 64-Bit-Zeiger (Fassung 7500): um 90 Grad um z gedreht, und das
# Modell haengt an einem zweiten, das um 5 in z steht. Beides muss sich
# aufmultiplizieren.
FBX_B = fbx_datei([
    fbx_knoten("Objects", [], [
        fbx_geometrie(100, breit=True),
        fbx_modell(200, "Model::teil", [("Lcl Rotation", [0, 0, 90])], breit=True),
        fbx_modell(300, "Model::oben", [("Lcl Translation", [0, 0, 5])], breit=True),
    ], breit=True),
    fbx_knoten("Connections", [], [fbx_c(100, 200, breit=True),
                                   fbx_c(200, 300, breit=True)], breit=True),
], fassung=7500)

# Szene C: zwei Vierecke, eins ohne Modell daran - das muss liegen bleiben,
# wo es steht, und darf nicht verschwinden.
FBX_C = fbx_datei([
    fbx_knoten("Objects", [], [
        fbx_geometrie(100),
        fbx_geometrie(101, ecken=[2, 0, 0, 3, 0, 0, 3, 1, 0, 2, 1, 0]),
        fbx_modell(200, "Model::teil", [("Lcl Scaling", [2, 2, 2])]),
    ]),
    fbx_knoten("Connections", [], [fbx_c(100, 200)]),
])

FBX_TEXT = """; FBX 7.4.0 project file
Objects:  {
\tGeometry: 100, "Geometry::", "Mesh" {
\t\tVertices: *12 {
\t\t\ta: 0,0,0,1,0,0,1,1,0,
\t\t\t0,1,0
\t\t}
\t\tPolygonVertexIndex: *4 {
\t\t\ta: 0,1,2,-4
\t\t}
\t}
\tModel: 200, "Model::teil", "Mesh" {
\t\tProperties70:  {
\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A",0,0,7
\t\t}
\t}
}
Connections:  {
\tC: "OO",100,200
}
""".encode("utf-8")

ECKEN = [(x, y, z) for x in (0, 10) for y in (0, 10) for z in (0, 10)]
WUERFEL = stl_binaer([
    [(0, 0, 0), (10, 0, 0), (10, 10, 0)], [(0, 0, 0), (10, 10, 0), (0, 10, 0)],
    [(0, 0, 10), (10, 0, 10), (10, 10, 10)], [(0, 0, 10), (10, 10, 10), (0, 10, 10)],
    [(0, 0, 0), (0, 0, 10), (0, 10, 10)], [(0, 0, 0), (0, 10, 10), (0, 10, 0)],
    [(10, 0, 0), (10, 0, 10), (10, 10, 10)], [(10, 0, 0), (10, 10, 10), (10, 10, 0)],
    [(0, 0, 0), (10, 0, 0), (10, 0, 10)], [(0, 0, 0), (10, 0, 10), (0, 0, 10)],
    [(0, 10, 0), (10, 10, 0), (10, 10, 10)], [(0, 10, 0), (10, 10, 10), (0, 10, 10)],
])

HARNISCH = r"""
const window = { devicePixelRatio: 2 };
function bytes(b64) {
  const roh = Buffer.from(b64, 'base64');
  return roh.buffer.slice(roh.byteOffset, roh.byteOffset + roh.byteLength);
}
""" + "\n".join(teile) + r"""

/* Ein gefaelschtes WebGL: es rechnet nicht, es schreibt mit. */
function glAttrappe() {
  const notiert = { mvp: null, dreh: null, gezeichnet: null, sichtfeld: null };
  return {
    notiert,
    gl: {
      COLOR_BUFFER_BIT: 1, DEPTH_BUFFER_BIT: 2, TRIANGLES: 4,
      viewport: (x, y, b, h) => { notiert.sichtfeld = [x, y, b, h]; },
      clear: () => {},
      uniformMatrix4fv: (_wo, _t, m) => { notiert.mvp = Array.from(m); },
      uniformMatrix3fv: (_wo, _t, m) => { notiert.dreh = Array.from(m); },
      drawArrays: (_art, _ab, zahl) => { notiert.gezeichnet = zahl; },
    },
  };
}

function werfen(m, p) {
  // spaltenweise: m[spalte * 4 + zeile]
  const o = [0, 1, 2, 3].map((z) =>
    m[0 * 4 + z] * p[0] + m[1 * 4 + z] * p[1] + m[2 * 4 + z] * p[2] + m[3 * 4 + z]);
  return { x: o[0], y: o[1], z: o[2], w: o[3] };
}

const ergebnis = {};
const AUFGABE = JSON.parse(process.argv[2]);

/* 1. Binaer, mit "solid" im Kopf */
const zwei = netzBauen(stlLesen(bytes(AUFGABE.zwei)));
ergebnis.zwei_dreiecke = zwei.dreiecke;
ergebnis.zwei_punkte = Array.from(zwei.punkte);
ergebnis.zwei_normalen = Array.from(zwei.normalen).map((w) => Math.round(w * 1000) / 1000);

/* 2. Text-STL */
const text = netzBauen(stlLesen(bytes(AUFGABE.text)));
ergebnis.text_dreiecke = text.dreiecke;
ergebnis.text_punkte = Array.from(text.punkte);

/* 3. OBJ */
const obj = netzBauen(objLesen(bytes(AUFGABE.obj)));
ergebnis.obj_dreiecke = obj.dreiecke;
ergebnis.obj_punkte = Array.from(obj.punkte);

/* 3b. Binaer, aber die Laenge passt nicht aufs Byte */
const angehaengt = netzBauen(stlLesen(bytes(AUFGABE.anhang)));
ergebnis.anhang_dreiecke = angehaengt.dreiecke;
ergebnis.anhang_punkte = Array.from(angehaengt.punkte);
const zuviel = netzBauen(stlLesen(bytes(AUFGABE.zuviel)));
ergebnis.zuviel_dreiecke = zuviel.dreiecke;

/* 4. Namen */
ergebnis.arten = ['teil.stl', 'TEIL.STL', 'ding.obj', 'teil.fbx', 'plan.3mf', 'bild.png', 'ohne']
  .map((n) => modellArt(n));

/* 5. Der Wuerfel durch die echte Matrix */
const wuerfel = netzBauen(stlLesen(bytes(AUFGABE.wuerfel)));
ergebnis.wuerfel_mitte = wuerfel.mitte;
ergebnis.wuerfel_radius = Math.round(wuerfel.radius * 1000) / 1000;

const attrappe = glAttrappe();
const z = {
  bild: { clientWidth: 320, clientHeight: 240, width: 0, height: 0 },
  glz: { gl: attrappe.gl, mvp: 'mvp', dreh: 'dreh' },
  netz: wuerfel, seite: 0.6, hoehe: -0.5, weg: MODELL_WEG, punkt: [0, 0, 0],
};
modellZeichnen(z);
ergebnis.puffergroesse = [z.bild.width, z.bild.height];
ergebnis.sichtfeld = attrappe.notiert.sichtfeld;
ergebnis.gezeichnet = attrappe.notiert.gezeichnet;

ergebnis.drehungen = [];
for (const [seite, hoehe] of [[0.6, -0.5], [0, 0], [1.5, 1.5], [3.1, -1.5], [-2.2, 0.7]]) {
  z.seite = seite; z.hoehe = hoehe;
  modellZeichnen(z);
  const m = attrappe.notiert.mvp;
  let drin = true, vorne = true, rand = 0;
  for (const e of AUFGABE.ecken) {
    const o = werfen(m, e);
    if (o.w <= 0) vorne = false;
    const dx = Math.abs(o.x / o.w), dy = Math.abs(o.y / o.w);
    if (dx > 1 || dy > 1) drin = false;
    rand = Math.max(rand, dx, dy);
  }
  ergebnis.drehungen.push({ seite, hoehe, drin, vorne, rand: Math.round(rand * 100) / 100 });
}

/* 5b. Umschalt-Ziehen schiebt den Drehpunkt */
function mitteAufDemSchirm() {
  modellZeichnen(z);
  const o = werfen(attrappe.notiert.mvp, wuerfel.mitte);
  return [Math.round((o.x / o.w) * 1000) / 1000, Math.round((o.y / o.w) * 1000) / 1000];
}
z.seite = 0; z.hoehe = 0; z.punkt = [0, 0, 0];
ergebnis.vor_dem_schieben = mitteAufDemSchirm();
punktSchieben(z, 60, 0, 240);
ergebnis.nach_rechts = mitteAufDemSchirm();
punktSchieben(z, -60, 40, 240);        // zurueck und nach unten
ergebnis.nach_unten = mitteAufDemSchirm();

// Der Beweis, dass wirklich der Drehpunkt gewandert ist und nicht nur das
// Bild: nach einer halben Drehung muss die Mitte auf die andere Seite.
z.punkt = [0, 0, 0];
punktSchieben(z, 60, 0, 240);
const links = mitteAufDemSchirm();
z.seite = Math.PI;
const rechts = mitteAufDemSchirm();
ergebnis.halbe_drehung = [links[0], rechts[0]];

// Und nicht beliebig weit weg.
z.seite = 0; z.punkt = [0, 0, 0];
punktSchieben(z, 100000, -100000, 240);
ergebnis.weitest = Math.round(Math.sqrt(z.punkt[0] ** 2 + z.punkt[1] ** 2
                                        + z.punkt[2] ** 2) * 1000) / 1000;
ergebnis.grenze = MODELL_SCHIEB_MAX;
z.seite = 0.6; z.hoehe = -0.5; z.punkt = [0, 0, 0];

/* 5c. Platz machen, bevor die naechste Flaeche aufgeht */
const eingefroren = [];
function modellEinfrieren(m) {      // im Harnisch nur das, worauf es ankommt
  const i = MODELL_LEBENDIG.indexOf(m);
  if (i >= 0) MODELL_LEBENDIG.splice(i, 1);
  eingefroren.push(m.name);
}
for (const name of ['a', 'b', 'c', 'd']) MODELL_LEBENDIG.push({ name });
const neues = { name: 'e' };
platzSchaffen(neues);
ergebnis.platz_frei = MODELL_LEBENDIG.length < MODELL_MAX_LEBENDIG;
ergebnis.eingefroren = eingefroren.slice();
MODELL_LEBENDIG.push(neues);
ergebnis.danach = MODELL_LEBENDIG.map((m) => m.name);
ergebnis.grenze = MODELL_MAX_LEBENDIG;

/* 6. Die Drehmatrix fuer die Normalen muss die Laengen lassen */
const laengen = [0, 1, 2].map((s) => {
  const d = attrappe.notiert.dreh;
  return Math.round(Math.sqrt(d[s * 3] ** 2 + d[s * 3 + 1] ** 2 + d[s * 3 + 2] ** 2) * 1000) / 1000;
});
ergebnis.drehlaengen = laengen;

/* 7. FBX - das muss warten, das Entpacken laeuft ueber einen Strom. */
(async () => {
  const rund = (f) => Array.from(f).map((w) => Math.round(w * 1000) / 1000);
  ergebnis.fbx_a = rund(await fbxLesen(bytes(AUFGABE.fbx_a)));
  ergebnis.fbx_b = rund(await fbxLesen(bytes(AUFGABE.fbx_b)));
  ergebnis.fbx_c = rund(await fbxLesen(bytes(AUFGABE.fbx_c)));
  ergebnis.fbx_text = rund(await fbxLesen(bytes(AUFGABE.fbx_text)));
  console.log(JSON.stringify(ergebnis));
})();
"""

aufgabe = json.dumps({
    "zwei": base64.b64encode(ZWEI).decode(),
    "text": base64.b64encode(TEXT_STL).decode(),
    "obj": base64.b64encode(OBJ).decode(),
    "wuerfel": base64.b64encode(WUERFEL).decode(),
    "anhang": base64.b64encode(ANHANG).decode(),
    "fbx_a": base64.b64encode(FBX_A).decode(),
    "fbx_b": base64.b64encode(FBX_B).decode(),
    "fbx_c": base64.b64encode(FBX_C).decode(),
    "fbx_text": base64.b64encode(FBX_TEXT).decode(),
    "zuviel": base64.b64encode(bytes(ZU_VIEL)).decode(),
    "ecken": ECKEN,
})

ordner = Path(tempfile.mkdtemp(prefix="modell-"))
(ordner / "pruef.js").write_text(HARNISCH, encoding="utf-8")
if shutil.which("node"):
    befehl = ["node", str(ordner / "pruef.js"), aufgabe]
elif shutil.which("docker"):
    (ordner / "aufgabe.json").write_text(aufgabe, encoding="utf-8")
    befehl = ["docker", "run", "--rm", "-v", f"{ordner}:/p:ro", "node:alpine", "sh", "-c",
              'node /p/pruef.js "$(cat /p/aufgabe.json)"']
else:
    print("  --  weder node noch docker da, die Modelle sind ungeprueft")
    sys.exit(0)

lauf = subprocess.run(befehl, capture_output=True, text=True)
if lauf.returncode != 0:
    print(lauf.stdout)
    print(lauf.stderr)
    sys.exit(1)
d = json.loads(lauf.stdout.strip().splitlines()[-1])

print("\nSTL, binaer")
pruefe("zwei Dreiecke, obwohl der Kopf mit \"solid\" anfaengt",
       d["zwei_dreiecke"] == 2, d["zwei_dreiecke"])
pruefe("die Ecken stehen richtig",
       d["zwei_punkte"] == [0, 0, 0, 1, 0, 0, 0, 1, 0,
                            0, 0, 0, 0, 1, 0, 1, 0, 0], d["zwei_punkte"])
# Die Datei behauptet (9,9,9) fuer beide Dreiecke. Wer sie glaubt, sieht nichts.
pruefe("die falsche Normale aus der Datei wird nicht geglaubt",
       9 not in d["zwei_normalen"], d["zwei_normalen"])
pruefe("sie wird aus den Ecken gerechnet - vorne (0,0,1)",
       d["zwei_normalen"][0:9] == [0, 0, 1] * 3, d["zwei_normalen"][0:9])
pruefe("und beim verkehrt herum gewickelten Dreieck (0,0,-1)",
       d["zwei_normalen"][9:18] == [0, 0, -1] * 3, d["zwei_normalen"][9:18])

print("\nWenn die Laenge nicht aufs Byte passt")
pruefe("hinten angehaengter Text macht die Datei nicht zu Text",
       d["anhang_dreiecke"] == 1, d["anhang_dreiecke"])
pruefe("die Ecken stimmen trotzdem",
       d["anhang_punkte"] == [0, 0, 0, 1, 0, 0, 0, 1, 0], d["anhang_punkte"])
pruefe("zaehlt der Kopf zu viel, gilt was wirklich dasteht",
       d["zuviel_dreiecke"] == 1, d["zuviel_dreiecke"])

print("\nSTL als Text")
pruefe("ein Dreieck", d["text_dreiecke"] == 1, d["text_dreiecke"])
pruefe("auch 2e0 wird als 2 gelesen",
       d["text_punkte"] == [0, 0, 0, 2, 0, 0, 0, 2, 0], d["text_punkte"])

print("\nOBJ")
pruefe("das Viereck wird zu zwei Dreiecken, die drei f-Zeilen zu vier",
       d["obj_dreiecke"] == 4, d["obj_dreiecke"])
pruefe("das Viereck als Faecher: 1-2-3 und 1-3-4",
       d["obj_punkte"][0:18] == [0, 0, 0, 1, 0, 0, 1, 1, 0,
                                 0, 0, 0, 1, 1, 0, 0, 1, 0], d["obj_punkte"][0:18])
pruefe("die Form 7/3/2 nimmt die erste Zahl",
       d["obj_punkte"][18:27] == [0, 0, 0, 1, 0, 0, 1, 1, 0], d["obj_punkte"][18:27])
pruefe("negative Nummern zaehlen vom Ende",
       d["obj_punkte"][27:36] == [0, 0, 0, 1, 0, 0, 1, 1, 0], d["obj_punkte"][27:36])

print("\nWelche Dateien ueberhaupt")
pruefe("stl, obj und fbx, gross oder klein geschrieben",
       d["arten"] == ["stl", "stl", "obj", "fbx", None, None, None], d["arten"])

print("\nFBX")
# Ein Viereck wird zu zwei Dreiecken, die letzte Ecke steht negativ da.
VIERECK_ROH = [0, 0, 0, 1, 0, 0, 1, 1, 0,
               0, 0, 0, 1, 1, 0, 0, 1, 0]
pruefe("binaer 7400, gepacktes Feld, Viereck zu zwei Dreiecken",
       len(d["fbx_a"]) == 18, len(d["fbx_a"]))
pruefe("die Lage des Modells wird angewendet (10 nach x)",
       d["fbx_a"] == [w + (10 if i % 3 == 0 else 0) for i, w in enumerate(VIERECK_ROH)],
       d["fbx_a"])
# 90 Grad um z: aus (1,0) wird (0,1). Dazu das Elternmodell: 5 nach oben.
pruefe("binaer 7500 mit 64-Bit-Zeigern wird gelesen", len(d["fbx_b"]) == 18, d["fbx_b"])
pruefe("Drehung und Elternmodell multiplizieren sich auf",
       d["fbx_b"][0:9] == [0, 0, 5, 0, 1, 5, -1, 1, 5], d["fbx_b"][0:9])
pruefe("zwei Geometrien kommen beide mit, auch die ohne Modell",
       len(d["fbx_c"]) == 36, len(d["fbx_c"]))
pruefe("die skalierte liegt doppelt so weit draussen",
       d["fbx_c"][0:9] == [0, 0, 0, 2, 0, 0, 2, 2, 0], d["fbx_c"][0:9])
pruefe("die ohne Modell bleibt, wo sie ist",
       d["fbx_c"][18:27] == [2, 0, 0, 3, 0, 0, 3, 1, 0], d["fbx_c"][18:27])
pruefe("die Textfassung ergibt dasselbe, ueber mehrere Zeilen verteilt",
       d["fbx_text"] == [w + (7 if i % 3 == 2 else 0) for i, w in enumerate(VIERECK_ROH)],
       d["fbx_text"])

print("\nDie Matrix")
pruefe("die Mitte des Wuerfels ist seine Mitte",
       d["wuerfel_mitte"] == [5, 5, 5], d["wuerfel_mitte"])
# Kugel um den Wuerfel: halbe Raumdiagonale, 10*sqrt(3)/2 = 8.66
pruefe("der Radius ist die halbe Raumdiagonale",
       abs(d["wuerfel_radius"] - 8.660) < 0.002, d["wuerfel_radius"])
pruefe("die Zeichenflaeche folgt der Bildschirmdichte",
       d["puffergroesse"] == [640, 480] and d["sichtfeld"] == [0, 0, 640, 480], d)
pruefe("gezeichnet werden alle 36 Eckpunkte", d["gezeichnet"] == 36, d["gezeichnet"])
for dr in d["drehungen"]:
    pruefe(f"in der Drehung {dr['seite']}/{dr['hoehe']} liegt der Wuerfel vor der Kamera",
           dr["vorne"], dr)
    pruefe(f"... und ganz im Bild (Rand {dr['rand']})", dr["drin"], dr)
pruefe("das Teil fuellt das Bild auch aus (nicht winzig in der Mitte)",
       max(dr["rand"] for dr in d["drehungen"]) > 0.45,
       [dr["rand"] for dr in d["drehungen"]])
print("\nPlatz fuer die naechste Flaeche")
# Der Browser gibt nur eine Handvoll 3D-Flaechen je Seite her. Wer erst
# aufmacht und dann aufraeumt, bekommt beim einen zu viel gar keine mehr -
# und dann waere das Modell endgueltig weg, obwohl es eben noch lief.
pruefe("vor dem Aufmachen ist wieder Platz", d["platz_frei"], d)
pruefe("eingefroren wird das aelteste, nicht das neue",
       d["eingefroren"] == ["a"], d["eingefroren"])
pruefe("und danach leben genau so viele, wie erlaubt sind",
       len(d["danach"]) == d["grenze"] and d["danach"][-1] == "e", d["danach"])

print("\nDen Drehpunkt schieben")
pruefe("ohne Schieben sitzt die Mitte in der Mitte",
       d["vor_dem_schieben"] == [0, 0], d["vor_dem_schieben"])
pruefe("nach rechts gezogen steht das Teil rechts, nicht hoeher",
       d["nach_rechts"][0] > 0.1 and abs(d["nach_rechts"][1]) < 0.001, d["nach_rechts"])
pruefe("nach unten gezogen steht es unten",
       d["nach_unten"][1] < -0.1 and abs(d["nach_unten"][0]) < 0.001, d["nach_unten"])
# Waere nur das Bild verschoben, bliebe die Mitte nach der halben Drehung an
# derselben Stelle stehen.
pruefe("nach einer halben Drehung liegt die Mitte auf der anderen Seite",
       d["halbe_drehung"][0] > 0.1 and d["halbe_drehung"][1] < -0.1, d["halbe_drehung"])
pruefe("der Drehpunkt laeuft nicht beliebig weit weg",
       abs(d["weitest"] - d["grenze"]) < 0.001, d)

pruefe("die Drehmatrix der Normalen laesst die Laengen",
       all(abs(w - 1) < 0.002 for w in d["drehlaengen"]), d["drehlaengen"])

shutil.rmtree(ordner, ignore_errors=True)
# Zwei Sachen, die sich hier ohne Browser nicht laufen lassen - geprueft wird
# deshalb nur, dass sie dastehen.
print("\nStatisch geprueft")
pruefe("auch ohne Standbild bleibt etwas Anklickbares stehen",
       "className: 'standbild leerbild'" in mappe
       and "ruhig.addEventListener('click'" in mappe)
# Ohne das zieht ein abgebrochener Zeiger weiter, ohne dass noch eine Taste
# gedrueckt ist. Die Stellen sehen im Fenster anders aus als in der
# Serverfassung (dort haengt jede einzeln, hier stehen sie in Listen) -
# geprueft wird deshalb, dass jede der drei ueberhaupt abbricht.
for wer, muster in (("das Modell", r"bild\.addEventListener\('pointercancel'"),
                    ("die Kaesten", r"'pointerup', 'pointercancel'"),
                    ("der Stift", r"'pointerup', 'pointercancel'\]")):
    pruefe(f"abgebrochener Zeiger: {wer} hoert auf",
           bool(re.search(muster, mappe)))

print()
if fehler:
    print(f"{len(fehler)} Prüfungen gescheitert")
    sys.exit(1)
print("STL, OBJ und FBX werden richtig gelesen")
