"""Tut das Menü am rechten Bandende, was draufsteht?

    .venv/bin/python tests/test_band.py

Vier Einstellungen, die alle dasselbe Band betreffen und sich gegenseitig
überschreiben können - und eine davon (Vollbild) nimmt den Knopf weg, mit
dem man sie gesetzt hat. Genau die Sorte Umschalterei, bei der eine
Kombination still nicht mehr zurückgeht.

Geprüft wird deshalb am Ergebnis: welche Klassen stehen hinterher am
Dokument, steht der Rückweg aus dem Vollbild da, und kommt man mit Esc
wieder heraus.
"""
import json
import re
import shutil
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
for muster, name in ((r"^function el\(.*?^\}", "el"),
                     (r"^const BAND_LAYOUT = [^;]*;", "BAND_LAYOUT"),
                     (r"^const BAND_ZEIGEN = [^;]*;", "BAND_ZEIGEN"),
                     (r"^const BANDTAFEL = \[.*?^\];", "BANDTAFEL"),
                     (r"^function bandStand\(.*?^\}", "bandStand"),
                     (r"^function bandWoerterBauen\(.*?^\}", "bandWoerterBauen"),
                     (r"^function bandAnwenden\(.*?^\}", "bandAnwenden"),
                     (r"^function bandTafelZu\(.*?^\}", "bandTafelZu"),
                     (r"^function bandTafelZeigen\(.*?^\}", "bandTafelZeigen"),
                     (r"^function bandMenueBauen\(.*?^\}", "bandMenueBauen"),
                     (r"^function flTaste\(.*?^\}", "flTaste"),
                     (r"^function ueberlaufEinrichten\(.*?^\}", "ueberlaufEinrichten")):
    treffer = re.search(muster, mappe, re.S | re.M)
    pruefe(f"{name} steht in mappe.js", bool(treffer))
    if treffer:
        teile.append(treffer.group(0))
if fehler:
    sys.exit(1)

