"""Kommt der Update-Hinweis wirklich an?

    .venv/bin/python tests/test_balken.py

Dreimal hintereinander hieß es "in der App wird kein Update angezeigt", und
dreimal war der Mechanismus in Ordnung: aktualisieren.py meldete sauber
"neuer: true". Hängen blieb es jedes Mal auf dem Weg von der Antwort zum
Balken - einmal am zweiten, getrennten Abfrageweg für den Knopf im Band,
einmal an einer Bedingung, die die Serverfassung gar nicht hat.

Geprüft wurde bis dahin nur, ob die Funktionen im Quelltext stehen. Das
sieht nicht, was sie tun. Hier läuft der Weg deshalb wirklich: eine Antwort
hinein, und hinterher wird nachgesehen, ob ein Balken im Dokument steht und
was auf ihm steht.
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
for muster, name in ((r"^const UPDATE_WEG = [^;]*;", "UPDATE_WEG"),
                     (r"^async function versionPruefen\(.*?^\}", "versionPruefen"),
                     (r"^function updateBalken\(.*?^\}", "updateBalken"),
                     (r"^function hilfeStandZeigen\(.*?^\}", "hilfeStandZeigen"),
                     (r"^function updateHinweisBauen\(.*?^\}", "updateHinweisBauen")):
    treffer = re.search(muster, mappe, re.S | re.M)
    pruefe(f"{name} steht in mappe.js", bool(treffer))
    if treffer:
        teile.append(treffer.group(0))
if fehler:
    sys.exit(1)

HARNISCH = r"""
/* Ein Dokument, so klein wie moeglich - mit dem, was der Hinweis braucht. */
class Knoten {
  constructor(art) {
    this.art = art; this.kinder = []; this.zuhoerer = {};
    this.id = ''; this.title = ''; this.textContent = ''; this.eltern = null;
    this.hidden = false; this.disabled = false; this.type = '';
  }
  append(...was) {
    for (const k of was) { if (k.eltern) k.remove(); k.eltern = this; this.kinder.push(k); }
  }
  remove() {
    if (this.eltern) this.eltern.kinder = this.eltern.kinder.filter((k) => k !== this);
    this.eltern = null;
  }
  addEventListener(art, f) { (this.zuhoerer[art] = this.zuhoerer[art] || []).push(f); }
  async klick() { for (const f of this.zuhoerer.click || []) await f(); }
  alle() { return this.kinder.reduce((a, k) => a.concat(k.alle()), [this]); }
}

const body = new Knoten('body');
const updateKnopf = new Knoten('button');
updateKnopf.id = 'update';
updateKnopf.hidden = true;
const hilfe = new Knoten('span');
hilfe.id = 'hilfe-version';
const fassung = new Knoten('span');
fassung.id = 'version';
fassung.textContent = '1.2.56';

const document = {
  createElement: (a) => new Knoten(a),
  body,
};
function $(waehler) {
  if (waehler === '#update') return updateKnopf;
  if (waehler === '#hilfe-version') return hilfe;
  if (waehler === '#version') return fassung;
  if (waehler === '#updatebalken') {
    return body.alle().slice(1).find((k) => k.id === 'updatebalken') || null;
  }
  if (waehler === '#u-text') {
    return body.alle().slice(1).find((k) => k.id === 'u-text') || null;
  }
  return null;
}

/* Der Merker ist drueben der localStorage. Hier reicht ein Woerterbuch -
   aber mit derselben Eigenschaft: was "Spaeter" hineinschreibt, steht beim
   naechsten Nachsehen noch da. */
const merkzettel = {};
const merker = {
  holen: (k, standard) => (k in merkzettel ? merkzettel[k] : standard),
  legen: (k, w) => { merkzettel[k] = w; },
};

// Was die Bruecke antworten soll - wird je Probe gesetzt.
let antwort = null;
let abgefragt = 0;
async function api(weg) {
  abgefragt += 1;
  if (antwort instanceof Error) throw antwort;
  return antwort;
}
function melden() {}
function updateFensterZeigen() {}
function updateVerfolgen() {}

/* Die Uhr anhalten: sonst wartet der Test vier Sekunden auf den ersten
   Blick und fuenf Minuten auf den zweiten. Gesammelt wird, was wann
   laufen sollte; gerufen wird es hier von Hand. */
const spaeter = [];
const takte = [];
const setTimeout = (f, ms) => { spaeter.push([ms, f]); return spaeter.length; };
const setInterval = (f, ms) => { takte.push([ms, f]); return takte.length; };
""" + "\n".join(teile) + r"""

const ergebnis = {};

