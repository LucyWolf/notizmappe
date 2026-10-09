#!/usr/bin/env bash
# Baut aus dem Projekt eine einzige Installationsdatei:
#   dist/notizmappe-v<version>-installer.sh
#
# Darin stecken Programm, Installationsskript und die Python-Pakete als Rad-
# Dateien - der Installer braucht damit kein Internet und kein GitHub. Die
# Versionsnummer kommt aus app/VERSION und steht im Dateinamen, im Kopf der
# Datei, im Menueintrag und im Dienst.
set -euo pipefail

WURZEL=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(tr -d ' \n' < "$WURZEL/app/VERSION")
AUSGABE=$WURZEL/dist/notizmappe-v$VERSION-installer.sh
BAU=$(mktemp -d)
trap 'rm -rf "$BAU"' EXIT

echo "Notizmappe v$VERSION"

# Nichts einpacken, was nicht uebersetzt - lieber hier merken als beim Anwender.
"${PY:-$WURZEL/.venv/bin/python}" "$WURZEL/tools/pruefen.py"

PAKET=$BAU/notizmappe
mkdir -p "$PAKET"
cp -r "$WURZEL/app" "$PAKET/app"
find "$PAKET/app" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
cp "$WURZEL/requirements.txt" "$WURZEL/README.md" "$PAKET/"
cp "$WURZEL/icon.png" "$PAKET/icon.png"
cp "$WURZEL/tools/install.sh" "$PAKET/install.sh"
chmod +x "$PAKET/install.sh"

PYBAU=${PY:-$WURZEL/.venv/bin/python}

echo "  Python-Pakete holen …"
# pip wheel statt pip download: manche Pakete (proxy_tools, eine Abhaengigkeit von
# pywebview) gibt es nur als Quellarchiv. Beim Einrichten ohne Netz koennte pip die
# nicht bauen, weil ihm dafuer die Bauwerkzeuge fehlen. pip wheel erledigt das hier,
# wo noch Netz ist, und legt fertige Rad-Dateien ab.
if "$PYBAU" -m pip wheel -q --no-input -r "$WURZEL/requirements.txt" -w "$PAKET/vendor"; then
  # markupsafe und pydantic_core sind uebersetzt und haengen an der Python-Version.
  # Gebaut wird hier mit einer, installiert wird dort vielleicht mit einer anderen -
  # deshalb die gaengigen Fassungen gleich mitnehmen. Das kostet ein paar MB und
  # erspart dem Anwender, dass der Installer doch wieder ins Netz muss.
  for paket in markupsafe pydantic_core; do
    fassung=$(ls "$PAKET/vendor" | sed -n "s/^${paket}-\([0-9][^-]*\)-.*/\1/p" | head -1)
    [ -n "$fassung" ] || continue
    name=$(echo "$paket" | tr '_' '-')
    for abi in 311 312 313 314; do
      "$PYBAU" -m pip download -q --no-input --no-deps --only-binary=:all: \
        --python-version "$abi" --implementation cp \
        --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 \
        -d "$PAKET/vendor" "$name==$fassung" 2>/dev/null || true
    done
  done
  echo "  $(ls "$PAKET/vendor" | wc -l) Rad-Dateien"

  # Nachsehen, ob sich daraus wirklich ohne Netz einrichten laesst. Sonst faellt der
  # Installer beim Anwender stillschweigend auf den Netzweg zurueck - und ein
  # Offline-Paket, das Netz braucht, ist keines.
  PROBE=$(mktemp -d)
  "$PYBAU" -m venv --system-site-packages "$PROBE/venv" >/dev/null 2>&1
  if "$PROBE/venv/bin/pip" install -q --no-index --find-links "$PAKET/vendor" \
       -r "$WURZEL/requirements.txt" >/dev/null 2>&1; then
    echo "  Einrichtung ohne Netz: geht"
  else
    rm -rf "$PROBE"
    echo "  FEHLER: aus den mitgelieferten Paketen laesst sich nicht ohne Netz einrichten." >&2
    "$PROBE/venv/bin/pip" install --no-index --find-links "$PAKET/vendor" -r "$WURZEL/requirements.txt" 2>&1 | tail -15 >&2
    exit 1
  fi
  rm -rf "$PROBE"
else
  echo "  (kein Netz - Paket wird ohne vendor gebaut, der Installer holt sie dann selbst)"
  rm -rf "$PAKET/vendor"
fi

tar czf "$BAU/nutzlast.tgz" -C "$BAU" notizmappe
base64 "$BAU/nutzlast.tgz" > "$BAU/nutzlast.b64"
PRUEF=$(sha256sum "$BAU/nutzlast.tgz" | cut -d' ' -f1)
GROESSE=$(du -h "$BAU/nutzlast.tgz" | cut -f1)

mkdir -p "$WURZEL/dist"
cat > "$AUSGABE" <<KOPFEOF
#!/usr/bin/env bash
# Notizmappe v$VERSION - Installationsdatei, alles enthalten.
#
#   bash notizmappe-v$VERSION-installer.sh                einrichten/aktualisieren
#   bash notizmappe-v$VERSION-installer.sh --deinstallieren
#   bash notizmappe-v$VERSION-installer.sh --hilfe
#
# Installiert ohne Root nach ~/.local/share/notizmappe, Notizen nach ~/Notizen.
# Andere Orte: NOTIZMAPPE_ZIEL=… NOTIZEN_ORDNER=… PORT=… davor setzen.
set -euo pipefail

VERSION="$VERSION"
PRUEFSUMME="$PRUEF"

[ "\${1:-}" = "--version" ] && { echo "Notizmappe v\$VERSION"; exit 0; }

for werkzeug in base64 tar sha256sum; do
  command -v "\$werkzeug" >/dev/null 2>&1 || { echo "Fehler: \$werkzeug fehlt." >&2; exit 1; }
done

AUS=\$(mktemp -d) || exit 1
trap 'rm -rf "\$AUS"' EXIT

# Alles ab der Markierung ist die Nutzlast. Erst die Pruefsumme, dann auspacken -
# eine halb heruntergeladene Datei soll nicht halb installieren.
ZEILE=\$(awk '/^__NUTZLAST__\$/ {print NR + 1; exit 0}' "\$0")
tail -n "+\$ZEILE" "\$0" | base64 -d > "\$AUS/nutzlast.tgz"
ECHT=\$(sha256sum "\$AUS/nutzlast.tgz" | cut -d' ' -f1)
if [ "\$ECHT" != "\$PRUEFSUMME" ]; then
  echo "Fehler: Die Datei ist beschaedigt (Pruefsumme passt nicht)." >&2
  echo "  erwartet \$PRUEFSUMME" >&2
  echo "  gelesen  \$ECHT" >&2
  exit 1
fi

tar xzf "\$AUS/nutzlast.tgz" -C "\$AUS"
exec bash "\$AUS/notizmappe/install.sh" "\$@"

exit 0
__NUTZLAST__
KOPFEOF
cat "$BAU/nutzlast.b64" >> "$AUSGABE"
chmod +x "$AUSGABE"
( cd "$WURZEL/dist" && sha256sum "$(basename "$AUSGABE")" > "$(basename "$AUSGABE").sha256" )

echo "  Nutzlast:  $GROESSE  ($PRUEF)"
echo "  Fertig:    $AUSGABE  ($(du -h "$AUSGABE" | cut -f1))"
