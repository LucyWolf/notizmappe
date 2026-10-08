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

**Bilder im Text:** Steht der Cursor in einem Textkasten, setzt Strg+V das Bild
genau dort in den Text; genauso, wenn man ein Bild auf einen Textkasten zieht. Im
HTML steht dann nur `<img data-datei="Urlaub.png">` — die Adresse ergänzt die
Oberfläche beim Anzeigen, damit der Verweis das Umbenennen der Seite übersteht.

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
| `tests/test_konten.py` | Sperre, Anmeldung, Projekte, Gerätschlüssel, Passwortraten |
| `tests/test_update.py` | Selbstupdate gegen einen nachgemachten GitHub-Server |
| `tests/test_installer.sh` | Installationsdatei in einem Wegwerf-Heim durchspielen |

Sie liegen **im Repo**, nicht im Scratchpad einer Sitzung: der wird geleert, und
dann sind sie weg. `release.yml` fährt sie bei jedem Release mit, `tools/pruefen.py`
hängt als `pre-commit` davor und parst Python, Jinja und JS.

## Einstellungen

Zahnrad unten in der Seitenleiste, neben der Versionsnummer. Dort steht, welche Version läuft und welche es gibt, mit Knopf
zum Einspielen; der Datenordner, wie viele Seiten darin liegen, was im Papierkorb
ist und wie viel Platz das Laufwerk noch hat; dazu die Darstellungsgröße.

**Datenordner wählen:** Unter „Daten“ einen Pfad eintragen oder „Durchsuchen …“
(Ordner-Dialog des Systems über kdialog/zenity). Auf Wunsch werden die vorhandenen
Notizen in den neuen Ordner **kopiert** — nur was dort noch fehlt, der alte Ordner
bleibt unangetastet. Vor dem Wechsel wird die offene Seite gespeichert, danach lädt
die Oberfläche neu, damit nichts mehr auf den alten Ordner zeigt. Umstellen geht nur
direkt an dem Rechner, auf dem die Notizmappe läuft.

Die Wahl steht in `~/.config/notizmappe/einstellungen.json` (Windows:
`%APPDATA%\notizmappe`), nicht im Datenordner selbst. Ist `NOTIZEN_ORDNER` gesetzt,
gewinnt das und die Wahl ist gesperrt — Tests und Docker verlassen sich darauf.

## Wenn die Oberfläche nicht reagiert

Ganz oben in der Seite sitzt ein Fehlerfänger: was beim Laden schiefgeht, landet in
der Meldungszeile über der Fläche, statt die Oberfläche stumm zu lassen. Und:

```bash
.venv/bin/python tools/fenster_pruefen.py
```

Das öffnet das Fenster, legt einen Kasten an, schreibt hinein, wartet aufs Speichern
und öffnet die Einstellungen — und meldet, was dabei herauskam. So kam heraus, dass
WebKitGTK gar kein `localStorage` kennt: der allererste Zugriff warf, das ganze
Skript brach ab, und nichts war mehr anklickbar. Alles, was dort gespeichert wird,
läuft deshalb über einen Merker, der es versucht und sonst nur für die Sitzung behält.

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

## Sperre (eigener Rechner)

Ohne weiteres Zutun gibt es keine Anmeldung — das Programm läuft nur auf
`127.0.0.1`. Unter **Einstellungen → Sperre** lässt sich ein Passwort festlegen: dann
fragt die Notizmappe beim Start danach und sperrt sich nach einer einstellbaren Zeit
ohne Benutzung (Standard 15 Minuten, 0 = nur beim Start). 🔒 unten in der Leiste
sperrt sofort. Vor dem Sperren wird gespeichert.

Die Dateien bleiben unverschlüsselt und lesbar — die Sperre schützt die Oberfläche,
nicht die Platte. Nextcloud synchronisiert weiter wie bisher.

## Server für ein Team (Docker)

Damit mehrere Leute an denselben Notizbüchern arbeiten, läuft die Notizmappe als
Server; jeder öffnet sie im Browser, installieren muss niemand etwas.

