#!/usr/bin/env python3
"""Nachsehen, was aus einer OneNote-Datei würde - ohne etwas anzulegen.

    .venv/bin/python tools/one_lesen.py <datei.one|datei.onepkg>

Gelesen wird mit **demselben** Code, der auch beim Übernehmen läuft
(`app/einfuhr.py`). Das ist der Sinn der Probe: was hier steht, kommt beim
Einlesen auch heraus. Vorher hatte dieses Werkzeug eine eigene Kopie der
Leselogik - dann zeigt es irgendwann etwas, das mit der Wirklichkeit nichts
mehr zu tun hat.

Angelegt wird nichts, die Datei wird nur gelesen.
"""
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "app"))

import einfuhr                                                      # noqa: E402


def zeigen(abschnitt: dict) -> None:
    print(f"\n=== Abschnitt: {abschnitt['name']}")
    if abschnitt.get("fehler"):
        print(f"  ging nicht: {abschnitt['fehler']}")
        return
    seiten = abschnitt.get("seiten") or []
    print(f"  Seiten: {len(seiten)}")
    for nr, seite in enumerate(seiten[:15], 1):
        titel = einfuhr.seitentitel(seite, nr)
        texte = seite.get("texte") or []
        zeichen = sum(len(t) for t in texte)
        print(f"    {nr:3}. {titel[:60]:62} {len(texte)} Textstücke, {zeichen} Zeichen")
        for t in texte[:2]:
            erste = t.strip().splitlines()[0] if t.strip() else ""
            if erste:
                print(f"         | {erste[:90]}")
    if len(seiten) > 15:
        print(f"    … und {len(seiten) - 15} weitere Seiten")
    anhaenge = abschnitt.get("anhaenge") or []
    print(f"  Dateien: {len(anhaenge)}")
    for a in anhaenge[:10]:
        print(f"    - {a['name']}  ({len(a['inhalt']) // 1024} KB)")
    if not seiten:
        print("  --> Kein Text gefunden. Entweder steckt er an einer Stelle des")
        print("      Formats, die der Leser nicht kennt, oder der Abschnitt ist")
        print("      mit einem Passwort geschützt.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    quelle = Path(sys.argv[1]).expanduser()
    if not quelle.is_file():
        sys.exit(f"Gibt es nicht: {quelle}")
    try:
        abschnitte = einfuhr.lesen(quelle)
    except einfuhr.EinfuhrFehler as f:
        sys.exit(f"{quelle.name}: {f}")

    print(f"{quelle.name}: {len(abschnitte)} Abschnitt(e), "
          f"{quelle.stat().st_size // 1024} KB")
    for abschnitt in abschnitte:
        zeigen(abschnitt)

    gesamt = sum(len(a.get("seiten") or []) for a in abschnitte)
    dateien = sum(len(a.get("anhaenge") or []) for a in abschnitte)
    print(f"\nZusammen: {gesamt} Seiten, {dateien} Dateien.")
    print("Beim Übernehmen entstünde daraus ein neues Notizbuch mit diesen")
    print("Abschnitten; die Dateien kämen gesammelt auf eine eigene Seite.")
