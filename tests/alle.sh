#!/usr/bin/env bash
# Alle Tests. Baut vorher das Paket, weil der Installer-Test eines braucht.
#   tests/alle.sh            alles
#   tests/alle.sh --schnell  ohne Paketbau und Installer-Test
set -uo pipefail
WURZEL=$(cd "$(dirname "$0")/.." && pwd)
PY=$WURZEL/.venv/bin/python
[ -x "$PY" ] || PY=python3
fehler=0

echo "=== Syntax ==="
"$PY" "$WURZEL/tools/pruefen.py" || fehler=$((fehler+1))
for t in test_api test_update; do
  echo "=== $t ==="
  "$PY" "$WURZEL/tests/$t.py" 2>&1 | grep -v StarletteDeprecation | grep -v "from starlette.testclient" | tail -40
  [ "${PIPESTATUS[0]}" = 0 ] || fehler=$((fehler+1))
done
if [ "${1:-}" != "--schnell" ]; then
  echo "=== Paket bauen ==="
  "$WURZEL/tools/paket_bauen.sh" || fehler=$((fehler+1))
  echo "=== test_installer ==="
  "$WURZEL/tests/test_installer.sh" | tail -45 || fehler=$((fehler+1))
fi
echo
[ $fehler -eq 0 ] && echo "ALLES GRUEN" || echo "$fehler Testgruppen mit Fehlern"
exit $fehler