HARNISCH = r"""
class Knoten {
  constructor(art) {
    this.art = art; this.kinder = []; this.zuhoerer = {};
    this.id = ''; this.title = ''; this.eigenerText = ''; this.eltern = null;
    this.hidden = false; this.style = {}; this.klassen = new Set();
    this.dataset = {};
    const selbst = this;
    this.classList = {
      add: (c) => selbst.klassen.add(c),
      remove: (c) => selbst.klassen.delete(c),
      contains: (c) => selbst.klassen.has(c),
      toggle: (c, an) => { if (an) selbst.klassen.add(c); else selbst.klassen.delete(c); },
    };
  }
  set className(w) { for (const c of String(w).split(/\s+/)) if (c) this.klassen.add(c); }
  get className() { return [...this.klassen].join(' '); }
  set textContent(w) {
    for (const k of this.kinder) k.eltern = null;
    this.kinder = []; this.eigenerText = String(w);
  }
  get textContent() {
    return this.eigenerText + this.kinder.map((k) => k.textContent).join('');
  }
  append(...was) {
    for (const k of was) { if (k.eltern) k.remove(); k.eltern = this; this.kinder.push(k); }
  }
  insertBefore(neu, davor) {
    if (neu.eltern) neu.remove();
    neu.eltern = this;
    const i = davor ? this.kinder.indexOf(davor) : -1;
    if (i < 0) this.kinder.push(neu); else this.kinder.splice(i, 0, neu);
  }
  remove() {
    if (this.eltern) this.eltern.kinder = this.eltern.kinder.filter((k) => k !== this);
    this.eltern = null;
  }
  addEventListener(art, f) { (this.zuhoerer[art] = this.zuhoerer[art] || []).push(f); }
  klick() {
    for (const f of this.zuhoerer.click || []) f({ stopPropagation() {} });
  }
  getBoundingClientRect() { return { left: 900, right: 980, top: 10, bottom: 32,
                                     width: 240, height: 180 }; }
  alle() { return this.kinder.reduce((a, k) => a.concat(k.alle()), [this]); }
  get children() { return this.kinder; }
  get childNodes() { return this.kinder; }
  get firstChild() { return this.kinder[0] || null; }
  get parentNode() { return this.eltern; }
  passt(w) {
    if (w === '.fl-reihe') return this.klassen.has('fl-reihe');
    if (w === '.fl-wort') return this.klassen.has('fl-wort');
    if (w === '.fl-pfeil') return this.klassen.has('fl-pfeil');
    if (w === '.fl-taste') return this.klassen.has('fl-taste');
    if (w === '.bt-punkt') return this.klassen.has('bt-punkt');
    if (w === '#werkzeuge .formatleiste') return this.klassen.has('formatleiste');
    return false;
  }
  querySelector(w) { return this.alle().slice(1).find((k) => k.passt(w)) || null; }
  querySelectorAll(w) { return this.alle().slice(1).filter((k) => k.passt(w)); }
}

const body = new Knoten('body');
const bandmenue = new Knoten('button');
bandmenue.id = 'bandmenue';
const bandtafel = new Knoten('div');
bandtafel.id = 'bandtafel';
bandtafel.hidden = true;

/* Eine Leiste mit zwei Knöpfen - einer davon mit Pfeil, damit sich prüfen
   lässt, ob das Wort davor landet und nicht dahinter. */
const leiste = new Knoten('div');
leiste.className = 'formatleiste';
function taste(titel, mitPfeil) {
  const k = new Knoten('button');
  k.className = 'fl-taste';
  k.title = titel;
  if (mitPfeil) {
    const p = new Knoten('span');
    p.className = 'fl-pfeil';
    p.textContent = '▾';
    k.append(p);
  }
  leiste.append(k);
  return k;
}
taste('Fett (Strg+B)', false);
taste('Kategorie', true);
body.append(leiste);

/* Eine Leiste, deren Breite sich steuern laesst: jedes Kind ist 50 breit,
   der Platz kommt von aussen. So laesst sich "das Fenster wird schmaler"
   nachstellen, ohne ein Fenster zu haben. */
const KNOPFBREIT = 50;
let platz = 1000;
class Reihe extends Knoten {
  get clientWidth() { return platz; }
  get scrollWidth() {
    return this.kinder.filter((k) => !k.hidden).length * KNOPFBREIT;
  }
}
const tasten = [];
const document = {
  createElement: (a) => new Knoten(a),
  body,
  querySelector: (w) => (w === '#werkzeuge .formatleiste' ? leiste : null),
  // bandWoerterBauen() geht seit dem Reiter Zeichnen über mehrere Leisten.
  // Hier gibt es nur die eine - das reicht, geprüft wird, was sie bekommt.
  querySelectorAll: (w) => (w.indexOf('.formatleiste') >= 0 ? [leiste] : []),
  addEventListener: (art, f) => { (tasten[art] = tasten[art] || []).push(f); },
};
function $(w) {
  if (w === '#bandmenue') return bandmenue;
  if (w === '#bandtafel') return bandtafel;
  if (w === '#bandraus') return body.alle().slice(1).find((k) => k.id === 'bandraus') || null;
  return null;
}
let messer = null;
class ResizeObserver {
  constructor(f) { messer = f; }
  observe() {}
}
function messenJetzt() { if (messer) messer(); }
const window = { innerWidth: 1200, innerHeight: 800, ResizeObserver };
const merkzettel = {};
const merker = {
  holen: (k, standard) => (k in merkzettel ? merkzettel[k] : standard),
  legen: (k, w) => { merkzettel[k] = w; },
};
let gemessen = 0;
function flaecheMessen() { gemessen += 1; }
""" + "\n".join(teile) + r"""

const ergebnis = {};
const klassen = () => [...body.klassen].sort();
function punkt(name) {
  return bandtafel.alle().slice(1)
    .find((k) => k.klassen.has('bt-punkt') && k.textContent.indexOf(name) >= 0) || null;
}
function waehlen(name) {
  bandTafelZeigen();
  const p = punkt(name);
  if (!p) return 'KEIN PUNKT ' + name;
  p.klick();
  return klassen();
}

bandMenueBauen();
ergebnis.anfang = klassen();

/* --- Der Ueberlauf bei schmalem Fenster --------------------------------- */
const bandleiste = new Knoten('div');
bandleiste.className = 'formatleiste fl-band';
const bandreihe = new Reihe('div');
bandreihe.className = 'fl-reihe';
const namen = ['Fett', 'Kursiv', 'Unterstrichen', 'Trenner', 'Liste', 'Nummern'];
for (const n of namen) {
  const k = new Knoten('button');
  k.className = n === 'Trenner' ? 'fl-trenner' : 'fl-taste';
  k.title = n;
  bandreihe.append(k);
}
bandleiste.append(bandreihe);
ueberlaufEinrichten(bandleiste);
const mehr = bandreihe.kinder.find((k) => k.klassen.has('fl-mehr'));
const topf = bandleiste.kinder.find((k) => k.klassen.has('fl-topf'));
function stand() {
  return { reihe: bandreihe.kinder.filter((k) => k !== mehr).map((k) => k.title),
           topf: topf.kinder.map((k) => k.title),
           mehr: !mehr.hidden };
}
// So breit, dass alles passt (7 x 50 = 350 mit dem Pfeil)
platz = 1000;
messenJetzt();
ergebnis.breit = stand();
// Jetzt schmal: nur noch vier Plaetze
platz = 200;
messenJetzt();
ergebnis.schmal = stand();
// Noch schmaler
platz = 100;
messenJetzt();
ergebnis.sehrschmal = stand();
// Und wieder breit - alles muss zurueck, in der alten Reihenfolge
platz = 1000;
messenJetzt();
ergebnis.wiederbreit = stand();
// Unsichtbar (Breite 0) darf nichts verschoben werden
platz = 0;
messenJetzt();
ergebnis.unsichtbar = stand();
platz = 1000;
messenJetzt();
ergebnis.raus_anfangs_weg = $('#bandraus') ? $('#bandraus').hidden : null;

/* Die Tafel: was drinsteht und wo der Haken sitzt */
bandTafelZeigen();
ergebnis.tafel = bandtafel.alle().slice(1)
  .filter((k) => k.klassen.has('bt-kopf') || k.klassen.has('bt-punkt'))
  .map((k) => k.textContent);
ergebnis.haken = bandtafel.alle().slice(1).filter((k) => k.klassen.has('bt-punkt'))
  .map((k) => (k.textContent.charAt(0) === '✓' ? k.textContent.slice(1) : ''));
bandTafelZu();
ergebnis.tafel_zu = bandtafel.hidden;

/* Umschalten */
ergebnis.klassisch = waehlen('Klassisches');
ergebnis.woerter = leiste.querySelectorAll('.fl-wort').map((k) => k.textContent);
// Das Wort gehoert vor den Pfeil, nicht dahinter.
const mitPfeil = leiste.querySelectorAll('.fl-taste')[1];
ergebnis.reihenfolge = mitPfeil.kinder.map((k) => k.className);
// Zweimal umschalten darf das Wort nicht doppeln.
waehlen('Vereinfachtes');
ergebnis.einfach = klassen();
waehlen('Klassisches');
ergebnis.woerter2 = leiste.querySelectorAll('.fl-wort').length;

ergebnis.reiter = waehlen('Nur Registerkarten');
ergebnis.voll = waehlen('Vollbildmodus');
ergebnis.raus_da = $('#bandraus') ? !$('#bandraus').hidden : null;

/* Esc holt aus dem Vollbild zurueck - ohne das waere es eine Falle, denn
   der Pfeil ist dann weg. */
for (const f of tasten.keydown || []) f({ key: 'Escape' });
ergebnis.nach_esc = klassen();
ergebnis.raus_wieder_weg = $('#bandraus') ? $('#bandraus').hidden : null;

/* Und der Knopf tut dasselbe */
waehlen('Vollbildmodus');
$('#bandraus').klick();
ergebnis.nach_knopf = klassen();

/* Gemerkt wird es auch */
ergebnis.gemerkt = { layout: merkzettel['notizmappe.bandlayout'],
                     zeigen: merkzettel['notizmappe.bandzeigen'] };
ergebnis.gemessen = gemessen > 0;

process.stdout.write(JSON.stringify(ergebnis) + '\n');
"""

