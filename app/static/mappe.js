/* Notizmappe - freie Flaeche. Kein Framework, damit es ohne Build laeuft.
 *
 * Grundgedanke: die Seite ist eine Liste von Kaesten mit x/y/Breite. Der Browser
 * haelt sie in `elemente`, der Server kennt nur das JSON. Gespeichert wird
 * verzoegert, aber immer die ganze Seite - bei einer Handvoll Kaesten pro Seite
 * ist das billiger als Einzelfeld-Buchhaltung. */

const WARTEN = 900;        // ms Ruhe nach der letzten Eingabe, bevor gespeichert wird
const POLL = 15000;        // ms zwischen "hat jemand von aussen geschrieben?"
const RASTER = 8;          // Positionen auf 8px runden, sonst zappelt alles

const geraet = (() => {
  let g = localStorage.getItem('geraet');
  if (!g) { g = Math.random().toString(36).slice(2, 10); localStorage.setItem('geraet', g); }
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
const zugeklappt = new Set(JSON.parse(localStorage.getItem('zugeklappt') || '[]'));

/* ------------------------------------------------------------------ Hilfen */

async function api(weg, art = 'GET', rumpf = null) {
  const o = { method: art, headers: {} };
  if (rumpf) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(rumpf); }
  const a = await fetch(weg, o);
  let daten = null;
  try { daten = await a.json(); } catch (e) { /* leere Antwort */ }
  if (!a.ok) { const f = new Error((daten && daten.fehler) || a.statusText); f.status = a.status; f.daten = daten; throw f; }
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
  localStorage.setItem('zugeklappt', JSON.stringify([...zugeklappt]));
  knoten.querySelector('.pfeil').textContent = knoten.classList.contains('eingeklappt') ? '▸' : '▾';
}

async function loeschen(art, pfad, wie) {
  if (!confirm(`"${wie}" in den Papierkorb?`)) return;
  await api('/api/loeschen', 'POST', { art, pfad });
  if (art === 'seite' && offen && offen.name === pfad[2]) { offen = null; flaecheLeeren(); }
  await baumLaden();
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
  localStorage.setItem('zuletzt', JSON.stringify({ buch, abschnitt, name: s.name }));
}

/* ------------------------------------------------------------------ Kaesten */

function kastenBauen(e) {
  const k = document.createElement('div');
  k.className = 'kasten';
  k.dataset.id = e.id;
  k.style.left = e.x + 'px';
  k.style.top = e.y + 'px';
  k.style.width = e.b + 'px';

  const griff = document.createElement('div');
  griff.className = 'griff';
  const weg = Object.assign(document.createElement('button'), { type: 'button', className: 'weg', textContent: '✕', title: 'Kasten löschen' });
  weg.addEventListener('click', () => kastenWeg(e.id));
  griff.append(weg);

  const text = document.createElement('div');
  text.className = 'text';
  text.contentEditable = 'true';
  text.spellcheck = true;
  text.innerHTML = e.html || '';

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

function ziehen(handgriff, bewegen, startWerte) {
  handgriff.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0) return;
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

function angefasst() {
  schmutzig = true;
  zustandAnzeige.textContent = '…';
  clearTimeout(speicherUhr);
  speicherUhr = setTimeout(speichernJetzt, WARTEN);
}

async function speichernJetzt() {
  clearTimeout(speicherUhr);
  if (!offen || !schmutzig) return;
  const stand = { ...offen };
  try {
    const r = await api('/api/seite', 'PUT', {
      notizbuch: stand.notizbuch, abschnitt: stand.abschnitt, name: stand.name,
      rev: stand.rev, titel: $('#titel').value, elemente, geraet,
    });
    if (offen && offen.name === stand.name) { offen.rev = r.rev; offen.mtime = r.mtime; }
    schmutzig = false;
    sagen('gespeichert');
  } catch (f) {
    if (f.status === 409) { konflikt(f.daten && f.daten.aktuell); return; }
    zustandAnzeige.textContent = 'nicht gespeichert';
    melden('Speichern ging nicht: ' + f.message, [['Nochmal', () => { schmutzig = true; speichernJetzt(); }]]);
  }
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

/* ------------------------------------------------------------------ Anlauf */

(async () => {
  zoomSetzen(parseFloat(localStorage.getItem('zoom') || '1'));
  await baumLaden();
  if (!baumDaten.length) {
    // Beim allerersten Start etwas zum Draufklicken hinstellen.
    await api('/api/notizbuch', 'POST', { name: 'Notizbuch' });
    await api('/api/abschnitt', 'POST', { notizbuch: 'Notizbuch', name: 'Allgemein' });
    await api('/api/seite', 'POST', { notizbuch: 'Notizbuch', abschnitt: 'Allgemein', titel: 'Erste Seite' });
    await baumLaden();
  }
  try {
    const z = JSON.parse(localStorage.getItem('zuletzt') || 'null');
    if (z) await seiteOeffnen(z.buch, z.abschnitt, z.name);
  } catch (f) {
    const b = baumDaten[0], a = b && b.abschnitte[0], s = a && a.seiten[0];
    if (s) await seiteOeffnen(b.name, a.name, s.name);
  }
})();
