# Notizmappe

Freie Notizfläche wie OneNote, aber die Daten liegen als Dateien in **deinem**
Ordner — Nextcloud, NAS-Freigabe oder einfach lokal. Kein Konto, kein Microsoft.

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
`~/Notizen` (Daten), ein Menüeintrag und — wenn systemd im Benutzerkontext
erreichbar ist — der Dienst `notizmappe.service`, sonst ein Autostart-Eintrag der
Sitzung. Läuft schon eine Fassung, fragt der Installer: aktualisieren,
deinstallieren oder abbrechen.

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

Dann http://127.0.0.1:8099 öffnen. Umgebungsvariablen: `NOTIZEN_ORDNER`, `HOST`, `PORT`.

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
