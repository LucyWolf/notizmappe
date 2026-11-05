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
                     (r"^const FL_MARKERSTIFT = [^;]*;", "FL_MARKERSTIFT"),
                     (r"^const FL_MARKERFARBEN = \[.*?\];", "FL_MARKERFARBEN"),
                     (r"^function markerSetzen\(.*?^\}", "markerSetzen"),
                     (r"^function flFarbtaste\(.*?^\}", "flFarbtaste"),
                     (r"^const FL_SCHERE = [^;]*;", "FL_SCHERE"),
                     (r"^const FL_KOPIE = [^;]*;", "FL_KOPIE"),
                     (r"^const FL_KLEMME = [^;]*;", "FL_KLEMME"),
                     (r"^const FL_AUS_ATTR = [^;]*;", "FL_AUS_ATTR"),
                     (r"^const FL_ZA_ATTR = [^;]*;", "FL_ZA_ATTR"),
                     (r"^function flAusBild\(.*?^\}", "flAusBild"),
                     (r"^const FL_AUSRICHTUNG = \[.*?\];", "FL_AUSRICHTUNG"),
                     (r"^const FL_ABSTAENDE = \[.*?\];", "FL_ABSTAENDE"),
                     (r"^const FL_ABSTANDBILD = [^;]*;", "FL_ABSTANDBILD"),
                     (r"^const FL_BLOECKE = [^;]*;", "FL_BLOECKE"),
                     (r"^function flBloecke\(.*?^\}", "flBloecke"),
                     (r"^function flBlockSetzen\(.*?^\}", "flBlockSetzen"),
                     (r"^function flAusrichten\(.*?$", "flAusrichten"),
                     (r"^function flAbstand\(.*?$", "flAbstand"),
                     (r"^async function flAblage\(.*?^\}", "flAblage"),
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
                     (r"^function flTafelStellen\(.*?^\}", "flTafelStellen"),
                     (r"^function flGalerie\(.*?^\}", "flGalerie"),
                     (r"^const FL_TABELLE_MAX = [^;]*;", "FL_TABELLE_MAX"),
                     (r"^const FL_SYMBOLE = \[.*?\];", "FL_SYMBOLE"),
                     (r"^const FL_TABELLE = [^;]*;", "FL_TABELLE"),
                     (r"^const FL_TEXTFELD = [^;]*;", "FL_TEXTFELD"),
                     (r"^const FL_BILD = [^;]*;", "FL_BILD"),
                     (r"^const FL_KETTE = [^;]*;", "FL_KETTE"),
                     (r"^const FL_KALENDER = [^;]*;", "FL_KALENDER"),
                     (r"^function flTafel\(.*?^\}", "flTafel"),
                     (r"^function tabelleEinfuegen\(.*?^\}", "tabelleEinfuegen"),
                     (r"^function flTabellenraster\(.*?^\}", "flTabellenraster"),
                     (r"^function flZeichentafel\(.*?^\}", "flZeichentafel"),
                     (r"^function datumText\(.*?^\}", "datumText"),
                     (r"^function altKlick\(.*?^\}", "altKlick"),
                     (r"^function dateiWaehlen\(.*?^\}", "dateiWaehlen"),
                     (r"^function textfeldEinfuegen\(.*?^\}", "textfeldEinfuegen"),
                     (r"^const FORMEL_WORTE = \{.*?^\};", "FORMEL_WORTE"),
                     (r"^const FORMEL_GROSS = [^;]*;", "FORMEL_GROSS"),
                     (r"^const FORMEL_ZEICHEN2 = \{.*?\};", "FORMEL_ZEICHEN2"),
                     (r"^const FORMEL_ZEICHEN1 = [^;]*;", "FORMEL_ZEICHEN1"),
                     (r"^const FORMEL_STRICH = \[.*?\];", "FORMEL_STRICH"),
                     (r"^function formelSchutz\(.*?^\}", "formelSchutz"),
                     (r"^function formelEins\(.*?^\}", "formelEins"),
                     (r"^function formelTeilen\(.*?^\}", "formelTeilen"),
                     (r"^function formelLesen\(.*?^\}", "formelLesen"),
                     (r"^function formelMathML\(.*?^\}", "formelMathML"),
                     (r"^function formelFensterZeigen\(.*?^\}", "formelFensterZeigen"),
                     (r"^function flWort\(.*?^\}", "flWort"),
                     (r"^function mitWort\(.*?^\}", "mitWort"),
                     (r"^function einfuegeleisteBauen\(.*?^\}", "einfuegeleisteBauen"),
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
  removeAttribute(name) { delete this.merkmale[name]; }
  getAttribute(name) { return this.merkmale[name]; }
  addEventListener(art, f) { (this.zuhoerer[art] = this.zuhoerer[art] || []).push(f); }
  klick() {
    for (const f of this.zuhoerer.click || []) {
      f({ preventDefault() {}, stopPropagation() {}, target: this });
    }
  }
  alle() { return this.kinder.reduce((a, k) => a.concat(k.alle()), [this]); }
  // Im Browser laeuft closest den Baum hinauf. Einzelne Tests setzen es von
  // Hand; das ueberschreibt diese Fassung dann.
  closest(w) {
    let k = this;
    while (k) {
      let traf = false;
      try { traf = k.passt(w); } catch (f) { traf = false; }
      if (traf) return k;
      k = k.eltern;
    }
    return null;
  }
  passt(w) {
    // Der Waehler mit allen Blocknamen - flBloecke() sucht damit.
    if (w.indexOf('blockquote') >= 0) {
      return w.split(',').indexOf(this.art) >= 0;
    }
    if (w === '.text') return this.klassen.has('text');
    if (w === '.formatleiste') return this.klassen.has('formatleiste');
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
  // Fuer die Einfuegen-Leiste: sie klickt die alten, versteckten Knoepfe an.
  getElementById: (id) => bekannt[id] || null,
};
let stand = {};
const bekannt = {};
// Die Flaeche, auf der ein Schreibbereich landet.
const buehne = { scrollLeft: 0, scrollTop: 0 };
const zoom = 1;
const RASTER = 8;
function kastenNeu(x, y) { befehle.push(['kastenNeu', x + ',' + y]); }
function linkSetzen() { befehle.push(['linkSetzen', null]); }
let letzterKasten = null;
// Das Formelfenster steht in index.html; hier reicht, dass $ nichts findet.
const $ = (w) => null;
function aufAuswahl(befehl, wert) { befehle.push([befehl, wert === undefined ? null : wert]); }
function hervorheben(f) { befehle.push(['hervorheben', f || null]); }
function hervorhebungWeg() { befehle.push(['hervorhebungWeg', null]); }
const window = { getSelection: () => auswahl, innerWidth: 1200, innerHeight: 800 };
function gemerkt() { befehle.push(['gemerkt', null]); }
let auswahl = null;
const console = { error: () => {} };
function sagen(text) { befehle.push(['sagen', text]); }
function melden(text) { befehle.push(['melden', text]); }
// Die Zwischenablage des Systems. Darf sie nicht, faellt die Leiste auf den
// alten Befehl zurueck - genau das soll hier pruefbar sein.
let ablageDarf = true;
let ablageInhalt = 'aus der Ablage';
const navigator = {
  clipboard: {
    writeText(t) {
      if (!ablageDarf) return Promise.reject(new Error('nein'));
      befehle.push(['ablage-schreiben', t]);
      return Promise.resolve();
    },
    readText() {
      if (!ablageDarf) return Promise.reject(new Error('nein'));
      return Promise.resolve(ablageInhalt);
    },
  },
};

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

