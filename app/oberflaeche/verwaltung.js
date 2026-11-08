/* Einen Server verwalten - in beiden Fassungen dieselbe Oberfläche.
 *
 * Benutzer, Einladungen, Projekte, Rollen, Mailversand, Datenablage und der
 * Name der Mappe. Das gibt es nur, wenn ein Server da ist: im Browser immer,
 * im Fenster, sobald es mit einem verbunden ist.
 *
 * Die Datei lag bis 1.2.28 in shim.js und damit nur im Browser. Wer vom
 * Fenster aus an seinem Server etwas einstellen wollte, musste ihn im
 * Browser aufmachen. Nachbauen wäre die falsche Antwort gewesen - zwei
 * Oberflächen für dieselbe Sache laufen auseinander, sobald eine von beiden
 * angefasst wird. Also liegt sie jetzt hier, bei der übrigen Oberfläche, und
 * beide Fassungen laden dieselbe Datei.
 *
 * Der einzige Unterschied ist der Weg zum Server:
 *
 *   Browser   fetch() auf denselben Rechner, mit dem Sitzungs-Keks.
 *             shim.js legt den Weg unter window.NOTIZMAPPE_HOL ab.
 *   Fenster   über die Brücke: bruecke.server_seite() -> ferne.serverseite().
 *             Dort liegt der Keks, nicht im Fenster. Welche Wege gehen,
 *             steht in ferne.SERVERSEITEN - eine feste Liste, kein
 *             Durchreichen beliebiger Adressen.
 *
 * Geladen wird die Datei **nach** mappe.js: sie benutzt deren api() und
 * melden(). shim.js dagegen wird davor geladen (der Stellvertreter für
 * window.pywebview muss stehen, bevor mappe.js ihn sucht) - deshalb steht
 * hier nichts, was shim.js bräuchte, und hier oben nichts, was erst später
 * entsteht.
 */
