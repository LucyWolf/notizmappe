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
pruefe "Programm liegt im Ziel"             "[ -f '$Z/app/main.py' ]"
pruefe "Version mitgeschrieben"             "[ \"\$(cat '$Z/app/VERSION')\" = $VER ]"
pruefe "venv angelegt"                      "[ -x '$Z/.venv/bin/python' ]"
pruefe "venv sieht die Systempakete"        "grep -q 'include-system-site-packages = true' '$Z/.venv/pyvenv.cfg'"
pruefe "fastapi aus dem Paket eingerichtet" "'$Z/.venv/bin/python' -c 'import fastapi'"
pruefe "pywebview im venv"                  "'$Z/.venv/bin/python' -c 'import webview'"
pruefe "Startskript ausfuehrbar"            "[ -x '$Z/starten.sh' ]"
pruefe "Programm (Fenster) ausfuehrbar"     "[ -x '$Z/notizmappe' ]"
pruefe "ohne --mit-dienst kein Dienst"      "[ ! -f '$H/.config/systemd/user/notizmappe.service' ]"
pruefe "ohne --mit-dienst kein Autostart"   "[ ! -f '$H/.config/autostart/notizmappe-dienst.desktop' ]"
pruefe "Notizordner angelegt"               "[ -d '$H/Notizen' ]"
pruefe "Menueintrag angelegt"               "[ -f '$H/.local/share/applications/notizmappe.desktop' ]"
pruefe "Menueintrag startet das Programm"   "grep -q 'Exec=$Z/notizmappe' '$H/.local/share/applications/notizmappe.desktop'"
pruefe "Version im Menueintrag"             "grep -q $VER '$H/.local/share/applications/notizmappe.desktop'"
pruefe "Symbol mitinstalliert"              "[ -s '$H/.local/share/icons/hicolor/512x512/apps/notizmappe.png' ]"
pruefe "Menueintrag zeigt aufs eigene Symbol" "grep -q '^Icon=notizmappe$' '$H/.local/share/applications/notizmappe.desktop'"
pruefe "Nichts im echten Heim gelandet"     "[ ! -e \$HOME/.config/systemd/user/notizmappe.service ]"

echo "--- Installierte Fassung starten und abfragen ---"
env HOME="$H" NOTIZEN_ORDNER="$H/Notizen" PORT=$PORT "$Z/starten.sh" > "$H/lauf.log" 2>&1 &
pid=$!
for i in $(seq 20); do curl -sf -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 0.5; done
pruefe "Startseite antwortet mit 200" "[ \"\$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/)\" = 200 ]"
pruefe "API antwortet"                "curl -sf 'http://127.0.0.1:$PORT/api/baum' | grep -q notizbuecher"
curl -sf -X POST -H 'Content-Type: application/json' -d '{"name":"Probe"}' "http://127.0.0.1:$PORT/api/notizbuch" >/dev/null
pruefe "Notizbuch landet im Notizordner" "[ -d '$H/Notizen/Probe' ]"
kill $pid 2>/dev/null; wait $pid 2>/dev/null
pruefe "Keine Ausnahme im Log"           "! grep -qi traceback '$H/lauf.log'"

echo "--- systemd-Unit auf Syntax ---"
sed -n '/^\[Unit\]/,/^WantedBy/p' "$WURZEL/tools/install.sh" \
  | sed -e "s|[\$]ZIEL|$Z|g" -e "s|[\$]DATEN|$H/Notizen|g" -e "s|[\$]PORT|$PORT|g" -e "s|[\$]NEU|$VER|g" \
  > "$H/notizmappe.service"
if command -v systemd-analyze >/dev/null 2>&1; then
  aus=$(systemd-analyze verify "$H/notizmappe.service" 2>&1 | grep -v 'Unit .* not found')
  pruefe "Unit ohne Beanstandung" "[ -z \"$aus\" ]"
  [ -n "$aus" ] && printf '%s\n' "$aus" | sed 's/^/      /'