ergebnis.marker = druecke('Hervorheben');
ergebnis.liste = druecke('Aufzählung');
ergebnis.nummern = druecke('Nummerierung');
ergebnis.einzug = druecke('Einzug vergrößern');
ergebnis.raus = druecke('Einzug verkleinern');
ergebnis.sauber = druecke('Formatierung entfernen');

/* Klappmenues: aufmachen, Eintrag anklicken, sehen was ankommt */
function klappe(titel, welcher, wo, wotasten) {
  befehle.length = 0;
  const k = (wotasten || tasten).find((t) => t.title === titel);
  k.klick();
  const liste = (wo || leiste).querySelector('.fl-liste');
  if (!liste) return { eintraege: null, befehle: [] };
  const namen = liste.kinder.map((e) => e.textContent.trim());
  liste.kinder[welcher].klick();
  return { eintraege: namen, befehle: befehle.slice() };
}

const vorlage = klappe('Formatvorlage', 1);
ergebnis.vorlagen = vorlage.eintraege;
ergebnis.vorlage_befehl = vorlage.befehle;
const farbe = klappe('Andere Schriftfarbe', 1);
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

/* --- Dieselbe Leiste oben im Band ---------------------------------------- */
const bandleiste = formatleisteBauen({ band: true });
wurzel.append(bandleiste);
const bandtasten = bandleiste.alle().filter((k) => k.klassen.has('fl-taste'));
ergebnis.bandreihen = bandleiste.kinder.filter((k) => k.klassen.has('fl-reihe')).length;
ergebnis.bandknoepfe = bandtasten.map((k) => k.title);
ergebnis.bandklasse = bandleiste.klassen.has('fl-band');
befehle.length = 0;
bandtasten.find((t) => t.title === 'Durchgestrichen').klick();
ergebnis.banddurch = befehle.slice();

/* --- Die beiden Farbknoepfe: Balken zeigt, was ein Klick nimmt ----------- */
const markerknopf = bandtasten.find((t) => t.title === 'Hervorheben');
const farbknopf = bandtasten.find((t) => t.title === 'Schriftfarbe');
ergebnis.balken_anfang = [markerknopf.kinder.map((k) => k.style.background),
                          farbknopf.kinder.map((k) => k.style.background)];
ergebnis.balkenklasse = [markerknopf.klassen.has('fl-farbtaste'),
                         farbknopf.klassen.has('fl-farbtaste')];
