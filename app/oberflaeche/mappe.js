/* Notizmappe - freie Flaeche. Kein Framework, damit es ohne Build laeuft.
 *
 * Grundgedanke: die Seite ist eine Liste von Kaesten mit x/y/Breite. Der Browser
 * haelt sie in `elemente`, auf der Platte steht nur das JSON. Gespeichert wird
 * verzoegert, aber immer die ganze Seite - bei einer Handvoll Kaesten pro Seite
 * ist das billiger als Einzelfeld-Buchhaltung. */

const WARTEN = 900;        // ms Ruhe nach der letzten Eingabe, bevor gespeichert wird
const POLL = 15000;        // ms zwischen "hat jemand von aussen geschrieben?"
const RASTER = 8;          // Positionen auf 8px runden, sonst zappelt alles
const MAX_ANHANG = 25 * 1024 * 1024;   // wie speicher.MAX_ANHANG

/* Kleiner Merker statt localStorage direkt.
 *
 * In WebKitGTK unter pywebview gibt es localStorage schlicht nicht - die Variable
 * ist nicht definiert, der Zugriff wirft einen ReferenceError, und das riss beim
 * ersten Aufruf das ganze Skript mit: kein Baum, keine Kästen, kein Tippen. Auch
 * im Browser kann der Zugriff fehlschlagen (privates Fenster, gesperrte
 * Seitendaten). Nichts hier drin ist wichtig genug, um daran zu scheitern - es
 * sind Bequemlichkeiten. Also: versuchen, und sonst nur für diese Sitzung merken.
 */
const merker = (() => {
  const ersatz = {};
  let laden, sichern;
  try {
    window.localStorage.setItem('probe', '1');
    window.localStorage.removeItem('probe');
    laden = (k) => window.localStorage.getItem(k);
    sichern = (k, w) => window.localStorage.setItem(k, w);
  } catch (f) {
    laden = (k) => (k in ersatz ? ersatz[k] : null);
    sichern = (k, w) => { ersatz[k] = String(w); };
  }
  return {
    holen(k, standard = null) { try { const w = laden(k); return w === null ? standard : w; } catch (f) { return standard; } },
    legen(k, w) { try { sichern(k, String(w)); } catch (f) { /* dann eben nicht */ } },
  };
})();

const geraet = (() => {
  let g = merker.holen('geraet');
  if (!g) { g = Math.random().toString(36).slice(2, 10); merker.legen('geraet', g); }
  return g;
})();

const $ = (s) => document.querySelector(s);
const flaeche = $('#flaeche');
const buehne = $('#buehne');
const zustandAnzeige = $('#zustand');

let offen = null;       // {notizbuch, abschnitt, name, rev, titel}
let elemente = [];      // [{id, typ, x, y, b, html}]
let schmutzig = false;
let speicherUhr = null;
let zoom = 1;
let baumDaten = [];
const zugeklappt = new Set(JSON.parse(merker.holen('zugeklappt', '[]')));

/* ------------------------------------------------------------------ Hilfen */

/* Ruft das Programm auf - direkt, ohne Netz.
 *
 * window.pywebview.api sind die Methoden aus bruecke.py, im selben Prozess -
 * kein Netz, keine Adresse. Die Namen unten sehen aus wie Pfade; das ist nur eine
 * Ordnung, damit an einer einzigen Stelle steht, was wohin geht.
 *
 * Fehler kommen als {fehler: "..."} zurueck und werden hier wieder zu Ausnahmen,
 * damit die try/catch drumherum bleiben koennen wie sie waren. */
const WEGE = {
  'GET /api/baum':             (p, b) => b.baum(),
  'POST /api/notizbuch':       (p, b, r) => b.notizbuch_anlegen(r.name),
  'POST /api/abschnitt':       (p, b, r) => b.abschnitt_anlegen(r.notizbuch, r.name),
  'POST /api/seite':           (p, b, r) => b.seite_anlegen(r.notizbuch, r.abschnitt, r.titel || ''),
  'GET /api/seite':            (p, b) => b.seite_lesen(p.notizbuch, p.abschnitt, p.name),
  'PUT /api/seite':            (p, b, r) => b.seite_speichern(r),
  'POST /api/seite/titel':     (p, b, r) => b.seite_umbenennen(r.notizbuch, r.abschnitt, r.name, r.titel),
  'GET /api/stand':            (p, b) => b.stand(p.notizbuch, p.abschnitt, p.name),
  'POST /api/loeschen':        (p, b, r) => b.loeschen(r.art, r.pfad),
  'GET /api/einstellungen':    (p, b) => b.einstellungen(),
  'GET /api/ferne':            (p, b) => b.ferne_stand(),
  'POST /api/ferne/anmelden':  (p, b, r) => b.ferne_anmelden(r),
  'POST /api/ferne/abmelden':  (p, b) => b.ferne_abmelden(),
  'POST /api/ferne/code':      (p, b, r) => b.ferne_code(r),
  'POST /api/ferne/umschalten': (p, b, r) => b.ferne_umschalten(r),
  'POST /api/einstellungen':   (p, b, r) => b.optionen_setzen(r),
  'POST /api/ordner/waehlen':  (p, b) => b.ordner_waehlen(),
  'POST /api/ordner':          (p, b, r) => b.ordner_setzen(r),
  'POST /api/server':          (p, b, r) => b.server_seite(r.art, r.weg, r.rumpf),
  'GET /api/version':          (p, b) => b.version(p.frisch === 'true'),
  'POST /api/update':          (p, b) => b.update(),
  'GET /api/update/stand':     (p, b) => b.update_stand(),
  'POST /api/onenote':         (p, b, r) => b.onenote_einlesen(r),
  'POST /api/datei/speichern': (p, b, r) => b.datei_speichern(r),
  'GET /api/verlauf':          (p, b) => b.versionen(p.notizbuch, p.abschnitt, p.name),
  'GET /api/verlauf/fassung':  (p, b) => b.version_lesen(p.notizbuch, p.abschnitt, p.name, p.marke),
  'POST /api/verlauf/zurueck': (p, b, r) => b.version_zurueck(r),
  'GET /api/papierkorb':       (p, b) => b.papierkorb(),
  'POST /api/papierkorb/zurueck': (p, b, r) => b.papierkorb_zurueck(r),
  'POST /api/papierkorb/weg':  (p, b, r) => b.papierkorb_weg(r),
  'POST /api/papierkorb/leeren': (p, b) => b.papierkorb_leeren(),
  'GET /api/sperre':           (p, b) => b.sperre_stand(),
  'POST /api/sperre/an':       (p, b, r) => b.sperre_einrichten(r),
  'POST /api/sperre/nachholen': (p, b) => b.sperre_nachholen(),
  'POST /api/sperre/auf':      (p, b, r) => b.entsperren(r),
  'POST /api/sperre/zu':       (p, b) => b.sperren(),
  'POST /api/sperre/passwort':      (p, b, r) => b.sperre_passwort(r),
  'POST /api/sperre/zuruecksetzen': (p, b, r) => b.sperre_zuruecksetzen(r),
  'POST /api/sperre/rettung':       (p, b, r) => b.sperre_rettung_neu(r),
  'POST /api/sperre/rettung/datei': (p, b, r) => b.rettung_speichern(r),
  'GET /api/sperre/rettung/ziel':   (p, b) => b.rettung_ziel(),
  'POST /api/sperre/aus':      (p, b, r) => b.sperre_aus(r),
  'POST /api/sperre/minuten':  (p, b, r) => b.sperre_minuten(r),
};

/* Das Fenster meldet sich kurz nach dem Laden.
 *
 * Nicht nur auf window.pywebview.api warten: das Objekt ist schon da, bevor die
 * Methoden daran hängen - dann gibt es ein "b.baum is not a function". Deshalb
 * auf das Ereignis "pywebviewready" hören und zusätzlich nachsehen, ob wirklich
 * eine der Methoden angekommen ist. */
let bruecke_bereit = null;

function bruecke_da() {
  const a = window.pywebview && window.pywebview.api;
  return a && typeof a.baum === 'function' ? a : null;
}

function bruecke() {
  const jetzt = bruecke_da();
  if (jetzt) return Promise.resolve(jetzt);
  if (bruecke_bereit) return bruecke_bereit;

  bruecke_bereit = new Promise((fertig, schiefgegangen) => {
    let versuche = 0;
    const nachsehen = () => {
      const a = bruecke_da();
      if (a) { clearInterval(uhr); window.removeEventListener('pywebviewready', nachsehen); fertig(a); return true; }
      return false;
    };
    window.addEventListener('pywebviewready', nachsehen);
    const uhr = setInterval(() => {
      if (nachsehen()) return;
      if (++versuche > 600) {        // eine Minute
        clearInterval(uhr);
        window.removeEventListener('pywebviewready', nachsehen);
        bruecke_bereit = null;       // beim nächsten Versuch von vorn warten

        // Verständlich bleiben: hier geht es um nichts im Netz, sondern um die
        // Schnittstelle, über die das Fenster mit dem Programm spricht.
        const was = !window.pywebview ? 'das Fenster meldet sich gar nicht'
          : !window.pywebview.api ? 'das Fenster ist da, aber ohne Schnittstelle'
          : 'die Schnittstelle ist leer geblieben';
        schiefgegangen(new Error(
          `Das Fenster und das Programm haben sich nicht gefunden (${was}). `
          + 'Das hat nichts mit dem Netz zu tun. Meist hilft: Notizmappe schließen und neu starten.'));
      }
    }, 100);
  });
  return bruecke_bereit;
}

async function api(weg, art = 'GET', rumpf = null) {
  const [pfad, abfrage] = weg.split('?');
  const teile = {};
  for (const [k, v] of new URLSearchParams(abfrage || '')) teile[k] = v;

  const schluessel = `${art} ${pfad}`;
  const tun = WEGE[schluessel];
  if (!tun) throw new Error('Unbekannter Aufruf: ' + schluessel);

  const b = await bruecke();
  const daten = await tun(teile, b, rumpf || {});
  // Bei der Versionsprüfung ist "fehler" ein Feld der Antwort ("GitHub nicht
  // erreichbar"), kein Abbruch - der Rest der Antwort gilt trotzdem. Würde hier
  // geworfen, bliebe in den Einstellungen für immer "wird geprüft …" stehen.
  // Zugesperrt waehrend der Arbeit (Zeitsperre): nicht einen roten Balken ueber
  // halb geladene Notizen legen, sondern alles wegraeumen und den Sperrschirm
  // zeigen. (Frueher stand hier location.reload() - siehe nichtsMehrZeigen:
  // die Seite hat keine Adresse, davon wird das Fenster schwarz.)
  if (daten && daten.art === 'zu' && !laeuftZu) {
    laeuftZu = true;
    zusperrenZeigen();
  }
  if (daten && daten.fehler && schluessel !== 'GET /api/version') {
    const f = new Error(daten.fehler);
    f.daten = daten;
    if (daten.art === 'konflikt') f.status = 409;
    throw f;
  }
  return daten;
}

function sagen(text, dauer = 2500) {
  zustandAnzeige.textContent = text;
  if (dauer) setTimeout(() => { if (zustandAnzeige.textContent === text) zustandAnzeige.textContent = ''; }, dauer);
}

function melden(text, knoepfe = []) {
  const m = $('#meldung');
  m.textContent = '';
  m.append(Object.assign(document.createElement('span'), { textContent: text }));
  for (const [beschriftung, tun] of knoepfe) {
    const b = Object.assign(document.createElement('button'), { type: 'button', textContent: beschriftung });
    b.addEventListener('click', tun);
    m.append(b);
  }
  m.hidden = false;
}
const meldungWeg = () => { $('#meldung').hidden = true; };

/* -------------------------------------------------------------------- Baum */

/* Eine Meldung dort, wo der Baum stünde.
 *
 * Bisher stand bei einem Fehler nur im Hauptbereich etwas - und wer das Fenster
 * schmal gezogen hat, sieht davon nichts und starrt auf eine schwarze Fläche.
 * Die Seitenleiste ist aber immer da. */
function baumMeldung(text, knopf) {
  const baum = $('#baum');
  baum.textContent = '';
  const kasten = document.createElement('div');
  kasten.className = 'baumleer';
  kasten.textContent = text;
  if (knopf) {
    const k = document.createElement('button');
    k.type = 'button';
    k.textContent = knopf[0];
    k.addEventListener('click', knopf[1]);
    kasten.append(k);
  }
  baum.append(kasten);
}

/* Was oben in der Leiste steht. Am Server der Name der Mappe dort, oertlich
 * "Eigener Ordner" - der Pfad gehoert in den Hinweis, nicht in die Zeile:
 * C:\\Users\\wolfi\\Notizen sagt einem beim Hinsehen nichts, was man nicht
 * ohnehin weiss, und bei einem langen Pfad steht die Leiste voll. Was zaehlt,
 * ist: schreibe ich gerade hier oder dort? */
function ordnerZeigen(e) {
  const wo = $('#ordner');
  if (!wo || !e) return;
  const fern = e.ferne && e.ferne.aktiv;
  wo.textContent = fern ? e.ordner : 'Eigener Ordner';
  // Die Adresse gehoert in den Hinweis, nicht in die Zeile: dort wird sie
  // abgeschnitten, und wissen will man "hier oder dort", nicht "welcher Port".
  wo.title = fern
    ? `${e.ferne.adresse || 'Server'} als ${e.ferne.benutzer || '?'}`
    : 'Datenordner: ' + (e.ordner || '?');
  wo.classList.toggle('amserver', !!fern);
  // Unten in der Leiste: als wer man am Server angemeldet ist - genau so wie
  // in der Serverfassung, mit rundem Zeichen und Menue nach oben.
  const knopf = $('#profilknopf');
  if (knopf) {
    // Ein Konto gibt es, wenn man mit einem Server verbunden ist - oder wenn
    // dies die Serverfassung selbst ist (dort laeuft die Oberflaeche nicht
    // am eigenen Rechner, und angemeldet ist man ohnehin).
    hierAmRechner = e.hier !== false;
    const konto = fern || !hierAmRechner;
    const wer = (e.ferne && e.ferne.benutzer) || '';
    knopf.hidden = !konto;
    if (!konto) $('#profilmenue').hidden = true;
    if (konto) {
      const zeigen = (name, rolle) => {
        $('#profilname').textContent = name || 'angemeldet';
        $('#profilbild').textContent = (name || '?').slice(0, 1).toUpperCase();
        $('#profilwer').textContent = name || '…';
        $('#profilrolle').textContent = rolle || '';
      };
      zeigen(wer, profilRolle);
      // Name und Rolle stehen im Profil am Server - einmal holen, dann
      // stehen sie da, ohne bei jedem Aufklappen zu fragen.
      if (!profilRolle) {
        serverHol('GET', '/profil').then((d) => {
          profilRolle = (d && d.rolle) || '';
          zeigen((d && d.ich) || wer, profilRolle);
        }).catch(() => { /* dann eben ohne */ });
      }
    } else {
      profilRolle = '';
    }
  }
}

function baumZeichnen() {
  const baum = $('#baum');
  baum.textContent = '';
  if (!baumDaten || !baumDaten.length) {
    baumMeldung('Hier liegt noch kein Notizbuch.', ['Einstellungen öffnen', () => tafelZeigen(true)]);
    // Wo "hier" ist, gehört dazu - sonst sucht man an der falschen Stelle.
    api('/api/einstellungen').then((e) => {
      ordnerZeigen(e);
      const kasten = $('#baum').querySelector('.baumleer');
      if (kasten && e && e.ordner) {
        kasten.firstChild.textContent = `Hier liegt noch kein Notizbuch (${e.ordner}).`;
      }
    }).catch(() => { /* dann eben ohne Pfad */ });
    return;
  }
  let letzteQuelle = null;
  for (const buch of baumDaten) {
    // Ueberschrift, sobald die Seite wechselt - sonst stuenden die
    // Notizbuecher von hier und von dort ununterscheidbar untereinander.
    if (buch.quelle && buch.quelle !== letzteQuelle) {
      letzteQuelle = buch.quelle;
      const welche = buch.quelle;
      const kopf = document.createElement('div');
      kopf.className = 'quelle' + (welche === baumSeite ? ' hier' : '');
      kopf.append(Object.assign(document.createElement('span'),
                                { textContent: welche === 'server' ? baumMappe : 'Eigener Ordner' }));
      const mehr = Object.assign(document.createElement('button'),
                                 { type: 'button', textContent: '＋',
                                   title: 'Neues Notizbuch hier' });
      mehr.addEventListener('click', () => notizbuchAnlegen(welche));
      kopf.append(mehr);
      kopf.title = welche === baumSeite
        ? 'Hier schreibst du gerade'
        : 'Ein Klick auf eine Seite wechselt hierher';
      baum.append(kopf);
    }
    const bd = document.createElement('div');
    const klappschluessel = (buch.quelle ? buch.quelle + '/' : '') + buch.name;
    bd.className = 'buch' + (zugeklappt.has(klappschluessel) ? ' eingeklappt' : '');
    // Auch auf der anderen Seite stehen die Knoepfe - sie wechseln vorher
    // dorthin. Ohne das legt ein "+ Seite" am eigenen Abschnitt eine Seite am
    // Server an; das passiert genau einmal, und danach sucht man sie.
    const fremd = !!buch.quelle && buch.quelle !== baumSeite;
    const hier = buch.quelle;
    if (fremd) bd.classList.add('drueben');
    bd.append(zeile(buch.name, [
      ['+ Abschnitt', '＋', () => aufSeite(hier, async () => {
        const n = prompt('Name des Abschnitts:'); if (!n) return;
        await api('/api/abschnitt', 'POST', { notizbuch: buch.name, name: n });
        zugeklappt.delete(klappschluessel); await baumLaden();
      })],
      ['Notizbuch loeschen', '🗑',
       () => aufSeite(hier, () => loeschen('notizbuch', [buch.name], buch.name))],
    ], () => klappen(bd, klappschluessel), zugeklappt.has(klappschluessel)));

    for (const ab of buch.abschnitte) {
      const schluessel = klappschluessel + '/' + ab.name;
      const ad = document.createElement('div');
      ad.className = 'abschnitt' + (zugeklappt.has(schluessel) ? ' eingeklappt' : '');
      ad.append(zeile(ab.name, [
        ['+ Seite', '＋', () => aufSeite(hier, async () => {
          const r = await api('/api/seite', 'POST', { notizbuch: buch.name, abschnitt: ab.name, titel: 'Neue Seite' });
          zugeklappt.delete(schluessel); await baumLaden();
          await seiteOeffnen(buch.name, ab.name, r.name);
          $('#titel').select();
        })],
        ['Abschnitt loeschen', '🗑',
         () => aufSeite(hier, () => loeschen('abschnitt', [buch.name, ab.name], ab.name))],
      ], () => klappen(ad, schluessel), zugeklappt.has(schluessel)));

      for (const s of ab.seiten) {
        const sd = zeile(s.titel, [
          ['Seite loeschen', '🗑',
           () => aufSeite(hier, () => loeschen('seite', [buch.name, ab.name, s.name], s.titel))],
        ]);
        sd.classList.add('seite');
        if (s.konflikt) sd.classList.add('konflikt');
        if (s.konflikt) sd.title = 'Konfliktkopie vom Sync - hier stehen zwei Fassungen derselben Seite';
        // Beschädigt: die Datei lässt sich nicht lesen. Das gehört in die
        // Leiste, nicht erst in eine Fehlermeldung beim Anklicken - sonst
        // sucht man den Grund bei sich.
        if (s.kaputt) {
          sd.classList.add('kaputt');
          sd.title = 'Diese Datei lässt sich nicht lesen - vermutlich halb übertragen. '
            + 'Unter Verlauf → Seitenversionen liegt meist eine frühere Fassung.';
        }
        if (!fremd && offen && offen.notizbuch === buch.name && offen.abschnitt === ab.name
            && offen.name === s.name) sd.classList.add('aktiv');
        sd.querySelector('.name').addEventListener('click', () => (fremd
          ? seiteDrueben(buch.name, ab.name, s.name, buch.quelle)
          : seiteOeffnen(buch.name, ab.name, s.name)));
        ad.append(sd);
      }
      bd.append(ad);
    }
    baum.append(bd);
  }
}

function zeile(text, aktionen = [], aufKlick = null, zu = false) {
  const z = document.createElement('div');
  z.className = 'zeile';
  if (aufKlick) {
    // Pfeil nach dem gemerkten Zustand - vorher stand nach jedem Neuzeichnen ▾,
    // auch bei eingeklappten Notizbuechern.
    const pfeil = Object.assign(document.createElement('span'), { className: 'pfeil', textContent: zu ? '▸' : '▾' });
    pfeil.addEventListener('click', aufKlick);
    z.append(pfeil);
  }
  z.append(Object.assign(document.createElement('span'), { className: 'name', textContent: text }));
  for (const [titel, zeichen, tun] of aktionen) {
    const b = Object.assign(document.createElement('button'), { type: 'button', title: titel, textContent: zeichen });
    b.addEventListener('click', (e) => { e.stopPropagation(); tun(); });
    z.append(b);
  }
  return z;
}

function klappen(knoten, schluessel) {
  knoten.classList.toggle('eingeklappt');
  if (knoten.classList.contains('eingeklappt')) zugeklappt.add(schluessel); else zugeklappt.delete(schluessel);
  merker.legen('zugeklappt', JSON.stringify([...zugeklappt]));
  knoten.querySelector('.pfeil').textContent = knoten.classList.contains('eingeklappt') ? '▸' : '▾';
}

async function loeschen(art, pfad, wie) {
  if (!confirm(`"${wie}" in den Papierkorb?`)) return;
  // Liegt die offene Seite darin - auch wenn ein ganzes Notizbuch oder ein
  // Abschnitt weggeht? Vorher nur der Seitenname verglichen: eine gleichnamige
  // Seite anderswo schloss die falsche, ein geloeschter Abschnitt keine.
  const drin = offen && offen.notizbuch === pfad[0]
    && (pfad.length < 2 || offen.abschnitt === pfad[1])
    && (pfad.length < 3 || offen.name === pfad[2]);
  if (drin) {
    clearTimeout(speicherUhr);
    while (speichertGerade) await speichertGerade;
  }
  try {
    await api('/api/loeschen', 'POST', { art, pfad });
  } catch (f) {
    melden('Löschen ging nicht: ' + f.message);
    return;
  }
  if (drin) {
    schmutzig = false;
    offen = null;
    flaecheLeeren();
    merker.legen('zuletzt', 'null');
  }
  await baumLaden();
}

/* Erste vorhandene Seite im ganzen Baum, oder null. */
function erstesSeitchen() {
  for (const b of baumDaten) {
    for (const a of b.abschnitte) {
      if (a.seiten.length) return [b.name, a.name, a.seiten[0].name];
    }
  }
  return null;
}

/* Verbunden stehen beide Seiten in der Leiste: die Notizbuecher am Server und
 * die eigenen. Welche davon gerade die aktive ist, sagt der Baum mit. */
let baumSeite = '';            // 'server', 'eigen' oder leer (gar nicht verbunden)
let baumMappe = 'Servermappe';

async function baumLaden() {
  const r = await api('/api/baum');
  baumDaten = r.notizbuecher;
  baumSeite = r.jetzt || '';
  baumMappe = r.mappe || 'Servermappe';
  baumZeichnen();
}

/* Die Seite wechseln - ohne Neuladen.
 *
 * location.reload() geht hier NICHT: das Fenster bekommt seine Seite als
 * Inhalt hineingereicht (pywebview, html=...), sie hat gar keine Adresse. Ein
 * Neuladen landet deshalb auf einer leeren Seite, und das Fenster wird
 * schwarz. Also wird von Hand erneuert, was der Wechsel betrifft: die offene
 * Seite, der Baum, die Kopfzeile.
 *
 * Ungespeichertes geht vorher noch weg - sonst kostet ein Klick auf die
 * andere Seite den letzten Satz. */
async function seitenwechsel(an, ziel) {
  try {
    if (schmutzig) await speichernJetzt();
  } catch (f) { /* lieber wechseln als haengenbleiben */ }
  await api('/api/ferne/umschalten', 'POST', { an });
  schmutzig = false;
  offen = null;
  flaecheLeeren();
  merker.legen('zuletzt', ziel ? JSON.stringify(ziel) : 'null');
  await baumLaden();
  try { ordnerZeigen(await api('/api/einstellungen')); } catch (f) { /* dann ohne */ }
  // Zugesperrt faengt der Sperrschirm das ab, nicht ein roter Balken.
  if (!await sperreAufmachen()) return;
  const wohin = ziel || (() => {
    const erste = erstesSeitchen();
    return erste ? { buch: erste[0], abschnitt: erste[1], name: erste[2] } : null;
  })();
  if (wohin) await seiteOeffnen(wohin.buch, wohin.abschnitt, wohin.name);
  sagen(an ? `Jetzt in ${baumMappe}` : 'Jetzt im eigenen Ordner');
}

/* Eine Seite von drueben aufmachen: umschalten und genau sie oeffnen. */
async function seiteDrueben(buch, abschnitt, name, quelle) {
  sagen(quelle === 'server' ? `Wechsle zu ${baumMappe} …` : 'Wechsle zum eigenen Ordner …', 0);
  try {
    await seitenwechsel(quelle === 'server', { buch, abschnitt, name });
  } catch (f) {
    melden('Umschalten ging nicht: ' + f.message);
  }
}

/* ------------------------------------------------------------------ Seiten */

function flaecheLeeren() {
  flaeche.textContent = '';
  elemente = [];
  $('#titel').value = '';
  $('#titel').disabled = true;
  $('#leerhinweis').hidden = false;
  flaecheMessen();
}

async function seiteOeffnen(buch, abschnitt, name) {
  if (schmutzig) await speichernJetzt();
  if (schmutzig) {
    // Speichern ging nicht (Konflikt, Programm beendet): nicht wegwechseln, sonst sind
    // die Aenderungen still verworfen. Die Meldung dazu steht schon oben.
    sagen('Erst speichern - die Seite hat ungesicherte Änderungen', 4000);
    return false;
  }
  meldungWeg();
  const s = await api(`/api/seite?notizbuch=${encodeURIComponent(buch)}&abschnitt=${encodeURIComponent(abschnitt)}&name=${encodeURIComponent(name)}`);
  offen = { notizbuch: buch, abschnitt, name: s.name, rev: s.rev, mtime: s.mtime };
  elemente = s.elemente;
  $('#titel').value = s.titel || '';
  $('#titel').disabled = false;
  flaeche.textContent = '';
  // Striche sind kein Kasten - sie kommen auf die Zeichenebene darueber.
  for (const e of elemente) if (e.typ !== 'stift') flaeche.append(kastenBauen(e));
  zeichnungLaden();
  $('#leerhinweis').hidden = elemente.some((e) => e.typ !== 'stift' || (e.striche || []).length);
  schmutzig = false;
  flaecheMessen();
  baumZeichnen();
  merker.legen('zuletzt', JSON.stringify({ buch, abschnitt, name: s.name }));
}

/* ------------------------------------------------------------------ Kaesten */

/* Bilddaten holen und als data:-Adresse einsetzen. Es gibt keine Adresse mehr,
 * unter der die Datei laege - und die Seite soll auch nicht beliebige lokale
 * Dateien laden duerfen. */
async function bildEinsetzen(bild, datei) {
  try {
    const b = await bruecke();
    const r = await b.anhang_bild(offen.notizbuch, offen.abschnitt, offen.name, datei);
    if (r && r.fehler) throw new Error(r.fehler);
    bild.src = `data:${r.medientyp};base64,${r.daten}`;
  } catch (f) {
    bild.replaceWith(Object.assign(document.createElement('div'), {
      className: 'fehlt', textContent: 'Bild fehlt: ' + datei,
    }));
  }
}

function kastenBauen(e) {
  const k = document.createElement('div');
  k.className = 'kasten kasten-' + e.typ;
  k.dataset.id = e.id;
  k.style.left = e.x + 'px';
  k.style.top = e.y + 'px';
  k.style.width = e.b + 'px';

  const griff = document.createElement('div');
  griff.className = 'griff';
  const weg = Object.assign(document.createElement('button'), { type: 'button', className: 'weg', textContent: '✕', title: 'Löschen' });
  weg.addEventListener('click', () => kastenWeg(e.id));
  griff.append(weg);

  if (e.typ !== 'text') {
    const inhalt = e.typ === 'bild' ? bildBauen(e) : dateiBauen(e);
    const breite = document.createElement('div');
    breite.className = 'breite';
    k.append(griff, inhalt, breite);
    ziehen(griff, (dx, dy, start) => {
      e.x = Math.max(0, Math.round((start.x + dx / zoom) / RASTER) * RASTER);
      e.y = Math.max(0, Math.round((start.y + dy / zoom) / RASTER) * RASTER);
      k.style.left = e.x + 'px';
      k.style.top = e.y + 'px';
    }, () => ({ x: e.x, y: e.y }));
    ziehen(breite, (dx, _dy, start) => {
      e.b = Math.max(e.typ === 'bild' ? 40 : 160, Math.round((start.b + dx / zoom) / RASTER) * RASTER);
      k.style.width = e.b + 'px';
    }, () => ({ b: e.b }));
    return k;
  }

  const text = document.createElement('div');
  text.className = 'text';
  text.contentEditable = 'true';
  text.spellcheck = true;
  text.innerHTML = e.html || '';
  textBilderZeigen(text);

  const breite = document.createElement('div');
  breite.className = 'breite';

  k.append(griff, text, breite);

  text.addEventListener('input', () => { e.html = text.innerHTML; angefasst(); });
  text.addEventListener('focus', () => k.classList.add('aktiv'));
  text.addEventListener('blur', () => {
    k.classList.remove('aktiv');
    // Leeren Kasten nicht stehen lassen - sonst sammeln sich unsichtbare Reste.
    if (!text.textContent.trim() && !text.querySelector('img')) kastenWeg(e.id, true);
  });
  // Eingefuegtes HTML aus fremden Seiten erst beim Speichern gesaeubert - hier
  // nur als Text annehmen, damit nicht gleich fremdes Layout mitkommt.
  text.addEventListener('paste', (ev) => {
    const dateien = Array.from((ev.clipboardData && ev.clipboardData.files) || []);
    if (dateien.length) {
      // Bild aus der Zwischenablage an die Schreibstelle, nicht daneben.
      ev.preventDefault();
      ev.stopPropagation();
      const sel = window.getSelection();
      const stelle = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
      inTextEinsetzen(text, e, dateien, stelle);
      return;
    }
    const roh = ev.clipboardData && ev.clipboardData.getData('text/plain');
    if (roh == null) return;
    ev.preventDefault();
    document.execCommand('insertText', false, roh);
  });

  ziehen(griff, (dx, dy, start) => {
    e.x = Math.max(0, Math.round((start.x + dx / zoom) / RASTER) * RASTER);
    e.y = Math.max(0, Math.round((start.y + dy / zoom) / RASTER) * RASTER);
    k.style.left = e.x + 'px';
    k.style.top = e.y + 'px';
  }, () => ({ x: e.x, y: e.y }));

  ziehen(breite, (dx, _dy, start) => {
    e.b = Math.max(80, Math.round((start.b + dx / zoom) / RASTER) * RASTER);
    k.style.width = e.b + 'px';
  }, () => ({ b: e.b }));

  return k;
}

function bildBauen(e) {
  const bild = document.createElement('img');
  bild.className = 'bild';
  bild.alt = e.beschriftung || e.datei;
  bild.draggable = false;
  bild.addEventListener('load', flaecheMessen);
  bildEinsetzen(bild, e.datei);
  return bild;
}

function dateiBauen(e) {
  // Kein Download: die Datei liegt auf dieser Platte. Ein Klick öffnet sie mit
  // dem Programm, das das System dafür vorsieht.
  const kachel = document.createElement('button');
  kachel.type = 'button';
  kachel.className = 'datei';
  kachel.title = 'Öffnen: ' + e.datei;
  kachel.addEventListener('click', async () => {
    try {
      const b = await bruecke();
      const r = await b.anhang_oeffnen(offen.notizbuch, offen.abschnitt, offen.name, e.datei);
      if (r && r.fehler) melden(r.fehler);
    } catch (f) { melden('Ließ sich nicht öffnen: ' + f.message); }
  });
  kachel.addEventListener('contextmenu', async (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    try {
      const b = await bruecke();
      await b.anhang_speichern_unter(offen.notizbuch, offen.abschnitt, offen.name, e.datei);
    } catch (f) { melden('Speichern ging nicht: ' + f.message); }
  });
  kachel.append(
    Object.assign(document.createElement('span'), { className: 'zeichen', textContent: '📎' }),
    Object.assign(document.createElement('span'), { className: 'dname', textContent: e.datei }),
    Object.assign(document.createElement('span'), { className: 'dgroesse', textContent: groesse(e.groesse) }),
  );
  return kachel;
}

function groesse(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1).replace('.', ',') + ' MB';
}

/* Hochladen: die Datei geht zuerst auf die Platte, erst danach entsteht das
 * Element. Andersherum zeigte die Seite kurz auf etwas, das es noch nicht gibt -
 * und bei einem Abbruch für immer. */
function anhangName(datei) {
  // Aus der Zwischenablage heisst jedes Bild "image.png". Ein Name mit Uhrzeit
  // ist im Dateimanager lesbarer und kommt dem nächsten Bild nicht in die Quere.
  const ablage = /^image\.(\w+)$/.exec(datei.name || '');
  if (!ablage) return datei.name || 'Datei';
  const z = new Date();
  const zwei = (n) => String(n).padStart(2, '0');
  return `Bild ${z.getFullYear()}-${zwei(z.getMonth() + 1)}-${zwei(z.getDate())}`
    + ` ${zwei(z.getHours())}-${zwei(z.getMinutes())}-${zwei(z.getSeconds())}.${ablage[1]}`;
}

async function alsBase64(datei) {
  const bytes = new Uint8Array(await datei.arrayBuffer());
  let text = '';
  // In Stücken: String.fromCharCode mit Hunderttausenden Argumenten sprengt den Stapel.
  for (let i = 0; i < bytes.length; i += 0x8000) {
    text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(text);
}

/* Bilder, die mitten im Text stehen, bekommen ihre Daten nachgereicht: im
 * gespeicherten HTML steht nur der Dateiname (data-datei), nie eine Adresse. */
function textBilderZeigen(text) {
  for (const bild of text.querySelectorAll('img[data-datei]')) {
    if (bild.getAttribute('src')) continue;
    bild.addEventListener('load', flaecheMessen, { once: true });
    bildEinsetzen(bild, bild.dataset.datei);
  }
}

/* Bilder an die Stelle setzen, an der der Zeiger steht - alles andere wird eine
 * Kachel auf der Fläche. */
async function inTextEinsetzen(text, e, dateien, stelle) {
  for (const d of dateien) {
    if (d.size > MAX_ANHANG) {
      melden(`"${d.name}" ist ${groesse(d.size)} groß - mehr als ${groesse(MAX_ANHANG)} gehen nicht.`);
      continue;
    }
    zustandAnzeige.textContent = 'lädt …';
    let r;
    try {
      const b = await bruecke();
      r = await b.anhang_ablegen(offen.notizbuch, offen.abschnitt, offen.name,
                                 anhangName(d), await alsBase64(d));
    } catch (f) {
      melden('Hinzufügen ging nicht: ' + f.message);
      continue;
    }
    if (r && r.fehler) { melden(`"${d.name}" ging nicht: ${r.fehler}`); continue; }

    if (r.art !== 'bild') {
      // Keine Bilder (PDF, Zip ...) bleiben Kacheln auf der Fläche.
      elementAnlegen(r, d, e.x, e.y + text.offsetHeight + 40);
      continue;
    }
    const bild = document.createElement('img');
    bild.dataset.datei = r.datei;
    bild.alt = d.name;
    if (stelle && text.contains(stelle.startContainer)) {
      stelle.deleteContents();
      stelle.insertNode(bild);
      stelle.setStartAfter(bild);
      stelle.collapse(true);
    } else {
      text.append(bild);
    }
    textBilderZeigen(text);
    // Gleich eintragen, nicht erst nach dem letzten Bild - sonst speichert die Uhr
    // zwischendurch einen Stand, der die schon hochgeladenen nicht kennt.
    e.html = text.innerHTML;
    angefasst();
  }
  e.html = text.innerHTML;
  zustandAnzeige.textContent = '';
  angefasst();
}

/* Ein fertig abgelegter Anhang wird zu einem Element auf der Fläche. */
function elementAnlegen(r, datei, x, y) {
  const e = {
    id: Math.random().toString(36).slice(2, 12),
    typ: r.art, x, y,
    b: r.art === 'bild' ? 420 : 280,
    datei: r.datei, beschriftung: datei.name, groesse: r.groesse,
  };
  elemente.push(e);
  flaeche.append(kastenBauen(e));
  $('#leerhinweis').hidden = true;
  flaecheMessen();
  angefasst();
  return e;
}

async function anhangHochladen(datei, x, y) {
  if (!offen) { sagen('Erst eine Seite öffnen', 2000); return; }
  // Vorher prüfen: sonst wandert eine riesige Datei erst durch die Brücke, nur
  // damit sie danach abgelehnt wird.
  if (datei.size > MAX_ANHANG) {
    melden(`"${datei.name}" ist ${groesse(datei.size)} groß - mehr als ${groesse(MAX_ANHANG)} gehen nicht.`);
    return;
  }
  zustandAnzeige.textContent = 'lädt …';
  let r;
  try {
    const b = await bruecke();
    r = await b.anhang_ablegen(offen.notizbuch, offen.abschnitt, offen.name,
                               anhangName(datei), await alsBase64(datei));
  } catch (f) {
    melden('Hinzufügen ging nicht: ' + f.message);
    zustandAnzeige.textContent = '';
    return;
  }
  if (r && r.fehler) {
    melden(`"${datei.name}" ging nicht: ${r.fehler}`);
    zustandAnzeige.textContent = '';
    return;
  }
  const e = {
    id: Math.random().toString(36).slice(2, 12),
    typ: r.art, x, y,
    b: r.art === 'bild' ? 420 : 280,
    datei: r.datei, beschriftung: datei.name, groesse: r.groesse,
  };
  elemente.push(e);
  flaeche.append(kastenBauen(e));
  $('#leerhinweis').hidden = true;
  flaecheMessen();
  angefasst();
}

async function dateienAnnehmen(dateien, x, y) {
  let versatz = 0;
  for (const d of dateien) {
    await anhangHochladen(d, x, y + versatz);
    versatz += 40;
  }
}

function ziehen(handgriff, bewegen, startWerte) {
  handgriff.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0) return;
    // Knoepfe im Griff (das ✕) nicht zum Ziehen nehmen: mit gefangenem Zeiger
    // ginge der Klick an den Griff statt an den Knopf.
    if (ev.target.closest('button')) return;
    ev.preventDefault();
    handgriff.setPointerCapture(ev.pointerId);
    const x0 = ev.clientX, y0 = ev.clientY, start = startWerte();
    const zug = (e2) => bewegen(e2.clientX - x0, e2.clientY - y0, start);
    const schluss = () => {
      handgriff.removeEventListener('pointermove', zug);
      handgriff.removeEventListener('pointerup', schluss);
      handgriff.removeEventListener('pointercancel', schluss);
      flaecheMessen();
      angefasst();
    };
    handgriff.addEventListener('pointermove', zug);
    handgriff.addEventListener('pointerup', schluss);
    handgriff.addEventListener('pointercancel', schluss);
  });
}

