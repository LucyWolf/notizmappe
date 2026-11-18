#!/usr/bin/env python3
"""Die Versionsressource für die Windows-exe schreiben.

    python3 tools/versionsdatei.py [ziel]

Eine .exe ohne Versionsressource hat keinen Firmennamen, keinen
Produktnamen und keine Versionsnummer - in den Eigenschaften steht nichts
außer der Dateigröße. Für den Virenscanner ist das ein Signal: fast jede
Schadsoftware kommt so, und fast jedes ordentliche Programm nicht. Zusammen
mit "frisch gebaut, unsigniert, kaum verbreitet" reicht das der Heuristik
von Defender für einen Fehlalarm.

Das nimmt die Erkennung nicht von selbst weg - dafür muss die Datei bei
Microsoft als Fehlalarm eingereicht werden. Es nimmt aber einen der
Gründe, aus denen sie entsteht, und es kostet nichts.

Die Nummer kommt aus app/VERSION, damit sie nicht an zwei Stellen steht und
auseinanderläuft. Windows will vier Zahlen; 1.2.31 wird zu (1, 2, 31, 0).
"""
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
FIRMA = "LucyWolf"
PRODUKT = "Notizmappe"
ZWECK = "Notizmappe - Notizen in eigenen Dateien"
RECHTE = "Freie Software, Quelltext auf github.com/LucyWolf/notizmappe"


def vierer(fassung: str) -> tuple:
    """1.2.31 -> (1, 2, 31, 0). Windows kennt nur vier Zahlen, nichts dazwischen."""
    teile = []
    for stueck in str(fassung).strip().split("."):
        ziffern = "".join(z for z in stueck if z.isdigit())
        teile.append(int(ziffern) if ziffern else 0)
    teile = (teile + [0, 0, 0, 0])[:4]
    return tuple(teile)


def text(fassung: str) -> str:
    a, b, c, d = vierer(fassung)
    return f"""# Von tools/versionsdatei.py erzeugt - nicht von Hand ändern.
# Die Nummer steht in app/VERSION.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({a}, {b}, {c}, {d}),
    prodvers=({a}, {b}, {c}, {d}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040704b0',
        [StringStruct('CompanyName', '{FIRMA}'),
         StringStruct('FileDescription', '{ZWECK}'),
         StringStruct('FileVersion', '{fassung}'),
         StringStruct('InternalName', '{PRODUKT}'),
         StringStruct('LegalCopyright', '{RECHTE}'),
         StringStruct('OriginalFilename', '{PRODUKT}.exe'),
         StringStruct('ProductName', '{PRODUKT}'),
         StringStruct('ProductVersion', '{fassung}')])
    ]),
    # 1031 = Deutsch, 1200 = Unicode. Ohne diesen Block zeigt Windows die
    # Felder oben gar nicht an - die Tabelle allein genuegt nicht.
    VarFileInfo([VarStruct('Translation', [1031, 1200])])
  ]
)
"""


def main() -> int:
    fassung = (WURZEL / "app/VERSION").read_text(encoding="utf-8").strip()
    ziel = Path(sys.argv[1]) if len(sys.argv) > 1 else WURZEL / "windows/version.txt"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(text(fassung), encoding="utf-8")
    print(f"Versionsressource {fassung} -> {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