ordner = Path(tempfile.mkdtemp(prefix="band-"))
(ordner / "pruef.js").write_text(HARNISCH, encoding="utf-8")
if shutil.which("node"):
    befehl = ["node", str(ordner / "pruef.js")]
elif shutil.which("docker"):
    befehl = ["docker", "run", "--rm", "-v", f"{ordner}:/p:ro", "node:alpine",
              "node", "/p/pruef.js"]
else:
    print("  --  weder node noch docker da, das Bandmenue ist ungeprueft")
    sys.exit(0)

lauf = subprocess.run(befehl, capture_output=True, text=True)
if lauf.returncode != 0:
    print(lauf.stdout)
    print(lauf.stderr)
    sys.exit(1)
d = json.loads(lauf.stdout.strip().splitlines()[-1])

print("\nWie es anfängt")
# Ohne Eintrag: vereinfacht und immer da - so wie es vorher war.
pruefe("ohne Eintrag steht nichts am Dokument", d["anfang"] == [], d["anfang"])
pruefe("und der Rückweg aus dem Vollbild ist versteckt", d["raus_anfangs_weg"] is True,
       d["raus_anfangs_weg"])

print("\nDas Menü")
pruefe("zwei Überschriften, fünf Punkte",
       [z.replace('✓', '') for z in d["tafel"]]
       == ['Menüband Layout', 'Klassisches Menüband',
           'Vereinfachtes Menüband', 'Menüband anzeigen',
           'Vollbildmodus', 'Nur Registerkarten anzeigen',
           'Menüband immer anzeigen'], d["tafel"])