function kastenNeu(x, y) {
  const e = { id: Math.random().toString(36).slice(2, 12), typ: 'text', x, y, b: 420, html: '' };
  elemente.push(e);
  const k = kastenBauen(e);
  flaeche.append(k);
  $('#leerhinweis').hidden = true;
  k.querySelector('.text').focus();
  flaecheMessen();
  return e;
}

function kastenWeg(id, still = false) {
  const i = elemente.findIndex((e) => e.id === id);
  if (i < 0) return;
  elemente.splice(i, 1);
  const k = flaeche.querySelector(`.kasten[data-id="${id}"]`);
  if (k) k.remove();
  $('#leerhinweis').hidden = elemente.length > 0;
  flaecheMessen();
  if (!still) angefasst(); else if (schmutzig) angefasst();
}

/* Die Flaeche waechst mit dem Inhalt, damit man nach rechts und unten
 * weiterschreiben kann - wie das endlose Blatt in OneNote. */
function flaecheMessen() {
  let b = 0, h = 0;
  for (const k of flaeche.children) {
    if (!k.classList || !k.classList.contains('kasten')) continue;
    b = Math.max(b, k.offsetLeft + k.offsetWidth);
    h = Math.max(h, k.offsetTop + k.offsetHeight);
  }
  // Auch die Striche zaehlen: sonst hoert die Flaeche dort auf, wo der letzte
  // Kasten steht, und man kann nicht weitermalen.
  const rand = strichRand();
  b = Math.max(b, rand.b);
  h = Math.max(h, rand.h);
  flaeche.style.width = Math.max(b + 600, buehne.clientWidth / zoom) + 'px';
  flaeche.style.height = Math.max(h + 600, buehne.clientHeight / zoom) + 'px';
  malblattMessen();
}

/* --------------------------------------------------------------- Speichern */

let aenderung = 0;          // zaehlt jede Eingabe - so sieht ein Speichern, ob danach noch getippt wurde
let speichertGerade = null; // laufendes Speichern, damit nie zwei gleichzeitig unterwegs sind

function angefasst() {
  aenderung++;
  schmutzig = true;
  zustandAnzeige.textContent = '…';
  clearTimeout(speicherUhr);
  speicherUhr = setTimeout(speichernJetzt, WARTEN);
}

const gleicheSeite = (a, b) => a && b && a.notizbuch === b.notizbuch && a.abschnitt === b.abschnitt && a.name === b.name;

async function speichernJetzt() {
  clearTimeout(speicherUhr);
  // Laeuft schon eines, erst abwarten: zwei Speichern mit derselben rev - das
  // zweite bekaeme 409 und haelt die eigene Aenderung fuer eine fremde.
  while (speichertGerade) await speichertGerade;
  if (!offen || !schmutzig) return;
  const stand = { ...offen };
  const nr = aenderung;
  speichertGerade = (async () => {
    try {
      const r = await api('/api/seite', 'PUT', {
        notizbuch: stand.notizbuch, abschnitt: stand.abschnitt, name: stand.name,
        rev: stand.rev, titel: $('#titel').value, elemente, geraet,
      });
      if (gleicheSeite(offen, stand)) { offen.rev = r.rev; offen.mtime = r.mtime; }
      // Nur sauber, wenn waehrenddessen nichts dazukam. Sonst ist die Uhr von
      // angefasst() noch gestellt und das naechste Speichern nimmt den Rest mit.
      if (aenderung === nr) { schmutzig = false; sagen('gespeichert'); }
    } catch (f) {
      if (f.status === 409) { konflikt(f.daten && f.daten.aktuell); return; }
      zustandAnzeige.textContent = 'nicht gespeichert';
      melden('Speichern ging nicht: ' + f.message, [['Nochmal', () => { schmutzig = true; speichernJetzt(); }]]);
    } finally {
      speichertGerade = null;
    }
  })();
  await speichertGerade;
}

function konflikt(fremd) {
  zustandAnzeige.textContent = 'Konflikt';
  melden(
    'Diese Seite wurde woanders geändert (Gerät ' + ((fremd && fremd.geraet) || '?') + '). Deine Änderungen sind noch nicht gespeichert.',
    [
      ['Meine Fassung behalten', async () => {
        // Bewusst drueberschreiben: wir uebernehmen die fremde rev und speichern erneut.
        if (fremd) offen.rev = fremd.rev;
        meldungWeg(); schmutzig = true; await speichernJetzt();
      }],
      ['Fremde Fassung laden', async () => {
        meldungWeg(); schmutzig = false;
        await seiteOeffnen(offen.notizbuch, offen.abschnitt, offen.name);
      }],
    ]
  );
}

/* Von aussen - also vom Sync-Client - kann die Datei sich jederzeit aendern.
 * Wir merken das am rev und fragen nach, statt stillschweigend zu ueberschreiben. */
async function nachsehen() {
  if (!offen || document.hidden) return;
  try {
    const s = await api(`/api/stand?notizbuch=${encodeURIComponent(offen.notizbuch)}&abschnitt=${encodeURIComponent(offen.abschnitt)}&name=${encodeURIComponent(offen.name)}`);
    if (!s.da) { melden('Die Seite ist nicht mehr da (gelöscht oder verschoben).'); return; }
    if (s.rev !== offen.rev && s.geraet !== geraet) {
      if (schmutzig) konflikt(s);
      else melden('Neuere Fassung vom Sync da.', [['Laden', async () => {
        meldungWeg(); await seiteOeffnen(offen.notizbuch, offen.abschnitt, offen.name);
      }]]);
    }
  } catch (f) { /* gerade nicht erreichbar - beim naechsten Mal wieder */ }
}

/* -------------------------------------------------------------- Bedienung */

buehne.addEventListener('dblclick', (ev) => {
  if (!offen) { sagen('Erst eine Seite öffnen', 2000); return; }
  if (ev.target.closest('.kasten')) return;
  const r = flaeche.getBoundingClientRect();
  kastenNeu(
    Math.max(0, Math.round((ev.clientX - r.left) / zoom / RASTER) * RASTER),
    Math.max(0, Math.round((ev.clientY - r.top) / zoom / RASTER) * RASTER)
  );
  angefasst();
});

// Dateien auf die Flaeche ziehen
for (const art of ['dragenter', 'dragover']) {
  buehne.addEventListener(art, (ev) => {
    if (!ev.dataTransfer || !Array.from(ev.dataTransfer.types || []).includes('Files')) return;
    ev.preventDefault();
    buehne.classList.add('zieltafel');
  });
}
buehne.addEventListener('dragleave', (ev) => {
  if (ev.relatedTarget && buehne.contains(ev.relatedTarget)) return;
  buehne.classList.remove('zieltafel');
});
buehne.addEventListener('drop', (ev) => {
  if (!ev.dataTransfer || !ev.dataTransfer.files.length) return;
  ev.preventDefault();
  buehne.classList.remove('zieltafel');
  // Auf einen Textkasten gezogen: Bilder dorthin, wo der Zeiger im Text steht.
  const text = ev.target.closest && ev.target.closest('.kasten .text');
  const k = text && text.closest('.kasten');
  const e = k && elemente.find((x) => x.id === k.dataset.id);
  if (e) {
    let stelle = null;
    if (document.caretRangeFromPoint) {
      stelle = document.caretRangeFromPoint(ev.clientX, ev.clientY);
    } else if (document.caretPositionFromPoint) {
      const pos = document.caretPositionFromPoint(ev.clientX, ev.clientY);
      if (pos) {
        stelle = document.createRange();
        stelle.setStart(pos.offsetNode, pos.offset);
      }
    }
    inTextEinsetzen(text, e, Array.from(ev.dataTransfer.files), stelle);
    return;
  }
  const r = flaeche.getBoundingClientRect();
  dateienAnnehmen(ev.dataTransfer.files,
    Math.max(0, Math.round((ev.clientX - r.left) / zoom / RASTER) * RASTER),
    Math.max(0, Math.round((ev.clientY - r.top) / zoom / RASTER) * RASTER));
});

// Bild aus der Zwischenablage: landet als Datei, nicht als Text im Kasten.
document.addEventListener('paste', (ev) => {
  const dateien = Array.from((ev.clipboardData && ev.clipboardData.files) || []);
  if (!dateien.length) return;
  ev.preventDefault();
  const k = document.activeElement && document.activeElement.closest('.kasten');
  const e = k && elemente.find((x) => x.id === k.dataset.id);
  dateienAnnehmen(dateien, e ? e.x : 40, e ? e.y + 60 : 40);
});

$('#anhang').addEventListener('click', () => $('#dateiwahl').click());
$('#dateiwahl').addEventListener('change', async (ev) => {
  if (!ev.target.files.length) return;
  const mitte = Math.round((buehne.scrollLeft + 80) / zoom / RASTER) * RASTER;
  const oben = Math.round((buehne.scrollTop + 80) / zoom / RASTER) * RASTER;
  await dateienAnnehmen(ev.target.files, mitte, oben);
  ev.target.value = '';
});

// Mit mittlerer Maustaste oder Leertaste die Flaeche schieben.
let schiebt = null;
buehne.addEventListener('pointerdown', (ev) => {
  const mitLeertaste = leertaste && !ev.target.closest('[contenteditable]');
  if (ev.button !== 1 && !mitLeertaste) return;
  ev.preventDefault();
  schiebt = { x: ev.clientX, y: ev.clientY, l: buehne.scrollLeft, t: buehne.scrollTop };
  buehne.classList.add('schiebt');
  buehne.setPointerCapture(ev.pointerId);
});
buehne.addEventListener('pointermove', (ev) => {
  if (!schiebt) return;
  buehne.scrollLeft = schiebt.l - (ev.clientX - schiebt.x);
  buehne.scrollTop = schiebt.t - (ev.clientY - schiebt.y);
});
for (const e of ['pointerup', 'pointercancel']) {
  buehne.addEventListener(e, () => { schiebt = null; buehne.classList.remove('schiebt'); });
}

let leertaste = false;
document.addEventListener('keydown', (ev) => {
  // Leertaste = Flaeche schieben, aber nicht dort, wo sie etwas tut: Text, Felder,
  // Knoepfe (die loest man mit Leertaste aus).
  if (ev.code === 'Space' && !ev.target.closest('[contenteditable], input, textarea, select, button, a')) {
    leertaste = true; ev.preventDefault();
  }
  if ((ev.ctrlKey || ev.metaKey) && ev.key === 's') { ev.preventDefault(); speichernJetzt(); }
  if ((ev.ctrlKey || ev.metaKey) && (ev.key === '+' || ev.key === '=')) { ev.preventDefault(); zoomen(0.1); }
  if ((ev.ctrlKey || ev.metaKey) && ev.key === '-') { ev.preventDefault(); zoomen(-0.1); }
  if ((ev.ctrlKey || ev.metaKey) && ev.key === '0') { ev.preventDefault(); zoomSetzen(1); }
});
document.addEventListener('keyup', (ev) => { if (ev.code === 'Space') leertaste = false; });
// Leertaste gedrueckt, Fenster gewechselt: das keyup kommt nie an, und jeder
// Klick schob danach die Flaeche statt etwas auszuwaehlen.
window.addEventListener('blur', () => { leertaste = false; });


let letzterKasten = null;

/* --- Schriftart und -groesse ------------------------------------------------
 *
 * execCommand ist aus der Mode, macht hier aber genau das Richtige: es setzt die
 * Auszeichnung auf die Auswahl und laesst den Rest in Ruhe. styleWithCSS=false
 * sorgt dafuer, dass dabei <font size> und <font face> entsteht statt beliebigem
 * CSS - nur diese beiden Angaben laesst der Reiniger durch. */
function aufAuswahl(befehl, wert) {
  const k = (document.activeElement && document.activeElement.closest('.kasten'))
    || letzterKasten;
  if (!k) { sagen('Erst in einen Kasten klicken', 2000); return; }
  try { document.execCommand('styleWithCSS', false, false); } catch (f) { /* egal */ }
  document.execCommand(befehl, false, wert);
  const e = elemente.find((x) => x.id === k.dataset.id);
  if (e) { e.html = k.querySelector('.text').innerHTML; angefasst(); }
}

// mousedown abfangen: ein Klick ins Auswahlfeld wuerde sonst erst den Textkasten
// verlassen, und dann gibt es keine Auswahl mehr, auf die man etwas anwenden kann.
for (const [feld, befehl] of [['#schriftart', 'fontName'], ['#schriftgroesse', 'fontSize']]) {
  const w = $(feld);
  let merker = null;
  w.addEventListener('mousedown', () => {
    const k = document.activeElement && document.activeElement.closest('.kasten');
    merker = k ? k.dataset.id : null;
  });
  w.addEventListener('change', () => {
    if (merker) {
      const kasten = flaeche.querySelector(`.kasten[data-id="${merker}"] .text`);
      if (kasten) kasten.focus();
    }
    aufAuswahl(befehl, w.value);
  });
}

/* --- Schriftenliste vom Rechner -------------------------------------------
 *
 * Eine feste Liste im Programm waere immer falsch: sie enthielte Schriften, die
 * hier fehlen, und kennte die nicht, die installiert sind. */
let schriftstand = null;

async function schriftenLaden() {
  try {
    const b = await bruecke();
    schriftstand = await b.schriften();
  } catch (f) { return; }
  if (!schriftstand || schriftstand.fehler) { schriftstand = null; return; }
  auswahlfelderFuellen();
}

function eintrag(feld, wert, beschriftung) {
  const o = document.createElement('option');
  o.value = wert;
  o.textContent = beschriftung;
  o.style.fontFamily = wert.includes(',') ? wert : `"${wert}"`;
  feld.append(o);
  return o;
}

function auswahlfelderFuellen() {
  const d = schriftstand;
  if (!d) return;
  for (const feld of document.querySelectorAll('select[data-befehl="fontName"], #schriftart')) {
    const vorher = feld.value;
    feld.textContent = '';

    // Favoriten ganz oben - dafür sind sie da. Erst danach die Gruppen.
    if (d.favoriten && d.favoriten.length) {
      const g = document.createElement('optgroup');
      g.label = '★ Favoriten';
      feld.append(g);
      for (const name of d.favoriten) eintrag(g, name, name);
    }
    for (const [wert, name] of (d.vorschlaege || [])) eintrag(feld, wert, name);
    for (const fach of Object.keys(d.empfohlen || {})) {
      const g = document.createElement('optgroup');
      g.label = d.empfohlen[fach].name;
      feld.append(g);
      for (const name of d.empfohlen[fach].schriften) eintrag(g, name, name);
    }
    if (d.schriften && d.schriften.length) {
      const g = document.createElement('optgroup');
      g.label = `Alle auf diesem Rechner (${d.schriften.length})`;
      feld.append(g);
      for (const name of d.schriften) eintrag(g, name, name);
    }
    if (vorher) feld.value = vorher;
  }
  // Die Leisten haben eine eigene Schriftliste, die von hier gespiegelt
  // wird. Ohne das stuende dort "Standard", bis man das erste Mal etwas
  // markiert - die Liste kommt ja erst vom Rechner nachgeladen.
  for (const w of document.querySelectorAll('.formatleiste')) flSchriftenSpiegeln(w);
}

/* --- Schriftenliste in den Einstellungen ---------------------------------- */
function schriftzeile(name, istFavorit) {
  const zeile = document.createElement('div');
  zeile.className = 'zeile';

  const stern = document.createElement('button');
  stern.type = 'button';
  stern.className = 'stern' + (istFavorit ? ' an' : '');
  stern.textContent = istFavorit ? '★' : '☆';
  stern.title = istFavorit ? 'Nicht mehr bevorzugen' : 'Nach oben in die Auswahl';
  stern.addEventListener('click', () => sternUmlegen(name, !istFavorit));

  // Der Name in seiner eigenen Schrift: so sieht man sofort, wie sie aussieht,
  // und muss nicht von einem Beispielsatz auf die Schrift schliessen.
  const probe = document.createElement('span');
  probe.className = 'probe';
  probe.style.fontFamily = `"${name}"`;
  probe.textContent = name;

  // Daneben derselbe Name in der gewohnten Schrift - bei Symbolschriften wie
  // Wingdings ist die Probe sonst nicht zu entziffern.
  const beschriftung = document.createElement('span');
  beschriftung.className = 'name';
  beschriftung.textContent = name;

  zeile.append(stern, probe, beschriftung);
  return zeile;
}

async function sternUmlegen(name, an) {
  try {
    const b = await bruecke();
    const r = await b.favorit_setzen(name, an);
    if (r && r.fehler) { $('#e-schrift-hinweis').textContent = r.fehler; return; }
    if (schriftstand) schriftstand.favoriten = r.favoriten;
    schriftenTafelFuellen();
    auswahlfelderFuellen();
  } catch (f) {
    $('#e-schrift-hinweis').textContent = 'Ging nicht: ' + f.message;
  }
}

function schriftenTafelFuellen() {
  const d = schriftstand;
  const oben = $('#e-schrift-favoriten');
  const alle = $('#e-schriftliste');
  if (!oben || !alle) return;
  oben.textContent = '';
  alle.textContent = '';
  if (!d) {
    $('#e-schrift-hinweis').textContent = 'Die Schriften ließen sich nicht lesen.';
    return;
  }
  const favoriten = d.favoriten || [];

  if (favoriten.length) {
    for (const name of favoriten) oben.append(schriftzeile(name, true));
  } else {
    oben.append(Object.assign(document.createElement('p'), {
      className: 'hinweis',
      textContent: 'Noch keine Favoriten. Unten eine Schrift mit ☆ markieren.',
    }));
  }

  const suche = ($('#e-schrift-suche').value || '').toLowerCase();
  const gezeigt = new Set();

  for (const fach of Object.keys(d.empfohlen || {})) {
    const treffer = d.empfohlen[fach].schriften.filter((n) => n.toLowerCase().includes(suche));
    if (!treffer.length) continue;
    alle.append(Object.assign(document.createElement('div'), {
      className: 'gruppe', textContent: d.empfohlen[fach].name,
    }));
    for (const name of treffer) { alle.append(schriftzeile(name, favoriten.includes(name))); gezeigt.add(name); }
  }

  const rest = (d.schriften || []).filter((n) => !gezeigt.has(n) && n.toLowerCase().includes(suche));
  if (rest.length) {
    alle.append(Object.assign(document.createElement('div'), {
      className: 'gruppe', textContent: `Alle weiteren (${rest.length})`,
    }));
    for (const name of rest) alle.append(schriftzeile(name, favoriten.includes(name)));
  }
  $('#e-schrift-hinweis').textContent = (d.schriften || []).length
    ? `${d.schriften.length} Schriften gefunden.`
    : 'Es ließen sich keine Schriften vom System lesen.';
}

$('#e-schrift-suche').addEventListener('input', schriftenTafelFuellen);

/* --- Leiste, die beim Markieren aufgeht -------------------------------------
 *
 * Markieren und dann nach oben in die Werkzeugleiste fahren ist weit; und wer
 * unterwegs irgendwo hinklickt, verliert die Markierung. Die Leiste kommt
 * deshalb dorthin, wo markiert wurde. */
const minileiste = $('#minileiste');
const FARBEN = [
  ['#1f1d1a', 'Standard'], ['#b23b2e', 'Rot'], ['#c2690a', 'Orange'],
  ['#2f7d32', 'Grün'], ['#1565c0', 'Blau'], ['#7a5cff', 'Violett'], ['#78736a', 'Grau'],
];
for (const [farbe, name] of FARBEN) {
  const k = document.createElement('button');
  k.type = 'button';
  k.title = name;
  k.style.background = farbe;
  k.dataset.farbe = farbe;
  $('#farben').append(k);
}

/* Welcher Textkasten ist gerade markiert? Geradeaus und ohne Verschachtelung -
 * jeder Sonderfall hier kostet die ganze Leiste. */
function kastenVonAuswahl() {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount || sel.isCollapsed) return null;
  let knoten = sel.getRangeAt(0).commonAncestorContainer;
  if (knoten && knoten.nodeType !== 1) knoten = knoten.parentElement;
  if (!knoten || !knoten.closest) return null;
  return knoten.closest('.kasten');
}

/* Liegt der Schreibzeiger gerade in einem Textkasten - oder in der Leiste selbst?
 *
 * Die Markierung allein genügt nicht: die Webansicht lässt sie stehen, auch wenn
 * man längst woandershin geklickt hat. Dann bliebe die Leiste über einem Text
 * schweben, mit dem man gar nicht mehr arbeitet. */
function schreibtGerade() {
  const a = document.activeElement;
  if (!a) return false;
  if (a.closest && a.closest('#minileiste')) return true;
  return !!(a.closest && a.closest('.kasten .text'));
}

function minileisteZeigen() {
  const kasten = kastenVonAuswahl();
  if (!kasten || !schreibtGerade()) { minileiste.hidden = true; return; }
  const sel = window.getSelection();
  letzterKasten = kasten;

  const r = sel.getRangeAt(0).getBoundingClientRect();
  minileiste.hidden = false;
  const b = minileiste.getBoundingClientRect();
  // Über die Markierung, und wenn dort kein Platz ist, darunter.
  let oben = r.top - b.height - 8;
  if (oben < 8) oben = r.bottom + 8;
  minileiste.style.top = Math.min(oben, window.innerHeight - b.height - 8) + 'px';
  minileiste.style.left = Math.max(8, Math.min(r.left + r.width / 2 - b.width / 2,
                                               window.innerWidth - b.width - 8)) + 'px';
  stand_anzeigen();
}

