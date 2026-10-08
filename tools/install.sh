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

  if [ ! -x "$ZIEL/.venv/bin/python" ]; then
    sagen "  Umgebung anlegen …"
    "$py" -m venv "$ZIEL/.venv" || fehler "venv liess sich nicht anlegen (Paket python3-venv fehlt?)"
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
exec env PYTHONPATH="$ZIEL/app" NOTIZEN_ORDNER="\${NOTIZEN_ORDNER:-$DATEN}" \\
  "$ZIEL/.venv/bin/python" -m uvicorn main:app --app-dir "$ZIEL/app" \\
  --host "\${HOST:-127.0.0.1}" --port "\${PORT:-$PORT}"
EOF
  chmod +x "$ZIEL/starten.sh"

  # Oeffnen heisst: Dienst sicherstellen, dann Browser. Als eigene Datei, damit der
  # Menueintrag per TryExec daran haengt - wird das Programm entfernt, verschwindet
  # der Eintrag von selbst statt ins Leere zu zeigen.
  cat > "$ZIEL/oeffnen.sh" <<EOF
#!/usr/bin/env bash
set -uo pipefail
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  systemctl --user start notizmappe.service 2>/dev/null
elif ! curl -sf -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null; then
  # Ohne systemd selbst starten und die Prozessnummer hinterlassen, damit man den
  # Server wieder findet - sonst bleibt er unerreichbar im Hintergrund haengen.
  setsid "$ZIEL/starten.sh" >> "$ZIEL/.lauf.log" 2>&1 &
  echo \$! > "$ZIEL/.pid"
fi
for i in \$(seq 20); do
  curl -sf -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null && break
  sleep 0.3
done
exec xdg-open "http://127.0.0.1:$PORT/"
EOF
  chmod +x "$ZIEL/oeffnen.sh"

  printf '%s\n' "$NEU" > "$ZIEL/.version"
  printf 'ZIEL=%s\nDATEN=%s\nPORT=%s\n' "$ZIEL" "$DATEN" "$PORT" > "$ZIEL/.einrichtung"

  # Denselben Dateinamen benutzt auch der Doppelklick-Installer (APP_ID=notizmappe),
  # es entsteht also kein zweiter Eintrag - wer zuletzt schreibt, gewinnt, und beide
  # Varianten starten dasselbe.
  mkdir -p "$(dirname "$MENUE")"
  cat > "$MENUE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Notizmappe
GenericName=Notizen
Comment=Freie Notizflaeche, Daten im eigenen Ordner ($NEU)
Exec=$ZIEL/oeffnen.sh
TryExec=$ZIEL/oeffnen.sh
Icon=accessories-text-editor
Terminal=false
Categories=Office;Utility;TextEditor;
StartupNotify=false
EOF
  update-desktop-database "$(dirname "$MENUE")" >/dev/null 2>&1 || true

  if dienst_moeglich; then
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
Environment=NOTIZEN_ORDNER=$DATEN
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
  sagen "Fertig. http://127.0.0.1:$PORT"
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
  rm -f "$AUTOSTART" "$MENUE"
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
  [ -x "$ZIEL/oeffnen.sh" ] && exec "$ZIEL/oeffnen.sh"
  command -v xdg-open >/dev/null 2>&1 && exec xdg-open "http://127.0.0.1:$PORT/"
  sagen "http://127.0.0.1:$PORT"
}

# --------------------------------------------------------------------- Menue

case "${1:-}" in
  --starten|--open) starten; exit 0 ;;
  --update|--install|--still) einrichten; exit 0 ;;
  --deinstallieren|--uninstall) deinstallieren; exit 0 ;;
  --version) sagen "Notizmappe $NEU"; exit 0 ;;
  --hilfe|-h|--help)
    sagen "Notizmappe $NEU"
    sagen "  --install / --update   einrichten oder aktualisieren"
    sagen "  --deinstallieren       Programm entfernen (Notizen bleiben)"
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