function balken() {
  const b = $('#updatebalken');
  if (!b) return null;
  const knopf = (t) => b.kinder.find((k) => k.textContent === t) || null;
  return {
    text: (b.kinder.find((k) => k.id === 'u-text') || {}).textContent || '',
    jetzt: knopf('Jetzt aktualisieren') ? !knopf('Jetzt aktualisieren').hidden : false,
    spaeter: !!knopf('Später'),
  };
}

function aufraeumen() {
  const b = $('#updatebalken');
  if (b) b.remove();
  // Auch den Merker: sonst wirkt das "Später" der ersten Probe in allen
  // weiteren weiter, und die melden dann einen Fehler, den es nicht gibt.
  for (const k of Object.keys(merkzettel)) delete merkzettel[k];
  spaeter.length = 0;
  takte.length = 0;
  updateKnopf.hidden = true;
  abgefragt = 0;
}

(async () => {
  /* 1. Eine neue Fassung, und sie laesst sich einspielen. */
  antwort = { installiert: '1.2.56', verfuegbar: '1.2.57', neuer: true,
              aktualisierbar: true, fehler: null };
  updateHinweisBauen();
  ergebnis.wartezeit = spaeter.length ? spaeter[0][0] : null;
  ergebnis.takt = takte.length ? takte[0][0] : null;
  await spaeter[0][1]();
  ergebnis.normal = balken();
  ergebnis.knopf = { aus: updateKnopf.hidden, text: updateKnopf.textContent };
  ergebnis.hilfe_neu = hilfe.textContent;

  /* Zweimal nachsehen baut keinen zweiten Balken. */
  const nochmal = takte[0][1];
  await nochmal();
  ergebnis.doppelt = body.alle().slice(1).filter((k) => k.id === 'updatebalken').length;

  /* "Später": fuer diese Fassung nicht mehr fragen. */
  const weg = $('#updatebalken').kinder.find((k) => k.textContent === 'Später');
  await weg.klick();
  ergebnis.nach_spaeter_weg = !$('#updatebalken');
  await nochmal();
  ergebnis.nach_spaeter_still = !$('#updatebalken');
  /* Aber bei der naechsten Fassung wieder. */
  antwort = { installiert: '1.2.56', verfuegbar: '1.2.58', neuer: true,
              aktualisierbar: true, fehler: null };
  await nochmal();
  ergebnis.naechste = balken();
  aufraeumen();

  /* 2. Neu, laesst sich hier aber nicht einspielen. Das war der Fall, in
     dem vorher gar nichts kam. */
  antwort = { installiert: '1.2.56', verfuegbar: '1.2.57', neuer: true,
              aktualisierbar: false, fehler: null };
  updateHinweisBauen();
  await spaeter[0][1]();
  ergebnis.ohne_installation = balken();
  ergebnis.ohne_installation_knopf = updateKnopf.hidden;
  aufraeumen();

  /* 3. Nichts Neues. */
  antwort = { installiert: '1.2.57', verfuegbar: '1.2.57', neuer: false,
              aktualisierbar: true, fehler: null };
  updateHinweisBauen();
  await spaeter[0][1]();
  ergebnis.nichts_neues = !$('#updatebalken');
  ergebnis.hilfe_aktuell = hilfe.textContent;
  aufraeumen();

  /* 4. Die Pruefung geht schief. */
  antwort = { installiert: null, verfuegbar: null, neuer: false,
              aktualisierbar: false, fehler: 'GitHub nicht erreichbar: zu' };
  updateHinweisBauen();
  await spaeter[0][1]();
  ergebnis.fehler_kein_balken = !$('#updatebalken');
  ergebnis.hilfe_fehler = hilfe.textContent;
  // Vier Sekunden nach dem Start steht die Bruecke manchmal noch nicht -
  // dann darf er nicht fuenf Minuten warten.
  ergebnis.zweiter_versuch = spaeter.length > 1 ? spaeter[1][0] : null;
  antwort = { installiert: '1.2.56', verfuegbar: '1.2.57', neuer: true,
              aktualisierbar: true, fehler: null };
  await spaeter[1][1]();
  ergebnis.nach_zweitem = balken();
  aufraeumen();

  /* 5. Die Bruecke wirft - genau das passiert, wenn sie noch nicht steht. */
  antwort = new Error('bruecke_da ist null');
  updateHinweisBauen();
  await spaeter[0][1]();
  ergebnis.wurf_kein_absturz = !$('#updatebalken');
  ergebnis.wurf_hilfe = hilfe.textContent;

  process.stdout.write(JSON.stringify(ergebnis) + '\n');
})();
"""

ordner = Path(tempfile.mkdtemp(prefix="balken-"))
(ordner / "pruef.js").write_text(HARNISCH, encoding="utf-8")
if shutil.which("node"):
    befehl = ["node", str(ordner / "pruef.js")]
elif shutil.which("docker"):
    befehl = ["docker", "run", "--rm", "-v", f"{ordner}:/p:ro", "node:alpine",
              "node", "/p/pruef.js"]
else:
    print("  --  weder node noch docker da, der Hinweis ist ungeprueft")
    sys.exit(0)

lauf = subprocess.run(befehl, capture_output=True, text=True)
if lauf.returncode != 0:
    print(lauf.stdout)
    print(lauf.stderr)
    sys.exit(1)
d = json.loads(lauf.stdout.strip().splitlines()[-1])

print("\nWann wird nachgesehen")
# Nicht sofort: erst soll die Oberflaeche stehen.
pruefe("vier Sekunden nach dem Start", d["wartezeit"] == 4000, d["wartezeit"])
pruefe("und danach alle fünf Minuten", d["takt"] == 300000, d["takt"])

print("\nEine neue Fassung ist da")
pruefe("der Balken steht im Dokument", bool(d["normal"]), d["normal"])
pruefe("und sagt, was da ist und was läuft",
       d["normal"] and d["normal"]["text"] == "Fassung 1.2.57 ist da - hier läuft 1.2.56.",
       d["normal"])
pruefe("mit beiden Knöpfen",
       d["normal"] and d["normal"]["jetzt"] and d["normal"]["spaeter"], d["normal"])
# Der Knopf im Band hing frueher an einem zweiten, eigenen Abfrageweg und
# kam nur, wenn "beim Start nachsehen" anstand.
pruefe("und der Knopf im Band kommt mit",
       d["knopf"] == {"aus": False, "text": "Update auf 1.2.57"}, d["knopf"])
pruefe("im Reiter Hilfe steht es auch",
       d["hilfe_neu"] == "Notizmappe 1.2.56 — Fassung 1.2.57 ist da", d["hilfe_neu"])
pruefe("zweimal nachsehen baut keinen zweiten Balken", d["doppelt"] == 1, d["doppelt"])

print("\nSpäter")
pruefe("nimmt ihn weg", d["nach_spaeter_weg"])
pruefe("und er kommt für diese Fassung nicht wieder", d["nach_spaeter_still"])
pruefe("für die nächste aber schon",
       d["naechste"] and "1.2.58" in d["naechste"]["text"], d["naechste"])

print("\nNeu, aber hier nicht einspielbar")
# Genau hier kam vorher gar nichts - und es sah aus, als sehe die App nie nach.
pruefe("der Balken kommt trotzdem", bool(d["ohne_installation"]), d["ohne_installation"])
pruefe("ohne 'Jetzt aktualisieren' - der Knopf könnte ja nichts tun",
       d["ohne_installation"] and not d["ohne_installation"]["jetzt"],
       d["ohne_installation"])
pruefe("dafür steht der Grund daneben",
       d["ohne_installation"] and "nicht aus einer Installation" in d["ohne_installation"]["text"],
       d["ohne_installation"])
pruefe("und im Band bleibt der Knopf aus", d["ohne_installation_knopf"])

print("\nNichts Neues")
pruefe("kein Balken", d["nichts_neues"])
pruefe("und Hilfe sagt, dass das die neueste ist",
       d["hilfe_aktuell"] == "Notizmappe 1.2.56 — das ist die neueste Fassung",
       d["hilfe_aktuell"])

print("\nWenn die Prüfung schiefgeht")
pruefe("kein Balken", d["fehler_kein_balken"])
# Keine Beschwichtigung, sondern der Grund - und zwar dort, wo man nachsieht.
pruefe("aber Hilfe nennt den Grund",
       "GitHub nicht erreichbar" in (d["hilfe_fehler"] or ""), d["hilfe_fehler"])
pruefe("und es wird nach 15 Sekunden noch einmal versucht",
       d["zweiter_versuch"] == 15000, d["zweiter_versuch"])
pruefe("klappt es dann, kommt der Balken",
       d["nach_zweitem"] and "1.2.57" in d["nach_zweitem"]["text"], d["nach_zweitem"])

print("\nWenn die Brücke noch gar nicht steht")
# Das ist der haeufigste Fall vier Sekunden nach dem Start.
pruefe("kein Absturz, kein Balken", d["wurf_kein_absturz"])
pruefe("und auch hier steht der Grund in Hilfe",
       "bruecke_da" in (d["wurf_hilfe"] or ""), d["wurf_hilfe"])

shutil.rmtree(ordner, ignore_errors=True)
print()
if fehler:
    print(f"{len(fehler)} Prüfungen gescheitert")
    sys.exit(1)
print("Der Update-Hinweis kommt an")