befehle.length = 0;
markerknopf.klick();
ergebnis.marker_klick = befehle.slice();
befehle.length = 0;
farbknopf.klick();
ergebnis.farbe_klick = befehle.slice();
// Eine andere Farbe waehlen: faerbt gleich und merkt sie sich fuer den Knopf
const markerwahl = klappe('Andere Farbe zum Hervorheben', 1, bandleiste, bandtasten);
ergebnis.markerfarben = markerwahl.eintraege;
ergebnis.marker_gewaehlt = markerwahl.befehle;
ergebnis.balken_danach = markerknopf.kinder.map((k) => k.style.background);
befehle.length = 0;
markerknopf.klick();
ergebnis.marker_nochmal = befehle.slice();
klappe('Andere Schriftfarbe', 2, bandleiste, bandtasten);
befehle.length = 0;
farbknopf.klick();
ergebnis.farbe_nochmal = befehle.slice();
ergebnis.farbbalken_danach = farbknopf.kinder.map((k) => k.style.background);

/* --- Ausrichtung und Zeilenabstand haengen am Absatz --------------------- */
const feld2 = new Knoten('div');
feld2.klassen.add('text');
feld2.nodeType = 1;
const absatz1 = new Knoten('p'); absatz1.nodeType = 1;
const absatz2 = new Knoten('p'); absatz2.nodeType = 1;
feld2.append(absatz1, absatz2);
let nurErster = false;
auswahl = {
  rangeCount: 1,
  isCollapsed: false,
  toString: () => 'markiert',
  getRangeAt: () => ({
    startContainer: absatz1,
    intersectsNode: (b) => (nurErster ? b === absatz1 : true),
  }),
};
befehle.length = 0;
bandtasten.find((t) => t.title === 'Zentriert').klick();
ergebnis.aus_befehle = befehle.slice();
ergebnis.aus = [absatz1.merkmale['data-aus'] || null, absatz2.merkmale['data-aus'] || null];

// Nur der markierte Absatz, nicht gleich die ganze Seite
nurErster = true;
absatz1.merkmale = {}; absatz2.merkmale = {};
bandtasten.find((t) => t.title === 'Blocksatz').klick();
ergebnis.aus_einer = [absatz1.merkmale['data-aus'] || null,
                      absatz2.merkmale['data-aus'] || null];
nurErster = false;

const za = klappe('Zeilenabstand', 2, bandleiste, bandtasten);
ergebnis.abstaende = za.eintraege;
ergebnis.za_befehle = za.befehle;
ergebnis.za = absatz1.merkmale['data-za'] || null;
klappe('Zeilenabstand', 5, bandleiste, bandtasten);   // "Standard" nimmt ihn weg
ergebnis.za_weg = absatz1.merkmale['data-za'] || null;

/* Steht der Text noch nackt im Feld, gibt es keinen Absatz - dann muss erst
   einer daraus werden, sonst haengt die Ausrichtung an nichts. */
const feld3 = new Knoten('div');
feld3.klassen.add('text');
feld3.nodeType = 1;
auswahl = {
  rangeCount: 1,
  getRangeAt: () => ({ startContainer: feld3, intersectsNode: () => true }),
};
befehle.length = 0;
const alterBefehl2 = aufAuswahl;
aufAuswahl = function (befehl, wert) {
  befehle.push([befehl, wert === undefined ? null : wert]);
  if (befehl === 'formatBlock') {
    const d = new Knoten('div');
    d.nodeType = 1;
    feld3.append(d);
  }
};
bandtasten.find((t) => t.title === 'Rechtsbündig').klick();
ergebnis.ohne_block = befehle.slice();
ergebnis.ohne_block_gesetzt = feld3.kinder.length
  ? (feld3.kinder[0].merkmale['data-aus'] || null) : null;
aufAuswahl = alterBefehl2;

/* --- Der Reiter "Einfügen" ----------------------------------------------- */
const einfkasten = new Knoten('div');
einfkasten.id = 'einfuegen';
bekannt.einfuegen = einfkasten;
for (const id of ['dateiwahl', 'neue-seite-band', 'neuer-abschnitt-band']) {
  const k = new Knoten('button');
  k.id = id;
  // Die Leiste klickt die alten Knoepfe an - die Logik steht dort.
  k.click = function () { befehle.push(['angeklickt', id + ':' + (this.accept || '')]); };
  bekannt[id] = k;
}
einfuegeleisteBauen();
const einfleiste = einfkasten.kinder.find((k) => k.klassen.has('formatleiste'));
const einftasten = einfleiste.alle().filter((k) => k.klassen.has('fl-taste'));
ergebnis.einfknoepfe = einftasten.map((k) => k.title);
ergebnis.einfalt = einfkasten.kinder[0].id;
// An jedem Knopf muss das Wort stehen, nicht nur das Bildchen.
ergebnis.einfworte = einftasten.map((k) => k.klassen.has('fl-mitwort'));
ergebnis.einftext = einftasten.map((k) => k.innerHTML);

function einfKlick(titel) {
  befehle.length = 0;
  const k = einftasten.find((t) => t.title === titel);
  if (!k) return ['KEIN KNOPF ' + titel];
  k.klick();
  return befehle.slice();
}

ergebnis.anlage = einfKlick('Dateianlage');
ergebnis.bilder = einfKlick('Bilder');
ergebnis.schreibbereich = einfKlick('Schreibbereich einfügen');
ergebnis.link = einfKlick('Link');
ergebnis.neueseite = einfKlick('Neue Seite');
ergebnis.neuerabschnitt = einfKlick('Neuer Abschnitt');