/* Zeigen, was an der Markierung schon gesetzt ist. */
function stand_anzeigen() {
  for (const knopf of minileiste.querySelectorAll('button[data-befehl]')) {
    let an = false;
    try { an = document.queryCommandState(knopf.dataset.befehl); } catch (f) { /* egal */ }
    knopf.style.background = an ? 'color-mix(in srgb, var(--akzent) 22%, transparent)' : '';
  }
  for (const [feld, befehl] of [['fontName', 'fontName'], ['fontSize', 'fontSize']]) {
    const w = minileiste.querySelector(`select[data-befehl="${befehl}"]`);
    if (!w) continue;
    try {
      const wert = document.queryCommandValue(befehl);
      if (wert) {
        const treffer = [...w.options].find((o) => o.value.toLowerCase().startsWith(String(wert).toLowerCase().replace(/^['"]|['"]$/g, '')) || o.value === wert);
        if (treffer) w.value = treffer.value;
      }
    } catch (f) { /* queryCommandValue kennt nicht jede Webansicht */ }
  }
}

document.addEventListener('selectionchange', () => {
  // Nicht bei jedem Zwischenstand springen - erst wenn die Maus losgelassen ist.
  if (!ziehtMarkierung) minileisteZeigen();
});
let ziehtMarkierung = false;
document.addEventListener('mousedown', (ev) => {
  if (ev.target.closest('#minileiste')) return;
  ziehtMarkierung = true;
  minileiste.hidden = true;
});
document.addEventListener('mouseup', () => { ziehtMarkierung = false; setTimeout(minileisteZeigen, 0); });

/* Verlässt der Schreibzeiger den Kasten, geht die Leiste mit - es sei denn, er
 * wandert in die Leiste selbst (Knopf, Auswahlfeld). */
document.addEventListener('focusout', () => {
  setTimeout(() => { if (!schreibtGerade()) minileiste.hidden = true; }, 0);
});
document.addEventListener('touchend', () => { ziehtMarkierung = false; setTimeout(minileisteZeigen, 30); });
document.addEventListener('dblclick', () => setTimeout(minileisteZeigen, 0));
document.addEventListener('keyup', (ev) => {
  // Mit Umschalt markieren, Strg+A, und nach Escape wieder weg.
  if (ev.shiftKey || ev.key === 'Shift' || (ev.ctrlKey && ev.key.toLowerCase() === 'a')) {
    setTimeout(minileisteZeigen, 0);
  } else if (ev.key === 'Escape') {
    minileiste.hidden = true;
  }
});

/* Ein Klick in die Leiste darf die Markierung nicht kosten. Bei Knöpfen genügt
 * preventDefault; ein Auswahlfeld muss den Fokus bekommen, sonst klappt es nicht
 * auf - dafür wird die Markierung gemerkt und nachher wiederhergestellt. */
let gemerkteStelle = null;
minileiste.addEventListener('mousedown', (ev) => {
  const sel = window.getSelection();
  gemerkteStelle = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  if (ev.target.tagName !== 'SELECT') ev.preventDefault();
});

function stelleZurueck() {
  if (!gemerkteStelle) return;
  const feld = letzterKasten && letzterKasten.querySelector('.text');
  if (feld) feld.focus();
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(gemerkteStelle);
}

minileiste.addEventListener('click', (ev) => {
  const knopf = ev.target.closest('button');
  if (!knopf) return;
  if (knopf.dataset.farbe) { aufAuswahl('foreColor', knopf.dataset.farbe); stand_anzeigen(); return; }
  if (knopf.dataset.befehl) { aufAuswahl(knopf.dataset.befehl); stand_anzeigen(); return; }
  if (knopf.dataset.eigen === 'sauber') { aufAuswahl('removeFormat'); hervorhebungWeg(); return; }
  if (knopf.dataset.eigen === 'mark') hervorheben();
});
for (const w of minileiste.querySelectorAll('select[data-befehl]')) {
  w.addEventListener('change', () => {
    stelleZurueck();
    aufAuswahl(w.dataset.befehl, w.value);
    minileisteZeigen();
  });
}

/* <mark> gibt es als Befehl nicht - also von Hand um die Auswahl legen.
 * Eine Hintergrundfarbe per style waere der uebliche Weg und genau die Art
 * Freitext-CSS, die hier nicht in die Dateien soll. Deshalb steht nur der
 * Name der Farbe als data-farbe da, und die Stildatei macht daraus die
 * Farbe - dieselbe feste Liste steht in reinigen.py. Gelb bekommt keinen
 * Eintrag: so bleibt alles unveraendert, was hervorgehoben wurde, als es
 * nur diese eine Farbe gab. */
function hervorheben(farbe) {
  const sel = window.getSelection();
  if (!sel.rangeCount || sel.isCollapsed) return;
  const r = sel.getRangeAt(0);
  const schon = (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement)
    .closest('mark');
  if (schon) {
    // Dieselbe Farbe noch einmal heisst: weg damit. Eine andere faerbt um.
    const jetzt = schon.getAttribute('data-farbe') || 'gelb';
    if (!farbe || farbe === jetzt) { hervorhebungWeg(); return; }
    if (farbe === 'gelb') schon.removeAttribute('data-farbe');
    else schon.setAttribute('data-farbe', farbe);
    gemerkt();
    return;
  }
  const m = document.createElement('mark');
  if (farbe && farbe !== 'gelb') m.setAttribute('data-farbe', farbe);
  try {
    m.appendChild(r.extractContents());
    r.insertNode(m);
    sel.removeAllRanges();
    const neu = document.createRange();
    neu.selectNodeContents(m);
    sel.addRange(neu);
  } catch (f) {
    melden('Das ließ sich nicht hervorheben: ' + f.message);
    return;
  }
  gemerkt();
}

function hervorhebungWeg() {
  const sel = window.getSelection();
  if (!sel.rangeCount) return;
  const knoten = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
  const m = knoten.closest('mark');
  if (m) {
    const eltern = m.parentNode;
    while (m.firstChild) eltern.insertBefore(m.firstChild, m);
    m.remove();
    eltern.normalize();
  }
  gemerkt();
}

/* Den geänderten Kasten übernehmen und zum Speichern vormerken. */
function gemerkt() {
  const k = letzterKasten || (document.activeElement && document.activeElement.closest('.kasten'));
  if (!k) return;
  const e = elemente.find((x) => x.id === k.dataset.id);
  if (e) { e.html = k.querySelector('.text').innerHTML; angefasst(); }
}

/* --- Menü bei der rechten Maustaste ----------------------------------------
 *
 * Die Webansicht im Fenster bringt keins mit. Ohne das kommt man an Kopieren und
 * Einfuegen nur ueber die Tastatur - und wer das nicht weiss, kann seinen eigenen
 * Text nicht herausbekommen. */
const rechtsmenue = $('#rechtsmenue');

function menueZu() { rechtsmenue.hidden = true; }

document.addEventListener('contextmenu', (ev) => {
  if (ev.target.closest('#einstellungen')) return;
  ev.preventDefault();
  const imText = !!ev.target.closest('[contenteditable]');
  const etwasMarkiert = !window.getSelection().isCollapsed;
  rechtsmenue.querySelector('[data-tun="ausschneiden"]').disabled = !(imText && etwasMarkiert);
  rechtsmenue.querySelector('[data-tun="kopieren"]').disabled = !etwasMarkiert;
  rechtsmenue.querySelector('[data-tun="einfuegen"]').disabled = !imText;
  rechtsmenue.querySelector('[data-tun="alles"]').disabled = !imText;
  rechtsmenue.hidden = false;
  // Ins Bild rücken, falls am Rand geklickt wurde
  const b = rechtsmenue.getBoundingClientRect();
  rechtsmenue.style.left = Math.min(ev.clientX, window.innerWidth - b.width - 8) + 'px';
  rechtsmenue.style.top = Math.min(ev.clientY, window.innerHeight - b.height - 8) + 'px';
});
document.addEventListener('mousedown', (ev) => { if (!ev.target.closest('#rechtsmenue')) menueZu(); });
document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') menueZu(); });

rechtsmenue.addEventListener('click', async (ev) => {
  const knopf = ev.target.closest('button');
  if (!knopf) return;
  const tun = knopf.dataset.tun;
  menueZu();
  const kasten = document.activeElement && document.activeElement.closest('.kasten');
  try {
    if (tun === 'kopieren' || tun === 'ausschneiden') {
      // Erst die Zwischenablage des Systems, sonst der alte Weg - je nach
      // Webansicht ist mal das eine, mal das andere erlaubt.
      const text = window.getSelection().toString();
      try { await navigator.clipboard.writeText(text); }
      catch (f) { document.execCommand('copy'); }
      if (tun === 'ausschneiden') document.execCommand('delete');
    } else if (tun === 'einfuegen') {
      let text = '';
      try { text = await navigator.clipboard.readText(); }
      catch (f) { sagen('Einfügen geht hier nur mit Strg+V', 3000); return; }
      document.execCommand('insertText', false, text);
    } else if (tun === 'alles') {
      const feld = kasten ? kasten.querySelector('.text') : null;
      if (feld) {
        const r = document.createRange();
        r.selectNodeContents(feld);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(r);
      }
    }
  } catch (f) {
    melden('Ging nicht: ' + f.message);
  }
  if (kasten) {
    const e = elemente.find((x) => x.id === kasten.dataset.id);
    if (e) { e.html = kasten.querySelector('.text').innerHTML; angefasst(); }
  }
});

function zoomen(d) { zoomSetzen(zoom + d); }
function zoomSetzen(z) {
  zoom = Math.min(2.5, Math.max(0.4, Math.round(z * 10) / 10));
  flaeche.style.transform = `scale(${zoom})`;
  $('#zoomwert').textContent = Math.round(zoom * 100) + '%';
  merker.legen('zoom', zoom);
  flaecheMessen();
}
$('#rein').addEventListener('click', () => zoomen(0.1));
$('#raus').addEventListener('click', () => zoomen(-0.1));
buehne.addEventListener('wheel', (ev) => {
  if (!ev.ctrlKey) return;
  ev.preventDefault();
  zoomen(ev.deltaY < 0 ? 0.1 : -0.1);
}, { passive: false });

$('#titel').addEventListener('input', angefasst);
$('#titel').addEventListener('change', async () => {
  if (!offen) return;
  // Seite und Titel jetzt festhalten: "change" kommt beim Verlassen des Feldes -
  // oft durch den Klick auf eine andere Seite im Baum. Las man offen erst nach
  // dem Speichern, war dort schon die neue Seite und bekam den Titel der alten.
  const seite = { ...offen };
  const titel = $('#titel').value;
  await speichernJetzt();
  if (schmutzig && gleicheSeite(offen, seite)) return;   // ungespeichert umbenennen gaebe einen Konflikt
  let r;
  try {
    r = await api('/api/seite/titel', 'POST', {
      notizbuch: seite.notizbuch, abschnitt: seite.abschnitt, name: seite.name, titel,
    });
  } catch (f) { melden('Umbenennen ging nicht: ' + f.message); return; }
  // Der Dateiname zieht mit dem Titel mit - nur neu laden, wenn diese Seite noch offen ist.
  if (gleicheSeite(offen, seite)) await seiteOeffnen(seite.notizbuch, seite.abschnitt, r.name);
  await baumLaden();
});

/* Ein neues Notizbuch - auf der Seite, auf der man es angeklickt hat.
 * Frueher hing das an einem Knopf unten in der Leiste; der sagte aber nicht,
 * wo das Buch entsteht, sobald dort zwei Baeume stehen. */
async function notizbuchAnlegen(quelle) {
  const n = prompt('Name des Notizbuchs:');
  if (!n) return;
  await aufSeite(quelle, async () => {
    await api('/api/notizbuch', 'POST', { name: n });
    await baumLaden();
  });
}

/* Etwas auf der anderen Seite tun: erst dorthin wechseln, dann tun. Sonst
 * legt ein "+ Seite" am eigenen Abschnitt eine Seite am Server an - das
 * passiert genau einmal, und danach sucht man sie. */
async function aufSeite(quelle, tun) {
  if (quelle && baumSeite && quelle !== baumSeite) {
    await seitenwechsel(quelle === 'server', null);
  }
  await tun();
}

window.addEventListener('beforeunload', (ev) => {
  if (!schmutzig) return;
  speichernJetzt();
  ev.preventDefault();
  ev.returnValue = '';
});
window.addEventListener('resize', flaecheMessen);
document.addEventListener('visibilitychange', () => { if (!document.hidden) nachsehen(); });
setInterval(nachsehen, POLL);

/* ------------------------------------------------------------------ Update */

const updateKnopf = $('#update');

async function versionPruefen(frisch = false) {
  try {
    const v = await api('/api/version' + (frisch ? '?frisch=true' : ''));
    if (!v.neuer || !v.aktualisierbar) { updateKnopf.hidden = true; return v; }
    updateKnopf.hidden = false;
    updateKnopf.disabled = false;
    updateKnopf.textContent = `Update auf ${v.verfuegbar}`;
    updateKnopf.title = `Installiert ist ${v.installiert}.` + (v.notizen ? '\n\n' + v.notizen.slice(0, 500) : '');
    return v;
  } catch (f) {
    // Nicht stillschweigend aufgeben: wer auf "Nach Updates suchen" gedrückt hat,
    // sieht sonst für immer "wird geprüft …". Der Fehler gehört dorthin, wo
    // gefragt wurde.
    updateKnopf.hidden = true;
    return { installiert: null, verfuegbar: null, neuer: false,
             aktualisierbar: false, fehler: f.message || String(f) };
  }
}

updateKnopf.addEventListener('click', async () => {
  const v = await api('/api/version');
  if (!confirm(`Auf Version ${v.verfuegbar} aktualisieren? Installiert ist ${v.installiert}.\n\n`
    + 'Die Notizen bleiben unberührt. Die Notizmappe startet dabei einmal neu.')) return;
  updateKnopf.disabled = true;
  if (schmutzig) await speichernJetzt();
  updateFensterZeigen('Update wird geladen …',
                      `Version ${v.verfuegbar} wird von GitHub geholt und geprüft.`);
  try {
    const r = await api('/api/update', 'POST');
    updateFensterZeigen('Update wird installiert …',
                        `${r.von} → ${r.nach}. Die Notizmappe startet gleich neu.`);
    updateVerfolgen(r.nach);
  } catch (f) {
    updateFensterFehler('Das Update ging nicht: ' + f.message);
    updateKnopf.disabled = false;
  }
});

const updatefenster = $('#updatefenster');

function updateFensterZeigen(titel, text) {
  $('#u-titel').textContent = titel;
  $('#u-schritt').textContent = text;
  $('#u-hinweis').textContent = '';
  $('#u-zu').hidden = true;
  updatefenster.querySelector('.balken').classList.remove('fertig');
  updatefenster.hidden = false;
}

function updateFensterFehler(text) {
  $('#u-titel').textContent = 'Update fehlgeschlagen';
  $('#u-schritt').textContent = text;
  $('#u-hinweis').textContent = 'Die alte Fassung läuft unverändert weiter.';
  updatefenster.querySelector('.balken').classList.add('fertig');
  $('#u-zu').hidden = false;
}
$('#u-zu').addEventListener('click', () => { updatefenster.hidden = true; });

/* Waehrend des Updates startet das Programm neu - die Abfragen laufen also eine
 * Weile ins Leere. Das ist kein Fehler, sondern genau der Moment. */
function updateVerfolgen(ziel) {
  let versuche = 0;
  const uhr = setInterval(async () => {
    versuche++;
    try {
      const v = await api('/api/version');
      if (v.installiert === ziel) {
        clearInterval(uhr);
        updateFensterZeigen('Fertig', `Version ${ziel} ist installiert.`);
        updatefenster.querySelector('.balken').classList.add('fertig');
        // Das Programm startet sich selbst neu; kommt es doch nicht dazu,
        // wird hier wenigstens frisch geholt - neu laden geht nicht, siehe
        // nichtsMehrZeigen().
        setTimeout(wiederAufbauen, 1200);
        return;
      }
      const p = await api('/api/update/stand');
      if (p.fehler) {
        clearInterval(uhr);
        updateFensterFehler('Beim Installieren ist etwas schiefgegangen.');
        $('#u-hinweis').textContent = p.text.slice(-400);
      }
    } catch (f) { /* läuft gerade nicht - weiter warten */ }
    if (versuche > 60) {   // 3 Minuten
      clearInterval(uhr);
      updateFensterFehler('Das dauert ungewöhnlich lange.');
      $('#u-hinweis').textContent = 'Falls nichts mehr passiert: die Notizmappe von Hand neu starten.';
    }
  }, 3000);
}

/* Beim Start nachsehen - und auf Wunsch gleich einspielen. Erst danach wird die
 * Seite geöffnet, damit ein Update nicht mitten in eine Bearbeitung platzt. */
/* ---- Der Hinweis auf eine neue Fassung --------------------------------
 *
 * Eins zu eins aus der Serverfassung: ein Balken unten rechts, der nicht nur
 * Bescheid sagt, sondern den Knopf gleich mitbringt - eine Meldung, die ein
 * Problem nur beschreibt, nimmt einem die Arbeit nicht ab. "Später" merkt
 * sich genau diese Fassung und fragt dafuer nicht wieder.
 *
 * Nachgesehen wird vier Sekunden nach dem Start (erst soll die Oberflaeche
 * stehen) und dann alle fuenf Minuten. Wer das Fenster offen stehen laesst,
 * erfuehre sonst stundenlang nichts. Bei GitHub landet dabei hoechstens eine
 * Anfrage je Stunde: aktualisieren.py haelt die Antwort so lange. */
const UPDATE_WEG = 'notizmappe.updateweg';

function updateBalken(v) {
  const schon = $('#updatebalken');
  if (schon) schon.remove();
  const melden = (t) => { const z = $('#u-text'); if (z) z.textContent = t; };
  // Laeuft das hier nicht aus einer Installation, laesst sich nichts
  // einspielen - aber da ist trotzdem eine neue Fassung, und das gehoert
  // gesagt. Vorher kam in diesem Fall gar nichts, und es sah aus, als
  // pruefe das Fenster nie nach.
  const geht = !!v.aktualisierbar;
  const text = Object.assign(document.createElement('span'),
    { id: 'u-text',
      textContent: `Fassung ${v.verfuegbar} ist da - hier läuft ${v.installiert}.`
        + (geht ? '' : ' Dieses Fenster läuft nicht aus einer Installation,'
                     + ' deshalb lässt es sich hier nicht einspielen.') });
  const jetzt = Object.assign(document.createElement('button'),
    { type: 'button', id: 'u-jetzt', textContent: 'Jetzt aktualisieren', hidden: !geht });
  const weg = Object.assign(document.createElement('button'),
    { type: 'button', id: 'u-spaeter', title: 'Für diese Fassung nicht mehr fragen',
      textContent: 'Später' });
  const balken = document.createElement('div');
  balken.id = 'updatebalken';
  balken.append(text, jetzt, weg);
  jetzt.addEventListener('click', async () => {
    jetzt.disabled = weg.disabled = true;
    melden(`Fassung ${v.verfuegbar} wird geholt …`);
    try {
      const r = await api('/api/update', 'POST');
      balken.remove();
      updateFensterZeigen('Update wird eingespielt …', `Version ${r.nach} ist unterwegs.`);
      updateVerfolgen(r.nach);
    } catch (f) {
      melden(f.message);
      jetzt.disabled = weg.disabled = false;
    }
  });
  weg.addEventListener('click', () => {
    merker.legen(UPDATE_WEG, v.verfuegbar || '');
    balken.remove();
  });
  document.body.append(balken);
}

// Was beim letzten Nachsehen herauskam. Steht im Reiter Hilfe, damit man
// nachsehen kann, statt zu raten, warum nichts angezeigt wird.
let updateStand = null;

function updateHinweisBauen() {
  let versuche = 0;
  const nachsehen = async () => {
    // Ueber versionPruefen, nicht ueber api(): nur so wird auch der Knopf
    // oben im Band gesetzt. Vorher hingen Balken und Knopf an zwei Wegen,
    // und der Knopf kam nur, wenn "beim Start nachsehen" anstand - war das
    // aus, blieb das Band stumm.
    const v = await versionPruefen();
    updateStand = v;
    hilfeStandZeigen();
    // Vier Sekunden nach dem Start steht die Bruecke manchmal noch nicht.
    // Dann nicht fuenf Minuten warten, sondern gleich noch einmal.
    if (v && v.fehler && versuche < 3) {
      versuche += 1;
      setTimeout(nachsehen, 15000);
      return;
    }
    // Nur auf neuer sehen, nicht auch auf aktualisierbar - genau wie die
    // Serverfassung. Dort steht der Balken da, sobald es etwas Neues gibt;
    // hier kam gar nichts, wenn sich die Fassung nicht einspielen laesst,
    // und es sah aus, als werde nie nachgesehen.
    if (!v || !v.neuer) return;
    if (merker.holen(UPDATE_WEG, '') === v.verfuegbar) return;
    if ($('#updatebalken')) return;
    updateBalken(v);
  };
  setTimeout(nachsehen, 4000);
  setInterval(nachsehen, 5 * 60 * 1000);
}

/* Im Reiter Hilfe steht, was Sache ist. Der Fall, der sonst stumm bleibt:
   eine neuere Fassung ist da, aber dieses Fenster laeuft aus dem
   Quellordner statt aus einer Installation - dann gibt es weder Knopf noch
   Balken, und ohne diesen Satz sieht es aus, als kaeme einfach nie ein
   Update. */
function hilfeStandZeigen() {
  const z = $('#hilfe-version');
  if (!z) return;
  const hier = ($('#version').textContent || '').trim();
  let text = 'Notizmappe ' + hier;
  const v = updateStand;
  if (v) {
    if (v.fehler) text += ' — Update-Prüfung: ' + v.fehler;
    else if (v.neuer && v.aktualisierbar) text += ` — Fassung ${v.verfuegbar} ist da`;
    else if (v.neuer) {
      text += ` — Fassung ${v.verfuegbar} ist da, lässt sich hier aber nicht`
            + ' einspielen: dieses Fenster läuft nicht aus einer Installation.';
    } else if (v.verfuegbar) text += ' — das ist die neueste Fassung';
  }
  z.textContent = text;
}

async function updateBeimStart() {
  let e;
  try { e = await api('/api/einstellungen'); } catch (f) { return; }
  const o = e.optionen || {};
  if (!o.beim_start_pruefen) return;

  const v = await versionPruefen(true);
  if (!v || !v.neuer || !v.aktualisierbar) return;
  if (!o.automatisch_einspielen || !e.hier) return;

  updateFensterZeigen('Update wird geladen …', `Version ${v.verfuegbar} wird geholt.`);
  try {
    const r = await api('/api/update', 'POST');
    updateVerfolgen(r.nach);
  } catch (f) {
    updateFensterFehler('Das Update beim Start ging nicht: ' + f.message);
    $('#u-hinweis').textContent = 'Über das Zahnrad lässt es sich von Hand versuchen.';
  }
}

/* ----------------------------------------------------------- Einstellungen */

/* Die Einstellungen sind kein eigenes Fenster mehr, sondern eine Seite in der
 * Datei-Ebene. tafelZeigen() bleibt trotzdem stehen: es wird von einem Dutzend
 * Stellen gerufen ("Einstellungen öffnen" in Meldungen, aus der Leiste) -
 * die sollen alle weiter funktionieren. Das Zahnrad unten gibt es nicht
 * mehr: dafuer ist oben die Datei-Ebene da, und zwei Wege zur selben Seite
 * sind einer zu viel. */
function tafelZeigen(an, punkt) {
  if (!an) { dateiZeigen(false); return; }
  dateiZeigen(true);
  dateiPunkt(punkt || 'optionen');
}


$('#e-ordner-waehlen').addEventListener('click', async () => {
  try {
    const r = await api('/api/ordner/waehlen', 'POST');
    if (r.ordner) $('#e-ordner-neu').value = r.ordner;
  } catch (f) { melden(f.message); }
});

async function ordnerSetzen(rumpf) {
  if (schmutzig) await speichernJetzt();
  try {
    const r = await api('/api/ordner', 'POST', rumpf);
    sagen(r.kopiert ? `Ordner umgestellt, ${r.kopiert} Einträge kopiert` : 'Ordner umgestellt', 0);
    // Frisch aufbauen, damit keine offene Seite mehr auf den alten Ordner
    // zeigt. (Neu laden geht nicht, siehe nichtsMehrZeigen.)
    merker.legen('zuletzt', 'null');
    setTimeout(wiederAufbauen, 600);
  } catch (f) {
    $('#e-ordner-hinweis').textContent = f.message;
  }
}
$('#e-ordner-setzen').addEventListener('click', () => {
  const ordner = $('#e-ordner-neu').value.trim();
  if (!ordner) { $('#e-ordner-neu').focus(); return; }
  ordnerSetzen({ ordner, mitnehmen: $('#e-mitnehmen').checked });
});
$('#e-ordner-standard').addEventListener('click', () => ordnerSetzen({ standard: true }));

async function einstellungenLaden() {
  try {
    const e = await api('/api/einstellungen');
    $('#e-version').textContent = e.version;
    $('#e-ordner').textContent = e.ordner;
    if (e.ordner_fehlt) $('#e-ordner-hinweis').textContent = e.ordner_fehlt;
    amRechner = !!e.hier;
    const fest = e.ordner_quelle === 'umgebung';
    $('#e-ordnerwahl').hidden = fest || !e.hier;
    $('#e-ordner-waehlen').hidden = !e.ordner_waehlbar;
    $('#e-ordner-standard').hidden = e.ordner_quelle !== 'gewaehlt';
    if (fest) $('#e-ordner-hinweis').textContent = 'Der Ordner ist beim Start über NOTIZEN_ORDNER fest vorgegeben.';
    else if (!e.hier) $('#e-ordner-hinweis').textContent = 'Den Ordner kann man nur direkt an dem Rechner umstellen, auf dem die Notizmappe läuft.';
    $('#e-seiten').textContent = e.seiten;
    $('#e-papierkorb').textContent = e.papierkorb;
    $('#e-frei').textContent = groesse(e.frei);
    $('#e-lage').textContent = e.aus_installation
      ? (e.hier ? 'Installierte Fassung, läuft auf diesem Rechner.'
                : 'Installierte Fassung, von einem anderen Rechner geöffnet - Updates gehen nur direkt dort.')
      : 'Läuft aus dem Quellordner - hier wird mit git aktualisiert, nicht über den Knopf.';
    $('#e-zoom').textContent = Math.round(zoom * 100) + ' %';
    ferneZeigen(e);
    await sperreTafelFuellen();
    if (!schriftstand) await schriftenLaden();
    schriftenTafelFuellen();
    $('#e-start-pruefen').checked = !!(e.optionen && e.optionen.beim_start_pruefen);
    $('#e-auto').checked = !!(e.optionen && e.optionen.automatisch_einspielen);
    for (const kasten of [$('#e-start-pruefen'), $('#e-auto')]) kasten.disabled = !e.hier;
  } catch (f) {
    $('#e-lage').textContent = 'Einstellungen ließen sich nicht laden: ' + f.message;
  }
  updateAnzeigen(await versionPruefen());
}

function updateAnzeigen(v) {
  if (!v) {
    $('#e-updatehinweis').textContent = 'Die Prüfung hat nichts zurückgegeben.';
    return;
  }
  if (v.installiert) $('#e-version').textContent = v.installiert;
  $('#e-verfuegbar').textContent = v.fehler ? '—' : (v.verfuegbar || 'unbekannt');
  $('#e-notizen').hidden = !v.notizen || !v.neuer;
  if (v.notizen) $('#e-notizen').textContent = v.notizen;
  $('#e-einspielen').hidden = !(v.neuer && v.aktualisierbar);
  $('#e-updatehinweis').textContent = v.fehler ? v.fehler
    : v.neuer ? (v.aktualisierbar ? `Version ${v.verfuegbar} steht bereit.`
                                  : 'Neuere Fassung da, aber hier nicht installierbar.')
    : 'Das ist die neueste Fassung.';
}

async function optionSetzen(feld, wert) {
  try {
    await api('/api/einstellungen', 'POST', { [feld]: wert });
  } catch (f) {
    melden('Einstellung ließ sich nicht sichern: ' + f.message);
    einstellungenLaden();
  }
}
$('#e-start-pruefen').addEventListener('change', (ev) => optionSetzen('beim_start_pruefen', ev.target.checked));
$('#e-auto').addEventListener('change', (ev) => optionSetzen('automatisch_einspielen', ev.target.checked));

$('#e-pruefen').addEventListener('click', async () => {
  const knopf = $('#e-pruefen');
  knopf.disabled = true;
  $('#e-updatehinweis').textContent = 'wird geprüft …';
  try {
    updateAnzeigen(await versionPruefen(true));
  } finally {
    knopf.disabled = false;
  }
});

$('#e-einspielen').addEventListener('click', () => $('#update').click());

$('#e-zoom-rein').addEventListener('click', () => { zoomen(0.1); $('#e-zoom').textContent = Math.round(zoom * 100) + ' %'; });
$('#e-zoom-raus').addEventListener('click', () => { zoomen(-0.1); $('#e-zoom').textContent = Math.round(zoom * 100) + ' %'; });
$('#e-zoom-zurueck').addEventListener('click', () => { zoomSetzen(1); $('#e-zoom').textContent = '100 %'; });

/* ----------------------------------------------------------------- Zeichnen
 *
 * Striche liegen als Linien in der Seite, nicht als Bild: beim Zoomen bleiben
 * sie scharf, die Datei bleibt klein, und ein einzelner Strich lässt sich
 * wieder entfernen. Alle Striche einer Seite stehen in **einem** Element vom
 * Typ "stift" - sonst wäre nach ein paar Minuten Malen die Grenze von 500
 * Elementen erreicht.
 *
 * Ein Strich: { f: Farbe, d: Dicke, a: 'stift'|'marker', p: [x, y, Druck, …] }
 * Die Punkte stehen flach hintereinander, das spart in der Datei etwa die
 * Hälfte gegenüber einer Liste von Objekten.
 */

const STIFTE = [
  { name: 'Bleistift',     f: '#1d1d1f', d: 2,  a: 'stift'  },
  { name: 'Kugelschreiber', f: '#1f4fd8', d: 4,  a: 'stift'  },
  { name: 'Rot',           f: '#d13232', d: 4,  a: 'stift'  },
  { name: 'Grün',          f: '#1a8f4a', d: 4,  a: 'stift'  },
  { name: 'Filzstift',     f: '#7c3aed', d: 8,  a: 'stift'  },
  { name: 'Marker gelb',   f: '#ffd84d', d: 22, a: 'marker' },
  { name: 'Marker türkis', f: '#4dd8d8', d: 22, a: 'marker' },
];
const MAX_STRICHE = 4000;
const MAX_PUNKTE = 1400;            // je Strich; danach faengt ein neuer an
/* Und ein Deckel über allem: eine Seite wird bei jedem Autosave ganz neu
 * geschrieben und vom Sync übertragen. Ohne das dürfte sie rechnerisch 96 MB
 * groß werden - echte Handschrift braucht etwa 400 KB für 250 Striche. */
const MAX_ZAHLEN_GESAMT = 400000;

let malblatt = null;                // das <canvas>
let malstift = null;                // sein 2d-Kontext
let zeichnung = null;               // das Element "stift" der offenen Seite
let werkzeug = 'auswahl';
let stiftnummer = 0;
let stifte = STIFTE.map((s) => ({ ...s }));
let laufend = null;                 // der Strich, der gerade gezogen wird
let lasso = null;                   // die Schlinge, waehrend sie gezogen wird
let gewaehlt = [];                  // ausgewaehlte Striche
let zurueckgenommen = [];           // fuer Wiederholen
let zieht = null;

function zeichnungHolen() {
  if (!elemente) return null;
  let e = elemente.find((x) => x && x.typ === 'stift');
  // Noch nicht in die Seite haengen: sonst bekaeme jede Seite, die man nur
  // anschaut, ein leeres Zeichnungs-Element in die Datei geschrieben.
  if (!e) e = { id: 'zeichnung', typ: 'stift', x: 0, y: 0, b: 0, striche: [] };
  if (!Array.isArray(e.striche)) e.striche = [];
  return e;
}

function zeichnungSichern() {
  if (zeichnung && elemente && !elemente.includes(zeichnung)) elemente.push(zeichnung);
}

function malblattBauen() {
  malblatt = document.createElement('canvas');
  malblatt.id = 'malblatt';
  flaeche.append(malblatt);
  malstift = malblatt.getContext('2d');
  for (const art of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel']) {
    malblatt.addEventListener(art, zeiger, { passive: false });
  }
}

/* Das Blatt wird mit der Fläche skaliert. Die Zeichenfläche selbst darf dabei
 * nicht beliebig groß werden: Breite × Höhe × Zoom² × Bildschirmdichte wäre bei
 * einer großen Seite schnell eine halbe Milliarde Punkte. Deshalb ein Deckel -
 * notfalls wird es bei starkem Zoom etwas weicher, statt dass der Speicher
 * vollläuft. */
function malblattMessen() {
  if (!malblatt) return;
  const b = flaeche.clientWidth || parseInt(flaeche.style.width, 10) || 1000;
  const h = flaeche.clientHeight || parseInt(flaeche.style.height, 10) || 1000;
  const dichte = window.devicePixelRatio || 1;
  let s = Math.min(zoom * dichte, 2.5);
  const DECKEL = 24e6;
  if (b * h * s * s > DECKEL) s = Math.sqrt(DECKEL / (b * h));
  malblatt.style.width = b + 'px';
  malblatt.style.height = h + 'px';
  malblatt.width = Math.max(1, Math.round(b * s));
  malblatt.height = Math.max(1, Math.round(h * s));
  malstift.setTransform(s, 0, 0, s, 0, 0);
  allesMalen();
}

function strichMalen(st, hervor) {
  const p = st.p;
  if (!p || p.length < 3) return;
  malstift.save();
  malstift.lineCap = 'round';
  malstift.lineJoin = 'round';
  malstift.strokeStyle = st.f;
  // Der Marker ist durchscheinend, damit Text darunter lesbar bleibt - sonst
  // waere es kein Marker, sondern Farbe.
  malstift.globalAlpha = st.a === 'marker' ? 0.35 : 1;
  if (p.length === 3) {
    malstift.fillStyle = st.f;
    malstift.beginPath();
    malstift.arc(p[0], p[1], Math.max(0.6, st.d / 2), 0, 6.2832);
    malstift.fill();
    malstift.restore();
    if (hervor) rahmenMalen(st);
    return;
  }
  for (let i = 3; i < p.length; i += 3) {
    // Druck des Stifts: dünner, wenn leicht aufgesetzt wird. Eine Maus meldet
    // 0.5, damit sieht ein Mausstrich aus wie ein normaler Strich.
    const druck = p[i + 2] == null ? 0.5 : p[i + 2];
    malstift.lineWidth = st.a === 'marker' ? st.d : Math.max(0.4, st.d * (0.45 + druck));
    malstift.beginPath();
    malstift.moveTo(p[i - 3], p[i - 2]);
    malstift.lineTo(p[i], p[i + 1]);
    malstift.stroke();
  }
  malstift.restore();
  if (hervor) rahmenMalen(st);
}

function rahmenMalen(st) {
  const g = strichGrenzen(st);
  malstift.save();
  malstift.strokeStyle = '#2f6fed';
  malstift.setLineDash([4, 3]);
  malstift.lineWidth = 1;
  malstift.strokeRect(g.x1 - 3, g.y1 - 3, g.x2 - g.x1 + 6, g.y2 - g.y1 + 6);
  malstift.restore();
}

function allesMalen() {
  if (!malstift) return;
  malstift.save();
  malstift.setTransform(1, 0, 0, 1, 0, 0);
  malstift.clearRect(0, 0, malblatt.width, malblatt.height);
  malstift.restore();
  if (!zeichnung) return;
  for (const st of zeichnung.striche) strichMalen(st, gewaehlt.includes(st));
  if (laufend) strichMalen(laufend, false);
  if (lasso && lasso.length > 3) {
    malstift.save();
    malstift.strokeStyle = '#2f6fed';
    malstift.setLineDash([5, 4]);
    malstift.lineWidth = 1;
    malstift.beginPath();
    malstift.moveTo(lasso[0], lasso[1]);
    for (let i = 2; i < lasso.length; i += 2) malstift.lineTo(lasso[i], lasso[i + 1]);
    malstift.closePath();
    malstift.stroke();
    malstift.restore();
  }
}

function strichGrenzen(st) {
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  for (let i = 0; i < st.p.length; i += 3) {
    x1 = Math.min(x1, st.p[i]); x2 = Math.max(x2, st.p[i]);
    y1 = Math.min(y1, st.p[i + 1]); y2 = Math.max(y2, st.p[i + 1]);
  }
  const rand = st.d;
  return { x1: x1 - rand, y1: y1 - rand, x2: x2 + rand, y2: y2 + rand };
}

/* Wie weit reichen die Striche? Die Fläche muss mitwachsen, sonst malt man an
 * den Rand und kann nicht weiter. */
function strichRand() {
  if (!zeichnung || !zeichnung.striche.length) return { b: 0, h: 0 };
  let b = 0, h = 0;
  for (const st of zeichnung.striche) {
    const g = strichGrenzen(st);
    b = Math.max(b, g.x2); h = Math.max(h, g.y2);
  }
  return { b, h };
}

function stelle(ev) {
  const r = flaeche.getBoundingClientRect();
  return { x: (ev.clientX - r.left) / zoom, y: (ev.clientY - r.top) / zoom };
}

function inSchlinge(st, punkte) {
  // Ein Strich gilt als gewählt, wenn irgendein Punkt in der Schlinge liegt -
  // so bekommt man auch lange Striche zu fassen, ohne sie ganz zu umkreisen.
  for (let i = 0; i < st.p.length; i += 3) {
    if (punktDrin(st.p[i], st.p[i + 1], punkte)) return true;
  }
  return false;
}

function punktDrin(x, y, p) {
  let drin = false;
  for (let i = 0, j = p.length - 2; i < p.length; j = i, i += 2) {
    const xi = p[i], yi = p[i + 1], xj = p[j], yj = p[j + 1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) drin = !drin;
  }
  return drin;
}

function wegwischen(x, y) {
  if (!zeichnung) return false;
  const vorher = zeichnung.striche.length;
  zeichnung.striche = zeichnung.striche.filter((st) => {
    const r = Math.max(6, st.d);
    for (let i = 0; i < st.p.length; i += 3) {
      if (Math.abs(st.p[i] - x) < r && Math.abs(st.p[i + 1] - y) < r) {
        zurueckgenommen = [];
        geloescht.push(st);
        return false;
      }
    }
    return true;
  });
  return zeichnung.striche.length !== vorher;
}

let geloescht = [];                 // was der Radierer in einem Zug weggenommen hat

function zeiger(ev) {
  if (!zeichnung) return;
  // Auf dem Tablet liegt der Handballen auf. Mit dem Haken zählt nur der Stift -
  // ohne ihn malt auch der Finger, sonst ginge es auf einem Handy gar nicht.
  if ($('#m-nurstift').checked && ev.pointerType !== 'pen') return;
  const p = stelle(ev);

  if (ev.type === 'pointerdown') {
    malblatt.setPointerCapture(ev.pointerId);
    ev.preventDefault();
    if (werkzeug === 'hand') {
      zieht = { x: ev.clientX, y: ev.clientY, l: buehne.scrollLeft, o: buehne.scrollTop };
      return;
    }
    if (werkzeug === 'radierer') {
      geloescht = [];
      if (wegwischen(p.x, p.y)) { allesMalen(); angefasst(); }
      return;
    }
    if (werkzeug === 'lasso') {
      const treffer = gewaehlt.length && gewaehlt.some((st) => {
        const g = strichGrenzen(st);
        return p.x >= g.x1 && p.x <= g.x2 && p.y >= g.y1 && p.y <= g.y2;
      });
      if (treffer) { zieht = { x: p.x, y: p.y, art: 'striche' }; return; }
      gewaehlt = [];
      lasso = [p.x, p.y];
      allesMalen();
      return;
    }
    const s = stifte[stiftnummer] || stifte[0];
    laufend = { f: s.f, d: s.d, a: s.a, p: [p.x, p.y, ev.pressure || 0.5] };
    return;
  }

  if (ev.type === 'pointermove') {
    if (zieht && zieht.art === 'striche') {
      const dx = p.x - zieht.x, dy = p.y - zieht.y;
      zieht.x = p.x; zieht.y = p.y;
      for (const st of gewaehlt) {
        for (let i = 0; i < st.p.length; i += 3) { st.p[i] += dx; st.p[i + 1] += dy; }
      }
      allesMalen();
      return;
    }
    if (zieht) {
      buehne.scrollLeft = zieht.l - (ev.clientX - zieht.x);
      buehne.scrollTop = zieht.o - (ev.clientY - zieht.y);
      return;
    }
    if (werkzeug === 'radierer' && ev.buttons) {
      if (wegwischen(p.x, p.y)) { allesMalen(); angefasst(); }
      return;
    }
    if (lasso) { lasso.push(p.x, p.y); allesMalen(); return; }
    if (!laufend) return;
    const n = laufend.p.length;
    // Punkte, die kaum auseinanderliegen, bringen nichts und blähen die Datei auf.
    if (Math.abs(laufend.p[n - 3] - p.x) < 0.7 && Math.abs(laufend.p[n - 2] - p.y) < 0.7) return;
    laufend.p.push(p.x, p.y, ev.pressure || 0.5);
    if (laufend.p.length > MAX_PUNKTE * 3) { strichAblegen(); return; }
    allesMalen();
    return;
  }

  // pointerup / pointercancel
  if (zieht) {
    if (zieht.art === 'striche') angefasst();
    zieht = null;
    return;
  }
  if (lasso) {
    const schlinge = lasso;
    lasso = null;
    if (schlinge.length > 7) {
      gewaehlt = zeichnung.striche.filter((st) => inSchlinge(st, schlinge));
      hinweis(gewaehlt.length ? `${gewaehlt.length} Striche gewählt - Entf löscht, Ziehen verschiebt` : '');
    }
    allesMalen();
    return;
  }
  if (werkzeug === 'radierer') { geloescht = []; return; }
  strichAblegen();
}

function zahlenGesamt() {
  let n = 0;
  for (const st of zeichnung.striche) n += st.p.length;
  return n;
}

function strichAblegen() {
  if (!laufend) return;
  const voll = zahlenGesamt() + laufend.p.length > MAX_ZAHLEN_GESAMT;
  if (voll) {
    hinweis('Die Zeichnung auf dieser Seite ist voll - bitte auf einer neuen Seite weitermalen.');
    laufend = null;
    allesMalen();
    return;
  }
  if (laufend.p.length >= 3 && zeichnung.striche.length < MAX_STRICHE) {
    zeichnungSichern();
    // Runden spart in der Datei viel: zwei Nachkommastellen sind feiner, als
    // ein Bildschirm darstellen kann.
    laufend.p = laufend.p.map((w, i) => (i % 3 === 2 ? Math.round(w * 100) / 100
                                                     : Math.round(w * 10) / 10));
    zeichnung.striche.push(laufend);
    zurueckgenommen = [];
    angefasst();
  } else if (zeichnung.striche.length >= MAX_STRICHE) {
    hinweis(`Mehr als ${MAX_STRICHE} Striche auf einer Seite gehen nicht.`);
  }
  laufend = null;
  allesMalen();
  flaecheMessen();
}

function hinweis(text) {
  $('#m-hinweis').textContent = text;
  if (text) setTimeout(() => { if ($('#m-hinweis').textContent === text) $('#m-hinweis').textContent = ''; }, 5000);
}

/* --- Werkzeuge --- */

function stiftknoepfeBauen() {
  const wo = $('#m-stifte');
  wo.textContent = '';
  stifte.forEach((s, i) => {
    const k = document.createElement('button');
    k.type = 'button';
    k.className = 'malwerkzeug stift';
    k.dataset.werkzeug = 'stift';
    k.dataset.nummer = String(i);
    k.title = `${s.name} (${s.d} px)`;
    k.textContent = s.a === 'marker' ? '▬' : '✎';
    k.style.setProperty('--stiftfarbe', s.f);
    wo.append(k);
  });
}

function werkzeugSetzen(name, nummer) {
  werkzeug = name;
  if (name === 'stift' && nummer != null) stiftnummer = nummer;
  if (name !== 'lasso') { gewaehlt = []; }
  for (const k of document.querySelectorAll('#malzeug .malwerkzeug')) {
    const dran = k.dataset.werkzeug === name
      && (name !== 'stift' || Number(k.dataset.nummer) === stiftnummer);
    k.classList.toggle('an', dran);
  }
  if (malblatt) {
    malblatt.classList.toggle('malt', name === 'stift' || name === 'lasso');
    malblatt.classList.toggle('wischt', name === 'radierer');
    malblatt.classList.toggle('zieht', name === 'hand');
  }
  if (name === 'stift') {
    const s = stifte[stiftnummer];
    $('#m-farbe').value = s.f;
    $('#m-dicke').value = String(s.d);
  }
  allesMalen();
}

const BANDLEISTEN = {
  start: 'werkzeuge', einfuegen: 'einfuegen', zeichnen: 'malzeug',
  verlauf: 'verlaufzeug', ansicht: 'ansicht', hilfe: 'hilfe',
};

function reiterSetzen(name) {
  // "Datei" ist kein Reiter mit Leiste, sondern eine Ebene darüber.
  if (name === 'datei') { dateiZeigen(true); return; }
  for (const k of document.querySelectorAll('#reiter .reiter')) {
    k.setAttribute('aria-selected', String(k.dataset.reiter === name));
  }
  for (const [reiter, leiste] of Object.entries(BANDLEISTEN)) {
    $('#' + leiste).hidden = reiter !== name;
  }
  merker.legen('reiter', name);
  if (name === 'hilfe') hilfeStandZeigen();
  // Beim Verlassen des Reiters nicht weitermalen: sonst fängt der nächste Klick
  // in den Text einen Strich an.
  werkzeugSetzen(name === 'zeichnen' ? (werkzeug === 'auswahl' ? 'stift' : werkzeug) : 'auswahl',
                 stiftnummer);
}

$('#leiste-schalten').addEventListener('click', () => {
  $('#leiste').classList.toggle('versteckt');
  flaecheMessen();
});
$('#hilfe-pruefen').addEventListener('click', () => zuDenEinstellungen('e-pruefen'));
$('#hilfe-diagnose').addEventListener('click', () => { reiterSetzen('start'); dateiZeigen(true); dateiPunkt('info'); });
$('#neue-seite-band').addEventListener('click', async () => {
  // Dort anlegen, wo man gerade ist - sonst in dem ersten Abschnitt, den es gibt.
  const erste = erstesSeitchen();
  const buch = offen ? offen.notizbuch : (erste && erste[0]);
  const ab = offen ? offen.abschnitt : (erste && erste[1]);
  if (!buch || !ab) { melden('Erst ein Notizbuch und einen Abschnitt anlegen.'); return; }
  try {
    const r = await api('/api/seite', 'POST', { notizbuch: buch, abschnitt: ab, titel: 'Neue Seite' });
    await baumLaden();
    await seiteOeffnen(buch, ab, r.name);
    $('#titel').select();
  } catch (f) { melden(f.message); }
});
$('#neuer-abschnitt-band').addEventListener('click', async () => {
  const buch = offen ? offen.notizbuch : (baumDaten[0] && baumDaten[0].name);
  if (!buch) { melden('Erst ein Notizbuch anlegen.'); return; }
  const n = prompt('Name des Abschnitts:');
  if (!n) return;
  try {
    await api('/api/abschnitt', 'POST', { notizbuch: buch, name: n });
    await baumLaden();
  } catch (f) { melden(f.message); }
});

$('#reiter').addEventListener('click', (ev) => {
  const k = ev.target.closest('.reiter');
  if (k) reiterSetzen(k.dataset.reiter);
});

$('#malzeug').addEventListener('click', (ev) => {
  const k = ev.target.closest('.malwerkzeug');
  if (!k) return;
  werkzeugSetzen(k.dataset.werkzeug, k.dataset.nummer == null ? null : Number(k.dataset.nummer));
});

$('#m-farbe').addEventListener('input', (ev) => {
  if (werkzeug !== 'stift') werkzeugSetzen('stift', stiftnummer);
  stifte[stiftnummer].f = ev.target.value;
  stiftknoepfeBauen();
  werkzeugSetzen('stift', stiftnummer);
  stifteMerken();
});

$('#m-dicke').addEventListener('change', (ev) => {
  if (werkzeug !== 'stift') werkzeugSetzen('stift', stiftnummer);
  stifte[stiftnummer].d = Number(ev.target.value) || 4;
  stiftknoepfeBauen();
  werkzeugSetzen('stift', stiftnummer);
  stifteMerken();
});

$('#m-nurstift').addEventListener('change', (ev) => merker.legen('nurstift', ev.target.checked ? '1' : ''));

function stifteMerken() {
  try { merker.legen('stifte', JSON.stringify(stifte)); } catch (f) { /* dann eben nicht */ }
}

function stifteHolen() {
  try {
    const roh = JSON.parse(merker.holen('stifte', 'null'));
    if (Array.isArray(roh) && roh.length === STIFTE.length) {
      stifte = roh.map((s, i) => ({
        name: STIFTE[i].name,
        f: /^#[0-9a-fA-F]{6}$/.test(s.f) ? s.f : STIFTE[i].f,
        d: Math.min(60, Math.max(1, Number(s.d) || STIFTE[i].d)),
        a: s.a === 'marker' ? 'marker' : 'stift',
      }));
    }
  } catch (f) { /* dann die eingebauten */ }
}

/* --- Rückgängig --- */

function strichZurueck() {
  if (!zeichnung || !zeichnung.striche.length) return;
  zurueckgenommen.push(zeichnung.striche.pop());
  gewaehlt = [];
  angefasst();
  allesMalen();
}

function strichVor() {
  if (!zurueckgenommen.length) return;
  zeichnungSichern();
  zeichnung.striche.push(zurueckgenommen.pop());
  angefasst();
  allesMalen();
  flaecheMessen();
}

$('#m-zurueck').addEventListener('click', strichZurueck);
$('#m-vor').addEventListener('click', strichVor);

document.addEventListener('keydown', (ev) => {
  if ($('#malzeug').hidden) return;
  if (ev.target.closest('.text, input, select, textarea')) return;
  if ((ev.key === 'Delete' || ev.key === 'Backspace') && gewaehlt.length) {
    ev.preventDefault();
    zeichnung.striche = zeichnung.striche.filter((st) => !gewaehlt.includes(st));
    gewaehlt = [];
    angefasst();
    allesMalen();
    return;
  }
  if (ev.key === 'Escape') { gewaehlt = []; werkzeugSetzen('auswahl'); allesMalen(); return; }
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') { ev.preventDefault(); strichZurueck(); }
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'y') { ev.preventDefault(); strichVor(); }
});

/* Beim Öffnen einer Seite: Blatt neu aufspannen und die Striche hinmalen. */
function zeichnungLaden() {
  zeichnung = zeichnungHolen();
  gewaehlt = [];
  zurueckgenommen = [];
  laufend = null;
  lasso = null;
  malblattBauen();
  malblattMessen();
  // Das Blatt ist neu - ohne das hier hat es die Klasse nicht, die Zeiger
  // durchlaesst oder faengt. Nach einem Seitenwechsel haette man im Reiter
  // Zeichnen gemalt und es waere nichts passiert.
  werkzeugSetzen(werkzeug, stiftnummer);
}

/* ----------------------------------------------------------------- Verlauf
 *
 * Frühere Fassungen und Gelöschtes. Beides liegt als Datei im Datenordner und
 * wandert mit dem Sync mit - deshalb braucht es dafür keine Datenbank und kein
 * Aufräumen im Hintergrund.
 */

function wann(sekunden) {
  const d = new Date(sekunden * 1000);
  const heute = new Date();
  const gleich = d.toDateString() === heute.toDateString();
  const uhr = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  if (gleich) return 'heute ' + uhr;
  const gestern = new Date(heute.getTime() - 86400000);
  if (d.toDateString() === gestern.toDateString()) return 'gestern ' + uhr;
  return d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: 'numeric' }) + ' ' + uhr;
}

function verlaufFenster(titel, erklaerung, zeilen, knoepfe) {
  $('#v-titel').textContent = titel;
  $('#v-erklaerung').textContent = erklaerung;
  const liste = $('#v-liste');
  liste.textContent = '';
  if (!zeilen.length) {
    const leer = document.createElement('p');
    leer.className = 'verlaufleer';
    leer.textContent = 'Hier liegt nichts.';
    liste.append(leer);
  }
  for (const z of zeilen) {
    const zeile = document.createElement('div');
    zeile.className = 'verlaufzeile';
    const wo = document.createElement('span');
    wo.className = 'wann';
    wo.textContent = z.wann;
    const was = document.createElement('span');
    was.className = 'was';
    was.textContent = z.was;
    if (z.ungenau) {
      const hin = document.createElement('span');
      hin.className = 'ungenau';
      hin.textContent = ' (Ort geraten)';
      was.append(hin);
    }
    zeile.append(wo, was);
    for (const [beschriftung, tun] of (z.knoepfe || [])) {
      const k = document.createElement('button');
      k.type = 'button';
      k.textContent = beschriftung;
      k.addEventListener('click', tun);
      zeile.append(k);
    }
    liste.append(zeile);
  }
  const unten = $('#v-knoepfe');
  unten.textContent = '';
  for (const [beschriftung, tun] of (knoepfe || [])) {
    const k = document.createElement('button');
    k.type = 'button';
    k.textContent = beschriftung;
    k.addEventListener('click', tun);
    unten.append(k);
  }
  $('#verlauffenster').hidden = false;
}

function verlaufZu() { $('#verlauffenster').hidden = true; }
$('#v-zu').addEventListener('click', verlaufZu);
$('#verlauffenster').addEventListener('click', (ev) => { if (ev.target === $('#verlauffenster')) verlaufZu(); });
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && !$('#verlauffenster').hidden) verlaufZu();
});