pruefe("der Haken steht bei dem, was gerade gilt",
       d["haken"] == ['', 'Vereinfachtes Menüband', '', '', 'Menüband immer anzeigen'],
       d["haken"])
pruefe("und es geht wieder zu", d["tafel_zu"])

print("\nKlassisch und vereinfacht")
pruefe("klassisch setzt die Klasse", d["klassisch"] == ['band-klassisch'], d["klassisch"])
# Der Text kommt aus dem title; was in Klammern steht, gehört nicht unter
# einen Knopf.
pruefe("an jedem Knopf steht das Wort, ohne Tastenkürzel",
       d["woerter"] == ['Fett', 'Kategorie'], d["woerter"])
pruefe("und es steht vor dem Pfeil, nicht dahinter",
       d["reihenfolge"] == ['fl-wort fl-autowort', 'fl-pfeil'], d["reihenfolge"])
# fl-autowort trennt das selbst angehängte Wort von einem eingebauten:
# im vereinfachten Band verschwindet nur das selbst angehängte.
pruefe("das angehängte Wort ist als solches erkennbar",
       all('fl-autowort' in k for k in d["reihenfolge"][:1]), d["reihenfolge"])
pruefe("vereinfacht nimmt die Klasse weg", d["einfach"] == [], d["einfach"])
# Die Wörter bleiben hängen und werden nur ausgeblendet - zweimal gebaut
# stünden sie doppelt da.
pruefe("und zweimal umschalten doppelt nichts", d["woerter2"] == 2, d["woerter2"])

print("\nNur Registerkarten und Vollbild")
# Layout und Anzeige sind unabhängig: wer klassisch eingestellt hat und
# dann ins Vollbild geht, hat beim Zurückkommen wieder klassisch.
pruefe("nur Registerkarten setzt seine Klasse",
       'band-reiter' in d["reiter"] and 'band-voll' not in d["reiter"], d["reiter"])
# Die beiden Anzeigearten schließen einander aus - sonst wäre das Band weg
# und die Reiter trotzdem aufklappbar.
pruefe("Vollbild löst sie ab, statt dazuzukommen",
       'band-voll' in d["voll"] and 'band-reiter' not in d["voll"], d["voll"])
pruefe("das Layout bleibt dabei stehen", 'band-klassisch' in d["voll"], d["voll"])
pruefe("und der Rückweg steht da", d["raus_da"])
# Ohne Rückweg wäre es eine Falle: im Vollbild ist auch der Pfeil weg.
pruefe("Esc holt zurück",
       'band-voll' not in d["nach_esc"] and 'band-reiter' not in d["nach_esc"],
       d["nach_esc"])
