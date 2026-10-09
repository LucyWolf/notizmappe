#!/usr/bin/env bash
# Wird vom Installer-Paket aufgerufen, nicht direkt. Neben dieser Datei liegen
# app/, vendor/ (mitgelieferte Python-Pakete) und requirements.txt.
#
# Installiert ohne Root-Rechte ins eigene Heimverzeichnis. Die Notizen bleiben
# davon unberuehrt - auch beim Deinstallieren.
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
NEU=$(tr -d ' \n' < "$HIER/app/VERSION")
ZIEL=${NOTIZMAPPE_ZIEL:-$HOME/.local/share/notizmappe}
DATEN=${NOTIZEN_ORDNER:-$HOME/Notizen}
PORT=${PORT:-8099}
MENUE=$HOME/.local/share/applications/notizmappe.desktop
SYMBOL=$HOME/.local/share/icons/hicolor/512x512/apps/notizmappe.png
UNIT=$HOME/.config/systemd/user/notizmappe.service
AUTOSTART=$HOME/.config/autostart/notizmappe-dienst.desktop

sagen() { printf '%s\n' "$*"; }
fehler() { printf 'Fehler: %s\n' "$*" >&2; exit 1; }

# Versionen vergleichen. 1.0.9 ist kleiner als 1.0.10 - deshalb sort -V und nicht
# ein Zeichenvergleich, der bei zweistelligen Stellen falsch liegt.
kleiner() { [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$1" ]; }

dienst_moeglich() { command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; }

python_finden() {
  for p in python3.13 python3.12 python3.11 python3 ; do
    command -v "$p" >/dev/null 2>&1 || continue
    "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null && { echo "$p"; return 0; }
  done
  return 1
}

installiert() { [ -f "$ZIEL/app/VERSION" ] && tr -d ' \n' < "$ZIEL/app/VERSION"; }

# ---------------------------------------------------------------- Einrichten

einrichten() {
  local alt; alt=$(installiert || true)
  if [ -n "$alt" ]; then
    if [ "$alt" = "$NEU" ]; then
      sagen "Version $NEU ist schon installiert - wird neu aufgelegt."
    elif kleiner "$NEU" "$alt"; then
      # Rueckwaerts installieren heisst: eine Datei, die eine neuere Fassung
      # geschrieben hat, wird von einer aelteren gelesen. Lieber abbrechen.
      fehler "Installiert ist $alt, das Paket hat $NEU. Rueckwaerts wird nicht installiert.
Wenn du das wirklich willst: erst deinstallieren (--deinstallieren)."
    else
      sagen "Aktualisierung $alt -> $NEU"
    fi
  else
    sagen "Notizmappe $NEU wird installiert"
  fi

  local py; py=$(python_finden) || fehler "Kein Python 3.10 oder neuer gefunden."
  sagen "  Python:       $($py -V 2>&1)"
  sagen "  Programm:     $ZIEL"
  sagen "  Notizen:      $DATEN"
  sagen "  Adresse:      http://127.0.0.1:$PORT"

  mkdir -p "$ZIEL" "$DATEN"
  # Alte Programmdateien weg, Notizen anfassen wir nicht.
  rm -rf "$ZIEL/app"
  cp -r "$HIER/app" "$ZIEL/app"
  cp "$HIER/requirements.txt" "$ZIEL/"

  # --system-site-packages: die Webansicht fuers Fenster (PyGObject/WebKit2 oder Qt)
  # kommt als Distributionspaket und ist per pip nicht zu bekommen. Ohne das Flag
  # sieht das venv sie nicht.
  if [ -x "$ZIEL/.venv/bin/python" ] \
     && ! grep -q "include-system-site-packages = true" "$ZIEL/.venv/pyvenv.cfg" 2>/dev/null; then
    sagen "  Umgebung war ohne Zugriff auf die Systempakete - wird neu angelegt."
    rm -rf "$ZIEL/.venv"
  fi
  if [ ! -x "$ZIEL/.venv/bin/python" ]; then
    sagen "  Umgebung anlegen …"
    "$py" -m venv --system-site-packages "$ZIEL/.venv" \
      || fehler "venv liess sich nicht anlegen (Paket python3-venv fehlt?)"
  fi

  sagen "  Pakete einrichten …"
  if [ -d "$HIER/vendor" ] && "$ZIEL/.venv/bin/pip" install -q --no-index \
        --find-links "$HIER/vendor" -r "$ZIEL/requirements.txt" 2>/dev/null; then
    sagen "  (aus dem Paket, ohne Internet)"
  else
    # Die mitgelieferten Pakete passen nicht zu dieser Python-Version - dann
    # eben aus dem Netz. Nur dafuer ist hier ueberhaupt Internet noetig.
    sagen "  (mitgelieferte Pakete passen nicht - hole sie aus dem Netz)"
    "$ZIEL/.venv/bin/pip" install -q -r "$ZIEL/requirements.txt" \
      || fehler "Pakete liessen sich nicht einrichten."
  fi

  # Startskript, damit man es auch ohne Dienst von Hand starten kann.
  cat > "$ZIEL/starten.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec env PYTHONPATH="$ZIEL/app" \\
  "$ZIEL/.venv/bin/python" -m uvicorn main:app --app-dir "$ZIEL/app" \\
  --host "\${HOST:-127.0.0.1}" --port "\${PORT:-$PORT}"
EOF
  chmod +x "$ZIEL/starten.sh"

  # Das eigentliche Programm: ein Fenster. Laeuft nebenher schon ein Dienst, dockt
  # es daran an; sonst bringt es seinen Server selbst mit und nimmt ihn beim
  # Schliessen wieder mit. Eigene Datei, damit der Menueintrag per TryExec daran
  # haengt - wird das Programm entfernt, verschwindet der Eintrag von selbst.
  cat > "$ZIEL/notizmappe" <<EOF
#!/usr/bin/env bash
set -uo pipefail
exec env PYTHONPATH="$ZIEL/app" \
  PORT="\${PORT:-$PORT}" "$ZIEL/.venv/bin/python" "$ZIEL/app/fenster.py" "\$@"
EOF
  chmod +x "$ZIEL/notizmappe"

  # Der Datenordner steht nicht mehr fest im Starter, sondern in den Einstellungen
  # dieses Rechners - dort laesst er sich in der Oberflaeche umstellen. Hier nur
  # eintragen, wenn bei der Installation ausdruecklich einer genannt wurde und
  # noch keiner gewaehlt ist.
  if [ -n "${NOTIZEN_ORDNER:-}" ]; then
    "$ZIEL/.venv/bin/python" - "$DATEN" <<'EINTRAG' || true
import json, os, sys
from pathlib import Path
k = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "notizmappe"
k.mkdir(parents=True, exist_ok=True)
f = k / "einstellungen.json"
try:
    d = json.loads(f.read_text(encoding="utf-8"))
except (OSError, ValueError):
    d = {}
if not d.get("ordner"):
    d["ordner"] = sys.argv[1]
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
EINTRAG
  fi

  printf '%s\n' "$NEU" > "$ZIEL/.version"
  printf 'ZIEL=%s\nDATEN=%s\nPORT=%s\n' "$ZIEL" "$DATEN" "$PORT" > "$ZIEL/.einrichtung"

  # Denselben Dateinamen benutzt auch der Doppelklick-Installer (APP_ID=notizmappe),
  # es entsteht also kein zweiter Eintrag - wer zuletzt schreibt, gewinnt, und beide
  # Varianten starten dasselbe.
  # Symbol aus dem Paket, nicht aus dem Netz nachgeladen: der Installer soll auch
  # ohne Internet ein vollstaendiges Programm hinterlassen.
  SYMBOL_NAME=accessories-text-editor
  if [ -f "$HIER/icon.png" ]; then
    mkdir -p "$(dirname "$SYMBOL")"
    cp -f "$HIER/icon.png" "$SYMBOL"
    SYMBOL_NAME=notizmappe
    command -v gtk-update-icon-cache >/dev/null 2>&1 \
      && gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
  fi

  mkdir -p "$(dirname "$MENUE")"
  cat > "$MENUE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Notizmappe
GenericName=Notizen
Comment=Freie Notizflaeche, Daten im eigenen Ordner ($NEU)
StartupWMClass=Notizmappe
Exec=$ZIEL/notizmappe
TryExec=$ZIEL/notizmappe
Icon=$SYMBOL_NAME
Terminal=false
Categories=Office;Utility;TextEditor;
StartupNotify=false
EOF
  update-desktop-database "$(dirname "$MENUE")" >/dev/null 2>&1 || true

  # Standard: kein Hintergrunddienst. Die Notizmappe ist ein Programm - startet man
  # es, laeuft es; schliesst man das Fenster, ist es weg. Wer sie auch vom Handy
  # oder vom zweiten Rechner aus erreichen will, nimmt --mit-dienst.
  if [ "${MIT_DIENST:-0}" != "1" ]; then
    if dienst_moeglich && systemctl --user is-enabled notizmappe.service >/dev/null 2>&1; then
      sagen "  Hintergrunddienst wird abgeschaltet (--mit-dienst behält ihn)."
      systemctl --user disable --now notizmappe.service >/dev/null 2>&1 || true
      rm -f "$UNIT"
      systemctl --user daemon-reload || true
    fi
    rm -f "$AUTOSTART"
  elif dienst_moeglich; then
    mkdir -p "$(dirname "$UNIT")"
    cat > "$UNIT" <<EOF
[Unit]
Description=Notizmappe $NEU
After=network.target
# Ist das Programm entfernt worden, bleibt der Dienst still statt zu scheitern.
ConditionPathExists=$ZIEL/.venv/bin/python

[Service]
Type=simple
Environment=PYTHONPATH=$ZIEL/app
ExecStart=$ZIEL/.venv/bin/python -m uvicorn main:app --app-dir $ZIEL/app --host 127.0.0.1 --port $PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now notizmappe.service >/dev/null
    sagen "  Dienst läuft (systemctl --user status notizmappe)"
    rm -f "$AUTOSTART"
  else
    # Kein systemd im Benutzerkontext (z.B. in einem Container): dann startet
    # die Sitzung das Programm selbst.
    mkdir -p "$(dirname "$AUTOSTART")"
    cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=Notizmappe (Dienst)
Exec=$ZIEL/starten.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
    sagen "  Kein systemd gefunden - Autostart über die Sitzung eingerichtet."
    sagen "  Jetzt starten: $ZIEL/starten.sh"
  fi

  sagen ""
  if [ "${MIT_DIENST:-0}" = "1" ]; then
    sagen "Fertig. Im Menü: Notizmappe - und im Netz unter http://127.0.0.1:$PORT"
  else
    sagen "Fertig. Im Menü: Notizmappe   (oder direkt: $ZIEL/notizmappe)"
  fi
}

# ------------------------------------------------------------ Deinstallieren

deinstallieren() {
  local alt; alt=$(installiert || true)
  [ -n "$alt" ] || fehler "Hier ist keine Notizmappe installiert ($ZIEL)."
  [ -f "$ZIEL/.einrichtung" ] && . "$ZIEL/.einrichtung"
  if dienst_moeglich; then
    systemctl --user disable --now notizmappe.service >/dev/null 2>&1 || true
    rm -f "$UNIT"
    systemctl --user daemon-reload || true
  fi
  rm -f "$AUTOSTART" "$MENUE" "$SYMBOL"
  rm -rf "$ZIEL"
  sagen "Notizmappe $alt entfernt."
  sagen "Die Notizen in $DATEN sind absichtlich stehen geblieben."
}

# -------------------------------------------------------------- Oeffnen/Start

hinweis() {
  # Beim Klick aus dem Menue gibt es kein Terminal - dann wenigstens ein Fenster.
  if command -v kdialog >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    kdialog --title "Notizmappe" --passivepopup "$1" 8 >/dev/null 2>&1 &
  elif command -v zenity >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    zenity --notification --text="$1" >/dev/null 2>&1 &
  else
    sagen "$1"
  fi
}

starten() {
  if [ -z "$(installiert || true)" ]; then
    # Erster Start nach dem Doppelklick-Installer: der hat nur diese Datei
    # hingelegt, eingerichtet wird jetzt.
    hinweis "Notizmappe wird eingerichtet, das dauert einen Moment …"
    einrichten
  fi
  [ -x "$ZIEL/notizmappe" ] && exec "$ZIEL/notizmappe"
  sagen "Programm nicht gefunden: $ZIEL/notizmappe"
}

# --------------------------------------------------------------------- Menue

# --mit-dienst darf vor oder hinter dem Befehl stehen
for arg in "$@"; do
  [ "$arg" = "--mit-dienst" ] && MIT_DIENST=1
done
set -- $(printf '%s\n' "$@" | grep -v -- '--mit-dienst' || true)

case "${1:-}" in
  --starten|--open) starten; exit 0 ;;
  --update|--install|--still) einrichten; exit 0 ;;
  --deinstallieren|--uninstall) deinstallieren; exit 0 ;;
  --version) sagen "Notizmappe $NEU"; exit 0 ;;
  --hilfe|-h|--help)
    sagen "Notizmappe $NEU"
    sagen "  --install / --update   einrichten oder aktualisieren"
    sagen "  --deinstallieren       Programm entfernen (Notizen bleiben)"
    sagen "  --mit-dienst           zusaetzlich im Hintergrund laufen lassen,"
    sagen "                         damit Handy und andere Rechner drankommen"
    sagen "Variablen: NOTIZMAPPE_ZIEL, NOTIZEN_ORDNER, PORT"
    exit 0 ;;
esac

ALT=$(installiert || true)
if [ -z "$ALT" ] || [ ! -t 0 ]; then
  einrichten
  exit 0
fi

sagen "Notizmappe $ALT ist installiert, dieses Paket hat $NEU."
sagen "  1) aktualisieren"
sagen "  2) deinstallieren (Notizen bleiben)"
sagen "  3) abbrechen"
printf 'Auswahl [1]: '
read -r wahl
case "${wahl:-1}" in
  1) einrichten ;;
  2) deinstallieren ;;
  *) sagen "Abgebrochen." ;;
esac