```bash
docker compose up -d                  # nimmt ghcr.io/lucywolf/notizmappe:latest
docker logs notizmappe                # dort steht der Einrichtungscode
```

Dann `http://<rechner>:8099` öffnen, Code eingeben und das Admin-Konto anlegen. Der
Code steht nur im Protokoll, damit nicht der Erstbeste, der die Adresse findet, sich
zum Admin macht. Ohne fertiges Image: `docker compose up -d --build`.

**Konten und Projekte** — in den Einstellungen (Zahnrad) legt ein Admin Konten an.
Jedes **Notizbuch ist ein Projekt**: Admins sehen alle, alle anderen nur die, bei
denen sie unter „Projekte“ angehakt sind. Wer selbst ein Notizbuch anlegt, ist
automatisch drin; ganze Notizbücher löschen dürfen nur Admins. Wer nicht Mitglied
ist, bekommt 404 — er erfährt nicht einmal, dass es das Notizbuch gibt.

Arbeiten zwei Leute gleichzeitig an **derselben Seite**, greift die Konflikterkennung
von oben: wer mit einem veralteten Stand speichert, wird gefragt, statt die fremde
Änderung zu überschreiben. Live-Mitschreiben wie in Google Docs gibt es nicht.

**Fürs Internet** gehört HTTPS davor, z. B. Caddy:

```
notizen.example.de {
    reverse_proxy 127.0.0.1:8099
}
```

Bei nginx `proxy_set_header Host $host;` und `X-Forwarded-Proto` mitgeben — sonst
lehnt die Herkunftsprüfung Änderungen ab bzw. der Keks bekommt kein `Secure`.

Gespeichert wird in zwei Volumes: `/notizen` (die Notizbücher, eine `.zugriff.json`
pro Notizbuch hält die Mitglieder) und `/konfig` (`konten.json`: scrypt-Hashes,
Sitzungen nur als SHA-256). Im Server-Betrieb (`NOTIZMAPPE_SERVER=1`) sind
Selbstupdate und Ordnerwahl abgeschaltet — aktualisiert wird mit
`docker compose pull && docker compose up -d`. Das Image baut `docker.yml` bei jedem
Release; beim allerersten Mal muss das Paket auf GitHub einmal auf „Public“
gestellt werden.

**Vom Desktop aus** — in der installierten Notizmappe unter **Einstellungen → Server**
Adresse, Name und Passwort eintragen und „Verbinden“. Der Server öffnet sich in einem
eigenen Fenster neben der lokalen Mappe, mit seinen Konten und Projekten. Gespeichert
wird nicht das Passwort, sondern ein Geräteschlüssel (in
`~/.config/notizmappe/einstellungen.json`, nur für den eigenen Benutzer lesbar). Am
Server lässt er sich unter „Mein Konto“ einzeln abmelden; ein neues Passwort macht
alle Geräteschlüssel ungültig.

**Sicherheit** — Anmeldung mit Bremse gegen Passwortraten (pro Absender und pro
Name), Keks `HttpOnly` + `SameSite=Strict`, Änderungen von fremden Seiten werden an
der Herkunft erkannt und abgelehnt. Ein neues Passwort meldet alle anderen
Sitzungen und Geräte ab.

## HTML aus dem Editor

Aus dem Editor kommendes HTML wird beim **Speichern** gesäubert (`app/reinigen.py`,
Positivliste). Das passiert absichtlich vor dem Schreiben, nicht erst beim Anzeigen:
sonst steht der Dreck in der Datei und jeder spätere Weg — Export, Suche, zweite
Oberfläche — sieht ihn wieder.

## Noch nicht gebaut

Bilder und Dateianhänge · Zeichenebene mit Stift · Suche über alle Seiten ·
Tags und Verweise zwischen Seiten · Papierkorb-Ansicht zum Wiederherstellen ·
PWA für das Handy (offline) · verschieben von Seiten zwischen Abschnitten.
