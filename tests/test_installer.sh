#!/usr/bin/env bash
# Die Installationsdatei in einem Wegwerf-Heimverzeichnis durchspielen.
#
#     tests/test_installer.sh [pfad/zur/installer.sh]
#
# Ohne Angabe wird die neueste aus dist/ genommen (tools/paket_bauen.sh baut sie).
# Der systemd des Benutzers wird absichtlich ausgeklammert (XDG_RUNTIME_DIR und
# DBUS weg), damit hier kein Dienst im echten Konto landet.
set -uo pipefail

WURZEL=$(cd "$(dirname "$0")/.." && pwd)
PAKET=${1:-$(ls -t "$WURZEL"/dist/notizmappe-v*-installer.sh 2>/dev/null | head -1)}
[ -f "$PAKET" ] || { echo "Keine Installationsdatei gefunden - erst ./tools/paket_bauen.sh" >&2; exit 2; }
VER=$(tr -d ' \n' < "$WURZEL/app/VERSION")
H=$(mktemp -d /tmp/notizmappe-probe-XXXX)
PORT=8155
fehler=0

# Bei einem Fehlschlag die genannten Dateien zeigen - sonst steht im Buildlauf nur
# "FEHLER" und man raet, was das Programm eigentlich gesagt hat.
pruefe() {
  if eval "$2" >/dev/null 2>&1; then
    echo "  ok    $1"
  else
    echo "FEHLER  $1"
    fehler=$((fehler+1))
    for datei in "${@:3}"; do
      [ -s "$datei" ] || continue
      echo "        --- $(basename "$datei") ---"
      sed 's/^/        /' "$datei" | tail -15
    done
  fi
}
lauf() { env -u XDG_RUNTIME_DIR -u DBUS_SESSION_BUS_ADDRESS \
           HOME="$H" PATH="$PATH" NOTIZMAPPE_ZIEL="$H/.local/share/notizmappe" \
           NOTIZEN_ORDNER="$H/Notizen" PORT="$PORT" bash "$PAKET" "$@" < /dev/null; }

echo "Paket: $(basename "$PAKET")  Probe-Heim: $H"
pruefe "--version nennt die Nummer" '[ "$(lauf --version)" = "Notizmappe v$VER" ]'

echo "--- Installieren ---"
lauf --install || { echo "FEHLER  Installation abgebrochen"; fehler=$((fehler+1)); }
Z=$H/.local/share/notizmappe
pruefe "Programm liegt im Ziel"             "[ -f '$Z/app/fenster.py' ]"
pruefe "Oberflaeche liegt im Ziel"          "[ -f '$Z/app/oberflaeche/index.html' ]"
pruefe "Version mitgeschrieben"             "[ \"\$(cat '$Z/app/VERSION')\" = $VER ]"
pruefe "venv angelegt"                      "[ -x '$Z/.venv/bin/python' ]"
pruefe "venv sieht die Systempakete"        "grep -q 'include-system-site-packages = true' '$Z/.venv/pyvenv.cfg'"
pruefe "kein Webserver mehr im venv"        "! '$Z/.venv/bin/python' -c 'import fastapi' 2>/dev/null"
pruefe "pywebview im venv"                  "'$Z/.venv/bin/python' -c 'import webview'"
pruefe "Programm (Fenster) ausfuehrbar"     "[ -x '$Z/notizmappe' ]"
pruefe "kein Hintergrunddienst"             "[ ! -f '$H/.config/systemd/user/notizmappe.service' ]"
pruefe "kein Autostart"                     "[ ! -f '$H/.config/autostart/notizmappe-dienst.desktop' ]"
pruefe "kein Startskript fuer einen Dienst" "[ ! -f '$Z/starten.sh' ]"
pruefe "Notizordner angelegt"               "[ -d '$H/Notizen' ]"
pruefe "Menueintrag angelegt"               "[ -f '$H/.local/share/applications/notizmappe.desktop' ]"
pruefe "Menueintrag startet das Programm"   "grep -q 'Exec=$Z/notizmappe' '$H/.local/share/applications/notizmappe.desktop'"
pruefe "Version im Menueintrag"             "grep -q $VER '$H/.local/share/applications/notizmappe.desktop'"
pruefe "Symbol mitinstalliert"              "[ -s '$H/.local/share/icons/hicolor/512x512/apps/notizmappe.png' ]"
pruefe "Menueintrag zeigt aufs eigene Symbol" "grep -q '^Icon=notizmappe$' '$H/.local/share/applications/notizmappe.desktop'"
pruefe "Nichts im echten Heim gelandet"     "[ ! -e \$HOME/.config/systemd/user/notizmappe.service ]"

mkdir -p "$H/Notizen/Probe/Allgemein"
echo '{"format":1,"titel":"Probe","rev":1,"elemente":[]}' > "$H/Notizen/Probe/Allgemein/Probe.json"

echo "--- Installierte Fassung pruefen ---"
env HOME="$H" "$Z/notizmappe" --pruefen > "$H/lauf.log" 2>&1
pruefe "--pruefen laeuft durch"           "[ $? -eq 0 ]" "$H/lauf.log"
pruefe "findet die Oberflaeche"           "grep -q 'Oberfläche:.*da' '$H/lauf.log'" "$H/lauf.log"
pruefe "liest die Daten"                  "grep -q 'Daten:' '$H/lauf.log'" "$H/lauf.log"
pruefe "Keine Ausnahme im Log"            "! grep -qi traceback '$H/lauf.log'" "$H/lauf.log"

