"""Ablage auf der Platte: Notizbuch = Ordner, Abschnitt = Unterordner, Seite = JSON.

Absichtlich keine Datenbank. Der Datenordner liegt im Nextcloud-/NAS-Sync-Ordner,
und SQLite-Dateien ueberleben einen Dateisync nicht zuverlaessig. Alles, was schnell
sein muss (Suche), kommt spaeter in einen Index ausserhalb des Sync-Ordners.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

FORMAT = 1
PAPIERKORB = ".papierkorb"
# Namen, die Nextcloud/Dropbox/Synology an Konfliktkopien haengen.
KONFLIKT_MUSTER = re.compile(r"\(Konflikt-?[Kk]opie|conflicted copy|\(Konflikt\)|_conflict-", re.I)


class SpeicherFehler(Exception):
    """Falscher Pfad, Name schon vergeben, Seite nicht da."""


class KonfliktFehler(Exception):
    """Die Datei auf der Platte ist neuer als die Fassung, die der Browser kennt."""

    def __init__(self, seite: dict):
        super().__init__("Seite wurde zwischenzeitlich geaendert")
        self.seite = seite


def wurzel() -> Path:
    p = Path(os.environ.get("NOTIZEN_ORDNER", "~/Notizen")).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


# --- Namen und Pfade ----------------------------------------------------------

def slug(name: str) -> str:
    """Dateiname aus einem Titel. Der echte Titel steht im JSON, das hier ist nur
    der Dateiname - er darf haesslich sein, aber nicht gefaehrlich."""
    name = unicodedata.normalize("NFC", name).strip()
    name = name.replace("/", "-").replace("\\", "-")
    name = re.sub(r"[\x00-\x1f<>:\"|?*]", "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if name.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}:
        name = "_" + name
    return name[:80] or "Ohne Namen"


def frei(ordner: Path, name: str, endung: str = "") -> str:
    """Haengt (2), (3), ... an, bis der Name im Ordner frei ist."""
    kandidat = name
    n = 2
    while (ordner / (kandidat + endung)).exists():
        kandidat = f"{name} ({n})"
        n += 1
    return kandidat


def _pruefen(teile: list[str]) -> list[str]:
    for t in teile:
        if not t or t in {".", ".."} or "/" in t or "\\" in t or t.startswith("."):
            raise SpeicherFehler(f"Unerlaubter Name: {t!r}")
    return teile


def pfad_von(teile: list[str]) -> Path:
    """Baut einen Pfad unter der Wurzel und prueft, dass er auch dort bleibt."""
    ziel = wurzel().joinpath(*_pruefen(teile))
    w = wurzel().resolve()
    # resolve() auch fuer noch nicht existierende Pfade (strict=False ist Standard)
    if not str(ziel.resolve()).startswith(str(w)):
        raise SpeicherFehler("Pfad verlaesst den Datenordner")
    return ziel


# --- Baum ---------------------------------------------------------------------

@dataclass
class Eintrag:
    name: str
    titel: str
    konflikt: bool = False


def _titel_aus(datei: Path) -> str:
    try:
        with datei.open(encoding="utf-8") as f:
            return json.load(f).get("titel") or datei.stem
    except (OSError, ValueError):
        return datei.stem


def baum() -> list[dict]:
    """Notizbuecher -> Abschnitte -> Seiten. Flach genug, um sie in einem Rutsch
    an den Browser zu geben; bei tausend Seiten wird daraus ein Lazy-Load."""
    aus = []
    for buch in sorted(p for p in wurzel().iterdir() if p.is_dir() and not p.name.startswith(".")):
        abschnitte = []
        for abs_ in sorted(p for p in buch.iterdir() if p.is_dir() and not p.name.startswith(".")):
            seiten = []
            for datei in sorted(abs_.glob("*.json")):
                seiten.append({
                    "name": datei.stem,
                    "titel": _titel_aus(datei),
                    "konflikt": bool(KONFLIKT_MUSTER.search(datei.name)),
                    "geaendert": int(datei.stat().st_mtime),
                })
            abschnitte.append({"name": abs_.name, "seiten": seiten})
        aus.append({"name": buch.name, "abschnitte": abschnitte})
    return aus


def notizbuch_anlegen(name: str) -> str:
    name = frei(wurzel(), slug(name))
    pfad_von([name]).mkdir()
    return name


def abschnitt_anlegen(buch: str, name: str) -> str:
    ordner = pfad_von([buch])
    if not ordner.is_dir():
        raise SpeicherFehler("Notizbuch gibt es nicht")
    name = frei(ordner, slug(name))
    pfad_von([buch, name]).mkdir()
    return name


# --- Seiten -------------------------------------------------------------------

def leere_seite(titel: str) -> dict:
    return {
        "format": FORMAT,
        "id": uuid.uuid4().hex,
        "titel": titel,
        "rev": 1,
        "geraet": "",
        "geaendert": time.time(),
        "elemente": [],
    }


def seite_anlegen(buch: str, abschnitt: str, titel: str) -> str:
    ordner = pfad_von([buch, abschnitt])
    if not ordner.is_dir():
        raise SpeicherFehler("Abschnitt gibt es nicht")
    name = frei(ordner, slug(titel), ".json")
    _schreiben(ordner / f"{name}.json", leere_seite(titel))
    return name


def seite_lesen(buch: str, abschnitt: str, name: str) -> dict:
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    if not datei.is_file():
        raise SpeicherFehler("Seite gibt es nicht")
    with datei.open(encoding="utf-8") as f:
        daten = json.load(f)
    daten.setdefault("elemente", [])
    daten.setdefault("rev", 1)
    daten["name"] = datei.stem
    daten["mtime"] = datei.stat().st_mtime
    return daten


def _schreiben(datei: Path, daten: dict) -> None:
    """Erst daneben schreiben, dann umbenennen. Sonst steht bei einem Absturz
    mitten im Schreiben eine halbe Seite auf der Platte - und der Sync-Client
    traegt sie auch noch weiter."""
    tmp = datei.with_name(f".{datei.name}.neu")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, datei)


def seite_speichern(buch: str, abschnitt: str, name: str, rev: int,
                    titel: str, elemente: list, geraet: str = "") -> dict:
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    if not datei.is_file():
        raise SpeicherFehler("Seite gibt es nicht")
    alt = seite_lesen(buch, abschnitt, name)
    if int(alt.get("rev", 1)) != int(rev):
        # Jemand anders (oder der Sync) war schneller. Nichts ueberschreiben.
        raise KonfliktFehler(alt)
    neu = dict(alt)
    neu.pop("name", None)
    neu.pop("mtime", None)
    neu.update({
        "titel": titel or alt.get("titel") or datei.stem,
        "elemente": elemente,
        "rev": int(rev) + 1,
        "geraet": geraet[:40],
        "geaendert": time.time(),
    })
    _schreiben(datei, neu)
    return {"rev": neu["rev"], "mtime": datei.stat().st_mtime}


def seite_umbenennen(buch: str, abschnitt: str, name: str, titel: str) -> str:
    """Titel aendern - und die Datei mitziehen, damit der Ordner im Dateimanager
    noch lesbar bleibt."""
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    if not datei.is_file():
        raise SpeicherFehler("Seite gibt es nicht")
    with datei.open(encoding="utf-8") as f:
        daten = json.load(f)
    daten["titel"] = titel
    daten["rev"] = int(daten.get("rev", 1)) + 1
    neuer = slug(titel)
    if neuer != datei.stem:
        neuer = frei(datei.parent, neuer, ".json")
        _schreiben(datei.parent / f"{neuer}.json", daten)
        datei.unlink()
        return neuer
    _schreiben(datei, daten)
    return datei.stem


def in_papierkorb(teile: list[str]) -> None:
    """Loeschen heisst verschieben. Der Papierkorb liegt im Datenordner, damit der
    Sync ihn mitnimmt und nichts auf einem einzelnen Geraet haengen bleibt."""
    quelle = pfad_von(teile)
    if not quelle.exists():
        raise SpeicherFehler("Gibt es nicht")
    korb = wurzel() / PAPIERKORB
    korb.mkdir(exist_ok=True)
    marke = time.strftime("%Y%m%d-%H%M%S")
    ziel = korb / frei(korb, f"{marke} {' - '.join(teile)}".replace("/", "-"))
    os.replace(quelle, ziel)


def stand(buch: str, abschnitt: str, name: str) -> dict:
    """Billiger Blick fuer den Browser: hat jemand von aussen reingeschrieben?"""
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    if not datei.is_file():
        return {"da": False}
    daten = seite_lesen(buch, abschnitt, name)
    return {"da": True, "rev": daten["rev"], "mtime": daten["mtime"], "geraet": daten.get("geraet", "")}