pruefe("und der Rückweg verschwindet wieder", d["raus_wieder_weg"] is True,
       d["raus_wieder_weg"])
pruefe("der Knopf tut dasselbe", 'band-voll' not in d["nach_knopf"], d["nach_knopf"])

print("\nWenn das Fenster schmaler wird")
# Vorher brach die Leiste um; bei einem schmalen Fenster wurde das Band
# drei- und vierzeilig und nahm der Seite den Platz, um den es geht.
pruefe("breit ist alles in der Reihe",
       d["breit"]["reihe"] == ['Fett', 'Kursiv', 'Unterstrichen', 'Trenner',
                               'Liste', 'Nummern']
       and not d["breit"]["topf"] and not d["breit"]["mehr"], d["breit"])
pruefe("schmal wandert das Letzte unter den Pfeil",
       d["schmal"]["mehr"] and d["schmal"]["topf"]
       and d["schmal"]["reihe"][0] == 'Fett', d["schmal"])
# Die Reihenfolge muss stimmen: was zuletzt wegfiel, steht im Topf vorn.
pruefe("und zwar von hinten, in der richtigen Reihenfolge",
       d["schmal"]["topf"] == sorted(d["schmal"]["topf"],
                                     key=lambda n: ['Fett', 'Kursiv', 'Unterstrichen',
                                                    'Trenner', 'Liste',
                                                    'Nummern'].index(n)),
       d["schmal"])
pruefe("noch schmaler wandert mehr hinein",
       len(d["sehrschmal"]["topf"]) > len(d["schmal"]["topf"]),
       (d["schmal"]["topf"], d["sehrschmal"]["topf"]))
# Ein Trenner am Anfang des Topfes trennt nichts mehr.
pruefe("ein Trenner steht nicht vorn im Topf",
       not d["sehrschmal"]["topf"] or d["sehrschmal"]["topf"][0] != 'Trenner',
       d["sehrschmal"])
# Das ist der Teil, der bei so etwas schiefgeht: zurück muss auch gehen.
pruefe("wieder breit holt alles zurück, in der alten Reihenfolge",
       d["wiederbreit"] == d["breit"], d["wiederbreit"])
# Die Leiste des nicht gewählten Reiters ist 0 breit - dann darf nichts
# wandern, sonst steht sie beim Hinwechseln leer da.
pruefe("unsichtbar wird nichts verschoben", d["unsichtbar"] == d["breit"],
       d["unsichtbar"])

# Untereinander, nicht nebeneinander umgebrochen. Das steht nur im
# Stylesheet, also wird es dort geprüft - sonst fällt es beim nächsten
# Umbauen still wieder auf nebeneinander zurück.
stil = (WURZEL / "app/oberflaeche/stil.css").read_text(encoding="utf-8")
topf = re.search(r"^\.fl-topf \{(.*?)^\}", stil, re.S | re.M)
print("\nDer Topf steht untereinander")
pruefe("es gibt eine Regel für .fl-topf", bool(topf))
pruefe("eine Spalte", bool(topf) and "flex-direction: column" in topf.group(1),
       topf.group(1) if topf else "")
pruefe("und kein Umbruch nebeneinander",
       bool(topf) and "flex-wrap" not in topf.group(1),
       topf.group(1) if topf else "")
# Die festen Breiten der Auswahlfelder stehen weiter unten in der Datei.
# Stünde die Aufhebung davor, gewänne die feste Breite - gleiche Stärke,
# später gewinnt.
pruefe("die Aufhebung der festen Breiten steht nach den Breiten",
       stil.index(".fl-band .fl-topf > *") > stil.index(".fl-band .fl-groesse"))

print("\nGemerkt")
# Wer das Band wegklappt, will es beim nächsten Start nicht wieder vorfinden.
pruefe("beides steht im Merker",
       d["gemerkt"] == {"layout": "klassisch", "zeigen": "immer"}, d["gemerkt"])
pruefe("und die Fläche wird neu vermessen", d["gemessen"])

shutil.rmtree(ordner, ignore_errors=True)
print()
if fehler:
    print(f"{len(fehler)} Prüfungen gescheitert")
    sys.exit(1)
print("Das Bandmenü tut, was draufsteht")