(function () {
  'use strict';

  /* Eigene kleine Helfer statt der aus mappe.js: diese Datei soll auch dann
     noch aufgehen, wenn dort etwas umbenannt wird. Es sind vier Zeilen. */
  function el(art, eigenschaften, kinder) {
    const k = document.createElement(art);
    Object.assign(k, eigenschaften || {});
    for (const kind of kinder || []) k.append(kind);
    return k;
  }

  /* Eine Meldung in der Verwaltung - nicht in der Statuszeile: wer hier
     etwas einstellt, schaut hierher. */
  function sagen(text) {
    const p = document.getElementById('v-meldung');
    if (p) p.textContent = text;
  }

  /* Der Weg zum Server. Im Browser legt shim.js ihn hin; im Fenster geht es
     über die Brücke, und ein Aufruf mit Rumpf ist ein POST - genau wie dort. */
  async function hol(weg, rumpf) {
    if (typeof window.NOTIZMAPPE_HOL === 'function') return window.NOTIZMAPPE_HOL(weg, rumpf);
    if (typeof window.serverHol !== 'function') throw new Error('Kein Server verbunden');
    return window.serverHol(rumpf ? 'POST' : 'GET', weg, rumpf || {});
  }

  /* "Zwei Schritte beim Anmelden" steht nicht hier, sondern in der Fassung,
     die gerade läuft - im Browser in shim.js, im Fenster in mappe.js. Die
     Verwaltung stößt es nur an. */
  function zweiLaden() {
    if (typeof window.NOTIZMAPPE_ZWEI_LADEN === 'function') window.NOTIZMAPPE_ZWEI_LADEN();
  }

  /* Die Bereichswahl oben im Band gibt es nur im Browser - im Fenster ist
     der Datenordner der Bereich. Ein neu angelegtes Projekt gehoert aber
     sofort in die Liste, sonst muesste man neu laden. */
  function bereicheFrischen() {
    if (typeof window.NOTIZMAPPE_BEREICHE === 'function') window.NOTIZMAPPE_BEREICHE();
  }

  /* Die Systemseite der Einstellungen. Hieß bis 1.2.0 "konto"; der Schlüssel
     ist "server" geblieben, umbenannt wurde nur die Beschriftung. */
  function systemseite() {
    return document.querySelector('.dateiseite[data-punkt="server"]');
  }

  let verwaltungStand = null;

  async function verwaltungLaden() {
    const abschnitt = document.getElementById('serververwaltung');
    if (!abschnitt) return;
    let d;
    try { d = await hol('/verwaltung'); } catch (f) { sagen(f.message); return; }
    verwaltungStand = d;
    abschnitt.hidden = false;           // "Zwei Schritte" geht jeden etwas an
    for (const id of ['v-benutzer', 'v-rollen', 'v-einladungen']) {
      const k = document.getElementById(id);
      if (k) k.hidden = !d.darf;
    }
    for (const h of abschnitt.querySelectorAll('h3')) {
      const nurVerwalter = ['Benutzer und Rollen', 'Einladen', 'Was die Rollen bedeuten',
                            'Name dieser Mappe']
        .indexOf(h.textContent) >= 0;
      h.hidden = nurVerwalter && !d.darf;
      // Seit die Verwaltung in Reiter zerlegt ist, haengt an jeder
      // Ueberschrift ein ganzer Unterabschnitt. Nur die Ueberschrift zu
      // verstecken liess die Eingabefelder darunter stehen - fuer jemanden,
      // der sie gar nicht benutzen darf.
      const teil = h.parentElement;
      if (teil && teil !== abschnitt && teil.tagName === 'SECTION') {
        teil.hidden = nurVerwalter && !d.darf;
      }
    }
    const wie = document.getElementById('v-mappe');
    if (wie && document.activeElement !== wie) {
      wie.value = d.mappe || '';
      // Leeres Feld heisst nicht "kein Name", sondern "der Standard" - und
      // der steht dann blass im Feld, damit man weiss, was drinsteht.
      wie.placeholder = d.mappe_jetzt || 'z. B. Servermappe';
    }
    zweiLaden();
    zeichneProjekte(d);
    if (!d.darf) return;            // Projekte darf man auch ohne Benutzerverwaltung sehen
    zeichneBenutzer(d);
    zeichneEinladungen(d);
    zeichneRollen(d);
  }

  function zeichneBenutzer(d) {
    const wo = document.getElementById('v-benutzer');
    wo.textContent = '';
    for (const b of d.benutzer) {
      const auswahl = el('select', { title: 'Rolle' });
      for (const r of d.rollen) {
        auswahl.append(el('option', { value: r.name, textContent: r.name, selected: r.name === b.rolle }));
      }
      auswahl.addEventListener('change', async () => {
        try {
          await hol('/verwaltung/benutzer', { was: 'rolle', name: b.name, rolle: auswahl.value });
          sagen(`${b.name} ist jetzt „${auswahl.value}“.`);
          verwaltungLaden();
        } catch (f) { sagen(f.message); verwaltungLaden(); }
      });
      const raus = el('button', { type: 'button', textContent: 'Entfernen' });
      raus.addEventListener('click', async () => {
        if (!confirm(`Zugang „${b.name}“ entfernen? Die Notizen bleiben liegen.`)) return;
        try {
          await hol('/verwaltung/benutzer', { was: 'entfernen', name: b.name });
          sagen(`Zugang ${b.name} entfernt. Die Notizen liegen weiter im Datenordner.`);
          verwaltungLaden();
        } catch (f) { sagen(f.message); }
      });
      const neuespw = el('button', { type: 'button', textContent: 'Passwort setzen' });
      neuespw.addEventListener('click', async () => {
        const pw = prompt(`Neues Passwort für ${b.name} (mind. 8 Zeichen):`);
        if (!pw) return;
        try {
          await hol('/verwaltung/benutzer', { was: 'passwort', name: b.name, passwort: pw });
          sagen(`Passwort für ${b.name} gesetzt - offene Sitzungen enden damit.`);
        } catch (f) { sagen(f.message); }
      });
      wo.append(el('p', { className: 'zeile2' }, [
        el('span', { textContent: b.name + (b.name === d.ich ? ' (du)' : '')
          + (b.zuletzt ? ' · zuletzt ' + b.zuletzt : ' · noch nie angemeldet') }),
        el('span', {}, [auswahl, neuespw, ...(b.name === d.ich ? [] : [raus])]),
      ]));
    }
  }

  function zeichneEinladungen(d) {
    const wo = document.getElementById('v-einladungen');
    if (!wo) return;
    wo.textContent = '';
    for (const e of d.einladungen || []) {
      const rest = Math.max(0, Math.round(e.bis - Date.now() / 1000));
      const weg = el('button', { type: 'button', textContent: 'zurücknehmen' });
      weg.addEventListener('click', async () => {
        try {
          await hol('/verwaltung/einladung', { was: 'zuruecknehmen', marke: e.marke });
          verwaltungLaden();
        } catch (f) { sagen(f.message); }
      });
      wo.append(el('p', { className: 'zeile2' }, [
        el('span', { textContent: `${e.rolle}${e.projekt ? ' · ' + e.projekt : ''} — `
          + `noch ${Math.floor(rest / 60)}:${String(rest % 60).padStart(2, '0')}` }),
        el('span', {}, [weg]),
      ]));
    }
  }

  function zeichneProjekte(d) {
    const wo = document.getElementById('v-projekte');
    if (!wo) return;
    wo.textContent = '';
    for (const pr of d.projekte || []) {
      const meins = pr.mitglieder[d.ich];
      const darf = d.darf_projekte || meins === 'verwalten';
      const zeilen = Object.entries(pr.mitglieder).map(([wer, recht]) => {
        const auswahl = el('select', {});
        for (const r of d.projektrechte) {
          auswahl.append(el('option', { value: r, textContent: r, selected: r === recht }));
        }
        auswahl.disabled = !darf;
        auswahl.addEventListener('change', async () => {
          try {
            await hol('/verwaltung/projekt', { was: 'mitglied', projekt: pr.name,
                                               benutzer: wer, recht: auswahl.value });
            verwaltungLaden();
          } catch (f) { sagen(f.message); verwaltungLaden(); }
        });
        const raus = el('button', { type: 'button', textContent: 'raus' });
        raus.disabled = !darf;
        raus.addEventListener('click', async () => {
          try {
            await hol('/verwaltung/projekt', { was: 'mitglied-raus', projekt: pr.name, benutzer: wer });
            verwaltungLaden();
          } catch (f) { sagen(f.message); }
        });
        return el('p', { className: 'zeile2' }, [
          el('span', { textContent: wer }), el('span', {}, [auswahl, raus])]);
      });

      const dazu = el('select', {});
      for (const b of d.benutzer || []) {
        if (!(b.name in pr.mitglieder)) dazu.append(el('option', { value: b.name, textContent: b.name }));
      }
      const dazuRecht = el('select', {});
      for (const r of d.projektrechte) dazuRecht.append(el('option', { value: r, textContent: r }));
      const dazuKnopf = el('button', { type: 'button', textContent: 'dazunehmen' });
      dazuKnopf.disabled = !darf;
      dazuKnopf.addEventListener('click', async () => {
        try {
          await hol('/verwaltung/projekt', { was: 'mitglied', projekt: pr.name,
                                             benutzer: dazu.value, recht: dazuRecht.value });
          verwaltungLaden();
        } catch (f) { sagen(f.message); }
      });
      const weg = el('button', { type: 'button', textContent: 'Projekt entfernen' });
      weg.disabled = !darf;
      weg.addEventListener('click', async () => {
        if (!confirm(`Projekt „${pr.name}" entfernen? Die Notizen darin bleiben liegen.`)) return;
        try {
          await hol('/verwaltung/projekt', { was: 'entfernen', projekt: pr.name });
          verwaltungLaden();
        } catch (f) { sagen(f.message); }
      });
      wo.append(el('div', { className: 'rollenkasten' }, [
        el('strong', { textContent: pr.name + (meins ? ` — du: ${meins}` : '') }),
        ...zeilen,
        el('p', { className: 'ordnerzeile' }, [dazu, dazuRecht, dazuKnopf]),
        el('p', { className: 'knoepfe' }, [weg]),
      ]));
    }
  }

  function zeichneRollen(d) {
    // Keine Haken zum Selberbauen mehr: es gibt drei Rollen, und hier steht
    // nur, wofür sie da sind. Wer feiner steuern will, wer was darf, stellt
    // das im Projekt ein - dort gehört es hin.
    const wo = document.getElementById('v-rollen');
    if (!wo) return;
    wo.textContent = '';
    for (const r of d.rollen || []) {
      wo.append(el('p', { className: 'zeile2' }, [
        el('strong', { textContent: r.name }),
        el('span', { className: 'rollenwozu', textContent: r.erklaerung }),
      ]));
    }
  }

  /* Die Server-Einstellungen gehoeren in die Tafel der Optionen - dorthin, wo
     auch "Daten", "Schriften" und "Fenster" stehen. Sie stehen oben in einem
     eigenen Kasten: was nur dieser Server kann, soll man zuerst sehen und
     nicht unter den Hinweisen suchen, die am Server nichts tun. */
  function optionentafel() {
    const seite = document.querySelector('.dateiseite[data-punkt="optionen"]');
    if (!seite) return null;
    return seite.querySelector('#einstellungen .tafel') || seite;
  }

  /* Eigene Abschnitte kommen vor die der Oberflaeche: was nur dieser Server
     kann, soll vor Daten, Schriften und Fenster stehen. */
  function optionAnhaengen(abschnitt) {
    const tafel = optionentafel();
    if (!tafel) return null;
    abschnitt.dataset.eigen = 'ja';
    const fremd = Array.from(tafel.children).find(
      (k) => k.tagName === 'SECTION' && !k.dataset.eigen);
    tafel.insertBefore(abschnitt, fremd || null);
    return abschnitt;
  }

  /* --------------------------------------------- Reiter in den Einstellungen

     Alles in einer Spalte war ein Band von zwei Metern: Benutzer, zwei
     Schritte, Einladen, Projekte, Rollen, Mailversand, Daten, Schriften,
     Fenster - und dazwischen die Hinweise, warum etwas am Server nicht geht.
     Jetzt steht oben eine Reiterleiste und darunter genau ein Abschnitt.

     Zugedeckt wird mit einer eigenen Klasse, nicht mit hidden. hidden setzen
     hier mehrere Stellen aus eigenem Grund - die Verwaltung erst, wenn die
     Rechte da sind, "Mit einem Server verbinden" ueberhaupt nicht. Wer hidden
     traegt, bekommt keinen Reiter; wer einen bekommt, wird mit der Klasse
     zugedeckt. So treten sich die beiden nicht gegenseitig weg. */
  const REITER_WEG = 'reiterzu';
  const REITER_MERK = 'notizmappe.optionenreiter';
  // Die Ueberschriften sind Saetze, Reiter muessen kurz sein.
  const REITERNAMEN = {
    'Benutzer und Rollen': 'Benutzer',
    'Zwei Schritte beim Anmelden': 'Zwei Schritte',
    'Was die Rollen bedeuten': 'Rollen',
    'Aus OneNote übernehmen': 'OneNote',
    'Mit einem Server verbinden': 'Server',
    'Name dieser Mappe': 'Name',
  };
  let offenerReiter = null;
  try { offenerReiter = localStorage.getItem(REITER_MERK); } catch (f) { /* ohne eben nicht */ }

  /* Einen langen Abschnitt an seinen Ueberschriften zerlegen, damit jedes
     Thema einen eigenen Reiter bekommen kann. Was vor der ersten Ueberschrift
     steht, bleibt stehen - es gehoert zu keinem Thema. */
  function nachH3Teilen(abschnitt) {
    const kinder = Array.from(abschnitt.children);
    if (!kinder.some((k) => k.tagName === 'H3')) return;
    let teil = null;
    for (const kind of kinder) {
      if (kind.tagName === 'H3') {
        kind.style.marginTop = '';        // der Abstand kam vom langen Band
        teil = el('section', {});
        abschnitt.append(teil);
      }
      if (teil) teil.append(kind);
    }
  }

  /* Ein Blatt ist, was einen Reiter bekommt: ein Abschnitt mit Ueberschrift.
     Stecken in einem Abschnitt weitere, zaehlen die inneren - so bleibt
     #serververwaltung als Ganzes abschaltbar und liefert trotzdem fuenf
     Reiter. */
  function reiterblaetter(tafel) {
    const blaetter = [];
    for (const aussen of Array.from(tafel.children)) {
      if (aussen.tagName !== 'SECTION' || aussen.hidden) continue;
      const innen = Array.from(aussen.children).filter((k) => k.tagName === 'SECTION');
      if (innen.length) {
        for (const i of innen) if (!i.hidden && i.querySelector('h3')) blaetter.push(i);
      } else if (aussen.querySelector('h3')) {
        blaetter.push(aussen);
      }
    }
    return blaetter;
  }

  function optionenReiterBauen() {
    const tafel = optionentafel();
    if (!tafel) return;
    const blaetter = reiterblaetter(tafel);
    // Erst alles aufdecken: was gerade keinen Reiter hat - weil es hidden
    // traegt oder weil ein Abschnitt zerlegt wurde -, darf nicht von einer
    // alten Runde zugedeckt bleiben.
    for (const s of tafel.querySelectorAll('section')) s.classList.remove(REITER_WEG);

    let leiste = document.getElementById('optionenreiter');
    if (!leiste) {
      leiste = el('div', { id: 'optionenreiter' });
      leiste.setAttribute('role', 'tablist');
      tafel.insertBefore(leiste, tafel.children[0] || null);
    }
    leiste.textContent = '';
    leiste.hidden = blaetter.length < 2;
    if (!blaetter.length) return;

    const wie = (s) => s.querySelector('h3').textContent.trim();
    if (!blaetter.some((s) => wie(s) === offenerReiter)) offenerReiter = wie(blaetter[0]);

    for (const blatt of blaetter) {
      const schluessel = wie(blatt);
      const auf = schluessel === offenerReiter;
      if (!auf) blatt.classList.add(REITER_WEG);
      const knopf = el('button', { type: 'button',
                                   textContent: REITERNAMEN[schluessel] || schluessel });
      knopf.setAttribute('role', 'tab');
      knopf.setAttribute('aria-selected', auf ? 'true' : 'false');
      knopf.addEventListener('click', function () {
        offenerReiter = schluessel;
        try { localStorage.setItem(REITER_MERK, schluessel); } catch (f) { /* egal */ }
        optionenReiterBauen();
      });
      leiste.append(knopf);
    }
  }

  function ablageBauen() {
    const seite = systemseite();
    if (!seite || document.getElementById('ablageteil')) return;

    const art = el('select', { id: 'ablage-art' });
    for (const [wert, text] of [['lokal', 'Im Docker-Volume (Standard)'],
                                ['ordner', 'Ordner auf diesem Rechner'],
                                ['smb', 'SMB-Freigabe (NAS, Windows)'],
                                ['nfs', 'NFS-Freigabe']]) {
      art.append(el('option', { value: wert, textContent: text }));
    }
    const wirt = el('input', { type: 'text', id: 'ablage-wirt', placeholder: 'nas.fritz.box' });
    const freigabe = el('input', { type: 'text', id: 'ablage-freigabe', placeholder: 'notizmappe' });
    const pfad = el('input', { type: 'text', id: 'ablage-pfad', placeholder: '/volume1/notizmappe' });
    const benutzer = el('input', { type: 'text', id: 'ablage-benutzer',
                                   placeholder: 'Benutzer auf der NAS', autocapitalize: 'none' });
    const passwort = el('input', { type: 'password', id: 'ablage-passwort',
                                   placeholder: 'Passwort' });
    const sichern = el('button', { type: 'button', textContent: 'Speichern' });
    const stand = el('p', { id: 'ablage-stand', className: 'zeile2' });
    const hinweis = el('p', { id: 'ablage-hinweis', className: 'hinweis' });

    const zeileSmb = el('p', { className: 'ordnerzeile', id: 'ablage-smb' },
                        [freigabe, benutzer, passwort]);
    // Wer eine Freigabe hat, auf der schon anderes liegt, will seine Notizen
    // in einem Unterordner und nicht mitten hinein.
    const unter = el('input', { type: 'text', id: 'ablage-unter',
                                placeholder: 'Unterordner (optional), z. B. notizmappe' });
    const zeileUnter = el('p', { className: 'ordnerzeile', id: 'ablage-unterzeile' }, [unter]);
    const zeileNfs = el('p', { className: 'ordnerzeile', id: 'ablage-nfs' }, [pfad]);

    // Eigener Weg, weil er ohne Sonderrechte auskommt: hier wird nichts
    // eingehängt, der Server schreibt beim nächsten Start einfach dorthin.
    const ordner = el('input', { type: 'text', id: 'ablage-ordner',
                                 placeholder: '/platten/notizen' });
    const ordnerPruefen = el('button', { type: 'button', textContent: 'Ordner prüfen' });
    ordnerPruefen.addEventListener('click', async () => {
      hinweis.textContent = 'wird geprüft …';
      try {
        const d = await hol('/ablage/pruefen', { pfad: ordner.value });
        hinweis.textContent = d.text;
      } catch (f) { hinweis.textContent = f.message; }
    });
    const zeileOrdner = el('p', { className: 'ordnerzeile', id: 'ablage-ordnerzeile' },
                           [ordner, ordnerPruefen]);

    function zeigen() {
      const a = art.value;
      wirt.hidden = a === 'lokal' || a === 'ordner';
      zeileSmb.hidden = a !== 'smb';
      zeileNfs.hidden = a !== 'nfs';
      zeileOrdner.hidden = a !== 'ordner';
      zeileUnter.hidden = a === 'lokal';
    }
    art.addEventListener('change', zeigen);

    sichern.addEventListener('click', async () => {
      hinweis.textContent = 'wird gespeichert …';
      try {
        const d = await hol('/ablage', {
          art: art.value, wirt: wirt.value, freigabe: freigabe.value,
          pfad: art.value === 'ordner' ? ordner.value : pfad.value,
          unterordner: unter.value,
          benutzer: benutzer.value, passwort: passwort.value,
        });
        passwort.value = '';
        hinweis.textContent = d.hinweis || '';
        standZeigen(d);
      } catch (f) { hinweis.textContent = f.message; }
    });

    const teil = el('section', { id: 'ablageteil' }, [
      el('h3', { textContent: 'Wo die Notizen liegen' }),
      stand,
      el('p', { className: 'ordnerzeile' }, [art, wirt]),
      zeileSmb, zeileNfs, zeileOrdner, zeileUnter,
      el('p', { className: 'knoepfe' }, [sichern]),
      hinweis,
      el('p', { className: 'hinweis', textContent:
        'Eingehängt wird beim Start des Containers, nicht sofort - der laufende '
        + 'Server hat die Rechte dafür abgelegt. Nach dem Speichern also '
        + 'docker compose restart notizmappe.' }),
    ]);
    seite.append(teil);
    zeigen();
    ablageLaden();
  }

  function standZeigen(d) {
    const stand = document.getElementById('ablage-stand');
    if (!stand) return;
    stand.textContent = '';
    let text;
    if (d.art === 'lokal') text = 'im Volume ' + d.ziel;
    else if (d.art === 'ordner') text = d.eingehaengt ? d.pfad
                                                      : `${d.pfad} eingestellt, noch nicht aktiv`;
    else if (d.eingehaengt) text = `${d.wirt} ist eingehängt auf ${d.ziel}`;
    else text = `${d.wirt} eingestellt, aber nicht eingehängt`;
    stand.append(el('span', { textContent: 'Gerade' }),
                 el('code', { textContent: text }));
    const h = document.getElementById('ablage-hinweis');
    if (h && d.meldung && !d.eingehaengt && d.art !== 'lokal') h.textContent = d.meldung;
  }

  async function ablageLaden() {
    let d;
    try { d = await hol('/ablage'); } catch (f) { return; }
    const art = document.getElementById('ablage-art');
    if (!art) return;
    art.value = d.art || 'lokal';
    for (const [id, wert] of [['ablage-wirt', d.wirt], ['ablage-freigabe', d.freigabe],
                              ['ablage-pfad', d.art === 'nfs' ? d.pfad : ''],
                              ['ablage-ordner', d.art === 'ordner' ? d.pfad : ''],
                              ['ablage-unter', d.unterordner],
                              ['ablage-benutzer', d.benutzer]]) {
      const k = document.getElementById(id);
      if (k && wert) k.value = wert;
    }
    art.dispatchEvent(new Event('change'));
    standZeigen(d);
  }

  /* Profilknopf: steht jetzt in der gemeinsamen Oberflaeche (mappe.js) -
     beide Fassungen teilen sie sich, also baut der Shim sie nicht
     mehr dazu. */


  /* Mailversand. Steht unter Optionen bei der Verwaltung, nicht im Profil: es
     ist eine Einstellung des Servers, keine des eigenen Zugangs. Nur Verwalter sehen
     sie - fuer alle anderen antwortet /post mit 403, und dann verschwindet
     der ganze Abschnitt wieder. */
  function postBauen() {
    if (!optionentafel() || document.getElementById('postteil')) return;

    const an = el('input', { type: 'checkbox', id: 'po-an' });
    const server = el('input', { type: 'text', id: 'po-server', placeholder: 'mail.example.de' });
    const port = el('input', { type: 'number', id: 'po-port', value: '587', min: '1', max: '65535' });
    const sicherheit = el('select', { id: 'po-sicherheit' });
    for (const [wert, text] of [['starttls', 'STARTTLS (meist Port 587)'],
                                ['ssl', 'SSL (meist Port 465)'],
                                ['keine', 'ohne Verschlüsselung']]) {
      sicherheit.append(el('option', { value: wert, textContent: text }));
    }
    const benutzer = el('input', { type: 'text', id: 'po-benutzer',
                                   placeholder: 'Anmeldename beim Mailserver',
                                   autocomplete: 'off' });
    const passwort = el('input', { type: 'password', id: 'po-passwort',
                                   placeholder: 'Passwort', autocomplete: 'new-password' });
    const absender = el('input', { type: 'email', id: 'po-absender',
                                   placeholder: 'notizmappe@example.de' });
    const stelle = el('input', { type: 'text', id: 'po-stelle',
                                 placeholder: 'https://notizen.example.de' });
    const hinweis = el('p', { className: 'hinweis', id: 'po-hinweis' });
    const sichern = el('button', { type: 'button', textContent: 'Speichern' });
    const testen = el('button', { type: 'button', textContent: 'Testnachricht an mich' });

    sichern.addEventListener('click', async () => {
      hinweis.textContent = 'wird gespeichert …';
      try {
        const d = await hol('/post', {
          an: an.checked, server: server.value, port: Number(port.value) || 0,
          sicherheit: sicherheit.value, benutzer: benutzer.value,
          passwort: passwort.value, absender: absender.value, stelle: stelle.value,
        });
        passwort.value = '';
        passwort.placeholder = d.passwort_da ? 'unverändert' : 'Passwort';
        hinweis.textContent = d.hinweis || 'Gespeichert.';
      } catch (f) { hinweis.textContent = f.message; }
    });
    testen.addEventListener('click', async () => {
      hinweis.textContent = 'wird verschickt … das kann einen Moment dauern.';
      try {
        const d = await hol('/post/probe', {});
        hinweis.textContent = d.hinweis || 'Abgeschickt.';
      } catch (f) { hinweis.textContent = f.message; }
    });

    const zeile = (text, feld) => el('p', { className: 'zeile2' },
                                     [el('span', { textContent: text }), feld]);
    optionAnhaengen(el('section', { id: 'postteil' }, [
      el('h3', { textContent: 'Mailversand' }),
      el('p', { className: 'hinweis', textContent:
        'Nur für eines da: einen Link zum Zurücksetzen des Passworts zu '
        + 'verschicken. Das Passwort des Mailkontos liegt dabei im Klartext im '
        + 'Datenordner - der Server muss sich damit anmelden können. Wer an die '
        + 'Datei kommt, hat das Mailkonto.' }),
      zeile('Einschalten', an),
      zeile('Mailserver', server),
      zeile('Port', port),
      zeile('Verschlüsselung', sicherheit),
      zeile('Anmeldename', benutzer),
      zeile('Passwort', passwort),
      zeile('Absender', absender),
      zeile('Adresse dieses Servers', stelle),
      el('p', { className: 'hinweis', textContent:
        'Die Adresse steht im Link der Mail. Sie wird hier eingetragen und '
        + 'nicht aus der Anfrage geraten - sonst könnte jemand den Server dazu '
        + 'bringen, einen Link auf seinen eigenen Rechner zu verschicken.' }),
      el('p', { className: 'knoepfe' }, [sichern, testen]),
      hinweis,
    ]));
    postLaden();
  }

  async function postLaden() {
    const teil = document.getElementById('postteil');
    if (!teil) return;
    let d;
    try { d = await hol('/post'); } catch (f) { teil.remove(); optionenReiterBauen(); return; }
    document.getElementById('po-an').checked = !!d.an;
    document.getElementById('po-server').value = d.server || '';
    document.getElementById('po-port').value = d.port || 587;
    document.getElementById('po-sicherheit').value = d.sicherheit || 'starttls';
    document.getElementById('po-benutzer').value = d.benutzer || '';
    document.getElementById('po-passwort').placeholder = d.passwort_da ? 'unverändert' : 'Passwort';
    document.getElementById('po-absender').value = d.absender || '';
    document.getElementById('po-stelle').value = d.stelle || '';
  }

  function abschnittBauen() {
    if (!optionentafel() || document.getElementById('serververwaltung')) return;

    const neuerName = el('input', { type: 'text', placeholder: 'Benutzername', autocapitalize: 'none' });
    const neuesPw = el('input', { type: 'password', placeholder: 'Passwort (mind. 8 Zeichen)' });
    const neueRolle = el('select', {});
    const anlegen = el('button', { type: 'button', textContent: 'Benutzer anlegen' });
    anlegen.addEventListener('click', async () => {
      try {
        await hol('/verwaltung/benutzer', { was: 'anlegen', name: neuerName.value,
                                            passwort: neuesPw.value, rolle: neueRolle.value });
        sagen(`Benutzer ${neuerName.value.trim().toLowerCase()} angelegt.`);
        neuerName.value = ''; neuesPw.value = '';
        verwaltungLaden();
      } catch (f) { sagen(f.message); }
    });

    // Einladung: ein Link, der kurz gilt und genau einmal. So muss kein
    // Passwort durch die Gegend geschickt werden - und wenn der Link doch
    // irgendwo liegen bleibt, ist er laengst wertlos.
    const einRolle = el('select', {});
    const einProjekt = el('select', {});
    const einMinuten = el('select', {});
    for (const m of [5, 15, 60]) {
      einMinuten.append(el('option', { value: String(m), textContent: m + ' Minuten' }));
    }
    const einKnopf = el('button', { type: 'button', textContent: 'Einladungslink erzeugen' });
    const einFeld = el('input', { type: 'text', id: 'v-einladungslink', readOnly: true, hidden: true });
    const einKopieren = el('button', { type: 'button', textContent: 'Kopieren', hidden: true });
    einKopieren.addEventListener('click', async () => {
      einFeld.select();
      try {
        await navigator.clipboard.writeText(einFeld.value);
        sagen('Link kopiert - er gilt nur kurz, also gleich weitergeben.');
      } catch (f) { sagen('Markiert - mit Strg+C kopieren.'); }
    });
    einKnopf.addEventListener('click', async () => {
      try {
        const r = await hol('/verwaltung/einladung', {
          rolle: einRolle.value, projekt: einProjekt.value,
          recht: 'schreiben', minuten: Number(einMinuten.value),
        });
        einFeld.value = r.link;
        einFeld.hidden = false;
        einKopieren.hidden = false;
        sagen(`Gilt ${r.minuten} Minuten und genau einmal.`);
        verwaltungLaden();
      } catch (f) { sagen(f.message); }
    });

    const projektName = el('input', { type: 'text', placeholder: 'Name des neuen Projekts' });
    const projektAnlegen = el('button', { type: 'button', textContent: 'Projekt anlegen' });
    projektAnlegen.addEventListener('click', async () => {
      try {
        await hol('/verwaltung/projekt', { was: 'anlegen', name: projektName.value });
        sagen(`Projekt „${projektName.value}" angelegt - du bist darin Verwalter.`);
        projektName.value = '';
        verwaltungLaden();
        bereicheFrischen();
      } catch (f) { sagen(f.message); }
    });

    // Der Name dieser Mappe. Wer zwei Installationen hat, sieht im Fenster
    // sonst nur eine Adresse - und "192.168.178.27:8112" sagt niemandem,
    // ob das die zu Hause oder die in der Firma ist.
    const mappenName = el('input', { type: 'text', id: 'v-mappe',
                                     placeholder: 'z. B. Servermappe', maxLength: 40 });
    const mappenKnopf = el('button', { type: 'button', textContent: 'Namen setzen' });
    mappenKnopf.addEventListener('click', async () => {
      try {
        const r = await hol('/verwaltung/mappe', { name: mappenName.value });
        sagen(r.mappe ? `Diese Mappe heißt jetzt „${r.mappe}".`
                      : 'Der Name ist weg - im Fenster steht wieder die Adresse.');
        verwaltungLaden();
      } catch (f) { sagen(f.message); }
    });

    const abschnitt = el('section', { id: 'serververwaltung', hidden: true }, [
      el('h3', { textContent: 'Name dieser Mappe' }),
      el('p', { className: 'hinweis', textContent:
        'Steht im Fenster der Notizmappe oben in der Leiste, sobald sich jemand '
        + 'von dort hier anmeldet - statt der Adresse. Leer lassen geht auch.' }),
      el('p', { className: 'ordnerzeile' }, [mappenName, mappenKnopf]),
      el('h3', { textContent: 'Benutzer und Rollen', style: 'margin-top:14px' }),
      el('div', { id: 'v-benutzer' }),
      el('p', { className: 'ordnerzeile' }, [neuerName, neuesPw, neueRolle]),
      el('p', { className: 'knoepfe' }, [anlegen]),
      el('h3', { textContent: 'Zwei Schritte beim Anmelden', style: 'margin-top:14px' }),
      el('div', { id: 'v-zwei' }),
      el('h3', { textContent: 'Einladen', style: 'margin-top:14px' }),
      el('p', { className: 'hinweis', textContent:
        'Ein Link, der kurz gilt und genau einmal. Wer ihn öffnet, legt sich Name und '
        + 'Passwort selbst an - so muss kein Passwort durch die Gegend geschickt werden.' }),
      el('p', { className: 'ordnerzeile' }, [einRolle, einProjekt, einMinuten, einKnopf]),
      el('p', { className: 'ordnerzeile' }, [einFeld, einKopieren]),
      el('div', { id: 'v-einladungen' }),
      el('h3', { textContent: 'Projekte', style: 'margin-top:14px' }),
      el('p', { className: 'hinweis', textContent:
        'Ein Projekt ist ein geteilter Bereich mit eigenen Notizbüchern. Umgeschaltet '
        + 'wird oben im Band. Private Notizen bleiben privat - dort kommt niemand hinein, '
        + 'auch kein Verwalter.' }),
      el('div', { id: 'v-projekte' }),
      el('p', { className: 'ordnerzeile' }, [projektName, projektAnlegen]),
      el('h3', { textContent: 'Was die Rollen bedeuten', style: 'margin-top:14px' }),
      el('div', { id: 'v-rollen' }),
      el('p', { className: 'hinweis', textContent:
        'Mehr Rollen gibt es bewusst nicht. Wer einspringen können soll, wird einfach '
        + 'auch Verwalter; wer in einem Projekt mehr oder weniger darf, wird dort '
        + 'eingestellt.' }),
      el('p', { className: 'hinweis', id: 'v-meldung' }),
      el('p', { className: 'hinweis', textContent:
        'Die Rechte werden am Server durchgesetzt, nicht nur in der Oberfläche. '
        + 'Ein Zugang zu entfernen löscht keine Notizen - die liegen weiter im Datenordner.' }),
    ]);
    optionAnhaengen(abschnitt);
    nachH3Teilen(abschnitt);
    // Die Meldezeile gehoert in keinen Reiter: "Zugang entfernt" soll man auch
    // dann noch lesen, wenn man weiterschaltet - im letzten Unterabschnitt
    // steckte sie sonst fest.
    const meldung = document.getElementById('v-meldung');
    if (meldung) abschnitt.append(meldung);

    // Die Auswahlfelder füllen sich aus dem Stand
    const fuellen = () => {
      if (!verwaltungStand || !verwaltungStand.darf) return;
      neueRolle.textContent = '';
      einRolle.textContent = '';
      for (const r of verwaltungStand.rollen) {
        neueRolle.append(el('option', { value: r.name, textContent: r.name }));
        einRolle.append(el('option', { value: r.name, textContent: r.name,
                                       selected: r.name === 'Benutzer' }));
      }
      einProjekt.textContent = '';
      einProjekt.append(el('option', { value: '', textContent: 'ohne Projekt' }));
      for (const pr of verwaltungStand.projekte || []) {
        einProjekt.append(el('option', { value: pr.name, textContent: 'Projekt: ' + pr.name }));
      }
    };
    const alt = verwaltungLaden;
    verwaltungLaden = async function () {
      await alt();
      fuellen();
      // Erst jetzt steht fest, welche Abschnitte dieser Mensch sehen darf -
      // also erst jetzt stehen die Reiter fest.
      optionenReiterBauen();
    };

    // Eingesetzte Elemente bringen ihre Gestaltung selbst mit. Sonst nehmen sie
    // die Standarddarstellung des Browsers - weisse Felder und Knoepfe in einer
    // dunklen Oberflaeche, und das sieht aus wie hineingefallen.
    const stil = document.createElement('style');
    stil.textContent = `
      #serververwaltung { max-width: 760px; }

      /* Reiterleiste der Einstellungen. Sieht aus wie die Reiter oben im
         Band - derselbe Handgriff, dieselben Farbnamen. */
      #optionenreiter {
        display: flex; flex-wrap: wrap; gap: 2px; margin: 0 0 18px;
        border-bottom: 1px solid var(--linie);
      }
      #optionenreiter button {
        background: none; border: 1px solid transparent; border-bottom: none;
        color: var(--matt); padding: 7px 13px; margin-bottom: -1px;
        border-radius: 8px 8px 0 0; font: inherit; font-size: 13px; cursor: pointer;
      }
      #optionenreiter button:hover { color: var(--schrift); background: var(--flaeche); }
      #optionenreiter button[aria-selected="true"] {
        color: var(--schrift); background: var(--papier);
        border-color: var(--linie); border-bottom-color: var(--papier);
      }
      .reiterzu { display: none !important; }

      /* Profil unten in der Leiste. Alles ueber die Farbnamen der Oberflaeche -
         eigene Farben hier waeren genau der weisse Fleck, der vorher auffiel. */
      /* Ohne das haengt sich das aufgeklappte Menue an den naechsten
         positionierten Vorfahren - und das waere irgendwo weit oben. */
      .fussrechts { position: relative; }
      #profilknopf {
        display: inline-flex; align-items: center; gap: 6px;
        height: 28px; padding: 0 8px 0 3px;
        border: 1px solid var(--linie); border-radius: 14px;
        background: var(--papier); color: var(--schrift);
        cursor: pointer; font-size: 12px; max-width: 150px;
      }
      #profilknopf:hover { border-color: var(--akzent); }
      #profilbild {
        width: 22px; height: 22px; border-radius: 50%;
        background: var(--akzent); color: var(--papier);
        display: inline-flex; align-items: center; justify-content: center;
        font-size: 11px; font-weight: 700; flex: 0 0 auto;
      }
      #profilname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      /* Die Leiste sitzt ganz unten - das Menue klappt deshalb nach oben auf. */
      #profilmenue {
        position: absolute; bottom: 36px; right: 8px; z-index: 40;
        min-width: 170px; padding: 4px;
        background: var(--papier); color: var(--schrift);
        border: 1px solid var(--linie); border-radius: 8px;
        box-shadow: 0 6px 20px rgba(0, 0, 0, .28);
      }
      #profilkopf {
        margin: 0; padding: 6px 8px 8px;
        border-bottom: 1px solid var(--linie); display: grid; gap: 1px;
      }
      #profilkopf .hinweis { font-size: 11px; }
      .profilpunkt {
        display: block; width: 100%; text-align: left;
        padding: 7px 8px; margin: 1px 0;
        background: none; border: 0; border-radius: 6px;
        color: var(--schrift); cursor: pointer; font-size: 13px;
      }
      .profilpunkt:hover { background: var(--flaeche); }

      /* Der Speicher-Reiter ist eine eigene Seite, kein #einstellungen - die
         Regeln von drueben greifen dort also nicht, und ein nacktes <select>
         nimmt die Browserfarben. Auf dunklem Grund steht dann ein weisser
         Kasten mitten in der Seite. Also dieselben Farben wie die Felder in
         den Einstellungen, ueber dieselben Namen. */
      #ablageteil .ordnerzeile { display: flex; gap: 8px; margin: 10px 0 4px; flex-wrap: wrap; }
      #ablageteil input[type="text"],
      #ablageteil input[type="password"],
      #ablageteil select {
        flex: 1; min-width: 0; padding: 4px 8px;
        border: 1px solid var(--linie); border-radius: 6px;
        background: var(--papier); color: var(--schrift);
        font: inherit; font-size: 13px;
      }
      #ablageteil select { flex: 0 0 auto; min-width: 220px; cursor: pointer; }
      /* Die Liste, die aufklappt, faerbt das Betriebssystem - ohne das steht
         sie wieder weiss da. */
      #ablageteil select option { background: var(--papier); color: var(--schrift); }
      #ablageteil input:focus, #ablageteil select:focus {
        outline: none; border-color: var(--akzent);
      }
      #ablageteil button {
        border: 1px solid var(--linie); background: var(--leiste); color: var(--schrift);
        border-radius: 6px; padding: 5px 10px; cursor: pointer; font-size: 13px;
      }
      #ablageteil button:hover { border-color: var(--akzent); }
      #ablageteil .hinweis { color: var(--matt); font-size: 12px; margin: 8px 0 0; }
      #ablageteil h3 { margin: 0 0 10px; }
      /* Das Profilfenster. Farben aus der Oberflaeche - ein <dialog> bringt
         sonst Weiss und einen hellen Rand mit. */
      #profilfenster {
        width: min(560px, calc(100vw - 32px)); max-height: calc(100vh - 64px);
        padding: 0 20px 20px; border: 1px solid var(--linie); border-radius: 12px;
        background: var(--papier); color: var(--schrift);
        box-shadow: 0 12px 48px rgba(0, 0, 0, .45);
      }
      #profilfenster::backdrop { background: rgba(0, 0, 0, .5); }
      #profilkopfzeile {
        position: sticky; top: 0; z-index: 1;
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; padding: 16px 0 10px; background: var(--papier);
        border-bottom: 1px solid var(--linie);
      }
      #profilkopfzeile h2 { margin: 0; font-size: 16px; }
      #profilzu {
        width: 28px; height: 28px; padding: 0; line-height: 1;
        border: 1px solid var(--linie); border-radius: 50%;
        background: var(--leiste); color: var(--schrift); cursor: pointer;
      }
      #profilzu:hover { border-color: var(--akzent); }
      #profilteil .ordnerzeile { display: flex; gap: 8px; margin: 10px 0 4px; flex-wrap: wrap; }
      /* Auch das E-Mail-Feld: die Regel galt nur fuer Passwortfelder, und ein
         weisses Feld in der dunklen Oberflaeche ist genau der Fleck, der hier
         schon zweimal aufgefallen ist. */
      #profilteil input[type="password"], #profilteil input[type="email"] {
        flex: 1; min-width: 0; padding: 4px 8px;
        border: 1px solid var(--linie); border-radius: 6px;
        background: var(--papier); color: var(--schrift);
        font: inherit; font-size: 13px;
      }
      #profilteil input:focus { outline: none; border-color: var(--akzent); }
      #profilteil button {
        border: 1px solid var(--linie); background: var(--leiste); color: var(--schrift);
        border-radius: 6px; padding: 5px 10px; cursor: pointer; font-size: 13px;
      }
      #profilteil button:hover { border-color: var(--akzent); }
      #profilteil .hinweis { color: var(--matt); font-size: 12px; margin: 8px 0 0; }
      #profilteil select {
        padding: 4px 8px; min-width: 220px;
        border: 1px solid var(--linie); border-radius: 6px;
        background: var(--papier); color: var(--schrift);
        font: inherit; font-size: 13px; cursor: pointer;
      }
      #profilteil select option { background: var(--papier); color: var(--schrift); }
      .farbgitter {
        display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 8px; margin: 10px 0 0;
      }
      .farbwahl {
        display: flex; align-items: center; gap: 8px;
        padding: 5px 8px; border: 1px solid var(--linie); border-radius: 6px;
        background: var(--flaeche); font-size: 12px; cursor: pointer;
      }
      .farbwahl input[type="color"] {
        width: 30px; height: 24px; padding: 0; border: 1px solid var(--linie);
        border-radius: 4px; background: none; cursor: pointer;
      }
      /* Rahmen mit Griffen - wie man es aus Textverarbeitungen kennt.
         Ziehen am Rahmen verschiebt, Ziehen am Griff aendert die Groesse;
         drehen geht noch nicht. */
      #malrahmen {
        position: absolute; z-index: 20; cursor: move;
        border: 1px dashed var(--schrift);
        background: color-mix(in srgb, var(--akzent) 6%, transparent);
        touch-action: none; user-select: none; -webkit-user-select: none;
      }
      .malgriff {
        position: absolute; width: 9px; height: 9px;
        background: var(--papier); border: 1px solid var(--schrift);
      }
      /* Ein markierter Kasten muss auch markiert aussehen. .aktiv gibt es
         drueben schon fuers Schreiben - deshalb ein eigener Name. */
      .kasten.mitgewaehlt { outline: 1px dashed var(--akzent); outline-offset: 2px; }
      #malband {
        position: absolute; z-index: 19; pointer-events: none;
        border: 1px dashed var(--akzent);
        background: color-mix(in srgb, var(--akzent) 10%, transparent);
      }
      .malgriff-nw, .malgriff-so { cursor: nwse-resize; }
      .malgriff-no, .malgriff-sw { cursor: nesw-resize; }
      .malgriff-n, .malgriff-s { cursor: ns-resize; }
      .malgriff-w, .malgriff-o { cursor: ew-resize; }
      .malgriff-nw { left: -5px; top: -5px; }
      .malgriff-n  { left: calc(50% - 5px); top: -5px; }
      .malgriff-no { right: -5px; top: -5px; }
      .malgriff-w  { left: -5px; top: calc(50% - 5px); }
      .malgriff-o  { right: -5px; top: calc(50% - 5px); }
      .malgriff-sw { left: -5px; bottom: -5px; }
      .malgriff-s  { left: calc(50% - 5px); bottom: -5px; }
      .malgriff-so { right: -5px; bottom: -5px; }
      .malweg {
        position: absolute; right: -11px; top: -26px;
        width: 22px; height: 22px; padding: 0; line-height: 1;
        border: 1px solid var(--linie); border-radius: 50%;
        background: var(--papier); color: var(--schrift);
        cursor: pointer; font-size: 12px;
      }
      .malweg:hover { border-color: var(--warnung); color: var(--warnung); }
      #m-loeschen, #m-gruppe { font-size: 14px; }
      #m-glatt { font-size: 15px; }
      #m-glatt[data-stufe="stark"] { font-weight: 700; }
      #ablage-stand code { color: var(--schrift); }
      #serververwaltung h3 {
        margin: 22px 0 8px; font-size: 13px; text-transform: uppercase;
        letter-spacing: .04em; color: var(--matt); font-weight: 600;
      }
      #serververwaltung .zeile2 {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; margin: 6px 0; padding-bottom: 6px;
        border-bottom: 1px solid var(--linie);
      }
      #serververwaltung .zeile2 span:last-child { display: flex; gap: 6px; flex: 0 0 auto; }
      #profilteil .zeile2 {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; margin: 10px 0 4px;
      }
      #postteil { max-width: 760px; }
      #postteil input[type="text"], #postteil input[type="email"],
      #postteil input[type="password"], #postteil input[type="number"],
      #postteil select {
        border: 1px solid var(--linie); border-radius: 6px; padding: 5px 8px;
        background: var(--flaeche, var(--papier)); color: var(--schrift);
        font: inherit; font-size: 13px; min-width: 220px;
      }
      #postteil option { background: var(--papier); color: var(--schrift); }
      #postteil button {
        border: 1px solid var(--linie); background: var(--leiste); color: var(--schrift);
        border-radius: 6px; padding: 5px 10px; cursor: pointer; font: inherit; font-size: 13px;
      }
      #postteil button:hover { border-color: var(--akzent); }
      #postteil .zeile2 {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; margin: 6px 0; padding-bottom: 6px;
        border-bottom: 1px solid var(--linie);
      }
      #postteil .hinweis { color: var(--matt); font-size: 12px; margin: 8px 0 0; }
      #postteil .knoepfe { display: flex; gap: 8px; margin-top: 12px; }
      #serververwaltung .hinweis {
        color: var(--matt); font-size: 12px; margin: 8px 0 0; max-width: 640px;
      }
      #serververwaltung button {
        border: 1px solid var(--linie); background: var(--leiste); color: var(--schrift);
        border-radius: 6px; padding: 5px 10px; cursor: pointer; font: inherit; font-size: 13px;
      }
      #serververwaltung button:hover { border-color: var(--akzent); }
      #serververwaltung button:disabled {
        opacity: .45; cursor: default; border-color: var(--linie);
      }
      #serververwaltung input[type="text"], #serververwaltung input[type="password"],
      #serververwaltung select {
        padding: 5px 8px; height: 28px; border: 1px solid var(--linie); border-radius: 6px;
        background: var(--papier); color: var(--schrift); font: inherit; font-size: 13px;
      }
      #serververwaltung input::placeholder { color: var(--matt); }
      #serververwaltung .ordnerzeile { display: flex; gap: 8px; margin: 10px 0 4px; flex-wrap: wrap; }
      #serververwaltung .ordnerzeile input[type="text"],
      #serververwaltung .ordnerzeile input[type="password"] { flex: 1; min-width: 140px; }
      #serververwaltung .knoepfe { display: flex; gap: 8px; margin: 10px 0 0; flex-wrap: wrap; }
      #serververwaltung .rechte { display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 6px 0; }
      #serververwaltung .rollenkasten {
        border: 1px solid var(--linie); border-radius: 8px; background: var(--leiste);
        padding: 10px 12px; margin-bottom: 8px;
      }
      #serververwaltung .rollenkasten strong { display: block; margin-bottom: 6px; }
      #serververwaltung .haken {
        display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--matt);
      }
      #serververwaltung .haken input { accent-color: var(--akzent); }
      /* Der Einladungslink wird abgeschrieben oder kopiert - also breit und
         in gleichmaessiger Schrift, nicht als schmales Eingabefeld. */
      #v-einladungslink {
        flex: 1; min-width: 240px; font-family: ui-monospace, "DejaVu Sans Mono", monospace;
        font-size: 12px; background: var(--flaeche, var(--papier));
      }
      #serververwaltung .rollenwozu { color: var(--matt); font-size: 12px;
        max-width: 430px; text-align: right; }
      #serververwaltung h4 { margin: 14px 0 6px; font-size: 13px; }
      #serververwaltung .qrkasten {
        display: inline-block; background: #fff; padding: 6px; border-radius: 8px;
        border: 1px solid var(--linie); line-height: 0;
      }
      #serververwaltung .qrkasten svg { width: 190px; height: 190px; }
      #serververwaltung .geheimnis {
        display: inline-block; font-family: ui-monospace, monospace; font-size: 13px;
        letter-spacing: .08em; background: var(--flaeche, var(--papier));
        border: 1px dashed var(--linie); border-radius: 6px; padding: 6px 10px; user-select: all;
      }
      #serververwaltung .notfallcodes {
        display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
        gap: 6px; margin: 8px 0; max-width: 560px;
      }
      #serververwaltung .notfallcodes code {
        font-family: ui-monospace, monospace; font-size: 13px; letter-spacing: .06em;
        background: var(--flaeche, var(--papier)); border: 1px solid var(--linie);
        border-radius: 6px; padding: 5px 8px; text-align: center; user-select: all;
      }
      #v-meldung { color: var(--matt); font-size: 12px; margin-top: 10px; }
      /* Der Balken sitzt ueber allem, aber unten rechts - nicht im Weg und
         nicht zu uebersehen. */
      #updatebalken {
        position: fixed; right: 16px; bottom: 16px; z-index: 60;
        display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
        max-width: min(460px, calc(100vw - 32px));
        padding: 10px 12px; border-radius: 10px;
        border: 1px solid var(--akzent); background: var(--papier);
        color: var(--schrift); font-size: 13px;
        box-shadow: 0 6px 24px rgba(0, 0, 0, .35);
      }
      #updatebalken button {
        border: 1px solid var(--linie); background: var(--leiste); color: var(--schrift);
        border-radius: 6px; padding: 5px 10px; cursor: pointer; font: inherit; font-size: 13px;
      }
      #u-jetzt { border-color: var(--akzent); }
      #u-jetzt:hover:not(:disabled) { background: var(--akzent); color: var(--papier); }
      #updatebalken button:disabled { opacity: .6; cursor: default; }
      #u-text { flex: 1 1 200px; }`;
    document.head.append(stil);
  }

  /* Gibt es überhaupt einen Server zu verwalten?

     Im Browser immer. Im Fenster nur, wenn es mit einem verbunden ist -
     örtlich gibt es keine Benutzer, keine Rollen und keinen Mailversand. */
  function serverDa() {
    // Im Browser legt shim.js den Weg hin - dann ist der Server dieser hier.
    if (typeof window.NOTIZMAPPE_HOL === 'function') return true;
    // Im Fenster sagt es mappe.js, sobald es die Einstellungen gelesen hat.
    return !!window.NOTIZMAPPE_SERVER_DA;
  }

  async function alles() {
    if (!serverDa()) return;
    for (const [name, tun] of [['Verwaltung', abschnittBauen],
                               ['Ablage', ablageBauen],
                               ['Mailversand', postBauen],
                               ['Reiter', optionenReiterBauen],
                               ['Verwaltung laden', verwaltungLaden]]) {
      // Jeder Schritt für sich: fällt einer aus, steht der Rest trotzdem da.
      try { await tun(); } catch (f) { console.error('[notizmappe] ' + name + ':', f); }
    }
  }

  window.Verwaltung = {
    bauen: abschnittBauen,
    ablage: ablageBauen,
    post: postBauen,
    laden: verwaltungLaden,
    reiterBauen: optionenReiterBauen,
    da: serverDa,
    alles: alles,
  };
})();