async function versionenZeigen() {
  if (!offen) { $('#v-hinweis').textContent = 'Erst eine Seite öffnen.'; return; }
  if (schmutzig) await speichernJetzt();
  const seite = { ...offen };
  let r;
  try {
    r = await api(`/api/verlauf?notizbuch=${encodeURIComponent(seite.notizbuch)}`
      + `&abschnitt=${encodeURIComponent(seite.abschnitt)}&name=${encodeURIComponent(seite.name)}`);
  } catch (f) { $('#v-hinweis').textContent = f.message; return; }

  const zeilen = (r.versionen || []).map((v) => ({
    wann: wann(v.zeit),
    was: Math.round(v.groesse / 1024 * 10) / 10 + ' KB',
    knoepfe: [
      ['Ansehen', async () => {
        try {
          const alt = await api(`/api/verlauf/fassung?notizbuch=${encodeURIComponent(seite.notizbuch)}`
            + `&abschnitt=${encodeURIComponent(seite.abschnitt)}&name=${encodeURIComponent(seite.name)}`
            + `&marke=${encodeURIComponent(v.marke)}`);
          const text = (alt.elemente || [])
            .map((e) => (e.typ === 'text' ? (e.html || '').replace(/<[^>]*>/g, ' ') : `[${e.typ}]`))
            .join('\n').replace(/\s+/g, ' ').trim();
          melden(`${wann(v.zeit)}: ${text.slice(0, 300) || '(ohne Text)'}`,
                 [['Diese Fassung zurückholen', () => zurueckholen(seite, v.marke)]]);
          verlaufZu();
        } catch (f) { $('#v-hinweis').textContent = f.message; }
      }],
      ['Zurückholen', () => zurueckholen(seite, v.marke)],
    ],
  }));
  verlaufFenster('Seitenversionen',
    'Beim Zurückholen wird der jetzige Stand vorher als Fassung abgelegt - '
    + 'du kannst es also gefahrlos ausprobieren. Eine Fassung entsteht höchstens '
    + 'alle zehn Minuten, dazu immer vor einem Konflikt.',
    zeilen, []);
}

async function zurueckholen(seite, marke) {
  try {
    await api('/api/verlauf/zurueck', 'POST', { ...seite, marke });
    verlaufZu();
    meldungWeg();
    await seiteOeffnen(seite.notizbuch, seite.abschnitt, seite.name);
    sagen('Fassung zurückgeholt');
  } catch (f) {
    $('#v-hinweis').textContent = f.message;
    melden('Zurückholen ging nicht: ' + f.message);
  }
}

const KORBART = { seite: 'Seite', ordner: 'Notizbuch oder Abschnitt',
                  anhaenge: 'Anhänge', verlauf: 'frühere Fassungen' };

async function papierkorbZeigen() {
  let r;
  try { r = await api('/api/papierkorb'); } catch (f) { $('#v-hinweis').textContent = f.message; return; }
  const eintraege = r.eintraege || [];
  const zeilen = eintraege.map((e) => ({
    wann: wann(e.zeit),
    was: `${e.titel}  ·  ${KORBART[e.art] || e.art}`,
    ungenau: !e.genau,
    knoepfe: [
      ['Zurückholen', async () => {
        try {
          const z = await api('/api/papierkorb/zurueck', 'POST', { eintrag: e.eintrag });
          await baumLaden();
          sagen('Zurückgeholt: ' + z.zurueck, 4000);
          papierkorbZeigen();
        } catch (f) { $('#v-hinweis').textContent = f.message; }
      }],
      ['Endgültig löschen', async () => {
        // Das ist der eine Knopf hier, der wirklich etwas vernichtet.
        if (!confirm(`„${e.titel}" endgültig löschen? Das lässt sich nicht rückgängig machen.`)) return;
        try {
          await api('/api/papierkorb/weg', 'POST', { eintrag: e.eintrag });
          papierkorbZeigen();
        } catch (f) { $('#v-hinweis').textContent = f.message; }
      }],
    ],
  }));
  verlaufFenster('Papierkorb',
    'Gelöschtes bleibt hier liegen, bis du es wegwirfst - von allein wird nichts '
    + 'geleert. „Ort geraten" heißt: der Eintrag stammt aus einer älteren Fassung '
    + 'ohne Herkunftsvermerk, der Platz wird aus dem Namen abgeleitet.',
    zeilen,
    eintraege.length ? [['Papierkorb leeren', async () => {
      if (!confirm(`Alle ${eintraege.length} Einträge endgültig löschen?`)) return;
      try {
        const w = await api('/api/papierkorb/leeren', 'POST', {});
        sagen(`${w.weg} Einträge gelöscht`);
        papierkorbZeigen();
      } catch (f) { $('#v-hinweis').textContent = f.message; }
    }]] : []);
}

function letzteZeigen() {
  const alle = [];
  for (const buch of baumDaten) {
    for (const ab of buch.abschnitte) {
      for (const s of ab.seiten) {
        alle.push({ buch: buch.name, abschnitt: ab.name, seite: s, zeit: s.geaendert || 0 });
      }
    }
  }
  alle.sort((a, b) => b.zeit - a.zeit);
  const zeilen = alle.slice(0, 40).map((e) => ({
    wann: e.zeit ? wann(e.zeit) : '—',
    was: `${e.seite.titel}  ·  ${e.buch} / ${e.abschnitt}`,
    knoepfe: [['Öffnen', async () => {
      verlaufZu();
      await seiteOeffnen(e.buch, e.abschnitt, e.seite.name);
    }]],
  }));
  verlaufFenster('Letzte Änderungen',
    'Die zuletzt angefassten Seiten, neueste zuerst.', zeilen, []);
}

$('#v-versionen').addEventListener('click', versionenZeigen);
$('#v-papierkorb').addEventListener('click', papierkorbZeigen);
$('#v-letzte').addEventListener('click', letzteZeigen);

/* ------------------------------------------------------------------ Sperre */

let sperreStand = { eingerichtet: false, offen: true, minuten: 0 };
let laeuftZu = false;            /* zusperren laeuft - keine zweite Runde */
let aufgeschlossen = null;       /* loest den Anlauf aus, sobald es offen ist */

async function sperreHolen() {
  try { sperreStand = await api('/api/sperre'); } catch (f) { /* dann wie offen */ }
  $('#sperren').hidden = !sperreStand.eingerichtet;
  return sperreStand;
}

/* Steht die Sperre, kommt hier nichts durch, bis das Passwort stimmt: erst
 * danach wird überhaupt ein Baum geladen. Der Schirm ist deckend - hinter ihm
 * steht nichts, was man lesen könnte. */
async function sperreAufmachen() {
  const s = await sperreHolen();
  if (!s.eingerichtet || s.offen) return true;
  $('#sperrschirm').hidden = false;
  setTimeout(() => $('#s-pw').focus(), 60);
  return new Promise((fertig) => { aufgeschlossen = fertig; });
}

/* Zugesperrt: nichts Lesbares darf stehen bleiben.
 *
 * Hier stand frueher location.reload() mit der Begruendung "so bleibt
 * garantiert nichts stehen". Das Fenster bekommt seine Seite aber als Inhalt
 * hineingereicht (pywebview, html=...) - sie hat gar keine Adresse, und ein
 * Neuladen endet auf einer leeren Seite. Schwarz ist zwar auch "nichts
 * Lesbares", aber niemand kommt von dort wieder zurueck. Also von Hand
 * wegraeumen und den Sperrschirm zeigen. */
function nichtsMehrZeigen() {
  offen = null;
  schmutzig = false;
  flaecheLeeren();
  baumDaten = [];
  baumZeichnen();
  dateiZeigen(false);
  meldungWeg();
}

function zusperrenZeigen() {
  nichtsMehrZeigen();
  sperreAufmachen().then(function (auf) {
    if (auf) { laeuftZu = false; wiederAufbauen(); }
  });
}

/* Nach dem Aufschliessen wieder hochfahren - ohne Neuladen. */
async function wiederAufbauen() {
  try {
    await baumLaden();
    ordnerZeigen(await api('/api/einstellungen'));
  } catch (f) { melden(f.message); return; }
  let z = null;
  try { z = JSON.parse(merker.holen('zuletzt', 'null')); } catch (f) { /* dann die erste */ }
  const erste = erstesSeitchen();
  const wohin = z || (erste ? { buch: erste[0], abschnitt: erste[1], name: erste[2] } : null);
  if (wohin) {
    try { await seiteOeffnen(wohin.buch, wohin.abschnitt, wohin.name); } catch (f) { /* dann leer */ }
  }
}

function sperreOffenMelden() {
  $('#sperrschirm').hidden = true;
  $('#s-pw').value = '';
  $('#s-neu').value = '';
  $('#s-rettung').value = '';
  if (aufgeschlossen) {
    const weiter = aufgeschlossen;
    aufgeschlossen = null;
    weiter(true);                /* der Anlauf läuft dort weiter, wo er wartet */
  } else {
    /* Mitten im Betrieb aufgeschlossen: wieder aufbauen, nicht neu laden. */
    laeuftZu = false;
    wiederAufbauen();
  }
}

function sperrfehler(text) {
  const z = $('#s-fehler');
  z.textContent = text;
  z.hidden = !text;
}

$('#s-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const geheim = $('#s-pw').value;
  if (!geheim) { $('#s-pw').focus(); return; }
  $('#s-auf').disabled = true;
  sperrfehler('');
  try {
    await api('/api/sperre/auf', 'POST', { geheim });
    sperreOffenMelden();
  } catch (f) {
    sperrfehler(f.message);
    $('#s-pw').select();
  } finally {
    $('#s-auf').disabled = false;
  }
});

$('#s-zuruecksetzen').addEventListener('click', async () => {
  const rettung = $('#s-rettung').value.trim();
  const neu = $('#s-neu').value;
  if (!rettung || !neu) { sperrfehler('Wiederherstellungsschlüssel und neues Passwort eingeben'); return; }
  sperrfehler('');
  try {
    await api('/api/sperre/zuruecksetzen', 'POST', { rettung, neu });
    sperreOffenMelden();
  } catch (f) {
    sperrfehler(f.message);
  }
});

async function zusperrenJetzt() {
  if (laeuftZu) return;
  laeuftZu = true;
  try { if (schmutzig) await speichernJetzt(); } catch (f) { /* trotzdem zu */ }
  try { await api('/api/sperre/zu', 'POST'); } catch (f) { /* auch dann zu */ }
  zusperrenZeigen();
}

$('#sperren').addEventListener('click', zusperrenJetzt);

/* Zeitsperre. Die Brücke zählt selbst mit, aber nur, wenn ein Aufruf kommt -
 * und wer nichts tut, ruft nichts auf. Deshalb sieht das Fenster zusätzlich
 * selbst nach. */
let letzteTat = Date.now();
for (const art of ['mousedown', 'keydown', 'wheel', 'touchstart']) {
  document.addEventListener(art, () => { letzteTat = Date.now(); }, { passive: true, capture: true });
}
setInterval(() => {
  if (!sperreStand.eingerichtet || !sperreStand.minuten || laeuftZu) return;
  if (!$('#sperrschirm').hidden) return;
  if (Date.now() - letzteTat > sperreStand.minuten * 60000) zusperrenJetzt();
}, 15000);

/* --- Wiederherstellungsschlüssel zeigen --- */

let rettungText = '';

async function rettungZeigen(schluessel) {
  rettungText = schluessel;
  $('#r-schluessel').textContent = schluessel;
  $('#r-hinweis').textContent = '';
  $('#rettungfenster').hidden = false;
  // Vorschlag: Dokumente im eigenen Ordner. Überschreibbar - deshalb ein Feld
  // und nicht nur der Dialog des Systems.
  if (!$('#r-pfad').value) {
    try {
      const z = await api('/api/sperre/rettung/ziel');
      $('#r-pfad').value = z.pfad || '';
    } catch (f) { /* dann tippt man ihn eben selbst */ }
  }
}

$('#r-durchsuchen').addEventListener('click', async () => {
  try {
    const r = await api('/api/sperre/rettung/datei', 'POST', { rettung: rettungText });
    if (r.abgebrochen) return;
    $('#r-pfad').value = r.ziel || '';
    $('#r-hinweis').textContent = (r.warnung ? r.warnung + ' ' : '') + 'Gespeichert: ' + r.ziel;
  } catch (f) {
    $('#r-hinweis').textContent = f.message;
  }
});

$('#r-fertig').addEventListener('click', () => { $('#rettungfenster').hidden = true; });

$('#r-kopieren').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(rettungText);
    $('#r-hinweis').textContent = 'Kopiert.';
  } catch (f) {
    // In manchen Webansichten gibt es die Zwischenablage nicht: dann wenigstens
    // markieren, damit Strg+C geht.
    const feld = $('#r-schluessel');
    const bereich = document.createRange();
    bereich.selectNodeContents(feld);
    const aus = window.getSelection();
    aus.removeAllRanges();
    aus.addRange(bereich);
    $('#r-hinweis').textContent = 'Markiert - mit Strg+C kopieren.';
  }
});

$('#r-datei').addEventListener('click', async () => {
  const pfad = $('#r-pfad').value.trim();
  try {
    const r = await api('/api/sperre/rettung/datei', 'POST', { rettung: rettungText, pfad });
    if (r.abgebrochen) return;
    if (r.ziel) $('#r-pfad').value = r.ziel;
    $('#r-hinweis').textContent = (r.warnung ? r.warnung + ' ' : '') + 'Gespeichert: ' + r.ziel;
  } catch (f) {
    $('#r-hinweis').textContent = f.message;
  }
});

/* --- In den Einstellungen --- */

$('#e-onenote').addEventListener('click', async () => {
  const knopf = $('#e-onenote');
  const stand = $('#e-onenote-stand');
  knopf.disabled = true;
  stand.textContent = 'Datei wählen …';
  try {
    const r = await api('/api/onenote', 'POST', {});
    if (r.abgebrochen) { stand.textContent = ''; return; }
    stand.textContent = `Angelegt: „${r.notizbuch}" mit ${r.abschnitte} Abschnitten, `
      + `${r.seiten} Seiten und ${r.anhaenge} Dateien.`
      + (r.uebersprungen && r.uebersprungen.length
         ? ' Nicht lesbar: ' + r.uebersprungen.join('; ') : '');
    await baumLaden();
  } catch (f) {
    stand.textContent = f.message;
  } finally {
    knopf.disabled = false;
  }
});

/* --------------------------------------------------------------- Datei
 *
 * Die Ebene über den Notizen: was man sonst in einem Menü "Datei" sucht -
 * wo liegt das hier, was ist neu, drucken, exportieren, Server, Optionen.
 */

function dateiZeigen(an) {
  $('#dateischirm').hidden = !an;
  if (an) {
    dateiPunkt(document.querySelector('#dateileiste .dateipunkt[aria-selected="true"]')
      ? document.querySelector('#dateileiste .dateipunkt[aria-selected="true"]').dataset.punkt
      : 'info');
  } else {
    // Zurück auf den Reiter, auf dem man vorher war.
    reiterSetzen(merker.holen('reiter', 'start') === 'datei' ? 'start'
      : merker.holen('reiter', 'start'));
  }
}

function dateiPunkt(punkt) {
  for (const k of document.querySelectorAll('#dateileiste .dateipunkt')) {
    k.setAttribute('aria-selected', String(k.dataset.punkt === punkt));
  }
  for (const s of document.querySelectorAll('.dateiseite')) {
    s.hidden = s.dataset.punkt !== punkt;
  }
  if (punkt === 'info') dateiInfoFuellen();
  if (punkt === 'server') dateiServerFuellen();
  // "Installiert", die Update-Knoepfe und die beiden Haken stehen in
  // #einstellungen-oben, und das liegt auf der Informationen-Seite. Gefuellt
  // werden sie aber von einstellungenLaden() - wer die Datei-Ebene ueber das
  // Band oeffnet statt ueber das Zahnrad, sah dort nur Punkte.
  if (punkt === 'info' || punkt === 'optionen') einstellungenLaden();
}

$('#dateileiste').addEventListener('click', (ev) => {
  const k = ev.target.closest('.dateipunkt');
  if (k) dateiPunkt(k.dataset.punkt);
});
$('#datei-zurueck').addEventListener('click', () => dateiZeigen(false));
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && !$('#dateischirm').hidden) dateiZeigen(false);
});

async function dateiInfoFuellen() {
  $('#d-seite').textContent = offen ? `${offen.notizbuch} / ${offen.abschnitt} / ${$('#titel').value}`
                                    : 'keine offen';
  try {
    const e = await api('/api/einstellungen');
    $('#d-ordner').textContent = e.ordner;
    $('#d-seiten').textContent = e.seiten;
    $('#d-papierkorb').textContent = e.papierkorb;
    $('#d-frei').textContent = groesse(e.frei);
    $('#d-version').textContent = e.version;
    $('#d-info-hinweis').textContent = e.ferne && e.ferne.aktiv
      ? 'Dieses Fenster arbeitet gerade auf einem Server.'
      : 'Die Notizen liegen als Ordner und Dateien auf dieser Platte.';
  } catch (f) { $('#d-info-hinweis').textContent = f.message; }
  try {
    const sp = await api('/api/sperre');
    $('#d-sperre').textContent = !sp.eingerichtet ? 'aus'
      : (sp.offen ? 'eingeschaltet, offen' : 'eingeschaltet, zugesperrt');
  } catch (f) { $('#d-sperre').textContent = '—'; }
}

/* Eine eigene Seite, weil es eine eigene Sache ist. Vorher hiess sie "Konto"
 * und zeigte nur den Zustand mit einem Knopf, der in die Optionen sprang, wo
 * das Formular lag: zwei Orte für eine Sache, und auf dem einen konnte man
 * nichts tun. "Konto" war dazu geraten - man hat hier keins, man verbindet
 * sich mit einem Server. */
async function dateiServerFuellen() {
  try {
    const e = await api('/api/einstellungen');
    ferneZeigen(e);
    $('#d-server-sonst').hidden = !!e.hier;
  } catch (f) {
    $('#e-ferne-hinweis').textContent = f.message;
  }
}

function zuDenEinstellungen(punkt) {
  // Updates stehen unter "Informationen", alles andere unter "Optionen".
  tafelZeigen(true, punkt === 'e-pruefen' ? 'info' : 'optionen');
  if (punkt) setTimeout(() => {
    const ziel = $('#' + punkt);
    if (ziel) ziel.scrollIntoView({ block: 'center' });
  }, 80);
}

/* Die Rolle steht im Profil am Server; gemerkt, damit das Menue sie zeigen
 * kann, ohne bei jedem Aufklappen zu fragen. */
let profilRolle = '';

$('#profilknopf').addEventListener('click', (ev) => {
  ev.stopPropagation();
  $('#profilmenue').hidden = !$('#profilmenue').hidden;
});
document.addEventListener('click', (ev) => {
  const m = $('#profilmenue');
  if (!m.hidden && !m.contains(ev.target)) m.hidden = true;
});
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape') $('#profilmenue').hidden = true;
});
$('#profil-oeffnen').addEventListener('click', () => {
  $('#profilmenue').hidden = true;
  profilBearbeitenBauen();
  profilOeffnen();
});
/* Laeuft die Oberflaeche in der Serverfassung? Die Bruecke sagt es mit
 * "hier": am eigenen Rechner true, im Browser false. Nicht an
 * window.pywebview.platform ablesen - die Oberflaeche redet mit dem Programm
 * ueber genau eine Schnittstelle, und das soll so bleiben. */
let hierAmRechner = true;

function amServer() {
  return hierAmRechner === false;
}

$('#profil-abmelden').addEventListener('click', async () => {
  $('#profilmenue').hidden = true;
  if (amServer()) { location.href = '/abmelden'; return; }
  try {
    await api('/api/ferne/abmelden', 'POST', {});
    merker.legen('zuletzt', 'null');
    sagen('Vom Server abgemeldet.', 0);
    await wiederAufbauen();
  } catch (f) { melden(f.message); }
});

// Beide Wege führen auf die Serverseite, nicht mehr in die Optionen.
$('#d-server').addEventListener('click', () => dateiPunkt('server'));
$('#d-ordner-waehlen').addEventListener('click', () => zuDenEinstellungen('e-ordnerwahl'));
$('#d-onenote').addEventListener('click', () => zuDenEinstellungen('e-onenote'));
$('#d-neu-buch').addEventListener('click', () => { dateiZeigen(false); notizbuchAnlegen(baumSeite); });
$('#d-neu-abschnitt').addEventListener('click', () => { dateiZeigen(false); $('#neuer-abschnitt-band').click(); });
$('#d-neu-seite').addEventListener('click', () => { dateiZeigen(false); $('#neue-seite-band').click(); });
$('#d-drucken').addEventListener('click', () => { dateiZeigen(false); setTimeout(() => window.print(), 150); });

/* Export: die Seite als eine Datei, die ohne dieses Programm aufgeht. Bilder
 * kommen als data:-Adresse mit hinein - sonst wäre es eine Datei mit Löchern. */
async function seiteAlsHtml() {
  if (!offen) throw new Error('Keine Seite offen');
  const stuecke = [];
  for (const e of elemente) {
    if (e.typ === 'text') {
      stuecke.push(`<div class="kasten">${e.html || ''}</div>`);
    } else if (e.typ === 'bild') {
      try {
        const b = await bruecke();
        const r = await b.anhang_bild(offen.notizbuch, offen.abschnitt, offen.name, e.datei);
        if (r && r.daten) {
          stuecke.push(`<div class="kasten"><img src="data:${r.medientyp};base64,${r.daten}"></div>`);
        }
      } catch (f) { stuecke.push(`<div class="kasten">[Bild fehlt: ${e.datei}]</div>`); }
    } else if (e.typ === 'datei') {
      stuecke.push(`<div class="kasten">[Datei: ${e.datei}]</div>`);
    } else if (e.typ === 'stift') {
      stuecke.push(`<div class="kasten">[Zeichnung mit ${(e.striche || []).length} Strichen - `
        + `beim Export noch nicht dabei]</div>`);
    }
  }
  const titel = ($('#titel').value || offen.name).replace(/[<>&]/g, '');
  return `<!doctype html>\n<html lang="de"><head><meta charset="utf-8">\n`
    + `<title>${titel}</title>\n<style>\n`
    + `body { font: 15px/1.6 system-ui, sans-serif; max-width: 48rem; margin: 2rem auto; padding: 0 1rem; }\n`
    + `h1 { font-size: 1.6rem; } .kasten { margin: 0 0 1.2rem; } img { max-width: 100%; }\n`
    + `</style></head><body>\n<h1>${titel}</h1>\n${stuecke.join('\n')}\n`
    + `<hr><p style="color:#888;font-size:.8rem">Aus der Notizmappe, `
    + `${new Date().toLocaleDateString()}</p>\n</body></html>\n`;
}

$('#d-export-html').addEventListener('click', async () => {
  $('#d-export-hinweis').textContent = 'wird gebaut …';
  try {
    const html = await seiteAlsHtml();
    const name = (($('#titel').value || 'Seite') + '.html').replace(/[\\/:*?"<>|]/g, '-');
    const r = await api('/api/datei/speichern', 'POST', { name, text: html });
    $('#d-export-hinweis').textContent = r.abgebrochen ? '' : 'Gespeichert: ' + r.ziel;
  } catch (f) {
    $('#d-export-hinweis').textContent = f.message;
  }
});

/* ------------------------------------------------- Verbindung zum Server */

function ferneZeigen(e) {
  // Nur am eigenen Rechner: in der Serverfassung wäre der Abschnitt sinnlos.
  $('#e-ferne-abschnitt').hidden = !e.hier;
  const f = e.ferne || {};
  $('#e-ferne-stand').textContent = f.aktiv
    ? `verbunden mit ${f.adresse} als ${f.benutzer}`
    : (f.angemeldet ? `angemeldet an ${f.adresse}, arbeitet gerade örtlich`
                    : 'nicht verbunden');
  $('#e-ferne-anmeldung').hidden = !!f.angemeldet || !!f.braucht_code;
  // Zwei Schritte: Passwort hat gestimmt, jetzt fehlt der Code aus der App.
  $('#e-ferne-zweischritt').hidden = !f.braucht_code;
  $('#e-ferne-knoepfe').hidden = !f.angemeldet;
  $('#e-ferne-ein').hidden = !!f.aktiv;
  $('#e-ferne-aus').hidden = !f.aktiv;
  if (f.adresse) $('#e-ferne-adresse').value = f.adresse;
  if (f.benutzer) $('#e-ferne-benutzer').value = f.benutzer;
  // Verbunden ist der örtliche Datenordner nicht das Thema.
  if (f.aktiv) {
    $('#e-ordnerwahl').hidden = true;
    $('#e-ordner-hinweis').textContent = 'Dieses Fenster arbeitet gerade auf dem Server. '
      + 'Zum Umstellen des eigenen Ordners erst auf „Eigene Notizen" zurückschalten.';
  }
}

async function ferneUmschalten(an) {
  try {
    sagen(an ? 'Auf dem Server …' : 'Zurück zu den eigenen Notizen …', 0);
    // Dieselbe Stelle wie beim Klick auf die andere Seite in der Leiste -
    // und vor allem ohne Neuladen, siehe seitenwechsel().
    await seitenwechsel(an, null);
    dateiZeigen(false);
  } catch (f) { $('#e-ferne-hinweis').textContent = f.message; }
}

$('#e-ferne-anmelden').addEventListener('click', async () => {
  const knopf = $('#e-ferne-anmelden');
  knopf.disabled = true;
  $('#e-ferne-hinweis').textContent = 'wird verbunden …';
  try {
    const r = await api('/api/ferne/anmelden', 'POST', {
      adresse: $('#e-ferne-adresse').value,
      benutzer: $('#e-ferne-benutzer').value,
      passwort: $('#e-ferne-passwort').value,
    });
    $('#e-ferne-passwort').value = '';
    $('#e-ferne-hinweis').textContent = `Angemeldet an ${r.adresse} als ${r.benutzer}.`;
    await einstellungenLaden();
  } catch (f) {
    $('#e-ferne-hinweis').textContent = f.message;
  } finally {
    knopf.disabled = false;
  }
});

$('#e-ferne-code-senden').addEventListener('click', async () => {
  $('#e-ferne-hinweis').textContent = 'wird geprüft …';
  try {
    const r = await api('/api/ferne/code', 'POST', { code: $('#e-ferne-code').value });
    $('#e-ferne-code').value = '';
    $('#e-ferne-hinweis').textContent = `Angemeldet an ${r.adresse} als ${r.benutzer}.`;
    await einstellungenLaden();
  } catch (f) { $('#e-ferne-hinweis').textContent = f.message; }
});

$('#e-ferne-ein').addEventListener('click', () => ferneUmschalten(true));
$('#e-ferne-aus').addEventListener('click', () => ferneUmschalten(false));
$('#e-ferne-abmelden').addEventListener('click', async () => {
  try {
    await api('/api/ferne/abmelden', 'POST', {});
    $('#e-ferne-hinweis').textContent = 'Abgemeldet.';
    // Der Serverteil der Leiste faellt damit weg.
    merker.legen('zuletzt', 'null');
    setTimeout(wiederAufbauen, 300);
  } catch (f) { $('#e-ferne-hinweis').textContent = f.message; }
});

function sperrhinweis(text) { $('#e-sperre-hinweis').textContent = text; }

async function sperreTafelFuellen() {
  const s = await sperreHolen();
  $('#e-sperre-stand').textContent = !s.eingerichtet ? 'aus'
    : (s.offen ? 'eingeschaltet, offen' : 'eingeschaltet, zugesperrt');
  $('#e-sperre-einschalten').hidden = s.eingerichtet;
  $('#e-sperre-verwalten').hidden = !s.eingerichtet;
  $('#e-sperre-minuten').value = String(s.minuten || 0);
}

$('#e-sperre-an').addEventListener('click', async () => {
  const pw = $('#e-sperre-pw1').value;
  if (pw !== $('#e-sperre-pw2').value) { sperrhinweis('Die beiden Passwörter sind nicht gleich.'); return; }
  if (pw.length < 8) { sperrhinweis('Das Passwort braucht mindestens 8 Zeichen.'); return; }
  const knopf = $('#e-sperre-an');
  knopf.disabled = true;
  sperrhinweis('wird eingeschaltet, die Notizen werden verschlüsselt …');
  try {
    if (schmutzig) await speichernJetzt();
    const r = await api('/api/sperre/an', 'POST', { passwort: pw });
    $('#e-sperre-pw1').value = '';
    $('#e-sperre-pw2').value = '';
    if (r.nicht_umgestellt && r.nicht_umgestellt.length) {
      // Das darf nicht untergehen: der Benutzer hielte seine Notizen sonst für
      // geschützt, während ein Teil davon weiter im Klartext auf der Platte
      // liegt. Lieber eine unbequeme Meldung als eine falsche Zusicherung.
      sperrhinweis(`Achtung: ${r.nicht_umgestellt.length} Dateien konnten NICHT `
        + `verschlüsselt werden und liegen weiter im Klartext. ${r.nicht_umgestellt[0]}`);
      melden(`Die Sperre ist an, aber ${r.nicht_umgestellt.length} Dateien liegen noch `
        + `im Klartext: ${r.nicht_umgestellt[0]}`, [
        ['Nochmal versuchen', async () => {
          try {
            const w = await api('/api/sperre/nachholen', 'POST', {});
            meldungWeg();
            sperrhinweis(w.offen
              ? `Noch immer ${w.offen} Dateien im Klartext.`
              : 'Jetzt ist alles verschlüsselt.');
          } catch (f) { melden(f.message); }
        }],
      ]);
    } else {
      sperrhinweis(`Eingeschaltet, ${r.umgestellt} Dateien verschlüsselt.`);
    }
    rettungZeigen(r.rettung);
    await sperreTafelFuellen();
  } catch (f) {
    sperrhinweis(f.message);
  } finally {
    knopf.disabled = false;
  }
});

$('#e-sperre-zu').addEventListener('click', () => { tafelZeigen(false); zusperrenJetzt(); });

$('#e-sperre-minuten').addEventListener('change', async (ev) => {
  try {
    const r = await api('/api/sperre/minuten', 'POST', { minuten: parseInt(ev.target.value, 10) });
    sperreStand.minuten = r.minuten;
    letzteTat = Date.now();
    sperrhinweis(r.minuten ? `Sperrt nach ${r.minuten} Minuten ohne Benutzung.` : 'Sperrt nicht nach Zeit.');
  } catch (f) { sperrhinweis(f.message); }
});

$('#e-pw-aendern').addEventListener('click', async () => {
  const alt = $('#e-pw-alt').value, neu = $('#e-pw-neu').value;
  if (!alt || !neu) { sperrhinweis('Beide Passwörter eingeben.'); return; }
  try {
    await api('/api/sperre/passwort', 'POST', { alt, neu });
    $('#e-pw-alt').value = '';
    $('#e-pw-neu').value = '';
    sperrhinweis('Passwort geändert. Der Wiederherstellungsschlüssel gilt weiter.');
  } catch (f) { sperrhinweis(f.message); }
});

$('#e-rettung-neu').addEventListener('click', async () => {
  const passwort = $('#e-rettung-pw').value;
  if (!passwort) { sperrhinweis('Passwort eingeben.'); return; }
  try {
    const r = await api('/api/sperre/rettung', 'POST', { passwort });
    $('#e-rettung-pw').value = '';
    rettungZeigen(r.rettung);
    sperrhinweis('Neuer Schlüssel ausgegeben, der alte gilt nicht mehr.');
  } catch (f) { sperrhinweis(f.message); }
});

$('#e-sperre-aus').addEventListener('click', async () => {
  const passwort = $('#e-sperre-aus-pw').value;
  if (!passwort) { sperrhinweis('Passwort eingeben.'); return; }
  const knopf = $('#e-sperre-aus');
  knopf.disabled = true;
  sperrhinweis('wird abgeschaltet, die Notizen werden entschlüsselt …');
  try {
    const r = await api('/api/sperre/aus', 'POST', { passwort });
    $('#e-sperre-aus-pw').value = '';
    sperrhinweis(`Abgeschaltet, ${r.umgestellt} Dateien liegen wieder im Klartext.`);
    await sperreTafelFuellen();
  } catch (f) {
    sperrhinweis(f.message);
  } finally {
    knopf.disabled = false;
  }
});

/* ------------------------------------------------------------------ Anlauf */


/* ============================================================ Formatieren
 *
 * Kam aus der Serverfassung (web/shim.js), wo das zur Laufzeit eingesetzt
 * wurde. Hier steht es jetzt richtig: beide Fassungen teilen sich diese
 * Datei, also sieht die Mappe im Fenster und im Browser gleich aus.
 */

/* Zu einem Kasten das Element finden. Steht hier und nicht viermal
 * ausgeschrieben wie weiter oben im Text. */
function kastenDaten(k) {
  try {
    if (typeof elemente === 'undefined' || !k) return null;
    return elemente.find((x) => x.id === k.dataset.id) || null;
  } catch (f) { return null; }
}

/* Ein Hinweis, der von selbst wieder verschwindet. In der Serverfassung hing
 * er an einer eigenen Zeile; hier ist die Zustandsanzeige genau dafuer da. */
function malsagen(text) {
  sagen(text, 5000);
}

/* Kurzschreibweise fuers Bauen - sonst stehen drei Zeilen fuer jeden Knopf. */
function el(art, eigenschaften, kinder) {
  const k = document.createElement(art);
  Object.assign(k, eigenschaften || {});
  for (const kind of kinder || []) k.append(kind);
  return k;
}


/* ------------------------------------------------------- Die Formatleiste

   Zwei Reihen, so wie in OneNote: Schriftart, Groesse, Formatvorlage,
   Einzug, Aufgabe und Kategorie oben; F K U, Marker, Farbe, Listen, Format
   uebertragen und Loeschen unten.

   Gebaut wird sie einmal und zweimal benutzt: in der schwebenden Leiste,
   die beim Markieren aufgeht, und unten im Rechtsklick-Menue. Zwei
   Leisten, die dasselbe tun sollen, sind eine zu viel - eine davon ist
   eines Tages anders.

   Gerechnet wird wieder nichts selbst: aufAuswahl() drueben setzt das
   Format, hervorheben() den Marker. Was hier steht, ist die Bedienung.

   Drei Sachen gehen bewusst anders als bei OneNote, weil die Ablage nur
   bestimmte Auszeichnungen annimmt (kein freies CSS, siehe reinigen.py):
   der Marker hat eine Farbe statt fuenf, die Groessen sind die sieben, die
   <font size> kennt, und ein Haken ist ein Zeichen im Text - keine
   Kontrollkaestchen-Auszeichnung, die beim Speichern wieder herausfiele. */

const FL_VORLAGEN = [['<p>', 'Normal'], ['<h1>', 'Überschrift 1'],
                     ['<h2>', 'Überschrift 2'], ['<h3>', 'Überschrift 3'],
                     ['<blockquote>', 'Zitat'], ['<pre>', 'Code']];
// Diese Zeichen landen im Text, nicht nur in der Leiste - also solche, die
// jede Schrift hat. Ein Kaestchen mitten im Satz waere schlimmer als kein
// Zeichen.
const FL_KATEGORIEN = [['☐', 'Aufgabe'], ['★', 'Wichtig'], ['⚑', 'Fahne'],
                       ['✔', 'Erledigt'], ['✘', 'Verworfen']];
const FL_GROESSEN = [['1', '8'], ['2', '10'], ['3', '12'], ['4', '14'],
                     ['5', '18'], ['6', '24'], ['7', '36']];
/* Die Nummerierungsbibliothek. Welche Zaehlung und was davor und dahinter
   steht, sagt der Wert selbst: '1)' sind Ziffern mit Klammer, '(a)' kleine
   Buchstaben in Klammern. Daraus wird beides gebaut - die Vorschau im Menue
   und die Regel im Stylesheet. Dieselbe Liste steht in web/listen.py; was
   dort nicht drinsteht, faellt beim Speichern heraus. */
const FL_NUMMERN = ['1.', '1)', 'a)', 'A.',
                    '1.)', 'I.', 'A)', '(1)', '(a)',
                    'a.', '1-', '1', 'A', 'a',
                    'i.', 'i)'];
const FL_ZAEHLER = { '1': 'decimal', a: 'lower-alpha', A: 'upper-alpha',
                     i: 'lower-roman', I: 'upper-roman' };
const FL_ZIFFERN = { '1': ['1', '2', '3'], a: ['a', 'b', 'c'], A: ['A', 'B', 'C'],
                     i: ['i', 'ii', 'iii'], I: ['I', 'II', 'III'] };

/* Dasselbe fuer die Aufzaehlung: das Zeichen ist der Wert. Nur Zeichen aus
   der Grundebene - ein Emoji faellt in Schriften aus, die es nicht haben,
   und dann steht ein Kaestchen in der Liste. */
const FL_ZEICHEN = ['●', '○', '•', '◦', '◉',
                    '✦', '◆', '◇', '❖', '⋄',
                    '■', '□', '▪', '▫', '◼',
                    '▶', '▸', '‣', '→', '⇒',
                    '›', '➢', '✱', '✸', '❉',
                    '–', '—', '✓', '✗', '★',
                    '☺', '☎', '✉', '♦', '♥'];

function nrTeile(art) {
  const i = String(art).search(/[1aAiI]/);
  if (i < 0) return null;
  return { typ: art.charAt(i), vorne: art.slice(0, i), hinten: art.slice(i + 1) };
}

function nrProbe(art) {
  const t = nrTeile(art);
  if (!t) return [];
  return FL_ZIFFERN[t.typ].map(function (z) { return t.vorne + z + t.hinten; });
}

function listenRegeln() {
  let text = '';
  FL_NUMMERN.forEach(function (art, i) {
    const t = nrTeile(art);
    text += `@counter-style nz${i} { system: extends ${FL_ZAEHLER[t.typ]};`
          + ` prefix: "${t.vorne}"; suffix: "${t.hinten} "; }\n`
          + `ol[data-art="${art}"] { list-style-type: nz${i}; }\n`;
  });
  FL_ZEICHEN.forEach(function (z, i) {
    // cyclic mit einem einzigen Zeichen: das steht dann vor jeder Zeile.
    text += `@counter-style az${i} { system: cyclic; symbols: "${z}";`
          + ` suffix: " "; }\n`
          + `ul[data-art="${z}"] { list-style-type: az${i}; }\n`;
  });
  return text;
}

// Die Liste, in der die Markierung steht - oder nichts.
function listeUm(tag) {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount) return null;
  let k = sel.getRangeAt(0).startContainer;
  if (k && k.nodeType !== 1) k = k.parentElement;
  return k && k.closest ? k.closest(tag) : null;
}

/* Eine Art setzen heisst: notfalls erst eine Liste daraus machen. Ohne das
   waere die halbe Bibliothek wirkungslos, solange der Absatz noch keine
   Liste ist - und genau so greift man danach hinein. */
function artSetzen(tag, befehl, wert) {
  const liste = listeUm(tag);
  if (!wert) {                      // "Keine": die Liste wieder weg
    if (liste) flBefehl(befehl);
    return;
  }
  if (!liste) flBefehl(befehl);
  const neue = listeUm(tag);
  if (!neue) return;
  neue.setAttribute('data-art', wert);
  gemerkt();
}

function flNummerSetzen(art) { artSetzen('ol', 'insertOrderedList', art); }
function flPunktSetzen(zeichen) { artSetzen('ul', 'insertUnorderedList', zeichen); }

let flPinsel = null;            // gemerktes Format beim Uebertragen

/* Symbole als Strich, nicht als Zeichen. Pfeile, Schild und Pinsel gibt es
   nicht in jeder Schrift - fehlen sie, zeigt der Browser ein Kaestchen, und
   eine Leiste voller Kaestchen sagt niemandem etwas. Gezeichnet ist immer
   da, und es nimmt die Farbe der Schrift mit. */
function flBild(inhalt) {
  return '<svg class="fl-bild" viewBox="0 0 16 16" width="15" height="15" '
       + 'fill="none" stroke="currentColor" stroke-width="1.4" '
       + 'stroke-linecap="round" stroke-linejoin="round">' + inhalt + '</svg>';
}
const FL_EINZUG_RAUS = flBild('<path d="M2 3h12M6 6h8M6 10h8M2 13h12"/>'
                              + '<path d="M4.5 6.5 2 8l2.5 1.5"/>');
const FL_EINZUG_REIN = flBild('<path d="M2 3h12M6 6h8M6 10h8M2 13h12"/>'
                              + '<path d="M1.5 6.5 4 8l-2.5 1.5"/>');
// Die beiden Listenknoepfe zeigen eine Liste, nicht nur ihr Zeichen: ein
// einzelner Punkt neben einer "1." sagt nicht, dass es um Absaetze geht.
const FL_ZEILEN = '<path d="M6 3.5h8M6 8h8M6 12.5h8"/>';
const FL_PUNKTLISTE = flBild(FL_ZEILEN
    + '<circle cx="2.6" cy="3.5" r="1.2" fill="currentColor" stroke="none"/>'
    + '<circle cx="2.6" cy="8" r="1.2" fill="currentColor" stroke="none"/>'
    + '<circle cx="2.6" cy="12.5" r="1.2" fill="currentColor" stroke="none"/>');
const FL_NUMMERNLISTE = flBild(FL_ZEILEN
    + '<text x="0" y="5.4" font-size="5.6" fill="currentColor" stroke="none">1</text>'
    + '<text x="0" y="9.9" font-size="5.6" fill="currentColor" stroke="none">2</text>'
    + '<text x="0" y="14.4" font-size="5.6" fill="currentColor" stroke="none">3</text>');
const FL_SCHILD = flBild('<path d="M8.5 1.5H14v5.5L7 14 2 9z"/>'
                         + '<circle cx="11.2" cy="4.6" r=".9"/>');
const FL_PINSEL = flBild('<path d="M11 2.5 13.5 5 7 11.5 4.5 9z"/>'
                         + '<path d="M4.5 9 3 12.5 6.5 11"/>');
// Der Textmarker. Ein "A" mit gelbem Grund sagt nicht, was passiert - der
// Stift schon, und darunter liegt der Balken in seiner Farbe.
const FL_MARKERSTIFT = flBild('<path d="M3.5 12.5h3L13 6l-3-3-6.5 6.5z"/>'
                              + '<path d="M9 4.5 11.5 7"/><path d="M2.5 14.5h5"/>');
// Die Farben des Markers. Dieselben Namen stehen in reinigen.py; was dort
// nicht drinsteht, faellt beim Speichern heraus. Gelb braucht keinen
// Eintrag im Text und steht deshalb vorn.
const FL_MARKERFARBEN = [['gelb', 'Gelb', '#ffe680'], ['gruen', 'Grün', '#b7ec9a'],
                         ['blau', 'Blau', '#aad8ff'], ['rosa', 'Rosa', '#ffc0dd'],
                         ['orange', 'Orange', '#ffcf9e'], ['grau', 'Grau', '#dcdcd4']];
const FL_SCHERE = flBild('<circle cx="4" cy="12.2" r="2"/><circle cx="12" cy="12.2" r="2"/>'
                         + '<path d="M5.4 10.8 12 2M10.6 10.8 4 2"/>');
const FL_KOPIE = flBild('<rect x="5.5" y="5.5" width="8.5" height="9" rx="1.2"/>'
                        + '<path d="M10.5 5.5v-3a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h2.5"/>');
const FL_KLEMME = flBild('<rect x="3" y="2.5" width="10" height="12" rx="1.2"/>'
                         + '<path d="M6 2.5a2 2 0 0 1 4 0"/><path d="M5.5 7.5h5M5.5 10.5h5"/>');

/* Ausrichtung und Zeilenabstand. Beides waere im Browser text-align und
   line-height, also freies CSS - und das nimmt die Ablage nicht an (siehe
   reinigen.py). Deshalb derselbe Weg wie bei den Listenarten: ein Attribut
   mit einem Wert aus einer festen Liste, und die Stildatei macht daraus die
   Regel. So laesst sich ueber data-aus nichts hineinschreiben. */
const FL_AUS_ATTR = 'data-aus';
const FL_ZA_ATTR = 'data-za';
// Welche Zeilen in welchem Bild kurz sind - daraus entsteht das Symbol.
function flAusBild(art) {
  const kurz = art === 'block' ? [] : [1, 3];
  let p = '';
  [2.6, 6.2, 9.8, 13.4].forEach(function (y, i) {
    let a = 2;
    let b = 14;
    if (kurz.indexOf(i) >= 0) {
      if (art === 'links') b = 10;
      else if (art === 'rechts') a = 6;
      else { a = 4; b = 12; }
    }
    p += `M${a} ${y}h${b - a}`;
  });
  return flBild(`<path d="${p}"/>`);
}
const FL_AUSRICHTUNG = [['links', 'Linksbündig'], ['mitte', 'Zentriert'],
                        ['rechts', 'Rechtsbündig'], ['block', 'Blocksatz']];
// Die Werte stehen genau so in reinigen.py; was dort fehlt, faellt beim
// Speichern wieder heraus.
const FL_ABSTAENDE = [['1', 'Einfach'], ['1.15', '1,15'], ['1.5', 'Anderthalb'],
                      ['2', 'Doppelt'], ['3', 'Dreifach'], ['', 'Standard']];
const FL_ABSTANDBILD = flBild('<path d="M6.5 3h7.5M6.5 8h7.5M6.5 13h7.5"/>'
                              + '<path d="M3 4.5V11.5M1.6 6 3 4.3 4.4 6M1.6 10 3 11.7 4.4 10"/>');

/* Die Bloecke, in denen die Markierung steckt. Absatzsachen - Ausrichtung,
   Zeilenabstand - gelten fuer die ganze Zeile, nicht fuer die markierten
   Buchstaben, also muessen sie am Block haengen. Steht der Text noch nackt
   im Feld, gibt es keinen: dann macht formatBlock erst einen daraus. */
const FL_BLOECKE = 'p,div,h1,h2,h3,h4,blockquote,pre,li,ul,ol';

function flBloecke() {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount) return [];
  const r = sel.getRangeAt(0);
  let anfang = r.startContainer;
  if (anfang && anfang.nodeType !== 1) anfang = anfang.parentElement;
  const feld = anfang && anfang.closest ? anfang.closest('.text') : null;
  if (!feld) return [];
  const treffer = [];
  for (const b of feld.querySelectorAll(FL_BLOECKE)) {
    let drin = true;
    try { drin = r.intersectsNode(b); } catch (f) { /* nicht jede Ansicht kann das */ }
    // Ein Block, der nur andere Bloecke enthaelt, bekommt nichts: sonst
    // steht die Ausrichtung zweimal da und die innere gewinnt ohnehin.
    if (drin && !b.querySelector(FL_BLOECKE)) treffer.push(b);
  }
  return treffer;
}

