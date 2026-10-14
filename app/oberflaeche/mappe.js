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
  'POST /api/einstellungen':   (p, b, r) => b.optionen_setzen(r),
  'POST /api/ordner/waehlen':  (p, b) => b.ordner_waehlen(),
  'POST /api/ordner':          (p, b, r) => b.ordner_setzen(r),
  'GET /api/version':          (p, b) => b.version(p.frisch === 'true'),
  'POST /api/update':          (p, b) => b.update(),
  'GET /api/update/stand':     (p, b) => b.update_stand(),
  'GET /api/sperre':           (p, b) => b.sperre_stand(),
  'POST /api/sperre/an':       (p, b, r) => b.sperre_einrichten(r),
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
  // halb geladene Notizen legen, sondern neu laden - dann kommt der Sperrschirm.
  if (daten && daten.art === 'zu' && !laeuftZu) {
    laeuftZu = true;
    location.reload();
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

function baumZeichnen() {
  const baum = $('#baum');
  baum.textContent = '';
  for (const buch of baumDaten) {
    const bd = document.createElement('div');
    bd.className = 'buch' + (zugeklappt.has(buch.name) ? ' eingeklappt' : '');
    bd.append(zeile(buch.name, [
      ['+ Abschnitt', '＋', async () => {
        const n = prompt('Name des Abschnitts:'); if (!n) return;
        await api('/api/abschnitt', 'POST', { notizbuch: buch.name, name: n });
        zugeklappt.delete(buch.name); await baumLaden();
      }],
      ['Notizbuch loeschen', '🗑', () => loeschen('notizbuch', [buch.name], buch.name)],
    ], () => klappen(bd, buch.name), zugeklappt.has(buch.name)));

    for (const ab of buch.abschnitte) {
      const schluessel = buch.name + '/' + ab.name;
      const ad = document.createElement('div');
      ad.className = 'abschnitt' + (zugeklappt.has(schluessel) ? ' eingeklappt' : '');
      ad.append(zeile(ab.name, [
        ['+ Seite', '＋', async () => {
          const r = await api('/api/seite', 'POST', { notizbuch: buch.name, abschnitt: ab.name, titel: 'Neue Seite' });
          zugeklappt.delete(schluessel); await baumLaden();
          await seiteOeffnen(buch.name, ab.name, r.name);
          $('#titel').select();
        }],
        ['Abschnitt loeschen', '🗑', () => loeschen('abschnitt', [buch.name, ab.name], ab.name)],
      ], () => klappen(ad, schluessel), zugeklappt.has(schluessel)));

      for (const s of ab.seiten) {
        const sd = zeile(s.titel, [
          ['Seite loeschen', '🗑', () => loeschen('seite', [buch.name, ab.name, s.name], s.titel)],
        ]);
        sd.classList.add('seite');
        if (s.konflikt) sd.classList.add('konflikt');
        if (s.konflikt) sd.title = 'Konfliktkopie vom Sync - hier stehen zwei Fassungen derselben Seite';
        if (offen && offen.notizbuch === buch.name && offen.abschnitt === ab.name && offen.name === s.name) sd.classList.add('aktiv');
        sd.querySelector('.name').addEventListener('click', () => seiteOeffnen(buch.name, ab.name, s.name));
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

async function baumLaden() {
  const r = await api('/api/baum');
  baumDaten = r.notizbuecher;
  baumZeichnen();
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

for (const b of document.querySelectorAll('#werkzeuge [data-befehl]')) {
  b.addEventListener('mousedown', (ev) => ev.preventDefault());  // Fokus im Text behalten
  b.addEventListener('click', () => {
    document.execCommand(b.dataset.befehl);
    const k = document.activeElement && document.activeElement.closest('.kasten');
    if (k) {
      const e = elemente.find((x) => x.id === k.dataset.id);
      if (e) { e.html = k.querySelector('.text').innerHTML; angefasst(); }
    }
  });
}

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
 * Freitext-CSS, die hier nicht in die Dateien soll. */
function hervorheben() {
  const sel = window.getSelection();
  if (!sel.rangeCount || sel.isCollapsed) return;
  const r = sel.getRangeAt(0);
  const schon = (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement)
    .closest('mark');
  if (schon) { hervorhebungWeg(); return; }
  const m = document.createElement('mark');
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

$('#neues-buch').addEventListener('click', async () => {
  const n = prompt('Name des Notizbuchs:');
  if (!n) return;
  await api('/api/notizbuch', 'POST', { name: n });
  await baumLaden();
});

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
        setTimeout(() => location.reload(), 1200);
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

const tafel = $('#einstellungen');

function tafelZeigen(an) {
  tafel.hidden = !an;
  if (an) einstellungenLaden();
}

$('#zahnrad').addEventListener('click', () => tafelZeigen(true));
$('#zu').addEventListener('click', () => tafelZeigen(false));
tafel.addEventListener('click', (ev) => { if (ev.target === tafel) tafelZeigen(false); });
document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && !tafel.hidden) tafelZeigen(false); });

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
    // Neu laden, damit keine offene Seite mehr auf den alten Ordner zeigt.
    merker.legen('zuletzt', 'null');
    setTimeout(() => location.reload(), 600);
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

function strichAblegen() {
  if (!laufend) return;
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

function reiterSetzen(name) {
  for (const k of document.querySelectorAll('#reiter .reiter')) {
    k.setAttribute('aria-selected', String(k.dataset.reiter === name));
  }
  $('#werkzeuge').hidden = name !== 'start';
  $('#malzeug').hidden = name !== 'zeichnen';
  merker.legen('reiter', name);
  // Beim Verlassen des Reiters nicht weitermalen: sonst fängt der nächste Klick
  // in den Text einen Strich an.
  werkzeugSetzen(name === 'zeichnen' ? (werkzeug === 'auswahl' ? 'stift' : werkzeug) : 'auswahl',
                 stiftnummer);
}

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
    location.reload();           /* mitten im Betrieb aufgeschlossen */
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
  // Neu laden statt Felder leeren: so bleibt garantiert nichts Lesbares stehen.
  location.reload();
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
    sperrhinweis(`Eingeschaltet, ${r.umgestellt} Dateien verschlüsselt.`);
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

(async () => {
  zoomSetzen(parseFloat(merker.holen('zoom', '1')));
  stifteHolen();
  stiftknoepfeBauen();
  $('#m-nurstift').checked = !!merker.holen('nurstift', '');
  reiterSetzen(merker.holen('reiter', 'start') === 'zeichnen' ? 'zeichnen' : 'start');
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
    return;
  }
  // Nicht nur beim ganz leeren Datenordner: auch ein Notizbuch ohne Abschnitte oder
  // ein Abschnitt ohne Seiten lässt einen vor einer Fläche sitzen, auf der sich
  // nichts schreiben lässt - und nichts sagt einem, warum.
  // Leerer Ordner, aber woanders liegen Notizen? Dann nicht einfach ein neues
  // Notizbuch anlegen - sonst sieht es aus, als waere alles weg.
  try {
    const e = await api('/api/einstellungen');
    if (!erstesSeitchen() && e.andere_orte && e.andere_orte.length) {
      const ziel = e.andere_orte[0];
      melden(`Hier liegen keine Notizen (${e.ordner}). Gefunden in: ${ziel}`, [
        ['Dorthin wechseln', async () => {
          try {
            await api('/api/ordner', 'POST', { ordner: ziel });
            location.reload();
          } catch (f) { melden('Umstellen ging nicht: ' + f.message); }
        }],
        ['Einstellungen', () => tafelZeigen(true)],
      ]);
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
