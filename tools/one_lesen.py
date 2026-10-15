#!/usr/bin/env python3
"""Nachsehen, was in einer OneNote-Datei drinsteht - ohne etwas zu verändern.

    .venv/bin/python tools/one_lesen.py <datei.one|datei.onepkg>

Das ist **keine** Einfuhr, sondern die Vorprobe dazu: es liest die Datei und
zeigt, was sich daraus holen lässt - Seiten, Text, eingebettete Dateien. Erst
wenn das brauchbar aussieht, lohnt sich ein Knopf in der Oberfläche.

Warum zuerst so: das Dateiformat von OneNote ist verwickelt, und der Leser,
den es dafür frei gibt, ist eigentlich für Virenanalysten gebaut. Ob der Text
sauber herauskommt, weiß man erst an einer echten Datei - und hier liegt keine.

Gelesen wird nur. Die Datei wird nicht angefasst.
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
from pathlib import Path

# Lesbarer Text steht in OneNote in Eigenschaften mit diesen Namen.
TEXTFELDER = ("RichEditTextUnicode", "TextRunData", "RichEditTextLangID")
TITELFELDER = ("CachedTitleString", "TitleText", "PageTitleText")


def lesbar(roh: str) -> str:
    """Steuerzeichen raus, Leerraum zusammenziehen."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", roh)
    return re.sub(r"[ \t]+", " ", text).strip()


# Am Dateianfang steht, um was fuer eine Datei es sich handelt. Das zu pruefen
# kostet nichts und erspart eine unverstaendliche Meldung aus dem Leser.
KENNUNG = {
    bytes.fromhex("e4525c7b8cd8a74daeb15378d0299 6d3".replace(" ", "")): "Abschnitt (.one)",
    bytes.fromhex("a12fff43d9ef764c9ee210ea5722765f"): "Inhaltsverzeichnis (.onetoc2)",
}


def art_von(pfad: Path) -> str | None:
    with pfad.open("rb") as f:
        return KENNUNG.get(f.read(16))


def eine_datei(pfad: Path) -> dict:
    try:
        # Ja, ohne "u": die Klasse heisst in der Bibliothek wirklich so.
        from pyOneNote.OneDocument import OneDocment
    except ImportError:
        sys.exit("pyOneNote fehlt:  .venv/bin/pip install pyOneNote")

    art = art_von(pfad)
    if art is None:
        raise ValueError("Das ist keine OneNote-Datei (die Kennung am Anfang fehlt)")
    if "onetoc2" in art:
        raise ValueError("Das ist nur das Inhaltsverzeichnis eines Notizbuchs, "
                         "die Seiten stehen in den .one-Dateien daneben")

    with pfad.open("rb") as f:
        try:
            dok = OneDocment(f)
        except Exception as f_:                     # noqa: BLE001
            raise ValueError(f"Der Leser kommt damit nicht zurecht: "
                             f"{type(f_).__name__}: {f_}") from f_

    roh = {}
    for holen in ("get_json", "get_properties"):
        if hasattr(dok, holen):
            try:
                wert = getattr(dok, holen)()
                roh[holen] = json.loads(wert) if isinstance(wert, str) else wert
            except Exception as f_:                     # noqa: BLE001
                roh[holen] = {"fehler": f"{type(f_).__name__}: {f_}"}

    dateien = {}
    if hasattr(dok, "get_files"):
        try:
            dateien = dok.get_files() or {}
        except Exception as f_:                         # noqa: BLE001
            dateien = {"fehler": str(f_)}

    # Text einsammeln: durch alles laufen und die Textfelder herausfischen.
    texte: list[str] = []
    def durch(wert, schluessel=""):
        if isinstance(wert, dict):
            for k, v in wert.items():
                durch(v, k)
        elif isinstance(wert, list):
            for v in wert:
                durch(v, schluessel)
        elif isinstance(wert, str) and any(f in schluessel for f in TEXTFELDER):
            t = lesbar(wert)
            if t:
                texte.append(t)
    durch(roh)

    return {"datei": pfad.name, "groesse": pfad.stat().st_size,
            "texte": texte, "dateien": dateien, "roh": roh}


def paket(pfad: Path) -> list[Path]:
    """.onepkg ist ein CAB-Archiv mit den einzelnen Abschnitten darin."""
    try:
        import cabarchive
    except ImportError:
        sys.exit("cabarchive fehlt:  .venv/bin/pip install cabarchive")
    ziel = Path(tempfile.mkdtemp(prefix="onepkg-"))
    archiv = cabarchive.CabArchive(pfad.read_bytes())
    aus = []
    for name, eintrag in archiv.items():
        wohin = ziel / Path(name).name
        wohin.write_bytes(eintrag.buf)
        aus.append(wohin)
    return aus


def zeigen(ergebnis: dict) -> None:
    print(f"\n=== {ergebnis['datei']}  ({ergebnis['groesse'] // 1024} KB)")
    texte = ergebnis["texte"]
    print(f"  Textstücke gefunden: {len(texte)}")
    for t in texte[:25]:
        print(f"    | {t[:100]}")
    if len(texte) > 25:
        print(f"    … und {len(texte) - 25} weitere")
    d = ergebnis["dateien"]
    if isinstance(d, dict) and d and "fehler" not in d:
        print(f"  Eingebettete Dateien: {len(d)}")
        for name in list(d)[:10]:
            print(f"    - {name}")
    elif isinstance(d, dict) and "fehler" in d:
        print(f"  Eingebettete Dateien: ging nicht ({d['fehler']})")
    else:
        print("  Eingebettete Dateien: keine")
    if not texte:
        print("  --> Kein Text gefunden. Entweder steckt er woanders im Format,")
        print("      oder der Abschnitt ist passwortgeschützt.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    quelle = Path(sys.argv[1]).expanduser()
    if not quelle.is_file():
        sys.exit(f"Gibt es nicht: {quelle}")
    if quelle.suffix.lower() == ".onepkg":
        teile = paket(quelle)
        print(f"{quelle.name}: {len(teile)} Abschnitte im Paket")
        for t in teile:
            if t.suffix.lower() == ".one":
                try:
                    zeigen(eine_datei(t))
                except Exception as f:                  # noqa: BLE001
                    print(f"\n=== {t.name}: ging nicht - {type(f).__name__}: {f}")
    else:
        try:
            zeigen(eine_datei(quelle))
        except ValueError as f:
            sys.exit(f"{quelle.name}: {f}")