function flBlockSetzen(name, wert) {
  let bloecke = flBloecke();
  if (!bloecke.length) {
    flBefehl('formatBlock', '<div>');
    bloecke = flBloecke();
  }
  if (!bloecke.length) return;
  for (const b of bloecke) {
    if (wert) b.setAttribute(name, wert);
    else b.removeAttribute(name);
  }
  gemerkt();
}

function flAusrichten(wert) { flBlockSetzen(FL_AUS_ATTR, wert); }
function flAbstand(wert) { flBlockSetzen(FL_ZA_ATTR, wert); }

/* Ausschneiden, Kopieren, Einfuegen als Knoepfe. Dieselbe Vorsicht wie im
   Rechtsklick-Menue: je nach Webansicht darf mal die Zwischenablage des
   Systems, mal nur der alte Befehl. */
async function flAblage(tun) {
  try {
    if (tun === 'kopieren' || tun === 'ausschneiden') {
      const text = window.getSelection().toString();
      try { await navigator.clipboard.writeText(text); }
      catch (f) { document.execCommand('copy'); }
      if (tun === 'ausschneiden') { document.execCommand('delete'); gemerkt(); }
      return;
    }
    let text = '';
    try { text = await navigator.clipboard.readText(); }
    catch (f) { sagen('Einfügen geht hier nur mit Strg+V', 3000); return; }
    document.execCommand('insertText', false, text);
    gemerkt();
  } catch (f) {
    melden('Ging nicht: ' + f.message);
  }
}

function flBefehl(was, wert) {
  try {
    if (typeof aufAuswahl === 'function') aufAuswahl(was, wert);
  } catch (f) { console.error('[notizmappe] Format:', f); }
}

/* Eine Taste mit Farbbalken darunter - Schriftfarbe und Textmarker. Der
   Balken zeigt, welche Farbe ein Klick nimmt; der Pfeil daneben waehlt eine
   andere. Genau so steht es in Word, und genau deshalb klickt dort niemand
   erst auf den Pfeil, wenn er die Farbe von eben noch einmal will. */
function markerSetzen(farbe) {
  try {
    if (typeof hervorheben === 'function') hervorheben(farbe);
  } catch (f) { console.error('[notizmappe] Hervorheben:', f); }
}

function flFarbtaste(inhalt, titel, farbe, tun) {
  const k = flTaste(inhalt, titel, tun);
  k.classList.add('fl-farbtaste');
  const balken = el('span', { className: 'fl-balken' });
  balken.style.background = farbe;
  k.append(balken);
  k.balken = balken;
  return k;
}

function flTaste(inhalt, titel, tun, stand) {
  const k = el('button', { type: 'button', className: 'fl-taste', title: titel });
  k.innerHTML = inhalt;
  if (stand) k.dataset.stand = stand;
  k.addEventListener('click', function (ev) {
    ev.preventDefault();
    ev.stopPropagation();
    tun(k);
  });
  return k;
}

/* Ein kleines Klappmenue - im Kasten der Leiste, nicht am Koerper: alles
   ausserhalb schliesst drueben die schwebende Leiste und das Rechtsklick-
   Menue, und dann waere die Liste weg, bevor man sie anklicken kann. */
function flKlappe(wirt, titel, inhalt, eintraege, tun) {
  const knopf = flTaste(inhalt + '<span class="fl-pfeil">▾</span>', titel, function (k) {
    const alte = wirt.querySelector('.fl-liste');
    if (alte) {
      alte.remove();
      if (alte.dataset.von === titel) return;      // derselbe Knopf: zu
    }
    const liste = el('div', { className: 'fl-liste' });
    liste.dataset.von = titel;
    for (const [wert, name, zeichen] of eintraege) {
      const z = el('button', { type: 'button', className: 'fl-eintrag' }, [
        el('span', { className: 'fl-probe', textContent: zeichen || '' }),
        el('span', { textContent: name }),
      ]);
      if (zeichen && zeichen.charAt(0) === '#') {
        z.firstChild.style.background = zeichen;
        z.firstChild.textContent = '';
        z.firstChild.classList.add('fl-tupfer');
      }
      z.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        liste.remove();
        tun(wert);
      });
      liste.append(z);
    }
    const r = k.getBoundingClientRect();
    const w = wirt.getBoundingClientRect();
    liste.style.left = Math.max(0, r.left - w.left) + 'px';
    liste.style.top = (r.bottom - w.top + 2) + 'px';
    wirt.append(liste);
  });
  knopf.classList.add('fl-mitpfeil');
  return knopf;
}

/* Haken und Kategorien sind Zeichen am Zeilenanfang. Eine eigene
   Auszeichnung (etwa ein input type=checkbox) faellt beim Speichern wieder
   heraus - die Ablage nimmt nur die Auszeichnungen an, die der Editor
   selbst setzt. Ein Zeichen ueberlebt jeden Weg, auch den nach drueben. */
function flZeichenSetzen(zeichen) {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount) return;
  const r = sel.getRangeAt(0);
  const feld = (r.startContainer.nodeType === 1 ? r.startContainer
                                                : r.startContainer.parentElement);
  if (!feld || !feld.closest('[contenteditable]')) return;
  const anfang = r.cloneRange();
  anfang.collapse(true);
  sel.removeAllRanges();
  sel.addRange(anfang);
  try {
    document.execCommand('insertText', false, zeichen + ' ');
  } catch (f) { /* dann eben nicht */ }
}

/* Ein Klick auf einen Haken im Text setzt ihn um. Das ist der Teil, der aus
   dem Zeichen eine Aufgabe macht. */
function flHakenAnschalten() {
  const grund = document.getElementById('flaeche');
  if (!grund || grund.dataset.haken === 'ja') return;
  grund.dataset.haken = 'ja';
  grund.addEventListener('click', function (ev) {
    const feld = ev.target.closest && ev.target.closest('.text');
    if (!feld) return;
    const stelle = document.caretRangeFromPoint
      ? document.caretRangeFromPoint(ev.clientX, ev.clientY) : null;
    if (!stelle || stelle.startContainer.nodeType !== 3) return;
    const text = stelle.startContainer.nodeValue || '';
    const i = stelle.startOffset;
    for (const [auf, zu] of [['☐', '☑'], ['☑', '☐']]) {
      for (const stern of [i - 1, i]) {
        if (text.charAt(stern) !== auf) continue;
        stelle.startContainer.nodeValue =
          text.slice(0, stern) + zu + text.slice(stern + 1);
        const e = kastenDaten(feld.closest('.kasten'));
        if (e) e.html = feld.innerHTML;
        gemerkt();
        return;
      }
    }
  });
}

/* Format uebertragen: einmal klicken merkt, was an der Stelle gilt; die
   naechste Markierung bekommt es. Mehr macht der Pinsel in OneNote auch
   nicht. */
function flPinselNehmen(knopf) {
  if (flPinsel) { flPinsel = null; flPinselZeigen(); return; }
  const lies = (was) => {
    try { return document.queryCommandState(was); } catch (f) { return false; }
  };
  const wert = (was) => {
    try { return String(document.queryCommandValue(was) || ''); } catch (f) { return ''; }
  };
  flPinsel = {
    bold: lies('bold'), italic: lies('italic'), underline: lies('underline'),
    strikeThrough: lies('strikeThrough'),
    fontName: wert('fontName').replace(/^['"]|['"]$/g, ''),
    fontSize: wert('fontSize'), foreColor: wert('foreColor'),
  };
  flPinselZeigen();
}

function flPinselZeigen() {
  for (const k of document.querySelectorAll('.fl-taste[data-stand="pinsel"]')) {
    k.classList.toggle('an', !!flPinsel);
  }
}

function flPinselAnschalten() {
  document.addEventListener('mouseup', function () {
    if (!flPinsel) return;
    setTimeout(function () {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !sel.anchorNode) return;
      const knoten = sel.anchorNode.nodeType === 1 ? sel.anchorNode
                                                   : sel.anchorNode.parentElement;
      if (!knoten || !knoten.closest('[contenteditable]')) return;
      const p = flPinsel;
      flPinsel = null;
      flPinselZeigen();
      flBefehl('removeFormat');
      for (const was of ['bold', 'italic', 'underline', 'strikeThrough']) {
        if (p[was]) flBefehl(was);
      }
      if (p.fontName) flBefehl('fontName', p.fontName);
      if (p.fontSize) flBefehl('fontSize', p.fontSize);
      if (p.foreColor) flBefehl('foreColor', p.foreColor);
    }, 0);
  });
}

function flFarben() {
  const aus = [];
  for (const k of document.querySelectorAll('#farben button[data-farbe]')) {
    aus.push([k.dataset.farbe, k.title || k.dataset.farbe, k.dataset.farbe]);
  }
  return aus;
}

// Drei Zeilen Vorschau - so steht es spaeter da.
function nrKachel(art) {
  return nrProbe(art).map(function (z) {
    return el('span', { className: 'fl-kzeile' }, [
      el('span', { className: 'fl-knr', textContent: z }),
      el('span', { className: 'fl-kstrich' }),
    ]);
  });
}

function azKachel(zeichen) {
  return [el('span', { className: 'fl-kzeichen', textContent: zeichen })];
}

/* Dieselbe Mechanik wie das Klappmenue, nur als Gitter mit Vorschau: ein
   paar Zeilen "1. 2. 3." sagen mehr als ihr Name. */
function flGalerie(wirt, titel, inhalt, arten, tun, bauen) {
  const knopf = flTaste(inhalt + '<span class="fl-pfeil">▾</span>', titel, function (k) {
    const alte = wirt.querySelector('.fl-liste');
    if (alte) {
      alte.remove();
      if (alte.dataset.von === titel) return;      // derselbe Knopf: zu
    }
    const kasten = el('div', { className: 'fl-liste fl-galerie' });
    kasten.dataset.von = titel;
    kasten.append(el('p', { className: 'fl-galkopf', textContent: titel }));
    const gitter = el('div', { className: 'fl-gitter' });
    for (const art of [''].concat(arten)) {
      const kachel = el('button', { type: 'button', className: 'fl-kachel' },
        art ? bauen(art) : [el('span', { className: 'fl-keine', textContent: 'Keine' })]);
      kachel.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        kasten.remove();
        tun(art);
      });
      gitter.append(kachel);
    }
    kasten.append(gitter);
    wirt.append(kasten);
    // Das Gitter ist breiter als die Leiste. Es darf ueber ihren Rand
    // hinausragen, nur nicht aus dem Fenster.
    flTafelStellen(kasten, k, wirt);
  });
  knopf.classList.add('fl-mitpfeil');
  return knopf;
}

/* Knopf und Pfeil gehoeren zusammen: links die Liste an- und ausschalten,
   rechts die Bibliothek. Getrennt standen vier Knoepfe nebeneinander, und
   keiner sagte, dass je zwei dasselbe meinen. */
function flGeteilt(knopf, pfeil) {
  pfeil.classList.add('fl-nurpfeil');
  return el('span', { className: 'fl-geteilt' }, [knopf, pfeil]);
}

function formatleisteBauen(wie) {
  const imBand = !!(wie && wie.band);
  const wirt = el('div', { className: 'formatleiste' + (imBand ? ' fl-band' : '') });

  const art = el('select', { className: 'fl-art', title: 'Schriftart' });
  art.addEventListener('change', function () { flBefehl('fontName', art.value); });
  const groesse = el('select', { className: 'fl-groesse', title: 'Schriftgröße' });
  for (const [wert, text] of FL_GROESSEN) {
    // 12 ist die Groesse, in der geschrieben wird - ohne das stand hier 8,
    // die erste der Liste.
    groesse.append(el('option', { value: wert, textContent: text,
                                  selected: wert === '3' }));
  }
  groesse.addEventListener('change', function () { flBefehl('fontSize', groesse.value); });

  const trenner = () => el('span', { className: 'fl-trenner' });

  // Gruppen statt einer festen Reihenfolge: im Band stehen sie nebeneinander
  // in einer Zeile, in der schwebenden Leiste und im Rechtsklick-Menue auf
  // zwei Reihen verteilt. Gebaut wird jeder Knopf nur einmal.
  //
  // Die schwebende Leiste zeigt davon nur, was sie schon vorher zeigte -
  // sie war so in Ordnung, und eine Palette, die beim Markieren aufgeht,
  // darf nicht breiter werden als der Text darunter. Die Zwischenablage,
  // hoch- und tiefgestellt, Ausrichtung und Zeilenabstand gibt es deshalb
  // nur oben im Band.
  const ablage = [
    flTaste(FL_KLEMME, 'Einfügen (Strg+V)', function () { flAblage('einfuegen'); }),
    flTaste(FL_SCHERE, 'Ausschneiden (Strg+X)', function () { flAblage('ausschneiden'); }),
    flTaste(FL_KOPIE, 'Kopieren (Strg+C)', function () { flAblage('kopieren'); }),
    flTaste(FL_PINSEL, 'Format übertragen', flPinselNehmen, 'pinsel'),
  ];

  const schrift = [art, groesse];

  const zeichen = [
    flTaste('<b>F</b>', 'Fett (Strg+B)', function () { flBefehl('bold'); }, 'bold'),
    flTaste('<i>K</i>', 'Kursiv (Strg+I)', function () { flBefehl('italic'); }, 'italic'),
    flTaste('<u>U</u>', 'Unterstrichen (Strg+U)',
            function () { flBefehl('underline'); }, 'underline'),
    flTaste('<s>S</s>', 'Durchgestrichen',
            function () { flBefehl('strikeThrough'); }, 'strikeThrough'),
    flTaste('x<sup class="fl-hoch">2</sup>', 'Hochgestellt',
            function () { flBefehl('superscript'); }, 'superscript'),
    flTaste('x<sub class="fl-hoch">2</sub>', 'Tiefgestellt',
            function () { flBefehl('subscript'); }, 'subscript'),
  ];

  // Beide Farbknoepfe wie in Word: links die Farbe von eben, rechts der
  // Pfeil fuer eine andere. Der Balken darunter zieht mit und sagt, was
  // ein Klick nimmt.
  let markerwahl = FL_MARKERFARBEN[0];
  const kMarkerKnopf = flFarbtaste(FL_MARKERSTIFT, 'Hervorheben', markerwahl[2],
                                   function () { markerSetzen(markerwahl[0]); });
  const kMarker = flGeteilt(kMarkerKnopf,
    flKlappe(wirt, 'Andere Farbe zum Hervorheben', '', FL_MARKERFARBEN,
             function (w) {
               markerwahl = FL_MARKERFARBEN.find((f) => f[0] === w) || markerwahl;
               kMarkerKnopf.balken.style.background = markerwahl[2];
               markerSetzen(markerwahl[0]);
             }));

  const farbliste = flFarben();
  // Nicht die erste: die ist die Schriftfarbe selbst, und ein schwarzer
  // Balken unter dem A sieht aus wie gar keiner.
  let schriftwahl = (farbliste[1] || farbliste[0] || ['#b23b2e'])[0];
  const kFarbeKnopf = flFarbtaste('<span class="fl-buchstabe">A</span>', 'Schriftfarbe',
                                  schriftwahl,
                                  function () { flBefehl('foreColor', schriftwahl); });
  const kFarbe = flGeteilt(kFarbeKnopf,
    flKlappe(wirt, 'Andere Schriftfarbe', '', farbliste, function (farbe) {
      schriftwahl = farbe;
      kFarbeKnopf.balken.style.background = farbe;
      flBefehl('foreColor', farbe);
    }));

  const farben = [
    kMarker,
    kFarbe,
    flTaste('<span class="fl-weg">✕</span>', 'Formatierung entfernen', function () {
      flBefehl('removeFormat');
      try { if (typeof hervorhebungWeg === 'function') hervorhebungWeg(); } catch (f) { /* egal */ }
    }),
  ];

  const listen = [
    flGeteilt(
      flTaste(FL_PUNKTLISTE, 'Aufzählung',
              function () { flBefehl('insertUnorderedList'); }, 'insertUnorderedList'),
      flGalerie(wirt, 'Aufzählungszeichenbibliothek', '',
                FL_ZEICHEN, flPunktSetzen, azKachel)),
    flGeteilt(
      flTaste(FL_NUMMERNLISTE, 'Nummerierung',
              function () { flBefehl('insertOrderedList'); }, 'insertOrderedList'),
      flGalerie(wirt, 'Nummerierungsbibliothek', '',
                FL_NUMMERN, flNummerSetzen, nrKachel)),
  ];

  const absatz = [
    flTaste(FL_EINZUG_RAUS, 'Einzug verkleinern',
            function () { flBefehl('outdent'); }),
    flTaste(FL_EINZUG_REIN, 'Einzug vergrößern',
            function () { flBefehl('indent'); }),
    ...FL_AUSRICHTUNG.map(([w, n]) => flTaste(flAusBild(w), n,
                                              function () { flAusrichten(w); })),
    flKlappe(wirt, 'Zeilenabstand', FL_ABSTANDBILD,
             FL_ABSTAENDE.map(([w, n]) => [w, n, '']),
             function (w) { flAbstand(w); }),
  ];

  const vorlagen = [
    flKlappe(wirt, 'Formatvorlage', '<span class="fl-sinn">¶</span>',
             FL_VORLAGEN.map(([w, n]) => [w, n, '']),
             function (w) { flBefehl('formatBlock', w); }),
    flTaste('<span class="fl-haken">☑</span>', 'Aufgabe (zum Abhaken)',
            function () { flZeichenSetzen('☐'); }),
    flKlappe(wirt, 'Kategorie', FL_SCHILD,
             FL_KATEGORIEN.map(([z, n]) => [z, n, z]),
             function (z) { flZeichenSetzen(z); }),
  ];

  const reihe = (gruppen) => {
    const r = el('div', { className: 'fl-reihe' });
    gruppen.forEach(function (g, i) {
      if (i) r.append(trenner());
      for (const k of g) r.append(k);
    });
    return r;
  };

  if (imBand) {
    // Oben ist Platz fuer alles auf einmal - und wer auf Start geht, will
    // nicht erst noch irgendwo aufklappen. Nur hier gibt es deshalb die
    // Zwischenablage, hoch- und tiefgestellt, Ausrichtung und Zeilenabstand.
    wirt.append(reihe([ablage, schrift, zeichen, farben, listen, absatz, vorlagen]));
  } else {
    // Schwebend und im Rechtsklick-Menue: unveraendert, zwei Reihen in
    // derselben Reihenfolge wie vorher. Sie war so in Ordnung, und eine
    // Leiste, die beim Markieren aufgeht, darf nicht breiter sein als der
    // Text darunter.
    wirt.append(reihe([schrift, [vorlagen[0], ...absatz.slice(0, 2)], vorlagen.slice(1)]),
                reihe([zeichen.slice(0, 4), farben.slice(0, 2), listen,
                       [ablage[3], farben[2]]]));
  }
  flSchriftenSpiegeln(wirt);      // gleich, nicht erst beim ersten Auffrischen
  // Ein Klick in die Leiste darf die Markierung nicht kosten - sonst
  // formatiert der Knopf nichts. Auswahlfelder brauchen den Fokus, sonst
  // klappen sie nicht auf.
  wirt.addEventListener('mousedown', function (ev) {
    if (ev.target.tagName !== 'SELECT') ev.preventDefault();
  });
  return wirt;
}

/* Was an der Markierung schon gilt, anzeigen - und die Schriftliste
   nachziehen, die der Server erst nachlaedt. */
/* Die Schriftliste steht drueben und wird vom Server nachgeladen - sie ist
   also erst spaeter vollstaendig. Deshalb jedes Mal nachsehen, ob sie
   gewachsen ist. */
function flSchriftenSpiegeln(wirt) {
  const art = wirt && wirt.querySelector('.fl-art');
  const echt = document.querySelector('#minialt select[data-befehl="fontName"]')
            || document.querySelector('#minileiste select[data-befehl="fontName"]')
            || document.getElementById('schriftart');
  if (!art || !echt || !echt.options.length
      || art.options.length === echt.options.length) return;
  const stand = art.value;
  art.textContent = '';
  // Mit den Gruppen: die Favoriten stehen drueben in einer eigenen, und
  // ohne sie waeren sie irgendwo in der Liste - gerade die, die man sucht.
  for (const kind of echt.children) {
    if (kind.tagName === 'OPTGROUP') {
      const g = el('optgroup', { label: kind.label });
      for (const o of kind.children) {
        g.append(el('option', { value: o.value, textContent: o.textContent }));
      }
      art.append(g);
    } else {
      art.append(el('option', { value: kind.value, textContent: kind.textContent }));
    }
  }
  if (stand) art.value = stand;
}

function formatleisteFrischen(wirt) {
  if (!wirt) return;
  flSchriftenSpiegeln(wirt);
  const klappe = wirt.querySelector('.fl-liste');
  if (klappe) klappe.remove();
  for (const [waehler, befehl] of [['.fl-art', 'fontName'], ['.fl-groesse', 'fontSize']]) {
    const feld = wirt.querySelector(waehler);
    if (!feld) continue;
    try {
      const wert = String(document.queryCommandValue(befehl) || '')
        .replace(/^['"]|['"]$/g, '');
      const treffer = Array.from(feld.options).find(function (o) {
        return o.value === wert || o.value.toLowerCase() === wert.toLowerCase();
      });
      if (treffer) feld.value = treffer.value;
    } catch (f) { /* nicht jede Webansicht kann das */ }
  }
  for (const k of wirt.querySelectorAll('.fl-taste[data-stand]')) {
    const befehl = k.dataset.stand;
    if (befehl === 'pinsel') { k.classList.toggle('an', !!flPinsel); continue; }
    let an = false;
    try { an = document.queryCommandState(befehl); } catch (f) { /* egal */ }
    k.classList.toggle('an', !!an);
  }
}

/* Die schwebende Leiste drueben bekommt denselben Inhalt. Ihre eigenen
   Knoepfe bleiben stehen, nur versteckt: an ihnen haengen drueben die
   Schriftliste und die Farben, und von dort werden sie hier gespiegelt. */
function minileisteUmbauen() {
  const leiste = document.getElementById('minileiste');
  if (!leiste || leiste.querySelector('.formatleiste')) return;
  const alt = el('div', { id: 'minialt', hidden: true });
  while (leiste.firstChild) alt.append(leiste.firstChild);
  const neu = formatleisteBauen();
  leiste.append(alt, neu);
  document.addEventListener('selectionchange', function () {
    if (!leiste.hidden) formatleisteFrischen(neu);
  });
  // Beim Ziehen mit der Maus geht die Leiste erst beim Loslassen auf - und
  // dabei kommt kein selectionchange mehr. Deshalb am Zustand der Leiste
  // selbst haengen: wird sie sichtbar, wird sie auch aufgefrischt.
  if (window.MutationObserver) {
    new MutationObserver(function () {
      if (!leiste.hidden) formatleisteFrischen(neu);
    }).observe(leiste, { attributes: true, attributeFilter: ['hidden'] });
  }
}

/* Dasselbe oben im Band, Reiter "Start". Dort standen bisher vier Knoepfe
   und zwei Auswahlfelder - alles andere gab es nur, wenn man etwas
   markierte und die schwebende Leiste aufging. Wer auf Start geht, erwartet
   aber die ganze Leiste.

   Die alten Knoepfe bleiben stehen, nur versteckt: an #schriftart haengt die
   Schriftliste, die der Rechner erst nachlaedt, und die Favoriten-Tafel -
   von dort wird hierher gespiegelt. */
function bandleisteUmbauen() {
  const leiste = document.getElementById('werkzeuge');
  if (!leiste || leiste.querySelector('.formatleiste')) return;
  const alt = el('div', { id: 'bandalt', hidden: true });
  while (leiste.firstChild) alt.append(leiste.firstChild);
  const neu = formatleisteBauen({ band: true });
  leiste.append(alt, neu);
  document.addEventListener('selectionchange', function () {
    if (!leiste.hidden) formatleisteFrischen(neu);
  });
}

/* --------------------------------------------- Der Reiter "Einfügen"

   Dort standen drei Knoepfe: Anhang, Seite, Abschnitt. In OneNote ist das
   die Leiste mit Tabelle, Schreibbereich, Dateianlage, Bild, Link, Datum,
   Symbol und ein paar Aufnahmesachen.

   Gebaut ist, was hier wirklich geht. Nicht dabei sind Bildschirmausschnitt,
   Audio- und Videoaufnahme, Onlinevideo, Formel und Dateiausdruck: die
   brauchen entweder Rechte, die eine Webansicht nicht hat, oder einen
   ganzen Apparat (PDF rendern, Rechnen setzen) - und am Server ginge die
   Haelfte davon ohnehin nicht. Lieber keine Knoepfe als Knoepfe, die nur
   erklaeren, warum sie nichts tun.

   Die alten Knoepfe bleiben versteckt stehen und werden angeklickt: an
   ihnen haengt die Logik fuer Anhaenge, neue Seiten und Abschnitte, und
   die soll es nur einmal geben. */

// Zeilen und Spalten, die das Raster anbietet.
const FL_TABELLE_MAX = 8;
// Zeichen, die man im Text braucht und auf keiner Tastatur findet. Nur
// solche aus der Grundebene - ein Emoji faellt in Schriften aus, die es
// nicht haben, und dann steht ein Kaestchen im Text.
const FL_SYMBOLE = [
  '€', '£', '¥', '¢', '§', '©', '®', '™', '°', '±', '×', '÷',
  '≈', '≠', '≤', '≥', '∞', '√', '∑', '∏', '∫', 'µ', 'Ω', 'π',
  '→', '←', '↑', '↓', '↔', '⇒', '⇔', '•', '·', '…', '–', '—',
  '½', '¼', '¾', '‰', '†', '‡', '«', '»', '„', '“', '”', '‘',
  'α', 'β', 'γ', 'δ', 'λ', 'φ', 'ψ', 'ω', 'Δ', '☐', '☑', '★',
];

const FL_TABELLE = flBild('<rect x="1.5" y="2.5" width="13" height="11" rx="1"/>'
                          + '<path d="M1.5 6.5h13M1.5 10h13M6 2.5v11M10.5 2.5v11"/>');
const FL_TEXTFELD = flBild('<rect x="1.5" y="3.5" width="13" height="9" rx="1"/>'
                           + '<path d="M4.5 6.5h7M4.5 9.5h4"/>');
const FL_BILD = flBild('<rect x="1.5" y="3" width="13" height="10" rx="1"/>'
                       + '<circle cx="5.5" cy="6.5" r="1.2"/>'
                       + '<path d="M2 11.5 6 8l2.5 2.3L11 8l3 3.2"/>');
const FL_KETTE = flBild('<path d="M6.5 9.5 9.5 6.5"/>'
                        + '<path d="M7.5 4.5 9 3a2.8 2.8 0 0 1 4 4l-1.5 1.5"/>'
                        + '<path d="M8.5 11.5 7 13a2.8 2.8 0 0 1-4-4l1.5-1.5"/>');
const FL_KALENDER = flBild('<rect x="1.5" y="3" width="13" height="11" rx="1"/>'
                           + '<path d="M1.5 6.5h13M5 1.8v2.4M11 1.8v2.4"/>');

/* Eine Klappe mit freiem Inhalt. flGalerie macht Kacheln; hier braucht es
   ein Raster, ueber das man faehrt, und ein dichtes Gitter aus Zeichen. */
function flTafel(wirt, titel, inhalt, bauen) {
  const knopf = flTaste(inhalt + '<span class="fl-pfeil">▾</span>', titel, function (k) {
    const alte = wirt.querySelector('.fl-liste');
    if (alte) {
      alte.remove();
      if (alte.dataset.von === titel) return;      // derselbe Knopf: zu
    }
    const kasten = el('div', { className: 'fl-liste fl-galerie' });
    kasten.dataset.von = titel;
    kasten.append(el('p', { className: 'fl-galkopf', textContent: titel }));
    kasten.append(bauen(function () { kasten.remove(); }));
    wirt.append(kasten);
    flTafelStellen(kasten, k, wirt);
  });
  knopf.classList.add('fl-mitpfeil');
  return knopf;
}

/* Die Tafel darf ueber den Rand der Leiste hinausragen, nur nicht aus dem
   Fenster. */
function flTafelStellen(kasten, knopf, wirt) {
  const k = knopf.getBoundingClientRect();
  const w = wirt.getBoundingClientRect();
  const b = kasten.getBoundingClientRect();
  const links = Math.max(8, Math.min(k.left, window.innerWidth - b.width - 8));
  const oben = Math.max(8, Math.min(k.bottom + 2, window.innerHeight - b.height - 8));
  kasten.style.left = (links - w.left) + 'px';
  kasten.style.top = (oben - w.top) + 'px';
}

function tabelleEinfuegen(zeilen, spalten) {
  let html = '<table>';
  for (let z = 0; z < zeilen; z++) {
    html += '<tr>';
    // Ohne <br> ist die Zelle null Pixel hoch und man trifft sie nicht.
    for (let s = 0; s < spalten; s++) html += '<td><br></td>';
    html += '</tr>';
  }
  // Ein Absatz dahinter, sonst kommt man unter der Tabelle nicht mehr heraus.
  flBefehl('insertHTML', html + '</table><p><br></p>');
}

/* Das Raster zum Ziehen: 8 x 8, und darunter steht, was gerade gewaehlt
   waere. Ohne die Anzeige zaehlt man Kaestchen. */
function flTabellenraster(zu) {
  const gitter = el('div', { className: 'fl-tabraster' });
  const schild = el('p', { className: 'fl-galkopf fl-tabmass' });
  const felder = [];
  const malen = (z, s) => {
    schild.textContent = z + ' × ' + s;
    for (const f of felder) {
      f.classList.toggle('an', Number(f.dataset.z) <= z && Number(f.dataset.s) <= s);
    }
  };
  for (let z = 1; z <= FL_TABELLE_MAX; z++) {
    for (let s = 1; s <= FL_TABELLE_MAX; s++) {
      const f = el('button', { type: 'button', className: 'fl-rasterfeld' });
      f.dataset.z = String(z);
      f.dataset.s = String(s);
      f.addEventListener('mouseover', function () { malen(z, s); });
      f.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        zu();
        tabelleEinfuegen(z, s);
      });
      felder.push(f);
      gitter.append(f);
    }
  }
  malen(1, 1);
  return el('div', { className: 'fl-tabtafel' }, [gitter, schild]);
}

