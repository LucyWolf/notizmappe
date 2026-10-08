# Notizmappe

Freie Notizfläche wie OneNote, aber die Daten liegen als Dateien in **deinem**
Ordner — Nextcloud, NAS-Freigabe oder einfach lokal. Kein Konto, kein Microsoft.

Ein normales Programm: eigenes Fenster, eigener Eintrag im Menü und in der
Fensterleiste, Schließen beendet es. Dass die Oberfläche innen aus HTML besteht
und ein kleiner Server dahinter läuft, merkt man nur, wenn man es wissen will —
der Server hört nur auf `127.0.0.1` und geht mit dem Fenster.

Stand: 08.10.2026 — Stufe 1 (Baum, Textkästen, Autosave, Konflikterkennung).

## Warum Dateien und keine Datenbank

Der Datenordner wird von einem Sync-Client angefasst, während das Programm läuft.
SQLite-Dateien überleben das nicht zuverlässig (Nextcloud kopiert sie mitten in
einer Transaktion und legt bei Bedarf eine Konfliktkopie daneben). Deshalb:

```
~/Notizen/                        ← NOTIZEN_ORDNER, liegt im Sync-Ordner
  Arbeit/                         ← Notizbuch  = Ordner
    Projekte/                     ← Abschnitt  = Unterordner
      Phobos.json                 ← Seite      = eine JSON-Datei
  .papierkorb/                    ← gelöschtes, mit Zeitstempel im Namen
```

Eine Seite ist eine Liste von Kästen mit `x`, `y`, Breite und HTML. Lesbar und
mit jedem Texteditor zu retten:

```json
{ "format": 1, "titel": "Phobos", "rev": 7, "geraet": "a3f1c9",
  "elemente": [ { "id": "k1", "typ": "text", "x": 40, "y": 60, "b": 420,
                  "html": "<p>Hallo <b>Welt</b></p>" } ] }
```

## Sync wird nicht selbst gebaut

Den Dateitransport macht der Nextcloud-Client bzw. die NAS-Freigabe. Das Programm
kümmert sich nur um die zwei Stellen, an denen das wehtut:

* **Verlorene Änderungen.** Jede Seite hat einen Zähler `rev`. Wer mit einem
  veralteten `rev` speichert, bekommt HTTP 409 und die aktuelle Fassung zurück —
  statt die fremde Änderung stillschweigend zu überschreiben. Im Browser kommt
  dann die Frage „meine behalten / fremde laden".
* **Konfliktkopien.** Legt der Sync-Client `Seite (Konflikt-Kopie …).json` daneben,
  taucht die im Baum mit ⚠ auf, statt unbemerkt herumzuliegen.

Alle 15 Sekunden fragt der Browser nach, ob die offene Seite von außen neuer
geworden ist, und sagt es, bevor etwas kaputtgeht.

## Installieren

**Linux, Doppelklick** — die `.desktop`-Datei zum eigenen System aus dem Release
herunterladen und doppelklicken (Arch/CachyOS, Debian/Ubuntu, oder die allgemeine).
Sie holt die Installationsdatei, installiert fehlende Pakete mit **einer**
Passwortfrage und legt den Menüeintrag an. Nochmal angeklickt: aktualisieren oder
entfernen.

**Windows** — `setup.exe` aus dem Release, doppelklicken. Kein Python nötig, das
steckt in der `.exe`. SmartScreen warnt bei unsignierten Programmen:
*Weitere Informationen → Trotzdem ausführen*. Die Notizmappe läuft, solange ihr
Fenster offen ist, und öffnet den Browser selbst.

**Linux, von Hand** — die Installationsdatei direkt:

```
https://github.com/LucyWolf/notizmappe/releases/latest/download/notizmappe-installer.sh
```

## Bilder und Dateien

Ziehen, einfügen mit Strg+V oder der Knopf 📎 — alles landet auf der Fläche, wo der
Zeiger war. Bilder werden angezeigt, alles andere als Kachel zum Herunterladen.
Die Dateien liegen neben der Seite:

```
Arbeit/Projekte/Phobos.json
Arbeit/Projekte/Phobos.anhang/Urlaub.png
```

Also im selben Ordner, den der Sync ohnehin trägt — kein zweiter Ablageort, und im
Dateimanager sieht man sofort, was zu welcher Seite gehört. Benennt man die Seite
um, zieht der Anhangsordner mit; löscht man sie, geht er mit in den Papierkorb.
Elemente, die man von der Seite entfernt, nehmen ihre Datei beim nächsten Speichern
in den Papierkorb mit — gelöscht wird nichts sofort.

Grenze: 25 MB pro Datei. Ob etwas ein Bild ist, wird an den ersten Bytes entschieden,
nicht am Dateinamen und nicht am Content-Type des Browsers — beide sagen, was der
Absender behauptet. **SVG gilt bewusst nicht als Bild**: das ist XML mit `<script>`
darin und wäre im Fenster dasselbe Loch wie fremdes HTML. Hochladen geht, angezeigt
wird es nicht, es kommt als Download — mit `nosniff`, damit der Browser nicht doch
selbst entscheidet.

## Tests

