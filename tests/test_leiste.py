"""Tut die Formatleiste, was auf den Knöpfen steht?

    .venv/bin/python tests/test_leiste.py

Die Leiste rechnet nichts selbst - sie ruft die Funktionen der gemeinsamen
Oberfläche. Genau deshalb kann sie lautlos nichts tun: ein Knopf, der einen
Befehl mit dem falschen Namen schickt, sieht aus wie jeder andere. Hier läuft
sie deshalb in einem nachgebauten DOM, und geprüft wird, was unten ankommt.

Nicht geprüft: wie sie aussieht. Das sieht Lucy zuerst.
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
                     (r"^const FL_VORLAGEN = \[.*?\];", "FL_VORLAGEN"),
                     (r"^const FL_KATEGORIEN = \[.*?\];", "FL_KATEGORIEN"),
                     (r"^const FL_GROESSEN = \[.*?\];", "FL_GROESSEN"),
                     (r"^let flPinsel = [^\n]*$", "flPinsel"),
                     (r"^function flBild\(.*?^\}", "flBild"),
                     (r"^const FL_EINZUG_RAUS = [^;]*;", "FL_EINZUG_RAUS"),
                     (r"^const FL_EINZUG_REIN = [^;]*;", "FL_EINZUG_REIN"),
                     (r"^const FL_ZEILEN = [^;]*;", "FL_ZEILEN"),
                     (r"^const FL_PUNKTLISTE = flBild\(.*?\);", "FL_PUNKTLISTE"),
                     (r"^const FL_NUMMERNLISTE = flBild\(.*?\);", "FL_NUMMERNLISTE"),
                     (r"^const FL_SCHILD = [^;]*;", "FL_SCHILD"),
                     (r"^const FL_PINSEL = [^;]*;", "FL_PINSEL"),
                     (r"^function flBefehl\(.*?^\}", "flBefehl"),
                     (r"^function flSchriftenSpiegeln\(.*?^\}", "flSchriftenSpiegeln"),
                     (r"^function flTaste\(.*?^\}", "flTaste"),
                     (r"^function flKlappe\(.*?^\}", "flKlappe"),
                     (r"^function flZeichenSetzen\(.*?^\}", "flZeichenSetzen"),
                     (r"^function flPinselNehmen\(.*?^\}", "flPinselNehmen"),
                     (r"^function flPinselZeigen\(.*?^\}", "flPinselZeigen"),
                     (r"^function flFarben\(.*?^\}", "flFarben"),
                     (r"^const FL_NUMMERN = \[.*?\];", "FL_NUMMERN"),
                     (r"^const FL_ZEICHEN = \[.*?\];", "FL_ZEICHEN"),
                     (r"^const FL_ZAEHLER = \{.*?\};", "FL_ZAEHLER"),
                     (r"^const FL_ZIFFERN = \{.*?\};", "FL_ZIFFERN"),
                     (r"^function nrTeile\(.*?^\}", "nrTeile"),
                     (r"^function nrProbe\(.*?^\}", "nrProbe"),
                     (r"^function listenRegeln\(.*?^\}", "listenRegeln"),
                     (r"^function listeUm\(.*?^\}", "listeUm"),
                     (r"^function artSetzen\(.*?^\}", "artSetzen"),
                     (r"^function flNummerSetzen\(.*?$", "flNummerSetzen"),
                     (r"^function flPunktSetzen\(.*?$", "flPunktSetzen"),
                     (r"^function nrKachel\(.*?^\}", "nrKachel"),
                     (r"^function azKachel\(.*?^\}", "azKachel"),
                     (r"^function flGeteilt\(.*?^\}", "flGeteilt"),
                     (r"^function flGalerie\(.*?^\}", "flGalerie"),
                     (r"^function formatleisteBauen\(.*?^\}", "formatleisteBauen"),
                     (r"^function formatleisteFrischen\(.*?^\}", "formatleisteFrischen")):
    treffer = re.search(muster, mappe, re.S | re.M)
    pruefe(f"{name} steht in mappe.js", bool(treffer))
    if treffer:
        teile.append(treffer.group(0))
if fehler:
    sys.exit(1)

HARNISCH = r"""
/* Ein DOM, so klein wie moeglich - mit den Waehlern, die die Leiste benutzt. */
class Knoten {
  constructor(art) {
    this.art = art; this.kinder = []; this.zuhoerer = {};
    this.style = {}; this.dataset = {}; this.hidden = false;
    this.klassen = new Set(); this.merkmale = {};
    this.eigenerText = ''; this.id = ''; this.title = ''; this.eltern = null;
    this.label = '';
    const selbst = this;
    this.classList = {
      add: (c) => selbst.klassen.add(c),
      remove: (c) => selbst.klassen.delete(c),
      contains: (c) => selbst.klassen.has(c),
      toggle: (c, an) => { if (an) selbst.klassen.add(c); else selbst.klassen.delete(c); },
    };
  }
  get tagName() { return this.art.toUpperCase(); }
  // select.options ist im Browser flach - auch ueber Gruppen hinweg.
  get options() { return this.alle().slice(1).filter((k) => k.art === 'option'); }
  // Ein Auswahlfeld hat den Wert der gewaehlten Moeglichkeit - im Browser
  // rechnet das der Browser aus, hier muss es dastehen.
  get value() {
    if (this._wert !== undefined) return this._wert;
    if (this.art !== 'select') return '';
    const o = this.options.find((x) => x.selected) || this.options[0];
    return o ? o.value : '';
  }
  set value(w) { this._wert = w; }
  get children() { return this.kinder; }
  get parentElement() { return this.eltern; }
  get firstChild() { return this.kinder[0] || null; }
  set className(w) { for (const c of String(w).split(/\s+/)) if (c) this.klassen.add(c); }
  get className() { return [...this.klassen].join(' '); }
  set innerHTML(w) { this.eigenerText = String(w).replace(/<[^>]*>/g, ''); }
  get innerHTML() { return this.eigenerText; }
  get textContent() {
    return this.eigenerText + this.kinder.map((k) => k.textContent).join('');
  }
  set textContent(w) {
    for (const k of this.kinder) k.eltern = null;
    this.kinder = []; this.eigenerText = String(w);
  }
  append(...was) {
    for (const k of was) {
      if (typeof k === 'string') { this.eigenerText += k; continue; }
      if (k.eltern) k.remove();
      k.eltern = this; this.kinder.push(k);
    }
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
  getBoundingClientRect() {
    return { left: 0, top: 0, right: 20, bottom: 20, width: 340, height: 220 };
  }
  setAttribute(name, wert) { this.merkmale[name] = wert; }
  getAttribute(name) { return this.merkmale[name]; }
  addEventListener(art, f) { (this.zuhoerer[art] = this.zuhoerer[art] || []).push(f); }
  klick() {
    for (const f of this.zuhoerer.click || []) {
      f({ preventDefault() {}, stopPropagation() {}, target: this });
    }
  }
  alle() { return this.kinder.reduce((a, k) => a.concat(k.alle()), [this]); }
  passt(w) {
    if (w === '.fl-liste') return this.klassen.has('fl-liste');
    if (w === '.fl-kachel') return this.klassen.has('fl-kachel');
    if (w === '.fl-art') return this.klassen.has('fl-art');
    if (w === '.fl-groesse') return this.klassen.has('fl-groesse');
    if (w === '.fl-taste[data-stand]') return this.klassen.has('fl-taste') && !!this.dataset.stand;
    if (w === '.fl-taste[data-stand="pinsel"]') {
      return this.klassen.has('fl-taste') && this.dataset.stand === 'pinsel';
    }
    if (w === '#farben button[data-farbe]') {
      return this.art === 'button' && !!this.dataset.farbe;
    }
    if (w === '#minialt select[data-befehl="fontName"]'
        || w === '#minileiste select[data-befehl="fontName"]') {
      return this.art === 'select' && this.dataset.befehl === 'fontName';
    }
    throw new Error('unbekannter Waehler: ' + w);
  }
  querySelector(w) { return this.alle().slice(1).find((k) => k.passt(w)) || null; }
  querySelectorAll(w) { return this.alle().slice(1).filter((k) => k.passt(w)); }
}

const wurzel = new Knoten('body');
const befehle = [];            // was unten ankommt
const document = {
  createElement: (a) => new Knoten(a),
  querySelector: (w) => wurzel.querySelector(w),
  querySelectorAll: (w) => wurzel.querySelectorAll(w),
  execCommand: (befehl, zeig, wert) => { befehle.push(['execCommand', befehl, wert]); return true; },
  queryCommandState: (b) => stand[b] === true,
  queryCommandValue: (b) => stand[b] || '',
  addEventListener: () => {},
};
let stand = {};
function aufAuswahl(befehl, wert) { befehle.push([befehl, wert === undefined ? null : wert]); }
function hervorheben() { befehle.push(['hervorheben', null]); }
function hervorhebungWeg() { befehle.push(['hervorhebungWeg', null]); }
const window = { getSelection: () => auswahl, innerWidth: 1200, innerHeight: 800 };
function gemerkt() { befehle.push(['gemerkt', null]); }
let auswahl = null;
const console = { error: () => {} };

/* Die Farben und die Schriftliste stehen drueben - hier nachgebaut. */
const farbkasten = new Knoten('span');
farbkasten.id = 'farben';
for (const [farbe, name] of [['#1f1d1a', 'Standard'], ['#b23b2e', 'Rot'],
                             ['#2f7d32', 'Grün']]) {
  const k = new Knoten('button');
  k.dataset.farbe = farbe;
  k.title = name;
  farbkasten.append(k);
}
const schriften = new Knoten('select');
schriften.dataset.befehl = 'fontName';
function schrift(wohin, name) {
  const o = new Knoten('option');
  o.value = name;
  o.textContent = name;
  wohin.append(o);
}
schrift(schriften, 'Standard');
const gruppe = new Knoten('optgroup');
gruppe.label = '★ Favoriten';
schriften.append(gruppe);
schrift(gruppe, 'DejaVu Sans');
schrift(schriften, 'Liberation Serif');
wurzel.append(farbkasten, schriften);
""" + "\n".join(teile) + r"""

const ergebnis = {};
const leiste = formatleisteBauen();
wurzel.append(leiste);

const tasten = leiste.alle().filter((k) => k.klassen.has('fl-taste'));
ergebnis.reihen = leiste.kinder.filter((k) => k.klassen.has('fl-reihe')).length;
ergebnis.groesse_anfang = leiste.querySelector('.fl-groesse').value;
ergebnis.schriften_anfang = leiste.querySelector('.fl-art').options.map((o) => o.value);
ergebnis.gruppen = leiste.querySelector('.fl-art').kinder
  .filter((k) => k.art === 'optgroup').map((k) => k.label);
ergebnis.knoepfe = tasten.map((k) => k.title);

function druecke(titel) {
  befehle.length = 0;
  const k = tasten.find((t) => t.title === titel);
  if (!k) return ['KEIN KNOPF ' + titel];
  k.klick();
  return befehle.slice();
}

ergebnis.fett = druecke('Fett (Strg+B)');
ergebnis.kursiv = druecke('Kursiv (Strg+I)');
ergebnis.unterstrichen = druecke('Unterstrichen (Strg+U)');
ergebnis.durch = druecke('Durchgestrichen');
ergebnis.marker = druecke('Hervorheben');
ergebnis.liste = druecke('Aufzählung');
ergebnis.nummern = druecke('Nummerierung');
ergebnis.einzug = druecke('Einzug vergrößern');
ergebnis.raus = druecke('Einzug verkleinern');
ergebnis.sauber = druecke('Formatierung entfernen');

/* Klappmenues: aufmachen, Eintrag anklicken, sehen was ankommt */
function klappe(titel, welcher) {
  befehle.length = 0;
  const k = tasten.find((t) => t.title === titel);
  k.klick();
  const liste = leiste.querySelector('.fl-liste');
  if (!liste) return { eintraege: null, befehle: [] };
  const namen = liste.kinder.map((e) => e.textContent.trim());
  liste.kinder[welcher].klick();
  return { eintraege: namen, befehle: befehle.slice() };
}

const vorlage = klappe('Formatvorlage', 1);
ergebnis.vorlagen = vorlage.eintraege;
ergebnis.vorlage_befehl = vorlage.befehle;
const farbe = klappe('Schriftfarbe', 1);
ergebnis.farben = farbe.eintraege;
ergebnis.farbe_befehl = farbe.befehle;

/* Aufgabe und Kategorie schreiben ein Zeichen in den Text */
const feld = new Knoten('div');
feld.nodeType = 1;              // im Browser: Element oder Textknoten
feld.klassen.add('text');
feld.closest = (w) => (w === '[contenteditable]' ? feld : null);
auswahl = {
  rangeCount: 1, isCollapsed: false, anchorNode: feld,
  getRangeAt: () => ({
    startContainer: feld, startOffset: 0,
    cloneRange() { return { collapse() {}, startContainer: feld }; },
  }),
  removeAllRanges() {}, addRange() {},
};
befehle.length = 0;
tasten.find((t) => t.title === 'Aufgabe (zum Abhaken)').klick();
ergebnis.aufgabe = befehle.slice();
const kat = klappe('Kategorie', 2);
ergebnis.kategorien = kat.eintraege;
ergebnis.kategorie_befehl = kat.befehle;

/* Der Pinsel: einmal merken, dann auf die naechste Markierung */
stand = { bold: true, italic: false, fontName: 'DejaVu Sans', fontSize: '5',
          foreColor: '#b23b2e' };
const pinsel = tasten.find((t) => t.title === 'Format übertragen');
pinsel.klick();
ergebnis.pinsel_an = pinsel.klassen.has('an');
befehle.length = 0;
// so wie es der Zuhoerer am Koerper tut
(function anwenden() {
  const p = flPinsel;
  flPinsel = null;
  flBefehl('removeFormat');
  for (const was of ['bold', 'italic', 'underline', 'strikeThrough']) if (p[was]) flBefehl(was);
  if (p.fontName) flBefehl('fontName', p.fontName);
  if (p.fontSize) flBefehl('fontSize', p.fontSize);
  if (p.foreColor) flBefehl('foreColor', p.foreColor);
})();
ergebnis.pinsel_befehle = befehle.slice();

/* Zustand anzeigen */
stand = { bold: true, insertUnorderedList: true, fontName: 'DejaVu Sans', fontSize: '5' };
formatleisteFrischen(leiste);
ergebnis.an = tasten.filter((k) => k.klassen.has('an')).map((k) => k.title);
ergebnis.schriftliste = leiste.querySelector('.fl-art').options.map((o) => o.value);
ergebnis.schriftwahl = leiste.querySelector('.fl-art').value;
ergebnis.groessenwahl = leiste.querySelector('.fl-groesse').value;

/* Knopf und Pfeil gehoeren zusammen */
ergebnis.paare = leiste.alle().filter((k) => k.klassen.has('fl-geteilt'))
  .map((k) => k.kinder.map((x) => x.title));
ergebnis.listenbild = [FL_PUNKTLISTE.slice(0, 4), FL_NUMMERNLISTE.slice(0, 4)];
ergebnis.pfeilnur = tasten.find((t) => t.title === 'Nummerierungsbibliothek').textContent;

/* Die Nummerierungsbibliothek */
ergebnis.probe = nrProbe('(a)');
ergebnis.regeln = listenRegeln();

const galerie = tasten.find((t) => t.title === 'Nummerierungsbibliothek');
galerie.klick();
const kasten = leiste.querySelector('.fl-liste');
const kacheln = kasten.querySelectorAll('.fl-kachel');
ergebnis.kacheln = kacheln.length;
ergebnis.erste = kacheln[0].textContent;
ergebnis.zweite = kacheln[1].textContent;

/* In einer Liste: nur die Art setzen, keine zweite Liste anlegen */
const ol = new Knoten('ol');
const zeile = new Knoten('li');
zeile.nodeType = 1;
ol.append(zeile);
zeile.closest = (w) => (w === 'ol' ? ol : null);
auswahl = { rangeCount: 1, getRangeAt: () => ({ startContainer: zeile }) };
befehle.length = 0;
kacheln.find((k) => k.textContent.startsWith('(1)')).klick();
ergebnis.in_liste = befehle.slice();
ergebnis.gesetzt = ol.merkmale['data-art'] || null;

/* Ohne Liste: erst anlegen, dann die Art setzen - so wie es der Browser tut */
let schonListe = false;
zeile.closest = (w) => (w === 'ol' && schonListe ? ol : null);
ol.merkmale = {};
befehle.length = 0;
galerie.klick();
const kacheln2 = leiste.querySelector('.fl-liste').querySelectorAll('.fl-kachel');
const alterBefehl = aufAuswahl;
aufAuswahl = function (befehl, wert) {
  befehle.push([befehl, wert === undefined ? null : wert]);
  if (befehl === 'insertOrderedList') schonListe = true;
};
kacheln2.find((k) => k.textContent.startsWith('a)')).klick();
ergebnis.ohne_liste = befehle.slice();
ergebnis.gesetzt2 = ol.merkmale['data-art'] || null;

/* Dasselbe fuer die Aufzaehlungszeichen */
const zeichen = tasten.find((t) => t.title === 'Aufzählungszeichenbibliothek');
zeichen.klick();
const zkacheln = leiste.querySelector('.fl-liste').querySelectorAll('.fl-kachel');
ergebnis.zkacheln = zkacheln.length;
ergebnis.zerste = zkacheln[0].textContent;
ergebnis.zzweite = zkacheln[1].textContent;
const ul = new Knoten('ul');
const zeile2 = new Knoten('li');
zeile2.nodeType = 1;
ul.append(zeile2);
zeile2.closest = (w) => (w === 'ul' ? ul : null);
auswahl = { rangeCount: 1, getRangeAt: () => ({ startContainer: zeile2 }) };
befehle.length = 0;
zkacheln.find((k) => k.textContent === '★').klick();
ergebnis.in_punkten = befehle.slice();
ergebnis.zgesetzt = ul.merkmale['data-art'] || null;

/* "Keine" macht die Liste wieder weg */
auswahl = { rangeCount: 1, getRangeAt: () => ({ startContainer: zeile }) };
schonListe = true;
ol.merkmale = {};
befehle.length = 0;
galerie.klick();
leiste.querySelector('.fl-liste').querySelectorAll('.fl-kachel')[0].klick();
ergebnis.keine = befehle.slice();
ergebnis.keine_art = ol.merkmale['data-art'] || null;
aufAuswahl = alterBefehl;

console.log = (...a) => process.stdout.write(a.join(' ') + '\n');
process.stdout.write(JSON.stringify(ergebnis) + '\n');
"""

ordner = Path(tempfile.mkdtemp(prefix="leiste-"))
(ordner / "pruef.js").write_text(HARNISCH, encoding="utf-8")
if shutil.which("node"):
    befehl = ["node", str(ordner / "pruef.js")]
elif shutil.which("docker"):
    befehl = ["docker", "run", "--rm", "-v", f"{ordner}:/p:ro", "node:alpine",
              "node", "/p/pruef.js"]
else:
    print("  --  weder node noch docker da, die Leiste ist ungeprueft")
    sys.exit(0)

lauf = subprocess.run(befehl, capture_output=True, text=True)
if lauf.returncode != 0:
    print(lauf.stdout)
    print(lauf.stderr)
    sys.exit(1)
d = json.loads(lauf.stdout.strip().splitlines()[-1])

print("\nDer Aufbau")
pruefe("zwei Reihen", d["reihen"] == 2, d["reihen"])
# 12 ist die Groesse, in der geschrieben wird - vorher stand hier 8, die
# erste der Liste.
pruefe("die Größe steht auf 12, nicht auf der ersten der Liste",
       d["groesse_anfang"] == '3', d["groesse_anfang"])
pruefe("und die Schriftliste ist gleich beim Bauen da",
       d["schriften_anfang"] == ['Standard', 'DejaVu Sans', 'Liberation Serif'],
       d["schriften_anfang"])
# Die Favoriten stehen drueben in einer eigenen Gruppe. Ohne sie waeren sie
# irgendwo in der Liste - gerade die, die man sucht.
pruefe("die Gruppen kommen mit", d["gruppen"] == ['★ Favoriten'], d["gruppen"])
ERWARTET = ['Formatvorlage', 'Einzug verkleinern', 'Einzug vergrößern',
            'Aufgabe (zum Abhaken)', 'Kategorie', 'Fett (Strg+B)', 'Kursiv (Strg+I)',
            'Unterstrichen (Strg+U)', 'Durchgestrichen', 'Hervorheben', 'Schriftfarbe',
            'Aufzählung', 'Aufzählungszeichenbibliothek', 'Nummerierung',
            'Nummerierungsbibliothek', 'Format übertragen', 'Formatierung entfernen']
pruefe("alle Knöpfe, in dieser Reihenfolge", d["knoepfe"] == ERWARTET, d["knoepfe"])

print("\nWas unten ankommt")
for was, soll in (("fett", [["bold", None]]), ("kursiv", [["italic", None]]),
                  ("unterstrichen", [["underline", None]]),
                  ("durch", [["strikeThrough", None]]),
                  ("marker", [["hervorheben", None]]),
                  ("liste", [["insertUnorderedList", None]]),
                  ("nummern", [["insertOrderedList", None]]),
                  ("einzug", [["indent", None]]), ("raus", [["outdent", None]])):
    pruefe(f"{was} schickt {soll[0][0]}", d[was] == soll, d[was])
pruefe("Formatierung entfernen räumt auch die Hervorhebung weg",
       d["sauber"] == [["removeFormat", None], ["hervorhebungWeg", None]], d["sauber"])

print("\nDie Klappmenüs")
pruefe("Formatvorlagen stehen drin",
       d["vorlagen"] == ['Normal', 'Überschrift 1', 'Überschrift 2', 'Überschrift 3',
                         'Zitat', 'Code'], d["vorlagen"])
pruefe("und setzen einen Block", d["vorlage_befehl"] == [["formatBlock", "<h1>"]],
       d["vorlage_befehl"])
pruefe("die Farben kommen aus der Leiste drüben",
       d["farben"] == ['Standard', 'Rot', 'Grün'], d["farben"])
pruefe("und setzen die Schriftfarbe",
       d["farbe_befehl"] == [["foreColor", "#b23b2e"]], d["farbe_befehl"])

print("\nAufgabe und Kategorie")
# Ein Zeichen im Text, keine eigene Auszeichnung: alles andere faellt beim
# Speichern wieder heraus.
pruefe("die Aufgabe schreibt ein Kästchen in den Text",
       d["aufgabe"] == [["execCommand", "insertText", "☐ "]], d["aufgabe"])
pruefe("die Kategorien stehen zur Wahl",
       d["kategorien"] == ['☐Aufgabe', '★Wichtig', '⚑Fahne',
                           '✔Erledigt', '✘Verworfen'], d["kategorien"])
pruefe("und schreiben ihr Zeichen",
       d["kategorie_befehl"] == [["execCommand", "insertText", "⚑ "]],
       d["kategorie_befehl"])

print("\nFormat übertragen")
pruefe("nach dem Klick ist der Pinsel geladen", d["pinsel_an"])
pruefe("und gibt genau das weiter, was an der Stelle galt",
       d["pinsel_befehle"] == [["removeFormat", None], ["bold", None],
                               ["fontName", "DejaVu Sans"], ["fontSize", "5"],
                               ["foreColor", "#b23b2e"]], d["pinsel_befehle"])

print("\nListe und Bibliothek sind ein Knopf")
# Vorher standen vier Knoepfe nebeneinander, und keiner sagte, dass je zwei
# dasselbe meinen.
pruefe("je Listenart ein Paar aus Knopf und Pfeil",
       d["paare"] == [['Aufzählung', 'Aufzählungszeichenbibliothek'],
                      ['Nummerierung', 'Nummerierungsbibliothek']], d["paare"])
pruefe("der Knopf zeigt eine Liste, nicht nur sein Zeichen",
       d["listenbild"] == ['<svg', '<svg'], d["listenbild"])
pruefe("am Pfeil steht nichts weiter", d["pfeilnur"] == '▾', d["pfeilnur"])

print("\nDie Nummerierungsbibliothek")
pruefe("die Vorschau zeigt, was spaeter dasteht",
       d["probe"] == ['(a)', '(b)', '(c)'], d["probe"])
# '(1)' ist die achte Art - Klammer davor, Klammer und Leerzeichen dahinter.
pruefe("daraus wird die Regel im Stylesheet",
       '@counter-style nz7 { system: extends decimal; prefix: "("; suffix: ") "; }'
       in d["regeln"] and 'ol[data-art="(1)"] { list-style-type: nz7; }' in d["regeln"],
       d["regeln"][:200])
pruefe("16 Arten und 'Keine'", d["kacheln"] == 17, d["kacheln"])
pruefe("'Keine' steht vorn", d["erste"] == 'Keine', d["erste"])
pruefe("dann die erste Art", d["zweite"] == '1.2.3.', d["zweite"])
pruefe("in einer Liste wird nur die Art gesetzt",
       d["in_liste"] == [["gemerkt", None]] and d["gesetzt"] == '(1)',
       (d["in_liste"], d["gesetzt"]))
pruefe("ohne Liste wird erst eine angelegt",
       d["ohne_liste"] == [["insertOrderedList", None], ["gemerkt", None]]
       and d["gesetzt2"] == 'a)', (d["ohne_liste"], d["gesetzt2"]))
pruefe("'Keine' nimmt die Nummerierung wieder weg",
       d["keine"] == [["insertOrderedList", None]] and d["keine_art"] is None,
       (d["keine"], d["keine_art"]))

print("\nDie Aufzählungszeichenbibliothek")
pruefe("35 Zeichen und 'Keine'", d["zkacheln"] == 36, d["zkacheln"])
pruefe("'Keine' steht auch hier vorn", d["zerste"] == 'Keine', d["zerste"])
pruefe("dann der volle Punkt", d["zzweite"] == '●', d["zzweite"])
pruefe("in einer Aufzählung wird nur das Zeichen gesetzt",
       d["in_punkten"] == [["gemerkt", None]] and d["zgesetzt"] == '★',
       (d["in_punkten"], d["zgesetzt"]))
# cyclic mit genau einem Zeichen: das steht dann vor jeder Zeile.
pruefe("und daraus wird die Regel im Stylesheet",
       '@counter-style az0 { system: cyclic; symbols: "●"; suffix: " "; }'
       in d["regeln"] and 'ul[data-art="●"] { list-style-type: az0; }' in d["regeln"])

print("\nWas gerade gilt")
pruefe("zeigt sich am Knopf", sorted(d["an"]) == sorted(['Fett (Strg+B)', 'Aufzählung']),
       d["an"])
pruefe("die Schriftliste kommt von drüben",
       d["schriftliste"] == ['Standard', 'DejaVu Sans', 'Liberation Serif'],
       d["schriftliste"])
pruefe("und beide Felder zeigen den Stand an der Markierung",
       d["schriftwahl"] == 'DejaVu Sans' and d["groessenwahl"] == '5',
       (d["schriftwahl"], d["groessenwahl"]))

print("\nBeim Rechtsklick ist die schwebende Leiste zu viel")
# Sie steht sonst neben dem Menue, das dieselben Knoepfe noch einmal zeigt.
# Der Fall, an dem die erste Fassung scheiterte: drueben holt das Loslassen
# der Maus die Leiste zurueck - und das kommt nach dem Zumachen.
teile2 = []
for muster, name in ((r"^function minileisteWeg\(.*?^\}", "minileisteWeg"),
                     (r"^function minileisteHueten\(.*?^\}", "minileisteHueten"),
                     (r"^function rechtsmenueFrischen\(.*?^\}", "rechtsmenueFrischen")):
    treffer = re.search(muster, mappe, re.S | re.M)
    pruefe(f"{name} steht in mappe.js", bool(treffer))
    if treffer:
        teile2.append(treffer.group(0))

ZWEITER = r"""
class MutationObserver {
  constructor(f) { this.f = f; }
  observe(knoten) { knoten.wecker = this.f; }
}
/* Nur so viel Knoten, wie es braucht: ein hidden, das Bescheid sagt. */
class Knoten {
  constructor() {
    this.versteckt = true; this.wecker = null; this.style = {};
    this.klassen = new Set(); this.textContent = '';
    const selbst = this;
    this.classList = {
      add: (c) => selbst.klassen.add(c),
      contains: (c) => selbst.klassen.has(c),
      toggle: (c, an) => { if (an) selbst.klassen.add(c); else selbst.klassen.delete(c); },
    };
  }
  get hidden() { return this.versteckt; }
  set hidden(wert) {
    const anders = this.versteckt !== wert;
    this.versteckt = wert;
    if (anders && this.wecker) this.wecker();
  }
  querySelector() { return null; }
  getBoundingClientRect() { return { width: 236, height: 300 }; }
}
const leiste = new Knoten();
const menue = new Knoten();
const block = new Knoten();
const link = new Knoten();
const wer = new Knoten();
const document = {
  getElementById: (id) => ({ minileiste: leiste, rechtsmenue: menue,
                             'rm-format': block, 'rm-link': link,
                             'rm-wer': wer })[id] || null,
};
const window = { MutationObserver, innerWidth: 1200, innerHeight: 800 };
let rmImText = false;
function formatleisteFrischen() {}
function rmFusszeile() { return 'lucy_wolf am 01.11.2026, 16:10'; }
""" + "\n".join(teile2) + r"""

const ergebnis = {};
minileisteHueten();

// Markiert: die Leiste geht auf, kein Menue im Weg
leiste.hidden = false;
ergebnis.beim_markieren = !leiste.hidden;

// Rechtsklick: Menue auf, Leiste weg
menue.hidden = false;
minileisteWeg();
ergebnis.beim_rechtsklick = leiste.hidden;

// und sie bleibt weg, auch wenn drueben jemand sie wieder aufmacht
leiste.hidden = false;
ergebnis.bleibt_weg = leiste.hidden;

// Menue zu: dann gelten wieder die Regeln von drueben
menue.hidden = true;
leiste.hidden = false;
ergebnis.danach_wieder = !leiste.hidden;
/* Rechtsklick in den Text und ins Leere: beide Male dasselbe Menue */
menue.hidden = false;
rmImText = true;
rechtsmenueFrischen(40, 40);
ergebnis.im_text = { leiste: !block.hidden, blass: block.klassen.has('rm-aus'),
                     link: !link.hidden };
rmImText = false;
rechtsmenueFrischen(40, 40);
ergebnis.im_leeren = { leiste: !block.hidden, blass: block.klassen.has('rm-aus'),
                       link: !link.hidden, link_blass: link.klassen.has('rm-aus') };
ergebnis.fuss = wer.textContent;
// Am rechten Rand darf das Menue nicht hinausragen
rechtsmenueFrischen(1190, 790);
ergebnis.ecke = [menue.style.left, menue.style.top];

process.stdout.write(JSON.stringify(ergebnis) + '\n');
"""

ordner2 = Path(tempfile.mkdtemp(prefix="leiste2-"))
(ordner2 / "pruef.js").write_text(ZWEITER, encoding="utf-8")
befehl2 = list(befehl)
befehl2[-1] = befehl2[-1].replace(str(ordner), str(ordner2))
if befehl2[0] == "docker":
    befehl2[befehl2.index("-v") + 1] = f"{ordner2}:/p:ro"
lauf2 = subprocess.run(befehl2, capture_output=True, text=True)
if lauf2.returncode != 0:
    print(lauf2.stdout)
    print(lauf2.stderr)
    sys.exit(1)
z = json.loads(lauf2.stdout.strip().splitlines()[-1])
pruefe("beim Markieren ist sie da", z["beim_markieren"])
pruefe("beim Rechtsklick geht sie weg", z["beim_rechtsklick"])
pruefe("und bleibt weg, solange das Menü steht", z["bleibt_weg"])
pruefe("ist das Menü zu, darf sie wieder", z["danach_wieder"])

print("\nDas Menü sieht im Leeren aus wie im Text")
# Vorher fehlten dort Leiste und Link - das Menue war halb so hoch und sprang
# einem unter der Maus weg.
pruefe("im Text: Leiste und Link da, nichts blass",
       z["im_text"] == {"leiste": True, "blass": False, "link": True}, z["im_text"])
pruefe("im Leeren: dieselben Teile, nur blass",
       z["im_leeren"] == {"leiste": True, "blass": True, "link": True,
                          "link_blass": True}, z["im_leeren"])
pruefe("die Fußzeile steht drin", z["fuss"] != "", z["fuss"])
pruefe("am Rand rutscht das Menü ins Bild",
       z["ecke"] == ["956px", "492px"], z["ecke"])
shutil.rmtree(ordner2, ignore_errors=True)

shutil.rmtree(ordner, ignore_errors=True)
print()
if fehler:
    print(f"{len(fehler)} Prüfungen gescheitert")
    sys.exit(1)
print("Die Formatleiste tut, was auf den Knöpfen steht")