/* Das Tabellenraster: darüberfahren wählt, der Klick fügt ein */
befehle.length = 0;
einftasten.find((t) => t.title === 'Tabelle').klick();
const tafel = einfleiste.querySelector('.fl-liste');
const felder = tafel.alle().filter((k) => k.klassen.has('fl-rasterfeld'));
ergebnis.rasterfelder = felder.length;
const zweiDrei = felder.find((f) => f.dataset.z === '2' && f.dataset.s === '3');
zweiDrei.zuhoerer.mouseover[0]();
ergebnis.rastermass = tafel.alle().find((k) => k.klassen.has('fl-tabmass')).textContent;
ergebnis.rasterhell = felder.filter((f) => f.klassen.has('an')).length;
zweiDrei.klick();
ergebnis.tabelle = befehle.slice();
ergebnis.tafelweg = !einfleiste.querySelector('.fl-liste');

/* Die Zeichentafel */
befehle.length = 0;
einftasten.find((t) => t.title === 'Symbol').klick();
const ztafel = einfleiste.querySelector('.fl-liste');
const zfelder = ztafel.alle().filter((k) => k.klassen.has('fl-zeichenfeld'));
ergebnis.zeichenzahl = zfelder.length;
zfelder.find((z) => z.textContent === '§').klick();
ergebnis.zeichen = befehle.slice();

/* Datum und Uhrzeit */
const datum = klappe('Datum und Uhrzeit', 0, einfleiste, einftasten);
ergebnis.datumwahl = datum.eintraege;
ergebnis.datum = datum.befehle;
ergebnis.datumgleich = datum.befehle.length
  ? datum.befehle[0][1] === new Date().toLocaleDateString() : false;

/* --- Formeln ------------------------------------------------------------- */
ergebnis.formeln = {};
for (const probe of ['x', '1+2', 'a/b', 'x^2', 'x_1', 'x_1^2', 'sqrt(x)',
                     'root(3)(x)', 'pi', 'alpha+Omega', '(a+b)/2', 'a+b/2',
                     'sum_(i=1)^n i', 'int_a^b f', 'x <= 3', 'f(x)', '2*3',
                     '-x', '', 'a)', '<script>']) {
  ergebnis.formeln[probe] = formelMathML(probe);
}

console.log = (...a) => process.stdout.write(a.join(' ') + '\n');

/* --- Ausschneiden, Kopieren, Einfuegen ----------------------------------- */
auswahl = {
  rangeCount: 1,
  isCollapsed: false,
  toString: () => 'markiert',
  getRangeAt: () => ({ startContainer: absatz1, intersectsNode: () => true }),
};
const ruhe = () => new Promise((f) => setTimeout(f, 0));

(async () => {
  for (const [name, titel] of [['kopieren', 'Kopieren (Strg+C)'],
                               ['ausschneiden', 'Ausschneiden (Strg+X)'],
                               ['einfuegen', 'Einfügen (Strg+V)']]) {
    befehle.length = 0;
    bandtasten.find((t) => t.title === titel).klick();
    await ruhe();
    ergebnis[name] = befehle.slice();
  }
  // Darf die Webansicht nicht an die Zwischenablage, muss das dastehen -
  // ein Knopf, der stumm nichts tut, ist schlimmer als kein Knopf.
  ablageDarf = false;
  befehle.length = 0;
  bandtasten.find((t) => t.title === 'Einfügen (Strg+V)').klick();
  await ruhe();
  ergebnis.einfuegen_verboten = befehle.slice();
  befehle.length = 0;
  bandtasten.find((t) => t.title === 'Kopieren (Strg+C)').klick();
  await ruhe();
  ergebnis.kopieren_alt = befehle.slice();
  ablageDarf = true;

  process.stdout.write(JSON.stringify(ergebnis) + '\n');
})();
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
AUSRICHTEN = ['Linksbündig', 'Zentriert', 'Rechtsbündig', 'Blocksatz']
ZEICHEN = ['Fett (Strg+B)', 'Kursiv (Strg+I)', 'Unterstrichen (Strg+U)',
           'Durchgestrichen', 'Hochgestellt', 'Tiefgestellt']
FARBEN = ['Hervorheben', 'Andere Farbe zum Hervorheben',
          'Schriftfarbe', 'Andere Schriftfarbe', 'Formatierung entfernen']
LISTEN = ['Aufzählung', 'Aufzählungszeichenbibliothek',
          'Nummerierung', 'Nummerierungsbibliothek']
ABSATZ = ['Einzug verkleinern', 'Einzug vergrößern', *AUSRICHTEN, 'Zeilenabstand']
VORLAGEN = ['Formatvorlage', 'Aufgabe (zum Abhaken)', 'Kategorie']
ABLAGE = ['Einfügen (Strg+V)', 'Ausschneiden (Strg+X)', 'Kopieren (Strg+C)',
          'Format übertragen']