echo "--- und macht dabei keinen Port auf ---"
env HOME="$H" NOTIZMAPPE_OHNE_FENSTER=1 "$Z/notizmappe" > "$H/ohne.log" 2>&1 &
ohnepid=$!
sleep 4
offen=$(ss -tlnp 2>/dev/null | grep -c "pid=$ohnepid," || true)
kill $ohnepid 2>/dev/null; wait $ohnepid 2>/dev/null
pruefe "kein offener Port"                "[ \"${offen:-0}\" = 0 ]" "$H/ohne.log"
pruefe "meldet Version und Ordner"        "grep -q 'Ohne Fenster' '$H/ohne.log'" "$H/ohne.log"

echo "--- Rueckwaerts installieren wird verweigert ---"
hoeher=$(python3 -c "t='$VER'.split('.'); t[-1]=str(int(t[-1])+1); print('.'.join(t))")
echo "$hoeher" > "$Z/app/VERSION"
aus=$(lauf --install 2>&1); rueck=$?
pruefe "Abbruch bei aelterem Paket" "[ $rueck -ne 0 ]"
pruefe "Begruendung genannt"        "printf '%s' \"\$aus\" | grep -qi rueckwaerts"
pruefe "Dateien unangetastet"       "[ \"\$(cat '$Z/app/VERSION')\" = $hoeher ]"
echo "$VER" > "$Z/app/VERSION"

echo "--- Aktualisieren auf dieselbe Version ---"
aus=$(lauf --update 2>&1)
pruefe "Neu auflegen geht"              "printf '%s' \"\$aus\" | grep -q 'schon installiert'"
pruefe "Notizen beim Update unberuehrt" "[ -d '$H/Notizen/Probe' ]"
pruefe "Pakete kamen aus dem Paket, nicht aus dem Netz" "! printf '%s' \"\$aus\" | grep -q 'aus dem Netz'"

echo "--- --starten: einrichten, und ohne Bildschirm sauber melden ---"
# Hier gibt es kein Fenstersystem, also kann auch kein Fenster aufgehen. Richtig
# ist dann: den Grund melden und enden.
Z3=$H/drittes
env -u XDG_RUNTIME_DIR -u DBUS_SESSION_BUS_ADDRESS -u DISPLAY -u WAYLAND_DISPLAY \
  HOME="$H" NOTIZMAPPE_ZIEL="$Z3" NOTIZEN_ORDNER="$H/Notizen" \
  timeout 120 bash "$PAKET" --starten < /dev/null > "$H/starten.log" 2>&1 &
startpid=$!
wait $startpid 2>/dev/null
pruefe "--starten richtet ein, wenn nichts da ist" "[ -f '$Z3/app/fenster.py' ]"
pruefe "Programm angelegt"                         "[ -x '$Z3/notizmappe' ]"
pruefe "ohne Fenster kein heimlicher Browser"      "! grep -qi 'im normalen Browser' '$H/starten.log'" "$H/starten.log"
pruefe "Grund wird genannt"                        "grep -qi 'fenster' '$H/starten.log'" "$H/starten.log"
pruefe "Menueintrag haengt an TryExec"             "grep -q 'TryExec=$Z3/notizmappe' '$H/.local/share/applications/notizmappe.desktop'"
rm -rf "$Z3"

echo "--- Beschaedigte Datei ---"
kaputt=$H/kaputt.sh
cp "$PAKET" "$kaputt"
python3 - "$kaputt" <<'PY'
import sys
p = sys.argv[1]
d = open(p, 'rb').read()
# rindex: das erste Vorkommen steht im awk-Muster im Kopf, nicht in der Nutzlast.
i = d.rindex(b'__NUTZLAST__\n') + len(b'__NUTZLAST__\n') + 5000
open(p, 'wb').write(d[:i] + (b'X' if d[i:i+1] != b'X' else b'Y') + d[i+1:])
PY
aus=$(env -u XDG_RUNTIME_DIR HOME="$H" NOTIZMAPPE_ZIEL="$H/zweitziel" bash "$kaputt" --install 2>&1); kaputtlauf=$?
pruefe "Beschaedigtes Paket bricht ab" "[ $kaputtlauf -ne 0 ]"
pruefe "Pruefsumme wird genannt"       "printf '%s' \"\$aus\" | grep -qi pruefsumme"
pruefe "Nichts installiert"            "[ ! -d '$H/zweitziel' ]"

echo "--- Deinstallieren ---"
lauf --deinstallieren | sed 's/^/      /'
pruefe "Programmordner weg" "[ ! -d '$Z' ]"
pruefe "Menueintrag weg"    "[ ! -f '$H/.local/share/applications/notizmappe.desktop' ]"
pruefe "Symbol weg"         "[ ! -f '$H/.local/share/icons/hicolor/512x512/apps/notizmappe.png' ]"
pruefe "NOTIZEN BLEIBEN"    "[ -d '$H/Notizen/Probe' ]"
lauf --deinstallieren >/dev/null 2>&1
pruefe "Zweites Deinstallieren meldet sauber Fehler" "[ $? -ne 0 ]"

echo
[ $fehler -eq 0 ] && echo "alles gruen" || echo "$fehler FEHLER"
rm -rf "$H"
exit $fehler