function flZeichentafel(zu) {
  const gitter = el('div', { className: 'fl-zeichengitter' });
  for (const z of FL_SYMBOLE) {
    const k = el('button', { type: 'button', className: 'fl-zeichenfeld', textContent: z });
    k.title = z;
    k.addEventListener('click', function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      zu();
      flBefehl('insertText', z);
    });
    gitter.append(k);
  }
  return gitter;
}

/* Datum und Uhrzeit in der Sprache des Rechners - nicht selbst
   zusammengesetzt, sonst steht in jedem Land dasselbe deutsche Format da. */
function datumText(art) {
  const d = new Date();
  const tag = d.toLocaleDateString();
  const zeit = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (art === 'datum') return tag;
  if (art === 'zeit') return zeit;
  return tag + ' ' + zeit;
}

/* Den versteckten Knopf von drueben anklicken - die Logik steht dort und
   soll es nur einmal geben. */
function altKlick(id) {
  const k = document.getElementById(id);
  if (k) k.click();
}

function dateiWaehlen(nurBilder) {
  const feld = document.getElementById('dateiwahl');
  if (!feld) return;
  // accept gilt nur fuer diesen einen Griff; danach darf wieder alles.
  feld.accept = nurBilder ? 'image/*' : '';
  feld.click();
}

function textfeldEinfuegen() {
  if (typeof kastenNeu !== 'function') return;
  const links = Math.round((buehne.scrollLeft + 80) / zoom / RASTER) * RASTER;
  const oben = Math.round((buehne.scrollTop + 80) / zoom / RASTER) * RASTER;
  kastenNeu(links, oben);
}

/* --------------------------------------------------------------- Formeln

   Eine Formel ist MathML. Das setzt die Webansicht von sich aus - ohne
   Bibliothek, ohne Schriftdateien, und am Server ohne ein fremdes Skript,
   das die CSP ohnehin nicht liesse.

   Getippt wird aber nicht MathML (das tut sich niemand an), sondern eine
   kleine Schreibweise: a/b ist ein Bruch, x^2 eine Potenz, x_1 ein Index,
   sqrt(x) eine Wurzel, pi ist π. Daraus macht der Parser unten das MathML.

   Er kennt absichtlich wenig, und was er nicht kennt, wird ein Bezeichner
   statt ein Fehler: beim Tippen steht eine Formel die meiste Zeit halb da,
   und eine halbe Formel ist besser als eine rote Meldung. */

const FORMEL_WORTE = {
  alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ε', zeta: 'ζ',
  eta: 'η', theta: 'θ', iota: 'ι', kappa: 'κ', lambda: 'λ', mu: 'µ',
  nu: 'ν', xi: 'ξ', rho: 'ρ', sigma: 'σ', tau: 'τ', phi: 'φ', chi: 'χ',
  psi: 'ψ', omega: 'ω', pi: 'π',
  Gamma: 'Γ', Delta: 'Δ', Theta: 'Θ', Lambda: 'Λ', Xi: 'Ξ', Pi: 'Π',
  Sigma: 'Σ', Phi: 'Φ', Psi: 'Ψ', Omega: 'Ω',
  inf: '∞', infty: '∞', deg: '°',
};
// Die grossen Zeichen: an ihnen stehen Grenzen darueber und darunter, nicht
// daneben. Genau das ist der Unterschied zwischen einer Summe und x hoch n.
const FORMEL_GROSS = { sum: '∑', prod: '∏', int: '∫', oint: '∮', lim: 'lim' };
// Was man tippt und was dastehen soll.
const FORMEL_ZEICHEN2 = { '<=': '≤', '>=': '≥', '!=': '≠', '+-': '±',
                          '->': '→', '=>': '⇒', '~~': '≈', '**': '∗' };
const FORMEL_ZEICHEN1 = { '*': '·', '-': '−' };

function formelSchutz(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* Steht da genau ein Element? Dann braucht es kein <mrow> darum. mfrac und
   msup wollen zwei Kinder, nicht zwei Gruppen - und eine Formel voller
   ueberfluessiger mrow liest sich spaeter niemand mehr durch. */
function formelEins(html) {
  if (!html || html.charAt(0) !== '<') return false;
  let tiefe = 0;
  const muster = /<(\/?)[a-z]+[^>]*>/g;
  let t = muster.exec(html);
  while (t) {
    tiefe += t[1] ? -1 : 1;
    if (tiefe === 0) return muster.lastIndex >= html.length;
    t = muster.exec(html);
  }
  return false;
}

function formelTeilen(text) {
  const raus = [];
  let i = 0;
  while (i < text.length) {
    const c = text.charAt(i);
    if (/\s/.test(c)) { i += 1; continue; }
    const zwei = text.slice(i, i + 2);
    if (FORMEL_ZEICHEN2[zwei]) {
      raus.push({ art: 'op', wert: FORMEL_ZEICHEN2[zwei] });
      i += 2;
      continue;
    }
    if (/[0-9]/.test(c)) {
      let j = i;
      while (j < text.length && /[0-9.,]/.test(text.charAt(j))) j += 1;
      raus.push({ art: 'zahl', wert: text.slice(i, j) });
      i = j;
      continue;
    }
    if (/[A-Za-z]/.test(c)) {
      let j = i;
      while (j < text.length && /[A-Za-z]/.test(text.charAt(j))) j += 1;
      raus.push({ art: 'wort', wert: text.slice(i, j) });
      i = j;
      continue;
    }
    raus.push({ art: 'op', wert: FORMEL_ZEICHEN1[c] || c, roh: c });
    i += 1;
  }
  return raus;
}

const FORMEL_STRICH = ['+', '−', '=', '<', '>', '≤', '≥', '≠', '±', '→', '⇒',
                       '≈', ',', ';', '∗'];

/* Vier Ebenen: Strich vor Punkt, Punkt vor Hoch/Tief, Hoch/Tief vor dem
   Einzelnen. Dieselbe Ordnung wie beim Rechnen - sonst wuerde a+b/2 zu
   (a+b)/2. */
function formelLesen(teile) {
  let i = 0;
  const schauen = () => teile[i] || null;
  const ist = (wert) => { const t = schauen(); return t && t.wert === wert; };
  const mi = (t) => `<mi>${formelSchutz(t)}</mi>`;
  const mn = (t) => `<mn>${formelSchutz(t)}</mn>`;
  const mo = (t) => `<mo>${formelSchutz(t)}</mo>`;
  const reihe = (t) => (formelEins(t) ? t : `<mrow>${t}</mrow>`);

  // Eine Klammer, die zu ist: ihr Inhalt. Eine, die noch offen steht: auch.
  function klammer() {
    const auf = schauen();
    i += 1;                                   // die Klammer selbst
    const inhalt = strich();
    const zu = { '(': ')', '[': ']', '{': '}' }[auf.wert];
    if (ist(zu)) i += 1;
    return { inhalt, auf: auf.wert, zu };
  }

  function basis() {
    const t = schauen();
    if (!t) return { html: '', gross: false };
    if (t.art === 'zahl') { i += 1; return { html: mn(t.wert), gross: false }; }
    if (t.art === 'wort') {
      i += 1;
      const w = t.wert;
      if (w === 'sqrt' && ist('(')) {
        return { html: `<msqrt>${reihe(klammer().inhalt)}</msqrt>`, gross: false };
      }
      if (w === 'root' && ist('(')) {
        const grad = klammer().inhalt;
        const was = ist('(') ? klammer().inhalt : hochtief().html;
        return { html: `<mroot>${reihe(was)}${reihe(grad)}</mroot>`, gross: false };
      }
      if (FORMEL_GROSS[w]) return { html: mo(FORMEL_GROSS[w]), gross: true };
      if (FORMEL_WORTE[w]) return { html: mi(FORMEL_WORTE[w]), gross: false };
      // Ein Wort vor einer Klammer ist eine Funktion: sin(x), f(x).
      if (ist('(')) {
        const k = klammer();
        return { html: mi(w) + mo('(') + reihe(k.inhalt) + mo(k.zu), gross: false };
      }
      return { html: mi(w), gross: false };
    }
    if (t.wert === '(' || t.wert === '[' || t.wert === '{') {
      const k = klammer();
      return { html: mo(k.auf) + reihe(k.inhalt) + mo(k.zu), gross: false };
    }
    if (t.wert === '−' || t.wert === '+') {       // Vorzeichen
      i += 1;
      return { html: mo(t.wert) + reihe(basis().html), gross: false };
    }
    i += 1;
    return { html: mo(t.wert), gross: false };
  }

  function hochtief() {
    let links = basis();
    for (;;) {
      if (ist('^')) {
        i += 1;
        const oben = basis().html;
        links = { html: links.gross ? `<mover>${reihe(links.html)}${reihe(oben)}</mover>`
                                    : `<msup>${reihe(links.html)}${reihe(oben)}</msup>`,
                  gross: false };
      } else if (ist('_')) {
        i += 1;
        const unten = basis().html;
        if (ist('^')) {
          i += 1;
          const oben = basis().html;
          links = { html: links.gross
            ? `<munderover>${reihe(links.html)}${reihe(unten)}${reihe(oben)}</munderover>`
            : `<msubsup>${reihe(links.html)}${reihe(unten)}${reihe(oben)}</msubsup>`,
                    gross: false };
        } else {
          links = { html: links.gross ? `<munder>${reihe(links.html)}${reihe(unten)}</munder>`
                                      : `<msub>${reihe(links.html)}${reihe(unten)}</msub>`,
                    gross: false };
        }
      } else {
        return links;
      }
    }
  }

  function punkt() {
    let text = hochtief().html;
    for (;;) {
      if (ist('/')) {
        i += 1;
        const unten = hochtief().html;
        text = `<mfrac>${reihe(text)}${reihe(unten)}</mfrac>`;
      } else if (ist('·') || ist('×')) {
        const z = schauen().wert;
        i += 1;
        text += mo(z) + hochtief().html;
      } else {
        return text;
      }
    }
  }

  function strich() {
    let text = punkt();
    for (;;) {
      const t = schauen();
      if (!t || FORMEL_STRICH.indexOf(t.wert) < 0) return text;
      i += 1;
      text += mo(t.wert) + punkt();
    }
  }

  let text = '';
  let wacht = 0;
  while (i < teile.length && wacht < 400) {
    const vorher = i;
    text += strich();
    // Eine schliessende Klammer ohne oeffnende haengt sonst fuer immer da.
    if (i === vorher) { text += mo(teile[i].wert); i += 1; }
    wacht += 1;
  }
  return text;
}

function formelMathML(text) {
  const inhalt = formelLesen(formelTeilen(String(text || '')));
  return `<math><mrow>${inhalt}</mrow></math>`;
}

/* Bausteine: was dazugeschrieben wird und wo der Cursor danach steht. Das
   Hütchen in der Mitte ist der Punkt, an dem man weiterschreibt - ohne das
   landet er hinter der Klammer und man klickt sich zurueck. */
const FORMEL_BAUSTEINE = [
  ['a/b', 'Bruch', '/'], ['x²', 'Hoch', '^2'], ['x₁', 'Tief', '_1'],
  ['√', 'Wurzel', 'sqrt(|)'], ['ⁿ√', 'n-te Wurzel', 'root(3)(|)'],
  ['( )', 'Klammer', '(|)'],
  ['∑', 'Summe', 'sum_(i=1)^n |'], ['∏', 'Produkt', 'prod_(i=1)^n |'],
  ['∫', 'Integral', 'int_a^b |'], ['lim', 'Grenzwert', 'lim_(x->0) |'],
  ['π', 'Pi', 'pi'], ['α', 'Alpha', 'alpha'], ['Δ', 'Delta', 'Delta'],
  ['∞', 'Unendlich', 'inf'], ['≤', 'Kleiner gleich', '<='],
  ['≥', 'Größer gleich', '>='], ['≠', 'Ungleich', '!='], ['±', 'Plusminus', '+-'],
];

let formelZiel = null;        // wohin die Formel geht

function formelFensterZeigen() {
  const fenster = $('#formelfenster');
  const feld = $('#f-eingabe');
  if (!fenster || !feld) return;
  // Den Kasten merken: der Klick ins Fenster kostet den Fokus, und ohne ihn
  // weiss insertHTML nachher nicht mehr, wohin.
  formelZiel = (document.activeElement && document.activeElement.closest('.kasten'))
    || letzterKasten;
  fenster.hidden = false;
  feld.value = '';
  formelVorschau();
  feld.focus();
}

function formelFensterZu() {
  const fenster = $('#formelfenster');
  if (fenster) fenster.hidden = true;
}

function formelVorschau() {
  const feld = $('#f-eingabe');
  const schau = $('#f-vorschau');
  if (!feld || !schau) return;
  // Kein fremder Text: das MathML entsteht hier und ist durchgehend
  // geschuetzt (formelSchutz).
  schau.innerHTML = feld.value.trim() ? formelMathML(feld.value) : '';
}

function formelEinsetzen(text) {
  const feld = $('#f-eingabe');
  if (!feld) return;
  const stelle = text.indexOf('|');
  const rein = stelle < 0 ? text : text.replace('|', '');
  const a = feld.selectionStart === null ? feld.value.length : feld.selectionStart;
  const b = feld.selectionEnd === null ? feld.value.length : feld.selectionEnd;
  feld.value = feld.value.slice(0, a) + rein + feld.value.slice(b);
  const neu = a + (stelle < 0 ? rein.length : stelle);
  try { feld.setSelectionRange(neu, neu); } catch (f) { /* nicht ueberall */ }
  feld.focus();
  formelVorschau();
}

function formelBauen() {
  const kasten = $('#f-bausteine');
  if (!kasten || kasten.children.length) return;
  for (const [zeichen, name, text] of FORMEL_BAUSTEINE) {
    const k = el('button', { type: 'button', className: 'f-baustein',
                             title: name, textContent: zeichen });
    k.addEventListener('click', function () { formelEinsetzen(text); });
    kasten.append(k);
  }
  $('#f-eingabe').addEventListener('input', formelVorschau);
  $('#f-eingabe').addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') { ev.preventDefault(); formelUebernehmen(); }
    if (ev.key === 'Escape') { ev.preventDefault(); formelFensterZu(); }
  });
  $('#f-ab').addEventListener('click', formelFensterZu);
  $('#f-ein').addEventListener('click', formelUebernehmen);
}

function formelUebernehmen() {
  const feld = $('#f-eingabe');
  if (!feld || !feld.value.trim()) { formelFensterZu(); return; }
  const mathml = formelMathML(feld.value);
  formelFensterZu();
  // Den Kasten von vorhin wieder nehmen - aufAuswahl() sucht sonst den
  // aktiven, und das ist gerade noch der Knopf im Fenster.
  if (formelZiel) {
    const text = formelZiel.querySelector('.text');
    if (text) text.focus();
    letzterKasten = formelZiel;
  }
  flBefehl('insertHTML', mathml);
}

/* Im Reiter Einfügen steht neben jedem Symbol das Wort - so wie in OneNote.
   Oben bei Start waere das eine Leiste ueber zwei Bildschirmbreiten; hier
   sind es neun Knoepfe, und "Schreibbereich einfuegen" errät niemand am
   Bildchen. */
function flWort(bild, wort) {
  return bild + '<span class="fl-wort">' + wort + '</span>';
}

function mitWort(knopf) {
  knopf.classList.add('fl-mitwort');
  return knopf;
}

function einfuegeleisteBauen() {
  const leiste = document.getElementById('einfuegen');
  if (!leiste || leiste.querySelector('.formatleiste')) return;
  const alt = el('div', { id: 'einfalt', hidden: true });
  while (leiste.firstChild) alt.append(leiste.firstChild);

  const wirt = el('div', { className: 'formatleiste fl-band' });
  const trenner = () => el('span', { className: 'fl-trenner' });
  const gruppen = [
    [mitWort(flTafel(wirt, 'Tabelle', flWort(FL_TABELLE, 'Tabelle'), flTabellenraster))],
    [mitWort(flTaste(flWort(FL_TEXTFELD, 'Schreibbereich einfügen'),
                     'Schreibbereich einfügen', textfeldEinfuegen))],
    [mitWort(flTaste(flWort(FL_KLEMME, 'Dateianlage'), 'Dateianlage',
                     function () { dateiWaehlen(false); })),
     mitWort(flTaste(flWort(FL_BILD, 'Bilder'), 'Bilder',
                     function () { dateiWaehlen(true); }))],
    [mitWort(flTaste(flWort(FL_KETTE, 'Link'), 'Link', function () {
      try { if (typeof linkSetzen === 'function') linkSetzen(); } catch (f) { /* egal */ }
    })),
     mitWort(flKlappe(wirt, 'Datum und Uhrzeit',
                      flWort(FL_KALENDER, 'Datum und Uhrzeit'),
                      [['datum', 'Datum', ''], ['zeit', 'Uhrzeit', ''],
                       ['beides', 'Datum und Uhrzeit', '']],
                      function (art) { flBefehl('insertText', datumText(art)); })),
     mitWort(flTafel(wirt, 'Symbol',
                     flWort('<span class="fl-sinn">Ω</span>', 'Symbol'),
                     flZeichentafel)),
     mitWort(flTaste(flWort('<span class="fl-sinn">∑</span>', 'Formel'), 'Formel',
                     formelFensterZeigen))],
    [mitWort(flTaste(flWort('＋', 'Seite'), 'Neue Seite',
                     function () { altKlick('neue-seite-band'); })),
     mitWort(flTaste(flWort('＋', 'Abschnitt'), 'Neuer Abschnitt',
                     function () { altKlick('neuer-abschnitt-band'); }))],
  ];
  const reihe = el('div', { className: 'fl-reihe' });
  gruppen.forEach(function (g, i) {
    if (i) reihe.append(trenner());
    for (const k of g) reihe.append(k);
  });
  wirt.append(reihe);
  wirt.addEventListener('mousedown', function (ev) {
    if (ev.target.tagName !== 'SELECT') ev.preventDefault();
  });
  leiste.append(alt, wirt);
}

function formatleistenBauen() {
  bandleisteUmbauen();
  einfuegeleisteBauen();
  formelBauen();
  minileisteUmbauen();
  flHakenAnschalten();
  flPinselAnschalten();
  // Die festen Regeln stehen in der Stildatei. Hier entsteht nur, was von den
  // Listenarten abhaengt: je Art ein @counter-style, und das laesst sich
  // nicht vorher hinschreiben.
  const stil = document.createElement('style');
  stil.textContent = listenRegeln();
  document.head.append(stil);
}

/* --------------------------------------- Rechtsklick: Formatieren gleich mit

   Drueben ist das Rechtsklick-Menue eine Liste mit vier Punkten, und zum
   Formatieren gibt es eine eigene Leiste, die bei einer Markierung aufgeht.
   In OneNote ist beides ein Menue: oben zwei Reihen Format, darunter die
   Punkte. Genau so sieht es hier jetzt aus.

   Gerechnet wird dabei nichts selbst. Geklickt wird auf die Funktionen
   drueben - aufAuswahl(), hervorheben(), hervorhebungWeg() -, und die
   Schriftliste und die Farben werden aus der vorhandenen Leiste gespiegelt.
   Zwei Stellen, die Fett setzen, waeren eine zu viel: eine davon ist eines
   Tages anders. */

let rmImText = false;
// Fuer die Fusszeile des Menues. Beides steht schon in Antworten, die der
// Stellvertreter ohnehin holt - hier nur gemerkt.
let meinName = '';
let meinBereich = '';

function rechtsmenueZu() {
  const menue = document.getElementById('rechtsmenue');
  if (menue) menue.hidden = true;
}

/* Beim Rechtsklick ist die schwebende Leiste zu viel: dieselben Knoepfe
   stehen eine Zeile tiefer noch einmal im Menue. Einmal zumachen genuegt
   nicht - drueben macht der Mausknopf sie weg und das Loslassen wieder hin,
   und das Loslassen kommt vor dem Menue. Deshalb bleibt sie zu, solange das
   Menue offen ist. Geht es zu, gelten wieder die Regeln von drueben: die
   naechste Markierung holt sie zurueck. */
function minileisteWeg() {
  const leiste = document.getElementById('minileiste');
  if (leiste) leiste.hidden = true;
}

function minileisteHueten() {
  const leiste = document.getElementById('minileiste');
  const menue = document.getElementById('rechtsmenue');
  if (!leiste || !menue || !window.MutationObserver) return;
  new MutationObserver(function () {
    if (!menue.hidden && !leiste.hidden) leiste.hidden = true;
  }).observe(leiste, { attributes: true, attributeFilter: ['hidden'] });
}

function rechtsmenueBauen() {
  const menue = document.getElementById('rechtsmenue');
  if (!menue || document.getElementById('rm-format')) return;

  // Die vier Punkte drueben bekommen ihr Zeichen davor - geaendert wird an
  // ihnen sonst nichts, sie haengen weiter an ihrem data-tun.
  for (const [was, zeichen] of [['ausschneiden', '✂'], ['kopieren', '⧉'],
                                ['einfuegen', '📋'], ['alles', '⬚']]) {
    const knopf = menue.querySelector(`button[data-tun="${was}"]`);
    if (!knopf || knopf.querySelector('.rm-zeichen')) continue;
    knopf.classList.add('rm-punkt');
    knopf.insertBefore(el('span', { className: 'rm-zeichen', textContent: zeichen }),
                       knopf.firstChild);
  }

  // Der Link gehoert zum Text, nicht zur Zwischenablage - deshalb unten,
  // hinter einem Strich. Mehr als http, https und mailto nimmt die Ablage
  // ohnehin nicht an; alles andere faellt beim Speichern wieder heraus.
  const link = el('button', { type: 'button', id: 'rm-link',
                              className: 'rm-punkt' }, [
    el('span', { className: 'rm-zeichen', textContent: '🔗' }),
    el('span', { textContent: 'Link …  (Strg+K)' }),
  ]);
  link.addEventListener('click', function (ev) {
    ev.preventDefault();
    ev.stopPropagation();
    rechtsmenueZu();
    linkSetzen();
  });
  menue.append(el('div', { className: 'rm-strich' }), link);

  // Wer wann - so weit wir es wirklich wissen. Die Seite merkt sich, wann
  // sie zuletzt geaendert wurde, aber nicht von wem; in einem Projekt waere
  // ein Name hier also geraten.
  menue.append(el('p', { id: 'rm-wer', className: 'rm-fuss' }));

  // Unten die Leiste - dieselbe wie die schwebende beim Markieren.
  const block = el('div', { id: 'rm-format' }, [formatleisteBauen()]);
  menue.append(block);

  // Ein Klick ins Menue darf die Markierung nicht kosten - sonst tut der
  // Knopf nichts. Bei Auswahlfeldern nicht: die brauchen den Fokus.
  menue.addEventListener('mousedown', function (ev) {
    if (ev.target.tagName !== 'SELECT') ev.preventDefault();
  });

  document.addEventListener('contextmenu', function (ev) {
    if (ev.target.closest && ev.target.closest('#einstellungen')) return;
    rmImText = !!(ev.target.closest && ev.target.closest('[contenteditable]'));
    minileisteWeg();
    // Nach dem Aufbau drueben: dort wird das Menue sichtbar gemacht und
    // gestellt. Was hier dazukommt, aendert die Hoehe - also noch einmal
    // nachruecken.
    setTimeout(function () { rechtsmenueFrischen(ev.clientX, ev.clientY); }, 0);
  });

  document.addEventListener('keydown', function (ev) {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k'
        && document.activeElement && document.activeElement.closest
        && document.activeElement.closest('[contenteditable]')) {
      ev.preventDefault();
      linkSetzen();
    }
  });

  minileisteHueten();

}

function linkSetzen() {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) {
    malsagen('Erst den Text markieren, der zum Link werden soll.');
    return;
  }
  const merk = sel.getRangeAt(0).cloneRange();
  const adresse = prompt('Adresse des Links:', 'https://');
  if (!adresse) return;
  if (!/^(https?:\/\/|mailto:)/i.test(adresse)) {
    malsagen('Nur http://, https:// und mailto: - anderes wird beim Speichern verworfen.');
    return;
  }
  // Der Dialog kostet die Markierung, also zurueckholen.
  sel.removeAllRanges();
  sel.addRange(merk);
  flBefehl('createLink', adresse);
}

function rechtsmenueFrischen(x, y) {
  const menue = document.getElementById('rechtsmenue');
  const block = document.getElementById('rm-format');
  if (!menue || !block || menue.hidden) return;
  // Auf der leeren Flaeche ist kein Text da, den die Leiste aendern koennte.
  // Trotzdem steht sie da: ein Menue, das mal lang und mal kurz ist, springt
  // einem unter der Maus weg. Sie ist dann blass und nimmt keine Klicks an -
  // so wie die vier Punkte drueben, die dort auch ausgegraut sind.
  block.hidden = false;
  block.classList.toggle('rm-aus', !rmImText);
  const link = document.getElementById('rm-link');
  if (link) {
    link.hidden = false;
    link.classList.toggle('rm-aus', !rmImText);
  }
  if (rmImText) formatleisteFrischen(block.querySelector('.formatleiste'));
  const wer = document.getElementById('rm-wer');
  if (wer) wer.textContent = rmFusszeile();
  const b = menue.getBoundingClientRect();
  menue.style.left = Math.max(4, Math.min(x, window.innerWidth - b.width - 8)) + 'px';
  menue.style.top = Math.max(4, Math.min(y, window.innerHeight - b.height - 8)) + 'px';
}


function rmFusszeile() {
  let zeit = null;
  try { zeit = offen && offen.mtime ? new Date(offen.mtime * 1000) : null; }
  catch (f) { zeit = null; }
  if (!zeit) return '';
  const wann = zeit.toLocaleString('de-DE', { day: '2-digit', month: '2-digit',
                                              year: 'numeric', hour: '2-digit',
                                              minute: '2-digit' });
  // Der Name nur dort, wo er stimmt: in den eigenen Notizen war es man
  // selbst. In einem Projekt schreiben mehrere, und wer zuletzt - das merkt
  // sich die Seite nicht.
  return (meinBereich ? 'Zuletzt geändert am ' : (meinName || 'Zuletzt geändert') + ' am ')
         + wann;
}


/* ================================================ Anhaenge zum Ansehen
 *
 * Kam aus der Serverfassung (web/shim.js), wo es zur Laufzeit eingesetzt
 * wurde - im Fenster gab es dort nur eine Kachel mit Bueroklammer. Beide
 * Fassungen teilen sich diese Datei, also sehen Modelle und Platinen jetzt
 * ueberall gleich aus.
 */

/* ------------------------------------------------- Platinen (Gerber-ZIP)

   Ein Gerber-Paket ist kein Modell, sondern ein Stapel Zeichnungen: je eine
   Datei fuer Kupfer oben, Kupfer unten, Bestueckungsdruck, Umriss, dazu die
   Bohrdatei. Uebereinandergelegt ergibt das die Platine - von oben und von
   unten.

   Kein gekipptes 3D und kein Foto: die Koerper der Bauteile stehen in
   keiner dieser Dateien. Die holt JLCPCB aus seiner eigenen Bibliothek
   ueber die Bauteilnummer. Hier steht nur, was wirklich in der Datei steht.

   Wieder ohne fremde Bibliothek: ein ZIP ist ein Verzeichnis am Ende der
   Datei, auspacken kann der Browser selbst (DecompressionStream), und
   Gerber ist eine Textsprache mit einer Handvoll Befehlen. */

const PCB_MAX_EINTRAEGE = 300;
const PCB_MAX_ENTPACKT = 40 * 1024 * 1024;   // je Datei
const PCB_MAX_STUECKE = 400000;              // Striche und Flaechen gesamt
const PCB_BOGEN = 24;                        // Ecken je Viertelkreis

/* --- ZIP ---------------------------------------------------------------- */

async function entpacken(roh) {
  if (!window.DecompressionStream) {
    throw new Error('dieser Browser kann kein ZIP auspacken');
  }
  const strom = new Blob([roh]).stream()
    .pipeThrough(new DecompressionStream('deflate-raw'));
  return new Uint8Array(await new Response(strom).arrayBuffer());
}

/* Gelesen wird ueber das Verzeichnis am Ende, nicht der Reihe nach durch
   die Datei: nur dort steht sicher, wie lang ein Eintrag gepackt ist. Im
   lokalen Kopf darf die Laenge fehlen (dann steht sie hinter den Daten). */
async function zipLesen(puffer) {
  const bytes = new Uint8Array(puffer);
  const sicht = new DataView(puffer);
  let e = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 66000); i--) {
    if (sicht.getUint32(i, true) === 0x06054b50) { e = i; break; }
  }
  if (e < 0) throw new Error('kein ZIP-Verzeichnis gefunden');
  const anzahl = sicht.getUint16(e + 10, true);
  let p = sicht.getUint32(e + 16, true);
  const aus = [];
  for (let i = 0; i < anzahl && i < PCB_MAX_EINTRAEGE; i++) {
    if (p + 46 > bytes.length || sicht.getUint32(p, true) !== 0x02014b50) break;
    const art = sicht.getUint16(p + 10, true);
    const klein = sicht.getUint32(p + 20, true);
    const gross = sicht.getUint32(p + 24, true);
    const nl = sicht.getUint16(p + 28, true);
    const xl = sicht.getUint16(p + 30, true);
    const kl = sicht.getUint16(p + 32, true);
    const wo = sicht.getUint32(p + 42, true);
    const name = new TextDecoder().decode(bytes.slice(p + 46, p + 46 + nl));
    p += 46 + nl + xl + kl;
    if (gross > PCB_MAX_ENTPACKT) continue;        // Packbombe
    if (name.endsWith('/') || wo + 30 > bytes.length) continue;
    if (sicht.getUint32(wo, true) !== 0x04034b50) continue;
    const anfang = wo + 30 + sicht.getUint16(wo + 26, true)
                 + sicht.getUint16(wo + 28, true);
    const roh = bytes.slice(anfang, anfang + klein);
    let daten = null;
    if (art === 0) daten = roh;
    else if (art === 8) daten = await entpacken(roh);
    else continue;                                  // andere Packart: selten
    aus.push({ name: name, daten: daten });
  }
  return aus;
}

/* --- Welche Datei ist welche Lage? --------------------------------------

   Die Endung sagt es meistens (GTL, GBL, GTO, GKO, DRL), aber nicht jedes
   Programm haelt sich daran - KiCad schreibt "F_Cu.gbr", EasyEDA
   "Gerber_TopLayer.GTL". Deshalb beides: erst die Endung, dann der Name. */
const PCB_LAGEN = [
  ['bohren', /\.(drl|xln|tap|nc)$/i, /drill|bohr|npth|\bpth\b/i],
  ['umriss', /\.(gko|gm1|gm2|gml)$/i, /outline|edge[._-]?cuts|boardoutline|profile|contour/i],
  ['kupfer-oben', /\.(gtl|cmp)$/i, /top[._-]?(layer|copper)|f[._-]cu|copper[._-]?top/i],
  ['kupfer-unten', /\.(gbl|sol)$/i, /bottom[._-]?(layer|copper)|b[._-]cu|copper[._-]?bottom/i],
  ['druck-oben', /\.(gto|plc)$/i, /top[._-]?(silk|overlay)|f[._-]silk/i],
  ['druck-unten', /\.(gbo|pls)$/i, /bottom[._-]?(silk|overlay)|b[._-]silk/i],
  ['lot-oben', /\.(gts|stc)$/i, /top[._-]?(solder)?mask|f[._-]mask/i],
  ['lot-unten', /\.(gbs|sts)$/i, /bottom[._-]?(solder)?mask|b[._-]mask/i],
];