# Die schwebende Leiste bleibt, wie sie war - Wort fuer Wort dieselbe Liste
# wie vor dem Umbau des Bands.
# Ohne "Durchgestrichen": das steht oben im Band. Hier ist es der Knopf,
# den man am seltensten trifft, und er macht die Leiste eine Breite länger.
ERWARTET = ['Formatvorlage', 'Einzug verkleinern', 'Einzug vergrößern',
            'Aufgabe (zum Abhaken)', 'Kategorie', 'Fett (Strg+B)', 'Kursiv (Strg+I)',
            'Unterstrichen (Strg+U)',
            'Hervorheben', 'Andere Farbe zum Hervorheben',
            'Schriftfarbe', 'Andere Schriftfarbe',
            'Aufzählung', 'Aufzählungszeichenbibliothek', 'Nummerierung',
            'Nummerierungsbibliothek', 'Format übertragen', 'Formatierung entfernen']
pruefe("alle Knöpfe, in dieser Reihenfolge", d["knoepfe"] == ERWARTET, d["knoepfe"])
# Das ist der Punkt: was oben dazukam, darf die kleine Leiste nicht aufblähen.
pruefe("und keiner der neuen Knöpfe steht schwebend mit drin",
       not [k for k in d["knoepfe"]
            if k in [*ABLAGE[:3], 'Hochgestellt', 'Tiefgestellt',
                     'Durchgestrichen', *AUSRICHTEN, 'Zeilenabstand']], d["knoepfe"])

print("\nDie Leiste oben im Reiter Start")
# Vorher standen dort vier Knöpfe; alles andere gab es nur, wenn man etwas
# markierte und die schwebende Leiste aufging.
pruefe("eine Reihe statt zwei", d["bandreihen"] == 1, d["bandreihen"])
pruefe("und sie weiß, dass sie im Band steht", d["bandklasse"])
pruefe("und Durchgestrichen tut dort, was draufsteht",
       d["banddurch"] == [["strikeThrough", None]], d["banddurch"])
# Vier Gruppen wie in Word: Zwischenablage, dann alles zur Schrift, dann
# alles zum Absatz, dann die Marken und die Formatvorlage. Vorher standen
# Schrift und Zeichen getrennt und die Listen vor dem Einzug - zwei
# Trenner, die quer zu dem lagen, was zusammengehört.
BAND = [
    *ABLAGE,
    'Fett (Strg+B)', 'Kursiv (Strg+I)', 'Unterstrichen (Strg+U)', 'Durchgestrichen',
    'Schriftfarbe', 'Andere Schriftfarbe',
    'Hervorheben', 'Andere Farbe zum Hervorheben',
    'Hochgestellt', 'Tiefgestellt', 'Formatierung entfernen',
    *LISTEN, 'Einzug verkleinern', 'Einzug vergrößern', *AUSRICHTEN, 'Zeilenabstand',
    'Aufgabe (zum Abhaken)', 'Kategorie', 'Formatvorlage',
]
pruefe("dort steht alles, in der Reihenfolge aus dem Band",
       d["bandknoepfe"] == BAND, d["bandknoepfe"])

