#!/usr/bin/env bash
# Neue Fassung herausgeben: Version hochzaehlen, committen, Tag setzen, pushen.
# Den Rest macht .github/workflows/release.yml (Pakete bauen, Release anlegen) und
# danach installer.yml (Doppelklick-Dateien, setup.exe).
#
#   ./tools/veroeffentlichen.sh                     letzte Stelle +1
#   ./tools/veroeffentlichen.sh 1.1.0               genau diese Nummer
set -euo pipefail
cd "$(dirname "$0")/.."

ALT=$(tr -d ' \n' < app/VERSION)

if [ $# -ge 1 ]; then
  NEU=$1
else
  # Letzte Stelle zaehlt bis 99, dann die davor - und nie rueckwaerts.
  NEU=$(python3 - "$ALT" <<'PY'
import sys
teile = [int(t) for t in sys.argv[1].split(".")]
teile[-1] += 1
i = len(teile) - 1
while i > 0 and teile[i] > 99:
    teile[i] = 0
    teile[i - 1] += 1
    i -= 1
print(".".join(str(t) for t in teile))
PY
)
fi

kleiner() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$2" ] && [ "$1" != "$2" ]; }
if ! kleiner "$NEU" "$ALT"; then
  echo "Fehler: $NEU ist nicht groesser als $ALT. Eine Nummer wird nie wiederverwendet." >&2
  exit 1
fi

# Die letzte Stelle zaehlt bis 99. Eine Stelle davor darf nur hochgehen, wenn die
# letzte wirklich voll war - sonst verbrennt ein Sprung wie 1.0.3 -> 1.1.0 den
# ganzen Rest des Hunderters. Das ist mir schon passiert.
python3 - "$ALT" "$NEU" <<'PRUEF' || exit 1
import sys
alt = [int(t) for t in sys.argv[1].split(".")]
neu = [int(t) for t in sys.argv[2].split(".")]
if len(alt) != len(neu):
    sys.exit(f"Fehler: {sys.argv[2]} hat andere Stellen als {sys.argv[1]}.")
if neu[:-1] != alt[:-1]:
    if alt[-1] < 99:
        sys.exit(f"Fehler: {sys.argv[1]} -> {sys.argv[2]} springt eine Stelle weiter, "
                 f"obwohl die letzte erst bei {alt[-1]} steht.\n"
                 f"       Die letzte Stelle zaehlt bis 99. Gemeint war vermutlich "
                 + ".".join(str(t) for t in alt[:-1] + [alt[-1] + 1]) + ".")
    # bei vollem Hunderter: weiterzaehlen mit Uebertrag, jede Stelle hoechstens 99
    soll = alt[:]
    soll[-1] += 1
    i = len(soll) - 1
    while i > 0 and soll[i] > 99:
        soll[i] = 0
        soll[i - 1] += 1
        i -= 1
    if neu != soll:
        sys.exit(f"Fehler: nach {sys.argv[1]} kommt " + ".".join(str(t) for t in soll) + f", nicht {sys.argv[2]}.")
PRUEF
if git rev-parse -q --verify "refs/tags/v$NEU" >/dev/null; then
  echo "Fehler: Tag v$NEU gibt es schon." >&2
  exit 1
fi

echo "$ALT -> $NEU"
printf '%s\n' "$NEU" > app/VERSION
git add app/VERSION
git commit -q -m "Version $NEU" || true
git tag -a "v$NEU" -m "Notizmappe v$NEU"
git push -q origin HEAD
git push -q origin "v$NEU"

echo "Getaggt und gepusht. Der Workflow baut jetzt:"
echo "  https://github.com/$(git remote get-url origin | sed 's#.*[:/]\([^/]*/[^/]*\)\.git#\1#')/actions"