function lageVon(name) {
  const kurz = String(name || '').replace(/^.*\//, '');
  for (const [lage, endung] of PCB_LAGEN) if (endung.test(kurz)) return lage;
  for (const [lage, , wort] of PCB_LAGEN) if (wort.test(kurz)) return lage;
  // Eine .txt ohne sprechenden Namen kann die Bohrdatei sein - das sagt
  // ihr Inhalt, nicht ihr Name. Entschieden wird das beim Lesen.
  if (/\.(txt|gbr|ger|art|pho)$/i.test(kurz)) return 'unklar';
  return null;
}

/* --- Gerber lesen -------------------------------------------------------

   Gerber ist eine Folge von Befehlen, jeder mit * abgeschlossen; was
   zwischen zwei % steht, sind Einstellungen (Format, Einheit, Blenden).
   Gezeichnet wird mit einer "Blende" (aperture): D01 zieht damit einen
   Strich, D03 drueckt sie einmal ab, D02 setzt nur den Stift um.

   Herauskommt eine flache Liste aus Strichen, Abdruecken und Flaechen, alle
   in Millimetern. Was davon spaeter welche Farbe bekommt, entscheidet die
   Lage, nicht diese Funktion. */
function gerberLesen(text) {
  const blenden = {};
  const stuecke = [];
  let nullen = 'L';
  let nach = 6;
  let ganz = 3;
  let maß = 1;                  // 1 = mm, 25.4 = Zoll
  let blende = null;
  let modus = 1;                // G01 gerade, G02/G03 Bogen
  let mehrquadrant = true;      // G75
  let loeschen = false;         // LPC: wegnehmen statt auftragen
  let x = 0;
  let y = 0;
  let flaeche = null;           // laeuft gerade ein G36-Bereich?
  let zug = null;

  function koord(s) {
    const minus = s.charAt(0) === '-';
    let ziffern = s.replace(/^[+-]/, '');
    // Fehlende Nullen stehen vorn (L) oder hinten (T). Steht es hinten,
    // ist "1" nicht 0,000001 sondern 1,0 - der haeufigste Lesefehler.
    if (nullen === 'T') ziffern = ziffern.padEnd(ganz + nach, '0');
    const wert = parseInt(ziffern, 10) / Math.pow(10, nach);
    return (minus ? -wert : wert) * maß;
  }

  function parameter(teil) {
    let m = /^FS([LT])[AI]X(\d)(\d)Y\d\d/.exec(teil);
    if (m) { nullen = m[1]; ganz = +m[2]; nach = +m[3]; return; }
    if (/^MOIN/.test(teil)) { maß = 25.4; return; }
    if (/^MOMM/.test(teil)) { maß = 1; return; }
    if (/^LPC/.test(teil)) { loeschen = true; return; }
    if (/^LPD/.test(teil)) { loeschen = false; return; }
    m = /^ADD(\d+)([A-Za-z_$][\w$.-]*)(?:,(.*))?$/.exec(teil);
    if (m) {
      const werte = (m[3] || '').split('X').map(parseFloat)
        .filter(function (w) { return w === w; });
      blenden[+m[1]] = { form: m[2], werte: werte.map(function (w) { return w * maß; }) };
    }
    // AM (eigene Blendenformen) und der Rest bleiben aussen vor: fuer das
    // Bild genuegt die Groesse, und die steht in der ersten Zahl.
  }

  function groesse(b) {
    if (!b) return 0.15 * maß;
    if (b.form === 'R' || b.form === 'O') {
      return Math.min(b.werte[0] || 0, b.werte[1] || b.werte[0] || 0) || 0.15;
    }
    return b.werte[0] || 0.15;
  }

  function bogen(x0, y0, x1, y1, i, j, uhrzeiger) {
    const mx = x0 + i;
    const my = y0 + j;
    const r = Math.hypot(x0 - mx, y0 - my);
    let a0 = Math.atan2(y0 - my, x0 - mx);
    let a1 = Math.atan2(y1 - my, x1 - mx);
    let d = a1 - a0;
    if (uhrzeiger) { while (d > 0) d -= 2 * Math.PI; } else { while (d < 0) d += 2 * Math.PI; }
    // Voller Kreis: Anfang gleich Ende. Dann ist die Drehung nicht null,
    // sondern einmal herum - sonst faellt der Kreis weg.
    if (Math.abs(d) < 1e-9 && Math.hypot(x1 - x0, y1 - y0) < 1e-9) {
      d = uhrzeiger ? -2 * Math.PI : 2 * Math.PI;
    }
    const n = Math.max(2, Math.ceil(Math.abs(d) / (Math.PI / 2) * PCB_BOGEN));
    const punkte = [];
    for (let k = 1; k <= n; k++) {
      const a = a0 + d * (k / n);
      punkte.push([mx + r * Math.cos(a), my + r * Math.sin(a)]);
    }
    return punkte;
  }

  function hin(zx, zy, i, j) {
    if (modus === 1) return [[zx, zy]];
    return bogen(x, y, zx, zy, i, j, modus === 2);
  }

  function kommando(b) {
    if (/^G0*4/.test(b) || /^M0/.test(b)) return;     // Kommentar, Ende
    if (/^G0*36/.test(b)) { flaeche = []; return; }
    if (/^G0*37/.test(b)) {
      if (flaeche && flaeche.length > 2) {
        stuecke.push({ t: 'flaeche', punkte: flaeche, weg: loeschen });
      }
      flaeche = null;
      return;
    }
    let m = /^G0*([0-9]+)/.exec(b);
    if (m) {
      const n = +m[1];
      if (n === 1 || n === 2 || n === 3) modus = n;
      else if (n === 74) mehrquadrant = false;
      else if (n === 75) mehrquadrant = true;
    }
    m = /D0*(\d+)\s*$/.exec(b);
    let tun = 0;
    if (m) {
      const d = +m[1];
      if (d >= 10) { blende = d; if (!/[XY]/.test(b)) return; } else tun = d;
    }
    const nx = /X([+-]?\d+)/.exec(b);
    const ny = /Y([+-]?\d+)/.exec(b);
    const ni = /I([+-]?\d+)/.exec(b);
    const nj = /J([+-]?\d+)/.exec(b);
    if (!nx && !ny && !tun) return;
    const zx = nx ? koord(nx[1]) : x;
    const zy = ny ? koord(ny[1]) : y;
    const i = ni ? koord(ni[1]) : 0;
    const j = nj ? koord(nj[1]) : 0;
    if (stuecke.length > PCB_MAX_STUECKE) return;
    if (tun === 1) {
      const weg = hin(zx, zy, i, j);
      if (flaeche) {
        if (!flaeche.length) flaeche.push([x, y]);
        for (const p of weg) flaeche.push(p);
      } else {
        if (!zug || zug.weg !== loeschen || zug.breite !== groesse(blenden[blende])
            || zug.punkte[zug.punkte.length - 1][0] !== x
            || zug.punkte[zug.punkte.length - 1][1] !== y) {
          zug = { t: 'zug', punkte: [[x, y]], breite: groesse(blenden[blende]),
                  eckig: (blenden[blende] || {}).form === 'R', weg: loeschen };
          stuecke.push(zug);
        }
        for (const p of weg) zug.punkte.push(p);
      }
    } else if (tun === 3) {
      stuecke.push({ t: 'abdruck', x: zx, y: zy, blende: blenden[blende] || null,
                     weg: loeschen });
      zug = null;
    } else {
      zug = null;                       // D02: der Stift setzt neu an
      if (flaeche && flaeche.length > 2) {
        stuecke.push({ t: 'flaeche', punkte: flaeche, weg: loeschen });
        flaeche = [];
      }
    }
    x = zx;
    y = zy;
  }

  let p = 0;
  while (p < text.length) {
    // Zeilenumbrueche zuerst weg: steht einer vor dem %, sucht die
    // Befehlsseite sonst das naechste * - und das steht im Parameterblock.
    if (/\s/.test(text.charAt(p))) { p++; continue; }
    if (text.charAt(p) === '%') {
      const ende = text.indexOf('%', p + 1);
      if (ende < 0) break;
      for (const teil of text.slice(p + 1, ende).split('*')) {
        if (teil.trim()) parameter(teil.trim());
      }
      p = ende + 1;
    } else {
      const ende = text.indexOf('*', p);
      if (ende < 0) break;
      const b = text.slice(p, ende).trim();
      if (b) kommando(b);
      p = ende + 1;
    }
  }
  return stuecke;
}

/* --- Bohrdatei (Excellon) ----------------------------------------------

   Viel aelter und viel schlampiger als Gerber: die Einheit steht irgendwo
   im Kopf, und ob die Koordinate "3175" nun 3,175 mm oder 31,75 mm heisst,
   steht oft gar nicht da. Steht ein Punkt drin, ist alles klar - sonst
   gilt die uebliche Annahme (metrisch drei Nachkommastellen). */
function bohrLesen(text) {
  const werkzeuge = {};
  const loecher = [];
  let maß = 1;
  let nach = 3;
  let jetzt = 0;

  function zahl(s) {
    if (s.indexOf('.') >= 0) return parseFloat(s) * maß;
    const minus = s.charAt(0) === '-';
    const ziffern = s.replace(/^[+-]/, '');
    const wert = parseInt(ziffern, 10) / Math.pow(10, nach);
    return (minus ? -wert : wert) * maß;
  }

  for (const zeile of String(text).split(/\r?\n/)) {
    const z = zeile.trim();
    if (!z || z.charAt(0) === ';') continue;
    if (/^(METRIC|M71)/.test(z)) { maß = 1; nach = 3; continue; }
    if (/^(INCH|M72)/.test(z)) { maß = 25.4; nach = 4; continue; }
    let m = /^T(\d+)[^C]*C\s*([\d.]+)/.exec(z);
    if (m) { werkzeuge[+m[1]] = parseFloat(m[2]) * maß; continue; }
    m = /^T(\d+)\s*$/.exec(z);
    if (m) { jetzt = +m[1]; continue; }
    m = /X([+-]?[\d.]+)\s*Y([+-]?[\d.]+)/.exec(z);
    if (m) {
      loecher.push({ x: zahl(m[1]), y: zahl(m[2]), d: werkzeuge[jetzt] || 0.3 });
    }
  }
  return loecher;
}

function istBohrdatei(text) {
  return /^\s*(M48|;.*(drill|Excellon))/i.test(text) || /^T\d+C[\d.]/m.test(text);
}

/* --- Aus den Dateien eine Platine machen -------------------------------- */

const PCB_SEITEN = {
  oben: { kupfer: 'kupfer-oben', druck: 'druck-oben' },
  unten: { kupfer: 'kupfer-unten', druck: 'druck-unten' },
};

function textVon(daten) {
  return new TextDecoder('utf-8', { fatal: false }).decode(daten);
}

function platinePacken(dateien) {
  const lagen = {};
  const loecher = [];
  const namen = [];
  for (const d of dateien) {
    const lage = lageVon(d.name);
    if (!lage) continue;
    const text = textVon(d.daten);
    if (lage === 'bohren' || (lage === 'unklar' && istBohrdatei(text))) {
      for (const l of bohrLesen(text)) loecher.push(l);
      namen.push(d.name);
      continue;
    }
    if (lage === 'unklar') continue;
    const stuecke = gerberLesen(text);
    if (!stuecke.length) continue;
    lagen[lage] = (lagen[lage] || []).concat(stuecke);
    namen.push(d.name);
  }
  return { lagen: lagen, loecher: loecher, namen: namen,
           umriss: umrissNaehen(lagen['umriss'] || []) };
}

/* Der Umriss kommt als lose Striche, nicht als Flaeche: vier Linien, oder
   bei abgerundeten Ecken ein Dutzend Stuecke. Zum Fuellen muessen sie erst
   wieder zu einem Ring werden - also Ende an Anfang naehen. */
function umrissNaehen(stuecke) {
  const nah = function (a, b) {
    return Math.abs(a[0] - b[0]) < 0.02 && Math.abs(a[1] - b[1]) < 0.02;
  };
  const offen = [];
  for (const s of stuecke) {
    if (s.t === 'flaeche') offen.push(s.punkte.slice());
    else if (s.t === 'zug' && s.punkte.length > 1) offen.push(s.punkte.slice());
  }
  const ringe = [];
  while (offen.length) {
    let kette = offen.pop();
    let weiter = true;
    while (weiter) {
      weiter = false;
      for (let i = 0; i < offen.length; i++) {
        const k = offen[i];
        const vorn = kette[0];
        const hinten = kette[kette.length - 1];
        if (nah(hinten, k[0])) kette = kette.concat(k.slice(1));
        else if (nah(hinten, k[k.length - 1])) kette = kette.concat(k.slice().reverse().slice(1));
        else if (nah(vorn, k[k.length - 1])) kette = k.slice(0, -1).concat(kette);
        else if (nah(vorn, k[0])) kette = k.slice().reverse().slice(0, -1).concat(kette);
        else continue;
        offen.splice(i, 1);
        weiter = true;
        break;
      }
    }
    if (kette.length > 2) ringe.push(kette);
  }
  return ringe;
}

function pcbRahmen(platine) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  const nimm = function (x, y) {
    if (x < x0) x0 = x; if (x > x1) x1 = x;
    if (y < y0) y0 = y; if (y > y1) y1 = y;
  };
  for (const ring of platine.umriss) for (const p of ring) nimm(p[0], p[1]);
  if (!platine.umriss.length) {
    for (const lage of Object.keys(platine.lagen)) {
      for (const s of platine.lagen[lage]) {
        if (s.t === 'abdruck') nimm(s.x, s.y);
        else for (const p of s.punkte) nimm(p[0], p[1]);
      }
    }
    for (const l of platine.loecher) nimm(l.x, l.y);
  }
  if (!(x1 > x0)) return null;
  return { x0: x0, y0: y0, x1: x1, y1: y1, breit: x1 - x0, hoch: y1 - y0 };
}

/* --- Malen --------------------------------------------------------------

   Alles in Millimetern: die Umrechnung macht die Matrix der Zeichenflaeche.
   Dadurch stimmt auch die Strichbreite ohne Nachrechnen, und die Unterseite
   ist nur ein gespiegeltes Vorzeichen. */

function pcbPfad(ctx, punkte, zu) {
  ctx.beginPath();
  ctx.moveTo(punkte[0][0], punkte[0][1]);
  for (let i = 1; i < punkte.length; i++) ctx.lineTo(punkte[i][0], punkte[i][1]);
  if (zu) ctx.closePath();
}

function abdruckMalen(ctx, s) {
  const b = s.blende || { form: 'C', werte: [0.2] };
  const w = b.werte || [];
  if (b.form === 'R' || b.form === 'O') {
    const bx = w[0] || 0.2;
    const by = w[1] || bx;
    if (b.form === 'O' && ctx.roundRect) {
      ctx.beginPath();
      ctx.roundRect(s.x - bx / 2, s.y - by / 2, bx, by, Math.min(bx, by) / 2);
      ctx.fill();
    } else {
      ctx.fillRect(s.x - bx / 2, s.y - by / 2, bx, by);
    }
    return;
  }
  if (b.form === 'P' && w.length >= 2) {
    const r = (w[0] || 0.2) / 2;
    const ecken = Math.max(3, Math.round(w[1] || 6));
    const dreh = (w[2] || 0) * Math.PI / 180;
    ctx.beginPath();
    for (let i = 0; i < ecken; i++) {
      const a = dreh + i * 2 * Math.PI / ecken;
      const px = s.x + r * Math.cos(a);
      const py = s.y + r * Math.sin(a);
      if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
    }
    ctx.closePath();
    ctx.fill();
    return;
  }
  ctx.beginPath();
  ctx.arc(s.x, s.y, (w[0] || 0.2) / 2, 0, 2 * Math.PI);
  ctx.fill();
}

function lageMalen(ctx, stuecke, farbe) {
  if (!stuecke || !stuecke.length) return;
  ctx.save();
  ctx.fillStyle = farbe;
  ctx.strokeStyle = farbe;
  ctx.lineJoin = 'round';
  for (const s of stuecke) {
    // LPC heisst: hier wird wieder weggenommen, was schon da war - so
    // entstehen Freistellungen im Kupfer. Mit "destination-out" macht das
    // die Zeichenflaeche selbst.
    ctx.globalCompositeOperation = s.weg ? 'destination-out' : 'source-over';
    if (s.t === 'zug') {
      ctx.lineWidth = Math.max(s.breite, 0.02);
      ctx.lineCap = s.eckig ? 'butt' : 'round';
      pcbPfad(ctx, s.punkte, false);
      ctx.stroke();
    } else if (s.t === 'flaeche') {
      pcbPfad(ctx, s.punkte, true);
      ctx.fill();
    } else {
      abdruckMalen(ctx, s);
    }
  }
  ctx.restore();
}

const PCB_FARBEN = {
  traeger: '#0d5c38', traegerRand: '#0a3f27',
  kupfer: '#d8a93c', druck: '#f2f4f5', loch: '#0b0c0d',
};

function platineZeichnen(z) {
  const c = z.bild;
  if (!c || !z.platine) return;
  const kasten = z.wo.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const br = Math.max(1, Math.round(kasten.width * dpr));
  const ho = Math.max(1, Math.round(kasten.height * dpr));
  if (c.width !== br || c.height !== ho) { c.width = br; c.height = ho; }
  const ctx = c.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, br, ho);
  const r = z.rahmen;
  if (!r) return;
  const rand = 1.0;                                  // mm Luft ringsum
  const k = Math.min(br / (r.breit + 2 * rand), ho / (r.hoch + 2 * rand)) * z.zoom;
  const mx = (r.x0 + r.x1) / 2;
  const my = (r.y0 + r.y1) / 2;
  const spiegel = z.seite === 'unten' ? -1 : 1;
  // y zeigt in Gerber nach oben, auf der Zeichenflaeche nach unten.
  ctx.setTransform(k * spiegel, 0, 0, -k, br / 2 + z.ox, ho / 2 + z.oy);
  ctx.translate(-mx, -my);

  // Der Traeger: die Ringe des Umrisses als ein Pfad, mit Evenodd - dann
  // bleiben Ausschnitte innen auch Ausschnitte.
  ctx.save();
  if (z.platine.umriss.length) {
    ctx.beginPath();
    for (const ring of z.platine.umriss) {
      ctx.moveTo(ring[0][0], ring[0][1]);
      for (let i = 1; i < ring.length; i++) ctx.lineTo(ring[i][0], ring[i][1]);
      ctx.closePath();
    }
    ctx.fillStyle = PCB_FARBEN.traeger;
    ctx.fill('evenodd');
    ctx.lineWidth = 0.15;
    ctx.strokeStyle = PCB_FARBEN.traegerRand;
    ctx.stroke();
    ctx.clip('evenodd');
  } else {
    ctx.fillStyle = PCB_FARBEN.traeger;
    ctx.fillRect(r.x0, r.y0, r.breit, r.hoch);
  }

  const seite = PCB_SEITEN[z.seite] || PCB_SEITEN.oben;
  lageMalen(ctx, z.platine.lagen[seite.kupfer], PCB_FARBEN.kupfer);
  // Die Bohrungen sitzen durch die ganze Platine - also nach dem Kupfer
  // und vor dem Aufdruck.
  ctx.fillStyle = PCB_FARBEN.loch;
  for (const l of z.platine.loecher) {
    ctx.beginPath();
    ctx.arc(l.x, l.y, Math.max(l.d, 0.05) / 2, 0, 2 * Math.PI);
    ctx.fill();
  }
  lageMalen(ctx, z.platine.lagen[seite.druck], PCB_FARBEN.druck);
  ctx.restore();
}

/* --- Der Kasten ---------------------------------------------------------- */

// Das Fenster ist so breit wie der Kasten - also so breit wie die Zeile
// darunter. Nur die Hoehe richtet sich nach der Platine: ein langes schmales
// Brett bekommt ein hohes Fenster, ein flaches ein flaches, und ein festes
// 4:3 wuerde beiden nicht passen.
function pcbFenster(r, platz) {
  const form = r.breit / Math.max(r.hoch, 0.01);
  const hoch = Math.max(90, Math.min(340, platz / Math.max(form, 0.01)));
  return { breit: platz, hoch: Math.round(hoch) };
}

async function platineStarten(z) {
  if (z.laeuft) return;
  z.laeuft = true;
  let puffer;
  try {
    puffer = await modellHolen(z.datei);
  } catch (f) {
    kachelBehalten(z, 'Platine ließ sich nicht holen: ' + f.message);
    return;
  }
  let dateien;
  try {
    dateien = await zipLesen(puffer);
  } catch (f) {
    kachelBehalten(z, 'ZIP ließ sich nicht öffnen: ' + f.message
                      + ' (' + puffer.byteLength + ' Byte)');
    return;
  }
  let platine;
  try {
    platine = platinePacken(dateien);
  } catch (f) {
    kachelBehalten(z, 'Gerber ließ sich nicht lesen: ' + f.message);
    return;
  }
  if (!platine.namen.length) {
    // Die meisten ZIPs sind einfach ZIPs. Darunter eine rote Zeile zu
    // setzen, waere Laerm: niemand hat hier eine Platine erwartet. Anders,
    // wenn Gerber-Dateien drin sind und trotzdem nichts dabei herauskommt -
    // dann will man wissen, warum.
    const gerber = dateien.filter(function (d) {
      const l = lageVon(d.name);
      return l && l !== 'unklar';
    });
    if (!gerber.length) { kachelBehalten(z, ''); return; }
    const liste = gerber.slice(0, 4).map(function (d) { return d.name; }).join(', ');
    kachelBehalten(z, 'Gerber gefunden, aber keine Linie darin (' + liste + ')');
    return;
  }
  z.platine = platine;
  z.rahmen = pcbRahmen(platine);
  if (!z.rahmen) {
    kachelBehalten(z, 'Die Gerber-Dateien sind leer - keine einzige Linie darin.');
    return;
  }
  const platz = (z.wo.parentElement && z.wo.parentElement.clientWidth)
                || z.wo.clientWidth || 320;
  const f = pcbFenster(z.rahmen, platz);
  z.wo.style.width = f.breit + 'px';
  z.wo.style.height = f.hoch + 'px';

  const zaehler = z.kasten.querySelector('.dzahl');
  if (zaehler) {
    zaehler.textContent = z.rahmen.breit.toFixed(1).replace('.', ',') + ' × '
      + z.rahmen.hoch.toFixed(1).replace('.', ',') + ' mm · '
      + platine.loecher.length + ' Bohrungen';
  }
  if (!platine.lagen['kupfer-unten'] && !platine.lagen['druck-unten']) {
    const knopf = z.wo.querySelector('.pcbseite');
    if (knopf) knopf.hidden = true;        // einseitig: nichts zum Wenden
  }
  platineZeichnen(z);
}

function platineGriffe(z) {
  const c = z.bild;
  let zieht = false;
  let zx = 0;
  let zy = 0;
  c.addEventListener('pointerdown', function (ev) {
    zieht = true;
    zx = ev.clientX;
    zy = ev.clientY;
    c.setPointerCapture(ev.pointerId);
    ev.stopPropagation();           // nicht den Kasten mitziehen
    ev.preventDefault();
  });
  c.addEventListener('pointermove', function (ev) {
    if (!zieht) return;
    const dpr = window.devicePixelRatio || 1;
    z.ox += (ev.clientX - zx) * dpr;
    z.oy += (ev.clientY - zy) * dpr;
    zx = ev.clientX;
    zy = ev.clientY;
    platineZeichnen(z);
  });
  const los = function (ev) {
    zieht = false;
    try { c.releasePointerCapture(ev.pointerId); } catch (f) { /* egal */ }
  };
  c.addEventListener('pointerup', los);
  c.addEventListener('pointercancel', los);
  c.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    ev.stopPropagation();
    z.zoom = Math.max(0.3, Math.min(40, z.zoom * (ev.deltaY > 0 ? 0.88 : 1.14)));
    platineZeichnen(z);
  }, { passive: false });
  c.addEventListener('dblclick', function (ev) {
    ev.stopPropagation();
    z.zoom = 1;
    z.ox = 0;
    z.oy = 0;
    platineZeichnen(z);
  });
}

function platineKasten(kasten, datei) {
  kasten.dataset.modell = 'ja';
  kasten.classList.add('kasten-pcb');
  const bild = el('canvas', {});
  const lade = el('p', { className: 'lade', textContent: 'Platine wird gelesen …' });
  const seite = el('button', { type: 'button', className: 'pcbseite',
                               title: 'Auf die andere Seite sehen',
                               textContent: 'Unterseite' });
  const wo = el('div', { className: 'modell pcb' }, [bild, lade, seite]);
  const kachel = kasten.querySelector('.datei');
  if (kachel) {
    kachel.before(wo);
    kachel.append(el('span', { className: 'dzahl', textContent: '…' }));
  } else {
    kasten.append(wo);
  }

  const z = { kasten: kasten, wo: wo, bild: bild, datei: datei, platine: null,
              rahmen: null, seite: 'oben', zoom: 1, ox: 0, oy: 0, laeuft: false };
  seite.addEventListener('click', function (ev) {
    ev.preventDefault();
    ev.stopPropagation();
    z.seite = z.seite === 'oben' ? 'unten' : 'oben';
    seite.textContent = z.seite === 'oben' ? 'Unterseite' : 'Oberseite';
    platineZeichnen(z);
  });
  platineGriffe(z);

  const sehen = new IntersectionObserver(function (treffer) {
    for (const t of treffer) {
      if (!t.isIntersecting) continue;
      sehen.disconnect();
      platineStarten(z).then(function () { lade.remove(); },
                             function (f) {
                               lade.remove();
                               kachelBehalten(z, 'Platine: ' + f.message);
                             });
    }
  }, { rootMargin: '200px' });
  sehen.observe(wo);
  if (window.ResizeObserver) {
    new ResizeObserver(function () { platineZeichnen(z); }).observe(wo);
  }
}

/* ----------------------------------------------------------- 3D-Anhaenge

   Eine .stl kam bisher als 📎-Kachel in die Notiz: man sah den Namen und
   musste sie herunterladen, um zu wissen, was drin ist. Jetzt steht das
   Modell da und laesst sich drehen.

   Bewusst kein neuer Elementtyp: der Kasten bleibt ein Datei-Kasten, nur
   sein Inhalt wird ausgetauscht. Am Format der Notizen aendert sich damit
   nichts - dieselbe Seite zeigt im Fenster-Programm weiter die Kachel, und
   eine alte Fassung stolpert nicht ueber etwas Unbekanntes.

   Und bewusst ohne fremde Bibliothek: STL ist Kopf, Anzahl, 50 Byte je
   Dreieck, OBJ sind Zeilen mit v und f. Fuer "graues Modell drehen" braucht
   es Matrizen, ein Licht von oben und sonst nichts. */

const MODELL_ARTEN = ['stl', 'obj', 'fbx'];
// Mehr als eine Handvoll 3D-Flaechen gibt der Browser pro Seite nicht her.
// Also leben nur die zuletzt benutzten; die anderen stehen als Standbild da
// und wachen beim Klick wieder auf.
const MODELL_LEBENDIG = [];
const MODELL_MAX_LEBENDIG = 4;
// Darueber bleibt die Kachel stehen, statt den Browser minutenlang
// einzulesen.
const MODELL_MAX_DREIECKE = 3000000;
// So weit weg, dass die Kugel um das Teil (Radius 1 nach dem Skalieren) in
// jeder Drehung ins Bild passt: 1 / sin(halber Oeffnungswinkel), plus Luft.
const MODELL_WEG = 3.6;
const MODELL_WINKEL = 0.6;        // Oeffnungswinkel der Kamera, im Bogenmass
const MODELL_SCHIEB_MAX = 4;      // so weit darf der Drehpunkt hoechstens weg

function modellArt(name) {
  const m = /\.([a-z0-9]+)$/i.exec(name || '');
  const art = m ? m[1].toLowerCase() : '';
  return MODELL_ARTEN.indexOf(art) >= 0 ? art : null;
}

/* Die Bytes kommen ueber dieselbe Stelle wie der Download: /anhang prueft
   die Anmeldung und liefert rohe Bytes. */
/* Die Bytes eines Anhangs. Im Fenster gibt es keine Adresse, unter der die
   Datei laege - sie kommt ueber die Bruecke, und gezeichnet wird daraus
   hier. Als HTML wird davon nie etwas eingesetzt. */
async function modellHolen(datei) {
  const b = await bruecke();
  const r = await b.anhang_roh(offen.notizbuch, offen.abschnitt, offen.name, datei);
  if (!r || r.fehler) throw new Error((r && r.fehler) || 'Anhang nicht lesbar');
  const roh = atob(r.daten);
  const feld = new Uint8Array(roh.length);
  for (let i = 0; i < roh.length; i++) feld[i] = roh.charCodeAt(i);
  return feld.buffer;
}

/* --- Einlesen ----------------------------------------------------------- */

function stlLesen(puffer) {
  /* Binaer oder Text? Nicht nach dem Wort "solid" am Anfang - binaere
     Dateien aus manchen Programmen fangen auch damit an. Zuerst die Laenge:
     passt sie aufs Byte, ist die Sache klar. Tut sie das nicht, hat eine
     binaere Datei hinten etwas angehaengt oder ihr Kopf zaehlt falsch;
     dann entscheidet, ob im Anfang ueberhaupt STL-Text steht. */
  if (puffer.byteLength >= 84) {
    const sicht = new DataView(puffer);
    const zahl = sicht.getUint32(80, true);
    if (84 + zahl * 50 === puffer.byteLength) return stlBinaer(sicht, zahl);
    const probe = new TextDecoder('utf-8', { fatal: false }).decode(puffer.slice(0, 1024));
    if (!/facet\s+normal|outer\s+loop|vertex\s/.test(probe) && zahl > 0) {
      // Was wirklich da ist, zaehlt - nicht, was im Kopf steht.
      const passen = Math.floor((puffer.byteLength - 84) / 50);
      return stlBinaer(sicht, Math.min(zahl, passen));
    }
  }
  return stlText(new TextDecoder().decode(puffer));
}

/* Fuer die Fehlerzeile. Ohne diese drei Angaben heisst es "geht nicht", und
   dann wird geraten statt nachgesehen. */
function kopfschau(puffer) {
  const anfang = new TextDecoder('utf-8', { fatal: false })
    .decode(puffer.slice(0, 12)).replace(/[^ -~]/g, '.');
  const zahl = puffer.byteLength >= 84
    ? new DataView(puffer).getUint32(80, true) : '?';
  return puffer.byteLength + ' Byte, Anfang „' + anfang + '", Kopfzahl ' + zahl;
}

function stlBinaer(sicht, zahl) {
  const punkte = new Float32Array(zahl * 9);
  let z = 0;
  for (let d = 0; d < zahl; d++) {
    // 12 Byte Normale ueberspringen: sie steht oft auf 0 oder zeigt falsch.
    // Gerechnet wird sie gleich sowieso aus den Ecken.
    let p = 84 + d * 50 + 12;
    for (let i = 0; i < 9; i++, p += 4) punkte[z++] = sicht.getFloat32(p, true);
  }
  return punkte;
}

function stlText(text) {
  const zahlen = [];
  const muster = /vertex\s+(-?[\d.eE+]+)\s+(-?[\d.eE+]+)\s+(-?[\d.eE+]+)/g;
  let t;
  while ((t = muster.exec(text))) {
    zahlen.push(Number(t[1]), Number(t[2]), Number(t[3]));
    if (zahlen.length > MODELL_MAX_DREIECKE * 9) break;
  }
  return new Float32Array(zahlen.slice(0, Math.floor(zahlen.length / 9) * 9));
}

function objLesen(puffer) {
  const ecken = [];
  const punkte = [];
  for (const zeile of new TextDecoder().decode(puffer).split('\n')) {
    const z = zeile.trim();
    if (z.charCodeAt(0) === 118 && z.charCodeAt(1) === 32) {          // "v "
      const t = z.split(/\s+/);
      ecken.push(Number(t[1]), Number(t[2]), Number(t[3]));
    } else if (z.charCodeAt(0) === 102 && z.charCodeAt(1) === 32) {   // "f "
      const t = z.split(/\s+/).slice(1).map(function (s) {
        // "7", "7/3", "7//2" - gebraucht wird nur die erste Zahl. Negative
        // Nummern zaehlen vom Ende her.
        const n = parseInt(s.split('/')[0], 10);
        return n < 0 ? ecken.length / 3 + n : n - 1;
      });
      // Vielecke als Faecher: ein n-Eck wird zu n-2 Dreiecken.
      for (let i = 1; i + 1 < t.length; i++) {
        for (const k of [t[0], t[i], t[i + 1]]) {
          punkte.push(ecken[k * 3], ecken[k * 3 + 1], ecken[k * 3 + 2]);
        }
      }
    }
  }
  return new Float32Array(punkte);
}

/* --- FBX ---------------------------------------------------------------

   FBX ist keine Datei mit einem Teil, sondern eine Szene: mehrere Objekte,
   jedes mit eigener Lage, Drehung und Groesse, dazu ein Elternbaum. Wer das
   weglaesst, legt bei einem Avatar alle Teile uebereinander in den
   Nullpunkt.

   Zwei Fassungen, ein Baum: binaer sind es geschachtelte Datensaetze mit
   zlib-gepackten Zahlenfeldern (das entpackt der Browser selbst), Text ist
   derselbe Baum in geschweiften Klammern. Danach arbeitet alles weitere auf
   derselben Form {name, werte, kinder}.

   Herausgeholt werden nur Vertices und PolygonVertexIndex. Nicht gelesen:
   Materialien, Texturen, Knochen, Animation, und von den Lagen die
   Exoten - andere Drehreihenfolgen als XYZ, Dreh- und Skalierpunkte,
   Vererbungsarten. Bei einem normalen Export aus Blender oder Fusion steht
   das Teil damit richtig; bei einer Szene aus Maya kann etwas schief
   stehen. */

const FBX_MAGIE = 'Kaydara FBX Binary';

async function fbxLesen(puffer) {
  const kopf = new TextDecoder('utf-8', { fatal: false }).decode(puffer.slice(0, 20));
  const baum = kopf.indexOf(FBX_MAGIE) === 0
    ? await fbxBinaer(puffer)
    : fbxText(new TextDecoder('utf-8', { fatal: false }).decode(puffer));
  return fbxNetz(baum);
}

async function auspacken(roh) {
  if (typeof DecompressionStream !== 'function') {
    throw new Error('dieser Browser kann FBX nicht entpacken (DecompressionStream fehlt)');
  }
  const strom = new Blob([roh]).stream().pipeThrough(new DecompressionStream('deflate'));
  return new Uint8Array(await new Response(strom).arrayBuffer());
}

async function fbxBinaer(puffer) {
  const sicht = new DataView(puffer);
  // Ab Fassung 7500 sind die Zeiger 64 Bit breit.
  const breit = sicht.getUint32(23, true) >= 7500;
  const wurzel = { name: '', werte: [], kinder: [] };
  let stelle = 27;
  while (stelle + (breit ? 25 : 13) <= puffer.byteLength) {
    const k = await fbxKnoten(sicht, puffer, stelle, breit);
    if (!k) break;
    wurzel.kinder.push(k.knoten);
    stelle = k.ende;
  }
  return wurzel;
}

async function fbxKnoten(sicht, puffer, stelle, breit) {
  const lang = (p) => (breit ? Number(sicht.getBigUint64(p, true)) : sicht.getUint32(p, true));
  const kopf = breit ? 25 : 13;
  const ende = lang(stelle);
  if (!ende) return null;                       // Schlussmarke
  const zahl = lang(stelle + (breit ? 8 : 4));
  const wertebytes = lang(stelle + (breit ? 16 : 8));
  const namelaenge = sicht.getUint8(stelle + (breit ? 24 : 12));
  let p = stelle + kopf;
  const name = new TextDecoder().decode(new Uint8Array(puffer, p, namelaenge));
  p += namelaenge;
  const werte = [];
  for (let i = 0; i < zahl; i++) {
    const w = await fbxWert(sicht, puffer, p);
    werte.push(w.wert);
    p = w.ende;
  }
  // Nicht mitzaehlen, sondern ausrechnen: so bringt ein Wert, den wir nicht
  // kennen, nicht den ganzen Baum durcheinander.
  p = stelle + kopf + namelaenge + wertebytes;
  const kinder = [];
  while (p + kopf <= ende) {
    const k = await fbxKnoten(sicht, puffer, p, breit);
    if (!k) break;
    kinder.push(k.knoten);
    p = k.ende;
  }
  return { knoten: { name, werte, kinder }, ende };
}

async function fbxWert(sicht, puffer, p) {
  const art = String.fromCharCode(sicht.getUint8(p));
  p += 1;
  if (art === 'Y') return { wert: sicht.getInt16(p, true), ende: p + 2 };
  if (art === 'C') return { wert: !!sicht.getUint8(p), ende: p + 1 };
  if (art === 'I') return { wert: sicht.getInt32(p, true), ende: p + 4 };
  if (art === 'F') return { wert: sicht.getFloat32(p, true), ende: p + 4 };
  if (art === 'D') return { wert: sicht.getFloat64(p, true), ende: p + 8 };
  if (art === 'L') return { wert: Number(sicht.getBigInt64(p, true)), ende: p + 8 };
  if (art === 'S' || art === 'R') {
    const n = sicht.getUint32(p, true);
    const roh = new Uint8Array(puffer, p + 4, n);
    return { wert: art === 'S' ? new TextDecoder().decode(roh) : roh, ende: p + 4 + n };
  }
  const laenge = sicht.getUint32(p, true);
  const packung = sicht.getUint32(p + 4, true);
  const bytes = sicht.getUint32(p + 8, true);
  let roh = new Uint8Array(puffer, p + 12, bytes);
  if (packung === 1) roh = await auspacken(roh);
  return { wert: fbxFeld(art, roh, laenge), ende: p + 12 + bytes };
}

function fbxFeld(art, roh, laenge) {
  // Eine frische Kopie: ein Feld mitten im Puffer liegt sonst schief fuer
  // 8-Byte-Zahlen, und dann wirft der Browser.
  const b = roh.slice().buffer;
  if (art === 'd') return new Float64Array(b, 0, laenge);
  if (art === 'f') return new Float32Array(b, 0, laenge);
  if (art === 'i') return new Int32Array(b, 0, laenge);
  if (art === 'l') return Array.from(new BigInt64Array(b, 0, laenge), Number);
  if (art === 'b') return new Uint8Array(b, 0, laenge);
  return [];
}

function fbxText(text) {
  const wurzel = { name: '', werte: [], kinder: [] };
  const stapel = [wurzel];
  for (let zeile of text.split('\n')) {
    const strich = zeile.indexOf(';');
    if (strich >= 0) zeile = zeile.slice(0, strich);
    zeile = zeile.trim();
    if (!zeile) continue;
    if (zeile.charAt(0) === '}') { if (stapel.length > 1) stapel.pop(); continue; }
    const auf = zeile.charAt(zeile.length - 1) === '{';
    if (auf) zeile = zeile.slice(0, -1).trim();
    const jetzt = stapel[stapel.length - 1];
    const doppel = zeile.indexOf(':');
    if (doppel < 0) {
      // Lange Zahlenreihen stehen ueber mehrere Zeilen - die Fortsetzung
      // gehoert zum zuletzt angefangenen Knoten.
      const letzte = jetzt.kinder[jetzt.kinder.length - 1];
      if (letzte) for (const w of fbxWerteText(zeile)) letzte.werte.push(w);
      continue;
    }
    const knoten = { name: zeile.slice(0, doppel).trim(),
                     werte: fbxWerteText(zeile.slice(doppel + 1)), kinder: [] };
    jetzt.kinder.push(knoten);
    if (auf) stapel.push(knoten);
  }
  return wurzel;
}

function fbxWerteText(stueck) {
  const werte = [];
  const muster = /"([^"]*)"|(-?\d[\d.eE+-]*)/g;
  let t;
  while ((t = muster.exec(stueck))) {
    if (t[1] !== undefined) { werte.push(t[1]); continue; }
    const zahl = Number(t[2]);
    werte.push(Number.isNaN(zahl) ? t[2] : zahl);
  }
  return werte;
}

function fbxKind(knoten, name) {
  return knoten ? knoten.kinder.find(function (k) { return k.name === name; }) : null;
}

function fbxFeldVon(knoten) {
  if (!knoten) return null;
  for (const w of knoten.werte) {
    if (w && typeof w === 'object' && typeof w.length === 'number') return w;
  }
  const a = fbxKind(knoten, 'a');      // so steht ein Feld in der Textfassung
  return a ? a.werte : null;
}

function fbxEigenschaft(modell, wie, standard) {
  const p = fbxKind(modell, 'Properties70') || fbxKind(modell, 'Properties60');
  if (!p) return standard;
  for (const e of p.kinder) {
    if ((e.name !== 'P' && e.name !== 'Property') || e.werte[0] !== wie) continue;
    const zahlen = e.werte.filter(function (w) { return typeof w === 'number'; });
    if (zahlen.length >= 3) return zahlen.slice(-3);
  }
  return standard;
}

function matDrehZ(w) {
  const c = Math.cos(w), s = Math.sin(w), m = matEinheit();
  m[0] = c; m[1] = s; m[4] = -s; m[5] = c; return m;
}
function matSkalaXYZ(s) {
  const m = matEinheit(); m[0] = s[0]; m[5] = s[1]; m[10] = s[2]; return m;
}
// Eulerwinkel in Grad, Reihenfolge XYZ - zuerst um X, zuletzt um Z.
function matDrehGrad(g) {
  const b = Math.PI / 180;
  return matMal(matDrehZ(g[2] * b), matMal(matDrehY(g[1] * b), matDrehX(g[0] * b)));
}

function fbxModellLage(modell) {
  const t = fbxEigenschaft(modell, 'Lcl Translation', [0, 0, 0]);
  const r = fbxEigenschaft(modell, 'Lcl Rotation', [0, 0, 0]);
  const s = fbxEigenschaft(modell, 'Lcl Scaling', [1, 1, 1]);
  const vor = fbxEigenschaft(modell, 'PreRotation', [0, 0, 0]);
  return matMal(matSchieben(t[0], t[1], t[2]),
                matMal(matDrehGrad(vor), matMal(matDrehGrad(r), matSkalaXYZ(s))));
}

