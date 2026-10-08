/* Notizmappe - freie Flaeche. Kein Framework, damit es ohne Build laeuft.
 *
 * Grundgedanke: die Seite ist eine Liste von Kaesten mit x/y/Breite. Der Browser
 * haelt sie in `elemente`, der Server kennt nur das JSON. Gespeichert wird
 * verzoegert, aber immer die ganze Seite - bei einer Handvoll Kaesten pro Seite
 * ist das billiger als Einzelfeld-Buchhaltung. */

const WARTEN = 900;        // ms Ruhe nach der letzten Eingabe, bevor gespeichert wird
const POLL = 15000;        // ms zwischen "hat jemand von aussen geschrieben?"
const RASTER = 8;          // Positionen auf 8px runden, sonst zappelt alles

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

async function api(weg, art = 'GET', rumpf = null) {
  const o = { method: art, headers: {} };
  if (rumpf) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(rumpf); }
  const a = await fetch(weg, o);
  let daten = null;
  try { daten = await a.json(); } catch (e) { /* leere Antwort */ }
  if (a.status === 401 && daten && daten.anmelden) {
    // Abgelaufen oder gesperrt: zur Anmeldung. Ungespeichertes kann hier nicht
    // mehr raus - deshalb sperrt die Oberflaeche selbst erst nach dem Speichern.
    location.href = '/anmelden';
  }
  if (!a.ok) { const f = new Error((daten && (daten.fehler || daten.detail)) || a.statusText); f.status = a.status; f.daten = daten; throw f; }
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
    ], () => klappen(bd, buch.name)));

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
      ], () => klappen(ad, schluessel)));

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