```bash
tests/alle.sh              # alles, baut auch das Paket (~3 Minuten)
tests/alle.sh --schnell    # nur API und Update
```

| | |
|---|---|
| `tests/test_api.py` | Seiten, Anhänge, Konflikte, XSS, Pfadausbruch, Papierkorb |
| `tests/test_update.py` | Selbstupdate gegen einen nachgemachten GitHub-Server |
| `tests/test_installer.sh` | Installationsdatei in einem Wegwerf-Heim durchspielen |

Sie liegen **im Repo**, nicht im Scratchpad einer Sitzung: der wird geleert, und
dann sind sie weg. `release.yml` fährt sie bei jedem Release mit, `tools/pruefen.py`
hängt als `pre-commit` davor und parst Python, Jinja und JS.

## Updates

Läuft eine Installation, schaut sie einmal pro Stunde beim neuesten Release vorbei.
Gibt es eine höhere Nummer, erscheint in der Kopfzeile *„Version x.y.z laden"* —
ein Klick lädt das Paket, vergleicht die SHA256-Summe und spielt es ein. Der Dienst
startet dabei neu, die Seite lädt sich von selbst wieder. Die Notizen bleiben unberührt.

Das Einspielen geht **nur direkt an dem Rechner**, auf dem die Notizmappe läuft
(`127.0.0.1`) — solange es keine Anmeldung gibt, soll niemand aus dem Netz Code
einspielen können. Protokoll des letzten Updates:
`~/.local/share/notizmappe/.update.log`.

Ist das Repo **privat**, kommt die Update-Prüfung nicht an die GitHub-API (404) und
der Knopf bleibt aus. Dann entweder das Repo öffentlich machen oder einen Token
hinlegen:

```bash
mkdir -p ~/.config/notizmappe && install -m 600 /dev/null ~/.config/notizmappe/token
printf '%s' "ghp_…" > ~/.config/notizmappe/token     # oder NOTIZMAPPE_TOKEN=…
```

Auf Windows gibt es kein Selbstupdate — dort die neue `setup.exe` ausführen.

## Neue Fassung herausgeben

```bash
./tools/veroeffentlichen.sh          # letzte Stelle +1, committen, taggen, pushen
./tools/veroeffentlichen.sh 1.1.0    # oder eine bestimmte Nummer
```

Danach macht GitHub den Rest:

| Workflow | baut |
|---|---|
| `release.yml` | `notizmappe-v<ver>-installer.sh` (+ fester Name, + SHA256) und `Notizmappe.exe`, legt das Release an |
| `installer.yml` | aus `installer.conf` die drei Linux-Doppelklick-Dateien und `notizmappe-setup.exe` |

`release.yml` bricht ab, wenn `app/VERSION` nicht zum Tag passt, installiert das
gebaute Paket zur Probe in ein Wegwerf-Heimverzeichnis und startet die
`Notizmappe.exe` einmal wirklich — ein fehlender PyInstaller-Import fällt sonst
erst beim Anwender auf.