print("\nWas unten ankommt")
for was, soll in (("fett", [["bold", None]]), ("kursiv", [["italic", None]]),
                  ("unterstrichen", [["underline", None]]),
                  ("marker", [["hervorheben", "gelb"]]),
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
pruefe("je Listenart ein Paar aus Knopf und Pfeil - und dasselbe bei den Farben",
       d["paare"] == [['Hervorheben', 'Andere Farbe zum Hervorheben'],
                      ['Schriftfarbe', 'Andere Schriftfarbe'],
                      ['Aufzählung', 'Aufzählungszeichenbibliothek'],
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

print("\nSchriftfarbe und Textmarker")
# Wie in Word: unter dem Zeichen ein Balken in der Farbe, die ein Klick
# nimmt. Ohne ihn sagt der Knopf nicht, was er gerade setzt.
pruefe("beide Knöpfe tragen einen Farbbalken",
       d["balken_anfang"] == [['#ffe680'], ['#b23b2e']], d["balken_anfang"])
pruefe("und sind als Farbtaste gebaut", d["balkenklasse"] == [True, True],
       d["balkenklasse"])
pruefe("ein Klick hebt gleich hervor, ohne Umweg über den Pfeil",
       d["marker_klick"] == [["hervorheben", "gelb"]], d["marker_klick"])
pruefe("und setzt die Schriftfarbe von eben",
       d["farbe_klick"] == [["foreColor", "#b23b2e"]], d["farbe_klick"])
pruefe("der Marker hat sechs Farben zur Wahl",
       d["markerfarben"] == ['Gelb', 'Grün', 'Blau', 'Rosa', 'Orange', 'Grau'],
       d["markerfarben"])
pruefe("eine andere Farbe färbt sofort",
       d["marker_gewaehlt"] == [["hervorheben", "gruen"]], d["marker_gewaehlt"])
pruefe("der Balken zieht mit", d["balken_danach"] == ['#b7ec9a'], d["balken_danach"])
# Das ist der Punkt an der geteilten Taste: die Farbe von eben bleibt die
# des Knopfs.
pruefe("und der nächste Klick nimmt sie wieder",
       d["marker_nochmal"] == [["hervorheben", "gruen"]], d["marker_nochmal"])
pruefe("dasselbe bei der Schriftfarbe",
       d["farbe_nochmal"] == [["foreColor", "#2f7d32"]]
       and d["farbbalken_danach"] == ['#2f7d32'],
       (d["farbe_nochmal"], d["farbbalken_danach"]))

print("\nAusrichtung und Zeilenabstand")
# Beides gilt fuer die Zeile, nicht fuer die markierten Buchstaben - also
# muss es am Absatz haengen und nicht als Befehl auf die Auswahl gehen.
pruefe("die Ausrichtung geht an den Absatz, nicht an die Auswahl",
       d["aus_befehle"] == [["gemerkt", None]], d["aus_befehle"])
pruefe("und steht an beiden markierten Absätzen",
       d["aus"] == ['mitte', 'mitte'], d["aus"])
pruefe("markiert man nur einen, bleibt der andere in Ruhe",
       d["aus_einer"] == ['block', None], d["aus_einer"])
pruefe("die Abstände stehen zur Wahl",
       d["abstaende"] == ['Einfach', '1,15', 'Anderthalb', 'Doppelt',
                          'Dreifach', 'Standard'], d["abstaende"])
pruefe("und landen am Absatz", d["za"] == '1.5' and d["za_befehle"] == [["gemerkt", None]],
       (d["za"], d["za_befehle"]))
pruefe("'Standard' nimmt ihn wieder weg", d["za_weg"] is None, d["za_weg"])
# Ohne Absatz haengt die Ausrichtung an nichts und ist beim naechsten
# Speichern weg - der Browser raeumt losen Text nicht von selbst ein.
pruefe("steht der Text nackt im Feld, wird erst ein Absatz daraus",
       d["ohne_block"] == [["formatBlock", "<div>"], ["gemerkt", None]]
       and d["ohne_block_gesetzt"] == 'rechts',
       (d["ohne_block"], d["ohne_block_gesetzt"]))

# Gegenprobe: was die Leiste setzt, muss der Reiniger kennen - sonst faellt
# es beim Speichern wieder heraus und niemand sieht, warum.
sys.path.insert(0, str(WURZEL))
from app import reinigen            # noqa: E402

js_aus = set(re.findall(r"\['(\w+)', '[^']+'\]",
                        re.search(r"^const FL_AUSRICHTUNG = \[.*?\];", mappe,
                                  re.S | re.M).group(0)))
js_za = {w for w in re.findall(r"\['([\d.]*)', '[^']+'\]",
                               re.search(r"^const FL_ABSTAENDE = \[.*?\];", mappe,
                                         re.S | re.M).group(0)) if w}
pruefe("der Reiniger kennt dieselben Ausrichtungen",
       js_aus == reinigen.AUSRICHTUNG, (js_aus, reinigen.AUSRICHTUNG))
pruefe("und dieselben Abstände", js_za == reinigen.ABSTAENDE,
       (js_za, reinigen.ABSTAENDE))
roh = '<p data-aus="mitte" data-za="1.5">hallo</p>'
pruefe("und laesst sie durch", reinigen.html(roh) == roh, reinigen.html(roh))
pruefe("Erfundenes fliegt raus",
       reinigen.html('<p data-aus="hinten" data-za="9">x</p>') == '<p>x</p>',
       reinigen.html('<p data-aus="hinten" data-za="9">x</p>'))

# Dasselbe fuer den Marker: die Farbe steht als Name im Text, und den muss
# der Reiniger kennen - sonst ist sie beim Speichern wieder weg. Gelb hat
# keinen Eintrag, damit alte Notizen unveraendert bleiben.
js_marker = {w for w in re.findall(
    r"\['(\w+)', '[^']+', '#[0-9a-fA-F]{6}'\]",
    re.search(r"^const FL_MARKERFARBEN = \[.*?\];", mappe, re.S | re.M).group(0))}
pruefe("der Reiniger kennt dieselben Markerfarben",
       js_marker - {'gelb'} == reinigen.MARKERFARBEN,
       (js_marker, reinigen.MARKERFARBEN))
pruefe("und lässt sie durch",
       reinigen.html('<mark data-farbe="gruen">x</mark>') == '<mark data-farbe="gruen">x</mark>')
pruefe("Erfundenes nicht",
       reinigen.html('<mark data-farbe="neon">x</mark>') == '<mark>x</mark>',
       reinigen.html('<mark data-farbe="neon">x</mark>'))

# Und die Stildatei muss daraus eine Regel machen, sonst sieht man nichts.
stil = (WURZEL / "app/oberflaeche/stil.css").read_text(encoding="utf-8")
stil = re.sub(r"/\*.*?\*/", "", stil, flags=re.S)
pruefe("die Stildatei hat zu jeder Markerfarbe eine Regel",
       all(f'mark[data-farbe="{w}"]' in stil for w in reinigen.MARKERFARBEN))
pruefe("die Stildatei hat zu jeder Ausrichtung eine Regel",
       all(f'[data-aus="{w}"]' in stil for w in reinigen.AUSRICHTUNG))
pruefe("und zu jedem Abstand",
       all(f'[data-za="{w}"]' in stil for w in reinigen.ABSTAENDE))

print("\nAusschneiden, Kopieren, Einfügen")
pruefe("Kopieren legt die Markierung in die Ablage",
       d["kopieren"] == [["ablage-schreiben", "markiert"]], d["kopieren"])
pruefe("Ausschneiden nimmt sie danach weg",
       d["ausschneiden"] == [["ablage-schreiben", "markiert"],
                             ["execCommand", "delete", None], ["gemerkt", None]],
       d["ausschneiden"])
pruefe("Einfügen schreibt den Text hinein",
       d["einfuegen"] == [["execCommand", "insertText", "aus der Ablage"],
                          ["gemerkt", None]], d["einfuegen"])
# Keine Beschwichtigung, sondern der Weg, der dann noch geht.
pruefe("darf die Ansicht nicht an die Ablage, steht der Tastenweg da",
       d["einfuegen_verboten"] == [["sagen", "Einfügen geht hier nur mit Strg+V"]],
       d["einfuegen_verboten"])
pruefe("und Kopieren fällt auf den alten Befehl zurück",
       d["kopieren_alt"] == [["execCommand", "copy", None]], d["kopieren_alt"])

print("\nDer Reiter Einfügen")
# Vorher standen dort drei Knöpfe. Nicht dabei sind Bildschirmausschnitt,
# Audio, Video, Onlinevideo, Formel und Dateiausdruck: die brauchen Rechte,
# die eine Webansicht nicht hat, oder einen ganzen Apparat - und am Server
# ginge die Hälfte ohnehin nicht.
pruefe("die Knöpfe stehen in dieser Reihenfolge",
       d["einfknoepfe"] == ['Tabelle', 'Schreibbereich einfügen', 'Dateianlage',
                            'Bilder', 'Link', 'Datum und Uhrzeit', 'Symbol',
                            'Formel', 'Neue Seite', 'Neuer Abschnitt'],
       d["einfknoepfe"])
# Die alten bleiben versteckt stehen: an ihnen hängt die Logik für Anhänge,
# neue Seiten und Abschnitte, und die soll es nur einmal geben.
pruefe("die alten Knöpfe stehen versteckt dahinter", d["einfalt"] == 'einfalt',
       d["einfalt"])
# "Schreibbereich einfügen" errät niemand am Bildchen.
pruefe("an jedem Knopf steht das Wort, nicht nur das Symbol",
       all(d["einfworte"]) and d["einftext"] == ['Tabelle▾', 'Schreibbereich einfügen',
                                                 'Dateianlage', 'Bilder', 'Link',
                                                 'Datum und Uhrzeit▾', 'ΩSymbol▾',
                                                 '∑Formel', '＋Seite', '＋Abschnitt'],
       (d["einfworte"], d["einftext"]))
pruefe("Dateianlage nimmt alles an",
       d["anlage"] == [["angeklickt", "dateiwahl:"]], d["anlage"])
pruefe("Bilder nur Bilder",
       d["bilder"] == [["angeklickt", "dateiwahl:image/*"]], d["bilder"])
pruefe("der Schreibbereich wird dort angelegt, wo man gerade ist",
       d["schreibbereich"] == [["kastenNeu", "80,80"]], d["schreibbereich"])
pruefe("Link fragt nach der Adresse", d["link"] == [["linkSetzen", None]], d["link"])
pruefe("Seite und Abschnitt klicken die alten Knöpfe an",
       d["neueseite"] == [["angeklickt", "neue-seite-band:"]]
       and d["neuerabschnitt"] == [["angeklickt", "neuer-abschnitt-band:"]],
       (d["neueseite"], d["neuerabschnitt"]))

print("\nDas Tabellenraster")
pruefe("8 × 8 zur Wahl", d["rasterfelder"] == 64, d["rasterfelder"])
pruefe("darüberfahren zeigt das Maß an", d["rastermass"] == '2 × 3', d["rastermass"])
pruefe("und hebt genau diese Felder hervor", d["rasterhell"] == 6, d["rasterhell"])
# Ohne <br> ist die Zelle null Pixel hoch und man trifft sie nicht; ohne den
# Absatz dahinter kommt man unter der Tabelle nicht mehr heraus.
pruefe("der Klick fügt 2 Zeilen zu 3 Spalten ein",
       d["tabelle"] == [["insertHTML",
                         "<table><tr><td><br></td><td><br></td><td><br></td></tr>"
                         "<tr><td><br></td><td><br></td><td><br></td></tr>"
                         "</table><p><br></p>"]], d["tabelle"])
pruefe("und die Tafel geht dabei zu", d["tafelweg"])

print("\nSymbol, Datum und Uhrzeit")
pruefe("60 Zeichen zur Wahl", d["zeichenzahl"] == 60, d["zeichenzahl"])
pruefe("ein Klick schreibt das Zeichen in den Text",
       d["zeichen"] == [["insertText", "§"]], d["zeichen"])
pruefe("Datum, Uhrzeit, beides",
       d["datumwahl"] == ['Datum', 'Uhrzeit', 'Datum und Uhrzeit'], d["datumwahl"])
# In der Sprache des Rechners, nicht selbst zusammengesetzt - sonst stünde
# in jedem Land dasselbe deutsche Format da.
pruefe("und es kommt das heutige Datum heraus", d["datumgleich"], d["datum"])

# Gegenprobe: eine Tabelle muss den Reiniger überleben, ihre Attribute nicht.
pruefe("Tabellen überleben das Speichern",
       reinigen.html('<table><tr><td>a</td></tr></table>')
       == '<table><tr><td>a</td></tr></table>')
pruefe("ihre Attribute nicht",
       reinigen.html('<table style="position:fixed" width="900"><tr>'
                     '<td colspan="9">a</td></tr></table>')
       == '<table><tr><td>a</td></tr></table>',
       reinigen.html('<table style="position:fixed" width="900"><tr>'
                     '<td colspan="9">a</td></tr></table>'))

print("\nFormeln")
# MathML setzt die Webansicht selbst - ohne Bibliothek, ohne Schriftdateien
# und am Server ohne ein fremdes Skript, das die CSP ohnehin nicht ließe.
F = d["formeln"]
def m(innen):
    return "<math><mrow>" + innen + "</mrow></math>"

for probe, soll in [
    ("x", "<mi>x</mi>"),
    ("1+2", "<mn>1</mn><mo>+</mo><mn>2</mn>"),
    ("a/b", "<mfrac><mi>a</mi><mi>b</mi></mfrac>"),
    ("x^2", "<msup><mi>x</mi><mn>2</mn></msup>"),
    ("x_1", "<msub><mi>x</mi><mn>1</mn></msub>"),
    ("x_1^2", "<msubsup><mi>x</mi><mn>1</mn><mn>2</mn></msubsup>"),
    ("sqrt(x)", "<msqrt><mi>x</mi></msqrt>"),
    ("root(3)(x)", "<mroot><mi>x</mi><mn>3</mn></mroot>"),
    ("pi", "<mi>\u03c0</mi>"),
    ("2*3", "<mn>2</mn><mo>\u00b7</mo><mn>3</mn>"),
    ("f(x)", "<mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo>"),
    ("-x", "<mo>\u2212</mo><mi>x</mi>"),
]:
    pruefe(f"{probe or 'leer'} wird richtig gesetzt", F[probe] == m(soll), F[probe])

# Punkt vor Strich - sonst würde a+b/2 zu (a+b)/2, und das ist eine andere
# Zahl.
pruefe("Klammern gelten: (a+b)/2",
       F["(a+b)/2"] == m("<mfrac><mrow><mo>(</mo><mrow><mi>a</mi><mo>+</mo>"
                         "<mi>b</mi></mrow><mo>)</mo></mrow><mn>2</mn></mfrac>"),
       F["(a+b)/2"])
pruefe("und ohne Klammern bindet der Bruch enger: a+b/2",
       F["a+b/2"] == m("<mi>a</mi><mo>+</mo><mfrac><mi>b</mi><mn>2</mn></mfrac>"),
       F["a+b/2"])
# An der Summe stehen die Grenzen darüber und darunter, nicht daneben. Das
# ist der ganze Unterschied zwischen einer Summe und x hoch n.
pruefe("Summengrenzen stehen über und unter dem Zeichen",
       "<munderover>" in F["sum_(i=1)^n i"] and "<msubsup>" not in F["sum_(i=1)^n i"],
       F["sum_(i=1)^n i"])
pruefe("beim Integral auch", "<munderover>" in F["int_a^b f"], F["int_a^b f"])
pruefe("<= wird zu \u2264", F["x <= 3"] == m("<mi>x</mi><mo>\u2264</mo><mn>3</mn>"),
       F["x <= 3"])
# Eine halbe Formel ist besser als eine rote Meldung: beim Tippen steht sie
# die meiste Zeit halb da.
pruefe("nichts getippt, nichts kaputt", F[""] == m(""), F[""])
pruefe("eine Klammer ohne Gegenstück hängt nicht fest",
       F["a)"] == m("<mi>a</mi><mo>)</mo>"), F["a)"])
# Der Vorschaukasten setzt das Ergebnis als HTML ein. Käme da etwas
# Spitzes durch, wäre das genau die Lücke, die reinigen.py sonst zuhält.
pruefe("spitze Klammern kommen nicht als Markup durch",
       "&lt;" in F["<script>"] and "<script>" not in F["<script>"], F["<script>"])

# Und der Reiniger muss MathML durchlassen - sonst ist die Formel beim
# Speichern weg.
pruefe("MathML überlebt das Speichern",
       reinigen.html(m("<mi>x</mi>")) == m("<mi>x</mi>"),
       reinigen.html(m("<mi>x</mi>")))
pruefe("Attribute daran nicht",
       reinigen.html('<math display="block"><mi onclick="x">a</mi></math>')
       == '<math><mi>a</mi></math>',
       reinigen.html('<math display="block"><mi onclick="x">a</mi></math>'))
# mglyph lädt ein Bild, maction führt beim Klicken etwas aus.
pruefe("mglyph und maction nicht",
       reinigen.html('<math><maction><mi>a</mi></maction><mglyph/></math>')
       == '<math><mi>a</mi></math>',
       reinigen.html('<math><maction><mi>a</mi></maction><mglyph/></math>'))

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