function zeile(text, aktionen = [], aufKlick = null) {
  const z = document.createElement('div');
  z.className = 'zeile';
  if (aufKlick) {
    const pfeil = Object.assign(document.createElement('span'), { className: 'pfeil', textContent: '▾' });
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
    // Speichern ging nicht (Konflikt, Server weg): nicht wegwechseln, sonst sind
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
  for (const e of elemente) flaeche.append(kastenBauen(e));
  $('#leerhinweis').hidden = elemente.length > 0;
  schmutzig = false;
  flaecheMessen();
  baumZeichnen();
  merker.legen('zuletzt', JSON.stringify({ buch, abschnitt, name: s.name }));
}

/* ------------------------------------------------------------------ Kaesten */

function anhangWeg(pfad) {
  const p = new URLSearchParams({
    notizbuch: offen.notizbuch, abschnitt: offen.abschnitt, name: offen.name, datei: pfad,
  });
  return '/api/anhang?' + p.toString();
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
  bild.src = anhangWeg(e.datei);
  bild.alt = e.beschriftung || e.datei;
  bild.draggable = false;
  bild.addEventListener('load', flaecheMessen);
  bild.addEventListener('error', () => {
    bild.replaceWith(Object.assign(document.createElement('div'), {
      className: 'fehlt', textContent: 'Bild fehlt: ' + e.datei,
    }));
  });
  return bild;
}

function dateiBauen(e) {
  const kachel = document.createElement('a');
  kachel.className = 'datei';
  kachel.href = anhangWeg(e.datei);
  kachel.download = e.datei;
  kachel.title = 'Herunterladen: ' + e.datei;
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
async function hochladen(datei) {
  if (!offen) { sagen('Erst eine Seite öffnen', 2000); return null; }
  const fd = new FormData();
  fd.append('notizbuch', offen.notizbuch);
  fd.append('abschnitt', offen.abschnitt);
  fd.append('name', offen.name);
  // Aus der Zwischenablage heisst jedes Bild "image.png". Ein Name mit Uhrzeit
  // ist im Dateimanager lesbarer und kommt dem naechsten Bild nicht in die Quere.
  const ablage = /^image\.(\w+)$/.exec(datei.name || '');
  if (ablage) {
    const z = new Date();
    const zwei = (n) => String(n).padStart(2, '0');
    const stempel = `${z.getFullYear()}-${zwei(z.getMonth() + 1)}-${zwei(z.getDate())}`
      + ` ${zwei(z.getHours())}-${zwei(z.getMinutes())}-${zwei(z.getSeconds())}`;
    fd.append('datei', datei, `Bild ${stempel}.${ablage[1]}`);
  } else {
    fd.append('datei', datei);
  }
  zustandAnzeige.textContent = 'lädt …';
  let a;
  try {
    a = await fetch('/api/anhang', { method: 'POST', body: fd });
  } catch (f) {
    melden('Hochladen ging nicht: ' + f.message);
    return null;
  }
  if (!a.ok) {
    let grund = a.statusText;
    try { grund = (await a.json()).fehler || grund; } catch (f) { /* egal */ }
    melden(`"${datei.name}" ging nicht: ${grund}`);
    zustandAnzeige.textContent = '';
    return null;
  }
  return a.json();
}

async function anhangHochladen(datei, x, y) {
  const r = await hochladen(datei);
  if (r) anhangHochladenFertig(r, datei, x, y);
}

function anhangHochladenFertig(r, datei, x, y) {
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

/* Bilder im Text: im HTML steht nur data-datei, die Adresse kommt beim Anzeigen
 * dazu. So bleibt der Verweis gueltig, wenn die Seite umbenannt wird. */
function textBilderZeigen(text) {
  for (const b of text.querySelectorAll('img[data-datei]')) {
    b.src = anhangWeg(b.dataset.datei);
    b.addEventListener('load', flaecheMessen, { once: true });
  }
}

async function inTextEinsetzen(text, e, dateien, stelle) {
  for (const d of dateien) {
    const r = await hochladen(d);
    if (!r) continue;
    if (r.art !== 'bild') {
      // Keine Bilder (PDF, Zip ...) bleiben Kacheln auf der Flaeche.
      anhangHochladenFertig(r, d, e.x, e.y + text.offsetHeight + 40);
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
  flaeche.style.width = Math.max(b + 600, buehne.clientWidth / zoom) + 'px';
  flaeche.style.height = Math.max(h + 600, buehne.clientHeight / zoom) + 'px';
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
  } catch (f) { /* Server weg - beim naechsten Mal wieder */ }
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
  if (ev.code === 'Space' && !ev.target.closest('[contenteditable], input')) { leertaste = true; ev.preventDefault(); }
  if ((ev.ctrlKey || ev.metaKey) && ev.key === 's') { ev.preventDefault(); speichernJetzt(); }
  if ((ev.ctrlKey || ev.metaKey) && (ev.key === '+' || ev.key === '=')) { ev.preventDefault(); zoomen(0.1); }
  if ((ev.ctrlKey || ev.metaKey) && ev.key === '-') { ev.preventDefault(); zoomen(-0.1); }
  if ((ev.ctrlKey || ev.metaKey) && ev.key === '0') { ev.preventDefault(); zoomSetzen(1); }
});
document.addEventListener('keyup', (ev) => { if (ev.code === 'Space') leertaste = false; });

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
  await speichernJetzt();
  if (schmutzig) return;      // ungespeichert umbenennen gaebe gleich den naechsten Konflikt
  const r = await api('/api/seite/titel', 'POST', {
    notizbuch: offen.notizbuch, abschnitt: offen.abschnitt, name: offen.name, titel: $('#titel').value,
  });
  // Der Dateiname zieht mit dem Titel mit, also muss die Seite neu geladen werden.
  await seiteOeffnen(offen.notizbuch, offen.abschnitt, r.name);
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
    updateKnopf.textContent = `Version ${v.verfuegbar} laden`;
    updateKnopf.title = `Installiert ist ${v.installiert}.` + (v.notizen ? '\n\n' + v.notizen.slice(0, 500) : '');
    return v;
  } catch (f) { updateKnopf.hidden = true; }
}

updateKnopf.addEventListener('click', async () => {
  const v = await api('/api/version');
  if (!confirm(`Version ${v.verfuegbar} einspielen? Installiert ist ${v.installiert}.\n\n`
    + 'Die Notizen bleiben unberührt. Der Dienst startet dabei neu, die Seite ist kurz weg.')) return;
  updateKnopf.disabled = true;
  updateKnopf.textContent = 'lädt …';
  if (schmutzig) await speichernJetzt();
  try {
    const r = await api('/api/update', 'POST');
    melden(`Update ${r.von} → ${r.nach} läuft. Die Seite lädt sich neu, sobald der Dienst wieder da ist.`);
    updateVerfolgen(r.nach);
  } catch (f) {
    updateKnopf.disabled = false;
    updateKnopf.textContent = 'Update fehlgeschlagen';
    melden('Update ging nicht: ' + f.message, [['Nochmal versuchen', () => versionPruefen(true)]]);
  }
});

/* Waehrend des Updates startet der Dienst neu - die Abfragen laufen also eine
 * Weile ins Leere. Das ist kein Fehler, sondern genau der Moment. */
function updateVerfolgen(ziel) {
  let versuche = 0;
  const uhr = setInterval(async () => {
    versuche++;
    try {
      const v = await api('/api/version');
      if (v.installiert === ziel) {
        clearInterval(uhr);
        melden(`Version ${ziel} ist da. Seite wird neu geladen …`);
        setTimeout(() => location.reload(), 1200);
        return;
      }
      const p = await api('/api/update/stand');
      if (p.fehler) {
        clearInterval(uhr);
        melden('Das Update ist auf einen Fehler gelaufen:', [['Protokoll zeigen', () => alert(p.text)]]);
      }
    } catch (f) { /* Dienst gerade weg - weiter warten */ }
    if (versuche > 60) {   // 3 Minuten
      clearInterval(uhr);
      melden('Das Update dauert ungewöhnlich lange. Protokoll: ~/.local/share/notizmappe/.update.log');
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

  melden(`Version ${v.verfuegbar} wird eingespielt …`);
  try {
    const r = await api('/api/update', 'POST');
    updateVerfolgen(r.nach);
  } catch (f) {
    melden('Das Update beim Start ging nicht: ' + f.message
      + ' — über das Zahnrad kann man es von Hand versuchen.');
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
    $('#e-start-pruefen').checked = !!(e.optionen && e.optionen.beim_start_pruefen);
    $('#e-auto').checked = !!(e.optionen && e.optionen.automatisch_einspielen);
    for (const kasten of [$('#e-start-pruefen'), $('#e-auto')]) kasten.disabled = !e.hier;
  } catch (f) {
    $('#e-lage').textContent = 'Einstellungen ließen sich nicht laden: ' + f.message;
  }
  await kontoTeileLaden();
  updateAnzeigen(await versionPruefen());
}

function updateAnzeigen(v) {
  if (!v) return;
  $('#e-verfuegbar').textContent = v.fehler ? '—' : (v.verfuegbar || 'unbekannt');
  $('#e-notizen').hidden = !v.notizen || !v.neuer;
  if (v.notizen) $('#e-notizen').textContent = v.notizen;
  $('#e-einspielen').hidden = !(v.neuer && v.aktualisierbar);
  $('#e-updatehinweis').textContent = v.fehler ? v.fehler
    : v.neuer ? (v.aktualisierbar ? `Version ${v.verfuegbar} kann eingespielt werden.`
                                  : 'Neuere Fassung da, aber hier nicht einspielbar.')
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
  $('#e-updatehinweis').textContent = 'wird geprüft …';
  updateAnzeigen(await versionPruefen(true));
});

$('#e-einspielen').addEventListener('click', () => $('#update').click());

$('#e-zoom-rein').addEventListener('click', () => { zoomen(0.1); $('#e-zoom').textContent = Math.round(zoom * 100) + ' %'; });
$('#e-zoom-raus').addEventListener('click', () => { zoomen(-0.1); $('#e-zoom').textContent = Math.round(zoom * 100) + ' %'; });
$('#e-zoom-zurueck').addEventListener('click', () => { zoomSetzen(1); $('#e-zoom').textContent = '100 %'; });

/* ------------------------------------------------------------------ Anlauf */

(async () => {
  zoomSetzen(parseFloat(merker.holen('zoom', '1')));
  try {
    await baumLaden();
  } catch (f) {
    // Z. B. Datenordner auf einem nicht eingehaengten Laufwerk: sagen, was los ist,
    // statt eine leere Flaeche zu zeigen - und nichts anlegen.
    melden(f.message, [['Einstellungen', () => tafelZeigen(true)]]);
    return;
  }
  // Nicht nur beim ganz leeren Datenordner: auch ein Notizbuch ohne Abschnitte oder
  // ein Abschnitt ohne Seiten lässt einen vor einer Fläche sitzen, auf der sich
  // nichts schreiben lässt - und nichts sagt einem, warum.
  let wer = null;
  try { wer = await api('/api/ich'); } catch (f) { /* dann wie bisher */ }
  if (!erstesSeitchen() && wer && wer.server) {
    // Auf dem Server nichts von selbst anlegen: ein neues Mitglied ohne Freigabe
    // bekaeme sonst ein leeres eigenes Notizbuch, und in ein geteiltes Projekt
    // ohne Abschnitte wuerde ungefragt einer geschrieben.
    melden(baumDaten.length
      ? 'Hier gibt es noch keine Seite. Mit ＋ am Notizbuch einen Abschnitt anlegen, dann eine Seite.'
      : 'Dir ist noch kein Projekt freigegeben. Frag einen Admin - oder lege unten mit „+ Notizbuch“ ein eigenes an.');
  } else if (!erstesSeitchen()) {
    const buch = baumDaten[0] ? baumDaten[0].name
      : (await api('/api/notizbuch', 'POST', { name: 'Notizbuch' })).name;
    const ab = (baumDaten[0] && baumDaten[0].abschnitte[0]) ? baumDaten[0].abschnitte[0].name
      : (await api('/api/abschnitt', 'POST', { notizbuch: buch, name: 'Allgemein' })).name;
    await api('/api/seite', 'POST', { notizbuch: buch, abschnitt: ab, titel: 'Erste Seite' });
    await baumLaden();
  }
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

/* ------------------------------------------------------- Anmeldung und Sperre */

let ich = null;
let amRechner = false;     // Einstellungen direkt am Rechner geoeffnet, auf dem die Mappe laeuft
let ruheUhr = null;

async function ichLaden() {
  try { ich = await api('/api/ich'); } catch (f) { ich = null; }
  const knopf = $('#sperren');
  knopf.hidden = !(ich && ich.anmeldung && ich.name);
  if (ich && ich.server) { knopf.textContent = '⎋'; knopf.title = `Abmelden (${ich.name})`; }
  ruheStellen();
  return ich;
}

async function sperrenJetzt() {
  if (schmutzig) { try { await speichernJetzt(); } catch (f) { /* Meldung kommt von dort */ } }
  if (schmutzig) return;        // nicht wegsperren, solange etwas ungespeichert ist
  try { await api('/api/abmelden', 'POST'); } catch (f) { /* trotzdem weiter */ }
  location.href = '/anmelden';
}
$('#sperren').addEventListener('click', sperrenJetzt);

/* Sperre nach X Minuten ohne Benutzung - nur auf dem eigenen Rechner. Im Browser
 * am Server bleibt man angemeldet, bis man sich abmeldet. */
function ruheStellen() {
  clearTimeout(ruheUhr);
  if (!ich || !ich.anmeldung || ich.server || !ich.name || !ich.sperre_minuten) return;
  ruheUhr = setTimeout(sperrenJetzt, ich.sperre_minuten * 60 * 1000);
}
let ruheZuletzt = 0;
for (const art of ['pointerdown', 'keydown', 'wheel', 'pointermove']) {
  document.addEventListener(art, () => {
    const jetzt = Date.now();
    if (jetzt - ruheZuletzt < 5000) return;     // nicht bei jeder Mausbewegung neu stellen
    ruheZuletzt = jetzt;
    ruheStellen();
  }, { passive: true, capture: true });
}

function eintrag(...kinder) {
  const d = document.createElement('div');
  d.className = 'eintrag';
  d.append(...kinder);
  return d;
}
function knopf(text, tun) {
  const b = Object.assign(document.createElement('button'), { type: 'button', textContent: text });
  b.addEventListener('click', tun);
  return b;
}

async function kontoTeileLaden() {
  await ichLaden();
  const lokalAdmin = !!(ich && !ich.server && ich.admin && amRechner);
  // Sperre: nur am eigenen Rechner und solange es hoechstens das eine Konto gibt.
  $('#e-sperre-teil').hidden = !(ich && !ich.server && ich.admin);
  $('#e-sperre-aus').hidden = !!(ich && ich.anmeldung);
  $('#e-sperre-ein').hidden = !(ich && ich.anmeldung);
  if (ich) $('#e-sperre-min').value = ich.sperre_minuten;
  if (!lokalAdmin && ich && !ich.anmeldung) {
    $('#e-sperre-hinweis').textContent = 'Die Sperre lässt sich nur direkt an diesem Rechner einschalten.';
  }

  $('#e-konto-teil').hidden = !(ich && ich.anmeldung && ich.name);
  if (ich && ich.name) {
    $('#e-ich').textContent = ich.name + (ich.admin ? ' (Admin)' : '');
    const g = $('#e-geraete');
    g.textContent = '';
    if (ich.geraete.length) {
      g.append(Object.assign(document.createElement('p'), { className: 'hinweis', textContent: 'Angemeldete Desktop-Geräte:' }));
      for (const d of ich.geraete) {
        g.append(eintrag(
          Object.assign(document.createElement('strong'), { textContent: d.geraet }),
          Object.assign(document.createElement('span'), { className: 'hinweis', textContent: 'seit ' + new Date(d.seit * 1000).toLocaleDateString('de-DE') }),
          knopf('Abmelden', async () => { await api('/api/ich/geraete/entfernen', 'POST', { id: d.id }); kontoTeileLaden(); }),
        ));
      }
    }
  }

  $('#e-konten-teil').hidden = !(ich && ich.anmeldung && ich.admin);
  if (ich && ich.anmeldung && ich.admin) await kontenLaden();

  // Verbindungen zu Servern: nur in der Desktop-Fassung am eigenen Rechner.
  $('#e-server-teil').hidden = !lokalAdmin;
  if (lokalAdmin) await verbindungenLaden();
}

async function verbindungenLaden() {
  let d;
  try { d = await api('/api/verbindungen'); } catch (f) { $('#e-srv-hinweis').textContent = f.message; return; }
  const liste = $('#e-verbindungen');
  liste.textContent = '';
  for (const v of d.verbindungen) {
    liste.append(eintrag(
      Object.assign(document.createElement('strong'), { textContent: v.adresse.replace(/^https?:\/\//, '') }),
      Object.assign(document.createElement('span'), { className: 'hinweis', textContent: v.name }),
      knopf('Öffnen', () => verbindungOeffnen(v.id)),
      knopf('Entfernen', async () => { await api('/api/verbindungen/entfernen', 'POST', { id: v.id }); verbindungenLaden(); }),
    ));
  }
}

async function verbindungOeffnen(id) {
  try {
    const r = await api('/api/verbindungen/oeffnen', 'POST', { id });
    if (!r.fenster) window.open(r.weg, '_blank', 'noopener');
    else sagen('Fenster geht auf …');
  } catch (f) { $('#e-srv-hinweis').textContent = f.message; }
}

$('#e-srv-verbinden').addEventListener('click', async () => {
  const knopfV = $('#e-srv-verbinden');
  knopfV.disabled = true;
  $('#e-srv-hinweis').textContent = 'Verbinde …';
  try {
    const v = await api('/api/verbindungen', 'POST', {
      adresse: $('#e-srv-adresse').value, name: $('#e-srv-name').value, passwort: $('#e-srv-pw').value,
    });
    $('#e-srv-pw').value = '';
    $('#e-srv-hinweis').textContent = `Verbunden mit ${v.adresse} als ${v.name}.`;
    await verbindungenLaden();
    verbindungOeffnen(v.id);
  } catch (f) {
    $('#e-srv-hinweis').textContent = f.message;
  }
  knopfV.disabled = false;
});

async function kontenLaden() {
  let d;
  try { d = await api('/api/konten'); } catch (f) { $('#e-konten-hinweis').textContent = f.message; return; }
  const liste = $('#e-kontenliste');
  liste.textContent = '';
  for (const k of d.konten) {
    const admin = Object.assign(document.createElement('input'), { type: 'checkbox', checked: k.admin });
    admin.addEventListener('change', () => kontoTun('/api/konten/admin', { name: k.name, admin: admin.checked }));
    const pw = Object.assign(document.createElement('input'), { type: 'password', placeholder: 'neues Passwort', autocomplete: 'new-password' });
    const istIch = k.name === ich.name;
    admin.disabled = istIch;
    const zeile = eintrag(
      Object.assign(document.createElement('strong'), { textContent: k.name + (istIch ? ' (du)' : '') }),
      Object.assign(document.createElement('label'), { className: 'haken' }),
      pw,
      knopf('Setzen', () => { if (pw.value) kontoTun('/api/konten/passwort', { name: k.name, passwort: pw.value }, 'Passwort gesetzt'); }),
    );
    zeile.children[1].append(admin, ' Admin');
    if (!istIch) zeile.append(knopf('Löschen', () => kontoTun('/api/konten/loeschen', { name: k.name }, 'Konto gelöscht')));
    liste.append(zeile);
  }

  const projekte = $('#e-projekte');
  projekte.textContent = '';
  const normale = d.konten.filter((k) => !k.admin);
  if (!d.projekte.length) projekte.append(Object.assign(document.createElement('p'), { className: 'hinweis', textContent: 'Noch keine Notizbücher.' }));
  for (const pr of d.projekte) {
    const haken = document.createElement('div');
    haken.className = 'mitglieder';
    if (!normale.length) haken.append(Object.assign(document.createElement('span'), { className: 'hinweis', textContent: 'nur Admins' }));
    for (const k of normale) {
      const h = Object.assign(document.createElement('input'), { type: 'checkbox', checked: pr.mitglieder.includes(k.name) });
      h.addEventListener('change', () => {
        const drin = [...haken.querySelectorAll('input')].filter((x) => x.checked).map((x) => x.dataset.name);
        kontoTun('/api/zugriff', { notizbuch: pr.notizbuch, mitglieder: drin }, 'Gespeichert', false);
      });
      h.dataset.name = k.name;
      const l = document.createElement('label');
      l.append(h, ' ' + k.name);
      haken.append(l);
    }
    projekte.append(eintrag(Object.assign(document.createElement('strong'), { textContent: pr.notizbuch }), haken));
  }
}

async function kontoTun(weg, rumpf, erfolg = 'Gespeichert', neuLaden = true) {
  try {
    await api(weg, 'POST', rumpf);
    $('#e-konten-hinweis').textContent = erfolg;
  } catch (f) {
    $('#e-konten-hinweis').textContent = f.message;
  }
  if (neuLaden) kontenLaden();
}

$('#e-konto-anlegen').addEventListener('click', async () => {
  try {
    await api('/api/konten', 'POST', {
      name: $('#e-neu-name').value, passwort: $('#e-neu-pw').value, admin: $('#e-neu-admin').checked,
    });
    $('#e-neu-name').value = ''; $('#e-neu-pw').value = ''; $('#e-neu-admin').checked = false;
    $('#e-konten-hinweis').textContent = 'Konto angelegt';
    kontenLaden();
  } catch (f) { $('#e-konten-hinweis').textContent = f.message; }
});

$('#e-pw-aendern').addEventListener('click', async () => {
  try {
    await api('/api/ich/passwort', 'POST', { alt: $('#e-pw-alt').value, neu: $('#e-pw-neu').value });
    $('#e-pw-alt').value = ''; $('#e-pw-neu').value = '';
    $('#e-konto-hinweis').textContent = 'Passwort geändert. Andere Geräte sind jetzt abgemeldet.';
    kontoTeileLaden();
  } catch (f) { $('#e-konto-hinweis').textContent = f.message; }
});
$('#e-abmelden').addEventListener('click', sperrenJetzt);

$('#e-sperre-an').addEventListener('click', async () => {
  const pw = $('#e-sperre-pw').value;
  if (pw !== $('#e-sperre-pw2').value) { $('#e-sperre-hinweis').textContent = 'Die beiden Passwörter sind nicht gleich.'; return; }
  try {
    await api('/api/sperre', 'POST', { passwort: pw });
    $('#e-sperre-pw').value = ''; $('#e-sperre-pw2').value = '';
    $('#e-sperre-hinweis').textContent = 'Sperre ist an. Beim nächsten Start fragt die Notizmappe nach dem Passwort.';
    kontoTeileLaden();
  } catch (f) { $('#e-sperre-hinweis').textContent = f.message; }
});
$('#e-sperre-min').addEventListener('change', async () => {
  try {
    const r = await api('/api/sperre/zeit', 'POST', { minuten: Number($('#e-sperre-min').value) });
    if (ich) ich.sperre_minuten = r.sperre_minuten;
    ruheStellen();
    $('#e-sperre-hinweis').textContent = r.sperre_minuten ? `Sperrt nach ${r.sperre_minuten} Minuten ohne Benutzung.` : 'Sperrt nur noch beim Start.';
  } catch (f) { $('#e-sperre-hinweis').textContent = f.message; }
});
$('#e-sperre-jetzt').addEventListener('click', sperrenJetzt);
$('#e-sperre-weg').addEventListener('click', () => { $('#e-sperre-weg-frage').hidden = false; $('#e-sperre-weg-pw').focus(); });
$('#e-sperre-weg-ok').addEventListener('click', async () => {
  try {
    await api('/api/sperre/aus', 'POST', { passwort: $('#e-sperre-weg-pw').value });
    $('#e-sperre-weg-pw').value = ''; $('#e-sperre-weg-frage').hidden = true;
    $('#e-sperre-hinweis').textContent = 'Sperre ist aus.';
    kontoTeileLaden();
  } catch (f) { $('#e-sperre-hinweis').textContent = f.message; }
});

ichLaden();