Die Workflow-Vorlage und `installer.conf` kommen aus
[LucyWolf/double-click-installer](https://github.com/LucyWolf/double-click-installer).
`template/` und `installer.conf` liegen unverändert da; `installer.yml` hat **einen**
Zusatz bekommen: einen `workflow_call`-Auslöser. Ein Release, das `release.yml` mit
dem `GITHUB_TOKEN` anlegt, löst nämlich keine weiteren Workflows aus — sonst könnten
sich Workflows endlos selbst starten. Der Auslöser `release: published` der Vorlage
greift deshalb nur, wenn ein Mensch das Release anlegt. Das wäre auch in der Vorlage
selbst einen Zusatz wert.

### Wo der Doppelklick-Installer und dieses Paket sich treffen

Beide benutzen `~/.local/share/notizmappe`. Der Doppelklick-Installer legt dort nur
die Installationsdatei ab und ruft sie mit `--starten` auf; die richtet daneben
`app/` und `.venv/` ein. Beide schreiben denselben Menüeintrag, es entsteht also
kein zweiter. Entfernt der Doppelklick-Installer alles per `rm -rf`, bleibt die
Dienstdatei zurück — sie startet dann aber nicht mehr (`ConditionPathExists`), und
der Menüeintrag verschwindet mit dem Programm (`TryExec`).

## Datei direkt herunterladen

Die fertige Datei hängt am jeweiligen Release. Der Link zeigt immer auf die neueste:

```
https://github.com/LucyWolf/notizmappe/releases/latest/download/notizmappe-v1.0.1-installer.sh
```

(Der Dateiname trägt die Version, also wechselt der Link mit jedem Release —
`releases/latest` listet die aktuelle.)

## Installationsdatei bauen

```bash
./tools/paket_bauen.sh      # -> dist/notizmappe-v<version>-installer.sh
```

Das Ergebnis ist **eine** Datei (~4,5 MB): Programm, Installationsskript und die
Python-Pakete als Rad-Dateien stecken als base64-Nutzlast darin. Der Installer
braucht deshalb weder Internet noch GitHub — nur `python3` ≥ 3.10. Passen die
mitgelieferten Pakete nicht zur Python-Version auf dem Zielrechner, holt er sie
als Rückfalllösung aus dem Netz und sagt das.

Auf dem Zielrechner:

```bash
bash notizmappe-v1.0.1-installer.sh                   # einrichten / aktualisieren
bash notizmappe-v1.0.1-installer.sh --deinstallieren  # Programm weg, Notizen bleiben
bash notizmappe-v1.0.1-installer.sh --version
NOTIZMAPPE_ZIEL=/opt/nm NOTIZEN_ORDNER=/mnt/nas/Notizen PORT=9000 \
  bash notizmappe-v1.0.1-installer.sh                 # andere Orte
```

Ohne Root. Es entstehen: `~/.local/share/notizmappe` (Programm und venv),
`~/Notizen` (Daten) und ein Menüeintrag **Notizmappe**. Läuft schon eine Fassung,
fragt der Installer: aktualisieren, deinstallieren oder abbrechen.

Standardmäßig läuft **nichts** im Hintergrund. Wer die Notizen auch vom Handy oder
vom zweiten Rechner aus erreichen will, nimmt `--mit-dienst` — dann läuft zusätzlich
ein Benutzerdienst auf Port 8099, und das Fenster dockt daran an, statt einen
zweiten Server zu starten.

## Das Fenster

Das Fenster kommt von der Webansicht des Systems, in dieser Reihenfolge:

1. **pywebview** über WebKit2GTK oder Qt — ein echtes Fenster, eigener Prozess.
   Die Webansicht ist ein Distributionspaket (`python-gobject` + `webkit2gtk-4.1`
   bzw. `python3-gi` + `gir1.2-webkit2-4.1`); der Doppelklick-Installer bringt sie
   mit, deshalb steht sie in `installer.conf`.
2. **Chromium-artiger Browser mit `--app=`** — sieht genauso aus (eigenes Fenster,
   keine Adresszeile), mit eigenem Profil, damit es nicht in einer laufenden
   Browsersitzung aufgeht. Firefox kann das nicht.
3. Normaler Browser — der Notnagel, mit Hinweis.

Was davon auf deinem Rechner da ist:

```bash
~/.local/share/notizmappe/.venv/bin/python ~/.local/share/notizmappe/app/fenster.py --pruefen
```

Das venv wird mit `--system-site-packages` angelegt, sonst sieht es die Webansicht
der Distribution nicht — die gibt es nicht über pip.

Vor dem Entpacken prüft die Datei ihre eigene SHA256-Summe, damit ein halber
Download nicht halb installiert.

## Versionsnummern

`app/VERSION` ist die eine Quelle. Die Nummer landet im Dateinamen des Installers,
im Kopf der Datei, im Menüeintrag, im Dienstnamen und in `--version`.

Die letzte Stelle zählt bis 99 (1.0.9 → 1.0.10), **nie rückwärts**. Der Installer
verweigert eine ältere Fassung über einer neueren: eine Datei, die die neuere
Fassung geschrieben hat, soll nicht von einer älteren gelesen werden. Wer das
wirklich will, deinstalliert erst.

## Starten (aus dem Quellordner, zum Entwickeln)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
NOTIZEN_ORDNER=~/Nextcloud/Notizen ./starten.sh      # Standard: ~/Notizen
```

`starten.sh` ist nur der nackte Server. Das Programm mit Fenster ist
`python3 app/fenster.py`. Umgebungsvariablen: `NOTIZEN_ORDNER`, `HOST`, `PORT`.

## Bedienung

| | |
|---|---|
| Doppelklick auf freie Fläche | neuer Textkasten an der Stelle |
| Balken über dem Kasten ziehen | verschieben |
| rechter Rand ziehen | Breite ändern |
| Strg+B / I / U | fett, kursiv, unterstrichen |
| Mittlere Maustaste oder Leertaste + ziehen | Fläche schieben |
| Strg+Rad, Strg +/−, Strg+0 | zoomen |
| Strg+S | sofort speichern (passiert sonst nach 0,9 s Ruhe) |

Die Fläche wächst nach rechts und unten mit, es gibt keinen Seitenrand.

## Kein Login

Stufe 1 hat keine Anmeldung — gedacht für `127.0.0.1` oder das eigene Netz.
Soll es von außen erreichbar sein, gehört ein Reverse-Proxy mit Basic-Auth davor
oder ein Passwort in die App. Vorher nicht ins Internet stellen: wer die URL hat,
liest und schreibt alle Notizen.

Aus dem Editor kommendes HTML wird beim **Speichern** gesäubert (`app/reinigen.py`,
Positivliste). Das passiert absichtlich vor dem Schreiben, nicht erst beim Anzeigen:
sonst steht der Dreck in der Datei und jeder spätere Weg — Export, Suche, zweite
Oberfläche — sieht ihn wieder.

## Noch nicht gebaut

Bilder und Dateianhänge · Zeichenebene mit Stift · Suche über alle Seiten ·
Tags und Verweise zwischen Seiten · Papierkorb-Ansicht zum Wiederherstellen ·
PWA für das Handy (offline) · verschieben von Seiten zwischen Abschnitten.