else
  echo "  --    systemd-analyze nicht da, Unit nicht geprueft"
fi

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

echo "--- --starten: einrichten, und ohne Desktop sauber melden ---"
# Hier gibt es kein Fenstersystem, also kann auch kein Fenster aufgehen. Richtig
# ist dann: den Grund melden und enden - und gerade nicht heimlich einen Browser
# aufmachen. Der Server kommt hier nur hoch, wenn man ihn ausdruecklich will.
Z3=$H/drittes
env -u XDG_RUNTIME_DIR -u DBUS_SESSION_BUS_ADDRESS -u DISPLAY -u WAYLAND_DISPLAY \
  HOME="$H" NOTIZMAPPE_ZIEL="$Z3" NOTIZEN_ORDNER="$H/Notizen" PORT=8157 \
  timeout 120 bash "$PAKET" --starten < /dev/null > "$H/starten.log" 2>&1 &
startpid=$!
for i in $(seq 90); do curl -sf -o /dev/null http://127.0.0.1:8157/ 2>/dev/null && break; sleep 1; done
pruefe "--starten richtet ein, wenn nichts da ist" "[ -f '$Z3/app/main.py' ]"
pruefe "ohne Fenster kein heimlicher Browser"      "! grep -qi 'im normalen Browser' '$H/starten.log'" "$H/starten.log"
pruefe "Grund wird genannt"                        "grep -qi 'fenster' '$H/starten.log'" "$H/starten.log" "$H/.local/share/notizmappe/.fenster.log"
pruefe "Menueintrag haengt an TryExec"             "grep -q 'TryExec=$Z3/notizmappe' '$H/.local/share/applications/notizmappe.desktop'"
pruefe "Dienst-Unit nur bei vorhandenem Programm"  "grep -q ConditionPathExists '$WURZEL/tools/install.sh'"
kill $startpid 2>/dev/null; wait $startpid 2>/dev/null
# Und jetzt ausdruecklich als Server: dann muss er antworten.
env NOTIZMAPPE_NUR_SERVER=1 PORT=8157 NOTIZEN_ORDNER="$H/Notizen" HOME="$H" \
  timeout 25 "$Z3/notizmappe" > "$H/nurserver.log" 2>&1 &
nurpid=$!
for i in $(seq 25); do curl -sf -o /dev/null http://127.0.0.1:8157/ 2>/dev/null && break; sleep 1; done
pruefe "mit NOTIZMAPPE_NUR_SERVER laeuft der Server" "curl -sf http://127.0.0.1:8157/api/baum | grep -q notizbuecher" "$H/nurserver.log"
kill $nurpid 2>/dev/null; wait $nurpid 2>/dev/null
# Vollen Pfad nehmen: ein kurzes Muster traefe auch eine andere Shell, die
# diesen Text zufaellig in ihrer Kommandozeile stehen hat.
pkill -f "$Z3/.venv/bin/python" 2>/dev/null
sleep 2
pruefe "Server ist mit dem Programm gegangen" "! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8157/"

echo "--- --mit-dienst legt zusaetzlich den Hintergrunddienst an ---"
Z4=$H/viertes
env -u XDG_RUNTIME_DIR -u DBUS_SESSION_BUS_ADDRESS HOME="$H" \
  NOTIZMAPPE_ZIEL="$Z4" NOTIZEN_ORDNER="$H/Notizen" PORT=8158 \
  bash "$PAKET" --install --mit-dienst < /dev/null > "$H/dienst.log" 2>&1
pruefe "mit --mit-dienst: Autostart angelegt" "[ -f '$H/.config/autostart/notizmappe-dienst.desktop' ]"
pruefe "Programm trotzdem da"                 "[ -x '$Z4/notizmappe' ]"
rm -rf "$Z4" "$Z3" "$H/.config/autostart/notizmappe-dienst.desktop"

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