function fbxGeoLage(modell) {
  const t = fbxEigenschaft(modell, 'GeometricTranslation', [0, 0, 0]);
  const r = fbxEigenschaft(modell, 'GeometricRotation', [0, 0, 0]);
  const s = fbxEigenschaft(modell, 'GeometricScaling', [1, 1, 1]);
  return matMal(matSchieben(t[0], t[1], t[2]),
                matMal(matDrehGrad(r), matSkalaXYZ(s)));
}

/* Von der Geometrie zum Modell, von dort nach oben: jede Lage multipliziert
   sich auf. Die Geometrie-Lage gilt nur am eigenen Modell, sie wird nicht
   vererbt. */
function fbxLage(nummer, eltern, modelle) {
  let m = null;
  let id = eltern.get(nummer);
  let tiefe = 0;
  while (id !== undefined && tiefe++ < 64) {
    const modell = modelle.get(id);
    if (modell) {
      const lage = m === null ? matMal(fbxModellLage(modell), fbxGeoLage(modell))
                              : fbxModellLage(modell);
      m = m === null ? lage : matMal(lage, m);
    }
    id = eltern.get(id);
  }
  return m;
}

function punkteWandeln(punkte, m) {
  const raus = new Float32Array(punkte.length);
  for (let i = 0; i < punkte.length; i += 3) {
    const x = punkte[i], y = punkte[i + 1], z = punkte[i + 2];
    raus[i] = m[0] * x + m[4] * y + m[8] * z + m[12];
    raus[i + 1] = m[1] * x + m[5] * y + m[9] * z + m[13];
    raus[i + 2] = m[2] * x + m[6] * y + m[10] * z + m[14];
  }
  return raus;
}

function fbxGeometrie(g) {
  const ecken = fbxFeldVon(fbxKind(g, 'Vertices'));
  const liste = fbxFeldVon(fbxKind(g, 'PolygonVertexIndex'));
  if (!ecken || !liste || !ecken.length) return null;
  const raus = [];
  let vieleck = [];
  for (let i = 0; i < liste.length; i++) {
    let n = liste[i];
    const schluss = n < 0;
    // Die letzte Ecke eines Vielecks steht negativ da - so merkt man, wo es
    // aufhoert.
    if (schluss) n = -n - 1;
    vieleck.push(n);
    if (!schluss) continue;
    for (let k = 1; k + 1 < vieleck.length; k++) {
      for (const e of [vieleck[0], vieleck[k], vieleck[k + 1]]) {
        raus.push(ecken[e * 3], ecken[e * 3 + 1], ecken[e * 3 + 2]);
      }
    }
    vieleck = [];
  }
  return new Float32Array(raus);
}

function fbxNetz(baum) {
  const objekte = fbxKind(baum, 'Objects');
  if (!objekte) return new Float32Array(0);

  const eltern = new Map();
  const verbindungen = fbxKind(baum, 'Connections');
  for (const c of (verbindungen ? verbindungen.kinder : [])) {
    if (c.name !== 'C' && c.name !== 'Connect') continue;
    if (c.werte[0] !== 'OO') continue;      // nur Objekt an Objekt
    eltern.set(Number(c.werte[1]), Number(c.werte[2]));
  }
  const modelle = new Map();
  for (const k of objekte.kinder) {
    if (k.name === 'Model') modelle.set(Number(k.werte[0]), k);
  }

  const stuecke = [];
  let laenge = 0;
  for (const g of objekte.kinder) {
    if (g.name !== 'Geometry') continue;
    let punkte = fbxGeometrie(g);
    if (!punkte || !punkte.length) continue;
    const lage = fbxLage(Number(g.werte[0]), eltern, modelle);
    if (lage) punkte = punkteWandeln(punkte, lage);
    stuecke.push(punkte);
    laenge += punkte.length;
  }
  if (stuecke.length === 1) return stuecke[0];
  const alles = new Float32Array(laenge);
  let p = 0;
  for (const s of stuecke) { alles.set(s, p); p += s.length; }
  return alles;
}

/* Normalen je Dreieck aus den Ecken, dazu Mitte und Groesse. Flach
   schattiert: jede Ecke bekommt die Normale ihres Dreiecks, damit Kanten
   Kanten bleiben - bei einem gedruckten Teil will man sie sehen. */
function netzBauen(punkte) {
  const dreiecke = Math.floor(punkte.length / 9);
  const normalen = new Float32Array(dreiecke * 9);
  let xa = Infinity, ya = Infinity, za = Infinity;
  let xb = -Infinity, yb = -Infinity, zb = -Infinity;
  for (let d = 0; d < dreiecke; d++) {
    const i = d * 9;
    const ux = punkte[i + 3] - punkte[i], uy = punkte[i + 4] - punkte[i + 1],
          uz = punkte[i + 5] - punkte[i + 2];
    const vx = punkte[i + 6] - punkte[i], vy = punkte[i + 7] - punkte[i + 1],
          vz = punkte[i + 8] - punkte[i + 2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
    nx /= l; ny /= l; nz /= l;
    for (let k = 0; k < 3; k++) {
      normalen[i + k * 3] = nx; normalen[i + k * 3 + 1] = ny; normalen[i + k * 3 + 2] = nz;
      const x = punkte[i + k * 3], y = punkte[i + k * 3 + 1], z = punkte[i + k * 3 + 2];
      if (x < xa) xa = x; if (x > xb) xb = x;
      if (y < ya) ya = y; if (y > yb) yb = y;
      if (z < za) za = z; if (z > zb) zb = z;
    }
  }
  if (!dreiecke) return { punkte, normalen, dreiecke: 0, mitte: [0, 0, 0], radius: 1 };
  const mitte = [(xa + xb) / 2, (ya + yb) / 2, (za + zb) / 2];
  // Der Radius der Kugel um das Teil, nicht die laengste Kante: sonst haengt
  // beim Drehen eine Ecke aus dem Bild.
  const kugel = Math.sqrt((xb - xa) * (xb - xa) + (yb - ya) * (yb - ya)
                          + (zb - za) * (zb - za)) / 2;
  return { punkte, normalen, dreiecke, mitte, radius: Math.max(kugel, 1e-6) };
}

/* --- Matrizen (spaltenweise, so wie WebGL sie will) --------------------- */

function matEinheit() {
  return new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
}
function matMal(a, b) {
  const m = new Float32Array(16);
  for (let s = 0; s < 4; s++) {
    for (let z = 0; z < 4; z++) {
      let w = 0;
      for (let i = 0; i < 4; i++) w += a[i * 4 + z] * b[s * 4 + i];
      m[s * 4 + z] = w;
    }
  }
  return m;
}
function matPerspektive(winkel, seite, nah, fern) {
  const f = 1 / Math.tan(winkel / 2);
  const m = new Float32Array(16);
  m[0] = f / seite; m[5] = f;
  m[10] = (fern + nah) / (nah - fern); m[11] = -1;
  m[14] = (2 * fern * nah) / (nah - fern);
  return m;
}
function matSchieben(x, y, z) {
  const m = matEinheit(); m[12] = x; m[13] = y; m[14] = z; return m;
}
function matSkala(s) {
  const m = matEinheit(); m[0] = s; m[5] = s; m[10] = s; return m;
}
function matDrehX(w) {
  const c = Math.cos(w), s = Math.sin(w), m = matEinheit();
  m[5] = c; m[6] = s; m[9] = -s; m[10] = c; return m;
}
function matDrehY(w) {
  const c = Math.cos(w), s = Math.sin(w), m = matEinheit();
  m[0] = c; m[2] = -s; m[8] = s; m[10] = c; return m;
}
// Der 3x3-Teil fuer die Normalen. Drehen allein veraendert ihre Richtung
// nicht ungleichmaessig, also reicht die Drehung selbst.
function mat3Von(m) {
  return new Float32Array([m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]]);
}

/* --- Zeichnen ----------------------------------------------------------- */

const MODELL_ECKPUNKT = [
  'attribute vec3 aOrt;',
  'attribute vec3 aNorm;',
  'uniform mat4 uMvp;',
  'uniform mat3 uDreh;',
  'varying vec3 vNorm;',
  'void main() {',
  '  vNorm = uDreh * aNorm;',
  '  gl_Position = uMvp * vec4(aOrt, 1.0);',
  '}',
].join('\n');

const MODELL_FLAECHE = [
  'precision mediump float;',
  'varying vec3 vNorm;',
  'void main() {',
  // Viele STL-Dateien haben Dreiecke verkehrt herum. Statt sie zu
  // reparieren, wird die Normale zum Betrachter gedreht - dann sieht die
  // Flaeche von beiden Seiten richtig aus.
  '  vec3 n = normalize(vNorm);',
  '  if (!gl_FrontFacing) n = -n;',
  '  vec3 licht = normalize(vec3(0.35, 0.75, 0.55));',
  '  float hell = 0.30 + 0.70 * max(dot(n, licht), 0.0);',
  '  float kante = 0.10 * pow(1.0 - abs(n.z), 3.0);',
  '  gl_FragColor = vec4(vec3(0.63, 0.64, 0.70) * hell + kante, 1.0);',
  '}',
].join('\n');

function glBauen(bild) {
  // alpha: die Flaeche bleibt hinter dem Modell durchsichtig, damit der
  // Kasten seine eigene Farbe behaelt - hell wie dunkel, ohne dass hier
  // eine Farbe nachgebaut wird.
  const gl = bild.getContext('webgl', { alpha: true, antialias: true,
                                        premultipliedAlpha: true });
  if (!gl) return null;
  const bauen = (art, quelle) => {
    const t = gl.createShader(art);
    gl.shaderSource(t, quelle);
    gl.compileShader(t);
    if (!gl.getShaderParameter(t, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(t) || 'Shader ging nicht');
    }
    return t;
  };
  const programm = gl.createProgram();
  gl.attachShader(programm, bauen(gl.VERTEX_SHADER, MODELL_ECKPUNKT));
  gl.attachShader(programm, bauen(gl.FRAGMENT_SHADER, MODELL_FLAECHE));
  gl.linkProgram(programm);
  if (!gl.getProgramParameter(programm, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(programm) || 'Programm ging nicht');
  }
  gl.useProgram(programm);
  gl.enable(gl.DEPTH_TEST);
  gl.clearColor(0, 0, 0, 0);
  return {
    gl,
    ort: gl.getAttribLocation(programm, 'aOrt'),
    norm: gl.getAttribLocation(programm, 'aNorm'),
    mvp: gl.getUniformLocation(programm, 'uMvp'),
    dreh: gl.getUniformLocation(programm, 'uDreh'),
  };
}

function netzHochladen(z) {
  const gl = z.glz.gl;
  z.pufferOrt = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, z.pufferOrt);
  gl.bufferData(gl.ARRAY_BUFFER, z.netz.punkte, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(z.glz.ort);
  gl.vertexAttribPointer(z.glz.ort, 3, gl.FLOAT, false, 0, 0);

  z.pufferNorm = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, z.pufferNorm);
  gl.bufferData(gl.ARRAY_BUFFER, z.netz.normalen, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(z.glz.norm);
  gl.vertexAttribPointer(z.glz.norm, 3, gl.FLOAT, false, 0, 0);
}

function modellZeichnen(z) {
  if (!z.glz || !z.netz) return;
  const gl = z.glz.gl;
  const breit = Math.max(1, Math.round(z.bild.clientWidth * (window.devicePixelRatio || 1)));
  const hoch = Math.max(1, Math.round(z.bild.clientHeight * (window.devicePixelRatio || 1)));
  if (z.bild.width !== breit || z.bild.height !== hoch) {
    z.bild.width = breit; z.bild.height = hoch;
  }
  gl.viewport(0, 0, breit, hoch);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

  // Der Drehpunkt sitzt normalerweise in der Mitte des Teils. Mit
  // Umschalt-Ziehen wandert er - und weil er vor der Drehung abgezogen
  // wird, dreht sich danach wirklich um den neuen Punkt.
  const grund = matMal(matSchieben(-z.punkt[0], -z.punkt[1], -z.punkt[2]),
                matMal(matSkala(1 / z.netz.radius),
                       matSchieben(-z.netz.mitte[0], -z.netz.mitte[1], -z.netz.mitte[2])));
  const dreh = matMal(matDrehX(z.hoehe), matDrehY(z.seite));
  const sicht = matSchieben(0, 0, -z.weg);
  const ferne = matPerspektive(MODELL_WINKEL, breit / hoch, 0.05, 100);
  gl.uniformMatrix4fv(z.glz.mvp, false,
                      matMal(ferne, matMal(sicht, matMal(dreh, grund))));
  gl.uniformMatrix3fv(z.glz.dreh, false, mat3Von(dreh));
  gl.drawArrays(gl.TRIANGLES, 0, z.netz.dreiecke * 3);
}

/* Umschalt-Ziehen schiebt den Drehpunkt, nicht nur das Bild: sonst sieht
   man das Teil zwar von der Seite, dreht aber weiter um seine alte Mitte
   und kommt an eine Ecke nie heran.

   Gerechnet wird in Bildpunkten: wie weit ist bei diesem Abstand eine
   Bildschirmhoehe? So viel wandert das Teil, wenn man ueber die ganze
   Flaeche zieht. Die Verschiebung steht in der Sicht, der Drehpunkt im
   Modell - dazwischen liegt die Drehung, also wird sie zurueckgerechnet
   (bei einer Drehung heisst umgekehrt: vertauscht). */
function punktSchieben(z, dx, dy, hoehePx) {
  const sichtbar = 2 * Math.tan(MODELL_WINKEL / 2) * z.weg;
  const vx = (dx / hoehePx) * sichtbar;
  const vy = -(dy / hoehePx) * sichtbar;
  const m = matMal(matDrehX(z.hoehe), matDrehY(z.seite));
  z.punkt = [z.punkt[0] - (m[0] * vx + m[1] * vy),
             z.punkt[1] - (m[4] * vx + m[5] * vy),
             z.punkt[2] - (m[8] * vx + m[9] * vy)];
  // Nicht beliebig weit: sonst ist das Teil aus dem Bild geschoben und man
  // findet es ohne Doppelklick nicht wieder.
  const weit = Math.sqrt(z.punkt[0] * z.punkt[0] + z.punkt[1] * z.punkt[1]
                         + z.punkt[2] * z.punkt[2]);
  if (weit > MODELL_SCHIEB_MAX) {
    const f = MODELL_SCHIEB_MAX / weit;
    z.punkt = [z.punkt[0] * f, z.punkt[1] * f, z.punkt[2] * f];
  }
}

/* --- Am Leben halten ---------------------------------------------------- */

function modellEinfrieren(z) {
  if (!z.glz) return;
  // Erst zeichnen, dann abfotografieren: ohne preserveDrawingBuffer ist das
  // Bild sonst leer.
  modellZeichnen(z);
  let standbild = null;
  try { standbild = z.bild.toDataURL('image/png'); } catch (f) { /* dann eben nicht */ }
  const verlust = z.glz.gl.getExtension('WEBGL_lose_context');
  if (verlust) verlust.loseContext();
  z.glz = null; z.pufferOrt = null; z.pufferNorm = null;
  const i = MODELL_LEBENDIG.indexOf(z);
  if (i >= 0) MODELL_LEBENDIG.splice(i, 1);
  // Auch wenn kein Standbild herauskam, muss hier etwas Anklickbares
  // stehen. Vorher blieb in dem Fall die Flaeche mit verlorenem Zeichner
  // liegen: ein schwarzes Feld, das sich nicht mehr dreht und aus dem es
  // keinen Weg zurueck gab.
  const ruhig = standbild
    ? el('img', { className: 'standbild', src: standbild, alt: z.datei,
                  title: 'Angehalten - zum Drehen anklicken' })
    : el('div', { className: 'standbild leerbild',
                  textContent: 'Angehalten - zum Drehen anklicken',
                  title: 'Angehalten - zum Drehen anklicken' });
  z.bild.replaceWith(ruhig);
  z.bild = ruhig;
  ruhig.addEventListener('click', function () { modellWecken(z); });
}

function platzSchaffen(ausser) {
  // Vorher, nicht hinterher: ein Browser gibt nur eine Handvoll 3D-Flaechen
  // je Seite her. Wer erst aufmacht und dann aufraeumt, bekommt beim einen
  // zu viel gar keine mehr - und dann war das Modell endgueltig weg, obwohl
  // es eben noch lief.
  while (MODELL_LEBENDIG.length >= MODELL_MAX_LEBENDIG) {
    const alt = MODELL_LEBENDIG.find(function (z) { return z !== ausser; });
    if (!alt) return;
    modellEinfrieren(alt);
  }
}

function modellWecken(z) {
  if (z.glz || !z.netz) return;
  platzSchaffen(z);
  const bild = el('canvas', {});
  z.bild.replaceWith(bild);
  z.bild = bild;
  let klage = '';
  try {
    z.glz = glBauen(bild);
  } catch (f) {
    z.glz = null;
    klage = f.message;
  }
  if (!z.glz) {
    kachelBehalten(z, klage ? 'Die 3D-Fläche ging nicht auf: ' + klage
                            : 'Dieser Browser zeichnet kein 3D (WebGL fehlt oder ist aus).');
    return;
  }
  netzHochladen(z);
  drehenAnbieten(z);
  MODELL_LEBENDIG.push(z);
  modellZeichnen(z);
}

/* --- Bedienung ---------------------------------------------------------- */

function drehenAnbieten(z) {
  const bild = z.bild;
  bild.addEventListener('pointerdown', function (ev) {
    if (ev.button !== 0) return;
    // Sonst faengt die Flaeche darunter an, einen Rahmen zu ziehen, und der
    // Kasten wandert.
    ev.stopPropagation();
    ev.preventDefault();
    bild.setPointerCapture(ev.pointerId);
    // Umschalt entscheidet beim Anfassen, nicht waehrenddessen: sonst
    // springt die Bewegung, wenn man die Taste mitten im Ziehen loslaesst.
    const schieben = ev.shiftKey;
    z.wo.classList.add(schieben ? 'schiebt' : 'dreht');
    let x = ev.clientX, y = ev.clientY;
    const bewegen = function (e2) {
      if (schieben) {
        punktSchieben(z, e2.clientX - x, e2.clientY - y, z.bild.clientHeight || 1);
      } else {
        z.seite += (e2.clientX - x) * 0.01;
        z.hoehe += (e2.clientY - y) * 0.01;
        // Nicht ueber den Kopf: sonst steht das Teil kopf und man findet
        // nicht zurueck.
        z.hoehe = Math.max(-1.5, Math.min(1.5, z.hoehe));
      }
      x = e2.clientX; y = e2.clientY;
      modellZeichnen(z);
    };
    const los = function () {
      bild.removeEventListener('pointermove', bewegen);
      bild.removeEventListener('pointerup', los);
      bild.removeEventListener('pointercancel', los);
      z.wo.classList.remove('dreht');
      z.wo.classList.remove('schiebt');
    };
    bild.addEventListener('pointermove', bewegen);
    bild.addEventListener('pointerup', los);
    bild.addEventListener('pointercancel', los);
  });
  bild.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    ev.stopPropagation();          // nicht die ganze Seite zoomen
    z.weg = Math.max(1.3, Math.min(14, z.weg * (ev.deltaY > 0 ? 1.12 : 0.89)));
    modellZeichnen(z);
  }, { passive: false });
  bild.addEventListener('dblclick', function (ev) {
    ev.stopPropagation();
    z.seite = 0.6; z.hoehe = -0.5; z.weg = MODELL_WEG; z.punkt = [0, 0, 0];
    modellZeichnen(z);
  });
}

/* --- Aufbau ------------------------------------------------------------- */

function kachelBehalten(z, warum) {
  // Die Kachel tut weiter, was sie immer getan hat - herunterladen. Der
  // Grund steht aber sichtbar darunter und nicht nur im Tooltip: sonst
  // steht da eine Kachel wie frueher und niemand weiss, warum kein Modell
  // kommt. In der Notiz gespeichert wird davon nichts.
  if (z.wo && z.wo.parentElement) z.wo.remove();
  z.kasten.classList.remove('kasten-3d');
  z.kasten.classList.remove('kasten-pcb');
  const zaehler = z.kasten.querySelector('.dzahl');
  if (zaehler) zaehler.remove();
  if (!warum) return;
  z.kasten.title = warum;
  const alt = z.kasten.querySelector('.modellfehler');
  if (alt) alt.remove();
  z.kasten.append(el('p', { className: 'modellfehler', textContent: warum }));
  console.error('[notizmappe] 3D: ' + warum);
}

async function modellStarten(z) {
  if (z.laeuft) return;
  z.laeuft = true;
  let puffer;
  try {
    puffer = await modellHolen(z.datei);
  } catch (f) {
    kachelBehalten(z, 'Modell ließ sich nicht holen: ' + f.message);
    return;
  }
  let punkte;
  try {
    punkte = z.art === 'fbx' ? await fbxLesen(puffer)
           : z.art === 'obj' ? objLesen(puffer) : stlLesen(puffer);
  } catch (f) {
    kachelBehalten(z, 'Modell ließ sich nicht lesen: ' + f.message
                      + ' (' + kopfschau(puffer) + ')');
    return;
  }
  if (!punkte.length) {
    kachelBehalten(z, 'Keine Dreiecke gefunden (' + kopfschau(puffer) + ')');
    return;
  }
  if (punkte.length / 9 > MODELL_MAX_DREIECKE) {
    kachelBehalten(z, 'Zu groß zum Anzeigen: '
                      + Math.round(punkte.length / 9).toLocaleString('de-DE')
                      + ' Dreiecke.');
    return;
  }
  z.netz = netzBauen(punkte);
  const zaehler = z.kasten.querySelector('.dzahl');
  if (zaehler) {
    zaehler.textContent = z.netz.dreiecke.toLocaleString('de-DE') + ' Dreiecke';
  }
  modellWecken(z);
}

function modellKasten(kasten) {
  if (kasten.dataset.modell || !offen) return;
  const eintrag = (elemente || []).find(function (x) { return x.id === kasten.dataset.id; });
  const datei = eintrag ? eintrag.datei : '';
  const art = modellArt(datei);
  if (!art) {
    // Ein ZIP kann ein Gerber-Paket sein - das sagt erst sein Inhalt.
    if (/\.zip$/i.test(datei || '')) platineKasten(kasten, datei);
    else kasten.dataset.modell = 'nein';
    return;
  }
  if (!window.WebGLRenderingContext) { kasten.dataset.modell = 'nein'; return; }
  kasten.dataset.modell = 'ja';
  kasten.classList.add('kasten-3d');

  const bild = el('canvas', {});
  const lade = el('p', { className: 'lade', textContent: 'Modell wird geladen …' });
  const wo = el('div', { className: 'modell' }, [bild, lade]);
  // Vor die Kachel: die bleibt als Fusszeile stehen und kann weiter
  // herunterladen.
  const kachel = kasten.querySelector('.datei');
  if (kachel) {
    kachel.before(wo);
    kachel.append(el('span', { className: 'dzahl', textContent: '…' }));
  } else {
    kasten.append(wo);
  }

  const z = { kasten, wo, bild, datei, art, netz: null, glz: null,
              seite: 0.6, hoehe: -0.5, weg: MODELL_WEG, punkt: [0, 0, 0],
              laeuft: false };

  // Erst laden, wenn das Modell ins Bild rollt: zehn Anhaenge auf einer
  // Seite waeren sonst zehn Dateien auf einmal.
  const sehen = new IntersectionObserver(function (treffer) {
    for (const t of treffer) {
      if (!t.isIntersecting) continue;
      sehen.disconnect();
      modellStarten(z).then(function () { lade.remove(); },
                            function () { lade.remove(); });
    }
  }, { rootMargin: '200px' });
  sehen.observe(wo);

  if (window.ResizeObserver) {
    new ResizeObserver(function () { modellZeichnen(z); }).observe(wo);
  }
}

function modelleNachsehen() {
  for (const k of document.querySelectorAll('.kasten-datei:not([data-modell])')) {
    try { modellKasten(k); } catch (f) { console.error('[notizmappe] 3D:', f); }
  }
}

function modelleBauen() {
  if (!window.IntersectionObserver) return;
  modelleNachsehen();
  // Die Kaesten entstehen erst, wenn eine Seite geladen ist - und bei jedem
  // Seitenwechsel neu.
  // Nur die Kaesten selbst, ohne subtree: die haengen direkt an der
  // Flaeche. Mit subtree liefe das bei jedem Tastendruck in einem Textkasten
  // mit - contenteditable aendert dabei staendig Knoten.
  const beobachter = new MutationObserver(modelleNachsehen);
  beobachter.observe(flaeche || document.body, { childList: true });
}


/* ============================================== Mein Profil (am Server)
 *
 * Eins zu eins aus der Serverfassung uebernommen, damit es im Fenster
 * genauso aussieht: ein Fenster ueber allem, mit Zugang, Mailadresse,
 * Passwort und Abmelden. Zwei Stellen sind anders und muessen es sein -
 * "Abmelden" loest hier die Verbindung statt eine Adresse aufzurufen, und
 * das Aussehen steht nicht drin: dafuer gibt es im Fenster die Optionen,
 * und zwei Stellen fuer dieselbe Farbe waeren eine zu viel.
 */

/* Eine Seite des Servers aufrufen. Drueben ist das hol(); hier geht es ueber
 * die Bruecke, die eine feste Liste erlaubter Seiten hat. */
async function serverHol(art, weg, rumpf) {
  return api('/api/server', 'POST', { art: art, weg: weg, rumpf: rumpf || {} });
}

function fensterZu() {
  const f = document.getElementById('profilfenster');
  if (f && typeof f.close === 'function') f.close();
}

function profilfenster() {
  const vorhanden = document.getElementById('profilfenster');
  if (vorhanden) return vorhanden;

  const zu = el('button', { type: 'button', id: 'profilzu', title: 'Schließen',
                            textContent: '✕' });
  const fenster = el('dialog', { id: 'profilfenster' }, [
    el('div', { id: 'profilkopfzeile' }, [el('h2', { textContent: 'Mein Profil' }), zu]),
  ]);
  zu.addEventListener('click', () => fenster.close());
  // Klick auf den dunklen Rand schliesst auch - das Fenster selbst faengt
  // seine eigenen Klicks ab.
  fenster.addEventListener('click', function (ev) {
    if (ev.target === fenster) fenster.close();
  });
  document.body.append(fenster);
  return fenster;
}

function profilOeffnen() {
  const fenster = profilfenster();
  if (!fenster) return;
  profilDatenLaden();
  if (typeof fenster.showModal === 'function') fenster.showModal();
  else fenster.setAttribute('open', 'open');
}

/* -------------------------------------------------------------- Mein Profil

   Getrennt von der Verwaltung, weil es zwei verschiedene Dinge sind: dort
   geht es um andere Leute, hier um einen selbst. Wer kein Verwalter ist,
   hatte bisher ueberhaupt keine Stelle, an der er sein eigenes Passwort
   aendern konnte. */

function profilBearbeitenBauen() {
  const seite = profilfenster();
  if (!seite || document.getElementById('profilteil')) return;

  const wer = el('p', { className: 'zeile2' }, [
    el('span', { textContent: 'Angemeldet als' }),
    el('code', { id: 'p-ich', textContent: '…' }),
  ]);
  const rolle = el('p', { className: 'zeile2' }, [
    el('span', { textContent: 'Rolle' }),
    el('span', { id: 'p-rolle', textContent: '…' }),
  ]);
  const zwei = el('p', { className: 'zeile2' }, [
    el('span', { textContent: 'Zwei Schritte beim Anmelden' }),
    el('span', { id: 'p-zwei', textContent: '…' }),
  ]);

  const alt = el('input', { type: 'password', id: 'p-alt',
                            placeholder: 'Bisheriges Passwort' });
  const neu1 = el('input', { type: 'password', id: 'p-neu',
                             placeholder: 'Neues Passwort (mind. 8 Zeichen)' });
  const neu2 = el('input', { type: 'password', id: 'p-neu2',
                             placeholder: 'Noch einmal' });
  const hinweis = el('p', { className: 'hinweis', id: 'p-hinweis' });
  const aendern = el('button', { type: 'button', textContent: 'Passwort ändern' });
  aendern.addEventListener('click', async () => {
    if (neu1.value !== neu2.value) {
      hinweis.textContent = 'Die beiden neuen Passwörter sind nicht gleich.';
      return;
    }
    hinweis.textContent = 'wird geändert …';
    try {
      const d = await serverHol('POST', '/profil/passwort', { alt: alt.value, neu: neu1.value });
      hinweis.textContent = d.hinweis || 'Geändert.';
      alt.value = neu1.value = neu2.value = '';
    } catch (f) { hinweis.textContent = f.message; }
  });

  /* Die eigene Adresse. Freiwillig und mit genau einem Zweck - deshalb
     steht der Zweck auch daneben: wer nicht weiss, wofuer eine Adresse
     gebraucht wird, traegt zu Recht keine ein. */
  const email = el('input', { type: 'email', id: 'p-email',
                              placeholder: 'name@beispiel.de', autocomplete: 'email' });
  const emailHinweis = el('p', { className: 'hinweis', id: 'p-emailhinweis' });
  const emailSichern = el('button', { type: 'button', textContent: 'Adresse speichern' });
  emailSichern.addEventListener('click', async () => {
    emailHinweis.textContent = 'wird gespeichert …';
    try {
      const d = await serverHol('POST', '/profil/email', { email: email.value });
      emailHinweis.textContent = d.hinweis || '';
    } catch (f) { emailHinweis.textContent = f.message; }
  });

  /* Bescheid, wenn jemand an der eigenen Tuer ruettelt. Hoechstens eine
     Nachricht je Viertelstunde - sonst wird daraus Spam, und Spam klickt
     man weg, auch den echten Einbruch. */
  const melde = el('select', { id: 'p-melde' });
  for (const [wert, text] of [['fehler', 'nur bei fehlgeschlagenen Versuchen'],
                              ['alle', 'bei jeder Anmeldung'],
                              ['aus', 'gar nicht']]) {
    melde.append(el('option', { value: wert, textContent: text }));
  }
  melde.addEventListener('change', async () => {
    emailHinweis.textContent = 'wird gespeichert …';
    try {
      const d = await serverHol('POST', '/profil/meldung', { art: melde.value });
      emailHinweis.textContent = d.hinweis || '';
    } catch (f) { emailHinweis.textContent = f.message; }
  });

  const abmelden = el('button', { type: 'button', textContent: 'Abmelden' });
  abmelden.addEventListener('click', async function () {
    fensterZu();
    if (amServer()) { location.href = '/abmelden'; return; }
    try {
      await api('/api/ferne/abmelden', 'POST', {});
      merker.legen('zuletzt', 'null');
      sagen('Vom Server abgemeldet.', 0);
      await wiederAufbauen();
    } catch (f) { melden(f.message); }
  });

  seite.append(el('section', { id: 'profilteil' }, [
    wer, rolle, zwei,
    el('h3', { textContent: 'E-Mail', style: 'margin-top:14px' }),
    el('p', { className: 'hinweis', id: 'p-emailzweck', textContent:
      'Nur dafür da, ein vergessenes Passwort zurückzusetzen. Ohne Adresse '
      + 'geht das nicht - dann hilft nur ein Verwalter.' }),
    el('p', { className: 'ordnerzeile' }, [email, emailSichern]),
    el('p', { className: 'zeile2' }, [
      el('span', { textContent: 'Nachricht bei Anmeldeversuchen' }), melde]),
    emailHinweis,
    el('h3', { textContent: 'Passwort ändern', style: 'margin-top:14px' }),
    el('p', { className: 'hinweis', textContent:
      'Das bisherige Passwort wird abgefragt - sonst könnte jemand an einem '
      + 'offen stehenden Rechner in zwei Klicks den Zugang übernehmen. Danach '
      + 'sind alle anderen Sitzungen abgemeldet.' }),
    el('p', { className: 'ordnerzeile' }, [alt]),
    el('p', { className: 'ordnerzeile' }, [neu1, neu2]),
    el('p', { className: 'knoepfe' }, [aendern]),
    hinweis,
    el('h3', { textContent: 'Sitzung', style: 'margin-top:14px' }),
    el('p', { className: 'knoepfe' }, [abmelden]),
  ]));
}

async function profilDatenLaden() {
  let d;
  try { d = await serverHol('GET', '/profil'); } catch (f) { return; }
  const setz = (id, wert) => {
    const k = document.getElementById(id);
    if (k) k.textContent = wert;
  };
  setz('p-ich', d.ich);
  setz('p-rolle', d.rolle);
  setz('p-zwei', d.zwei ? 'eingeschaltet' : 'aus');
  const email = document.getElementById('p-email');
  if (email) email.value = d.email || '';
  const melde = document.getElementById('p-melde');
  if (melde) melde.value = d.melde || 'fehler';
  const zweck = document.getElementById('p-emailzweck');
  // Ohne eingerichteten Mailversand waere die Adresse ein Feld, das nichts
  // tut. Dann lieber sagen, woran es liegt.
  if (zweck && !d.post_an) {
    zweck.textContent = 'Auf diesem Server ist noch kein Mailversand eingerichtet - '
      + 'bis dahin kann auch mit Adresse nichts zurückgesetzt werden. '
      + (d.darf_verwalten ? 'Einrichten lässt sich das unter Optionen.'
                          : 'Das kann nur ein Verwalter einrichten.');
  }
}

(async () => {
  zoomSetzen(parseFloat(merker.holen('zoom', '1')));
  stifteHolen();
  stiftknoepfeBauen();
  $('#m-nurstift').checked = !!merker.holen('nurstift', '');
  reiterSetzen(merker.holen('reiter', 'start') === 'zeichnen' ? 'zeichnen' : 'start');
  // Jeder Schritt fuer sich: faellt einer aus, laeuft der Rest trotzdem - und
  // man sieht im Protokoll, welcher es war.
  for (const [name, tun] of [['Formatleiste', formatleistenBauen],
                             ['Rechtsklick', rechtsmenueBauen],
                             ['Anhangvorschau', modelleBauen],
                             ['Update-Hinweis', updateHinweisBauen]]) {
    try { tun(); } catch (f) { console.error('[notizmappe] ' + name + ':', f); }
  }
  // Vor allem anderen: ist zugesperrt, wird hier gewartet, bis das Passwort
  // stimmt. Kein Baum, keine Seite, nichts.
  if (!await sperreAufmachen()) return;
  try {
    await baumLaden();
  } catch (f) {
    // Z. B. Datenordner auf einem nicht eingehaengten Laufwerk: sagen, was los ist,
    // statt eine leere Flaeche zu zeigen - und nichts anlegen.
    // Mit Pfad: "geht nicht" allein hilft niemandem beim Suchen.
    let wo = '';
    try {
      const b = await bruecke();
      const e = await b.einstellungen();
      wo = e && e.ordner ? `  (${e.ordner})` : '';
    } catch (x) { /* dann eben ohne */ }
    melden(f.message + wo, [['Einstellungen', () => tafelZeigen(true)]]);
    baumMeldung(f.message + wo, ['Einstellungen öffnen', () => tafelZeigen(true)]);
    return;
  }
  // Nicht nur beim ganz leeren Datenordner: auch ein Notizbuch ohne Abschnitte oder
  // ein Abschnitt ohne Seiten lässt einen vor einer Fläche sitzen, auf der sich
  // nichts schreiben lässt - und nichts sagt einem, warum.
  // Leerer Ordner, aber woanders liegen Notizen? Dann nicht einfach ein neues
  // Notizbuch anlegen - sonst sieht es aus, als waere alles weg.
  try {
    const e = await api('/api/einstellungen');
    // Wo die Notizen liegen, gehört in die Leiste - die ist immer zu sehen,
    // auch wenn das Fenster schmal gezogen ist.
    ordnerZeigen(e);
    if (!erstesSeitchen() && e.andere_orte && e.andere_orte.length) {
      const ziel = e.andere_orte[0];
      const wechseln = async () => {
        try {
          await api('/api/ordner', 'POST', { ordner: ziel });
          merker.legen('zuletzt', 'null');
          await wiederAufbauen();
        } catch (f) { melden('Umstellen ging nicht: ' + f.message); }
      };
      melden(`Hier liegen keine Notizen (${e.ordner}). Gefunden in: ${ziel}`, [
        ['Dorthin wechseln', wechseln],
        ['Einstellungen', () => tafelZeigen(true)],
      ]);
      // Und dasselbe in der Leiste. Genau dieser Hinweis stand bisher nur im
      // Hauptbereich - wer das Fenster schmal gezogen hat, sah eine schwarze
      // Fläche und nirgends einen Grund.
      baumMeldung(`Hier liegen keine Notizen:\n${e.ordner}\n\nGefunden in:\n${ziel}`,
                  ['Dorthin wechseln', wechseln]);
      return;
    }
  } catch (f) { /* dann weiter wie bisher */ }

  if (!erstesSeitchen()) {
    const buch = baumDaten[0] ? baumDaten[0].name
      : (await api('/api/notizbuch', 'POST', { name: 'Notizbuch' })).name;
    const ab = (baumDaten[0] && baumDaten[0].abschnitte[0]) ? baumDaten[0].abschnitte[0].name
      : (await api('/api/abschnitt', 'POST', { notizbuch: buch, name: 'Allgemein' })).name;
    await api('/api/seite', 'POST', { notizbuch: buch, abschnitt: ab, titel: 'Erste Seite' });
    await baumLaden();
  }
  schriftenLaden();
  await updateBeimStart();
  let z = null;
  try { z = JSON.parse(merker.holen('zuletzt', 'null')); } catch (f) { /* dann die erste */ }
  try {
    if (z) await seiteOeffnen(z.buch, z.abschnitt, z.name);
    else throw new Error('nichts gemerkt');
  } catch (f) {
    const erste = erstesSeitchen();
    if (erste) await seiteOeffnen(erste[0], erste[1], erste[2]);
  }
})();
