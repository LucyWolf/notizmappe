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

import konfig
import reinigen

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


def ordner_quelle() -> str:
    """Woher der Datenordner kommt: "umgebung" (NOTIZEN_ORDNER, fest), "gewaehlt"
    (in den Einstellungen) oder "standard"."""
    if os.environ.get("NOTIZEN_ORDNER"):
        return "umgebung"
    return "gewaehlt" if konfig.lesen().get("ordner") else "standard"


def wurzel() -> Path:
    # NOTIZEN_ORDNER vor der Einstellung: Tests und Docker muessen sich darauf
    # verlassen koennen, dass nichts anderes angefasst wird.
    roh = os.environ.get("NOTIZEN_ORDNER") or konfig.lesen().get("ordner") or "~/Notizen"
    p = Path(roh).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def inhalt_kopieren(alt: Path, neu: Path) -> int:
    """Notizbuecher in den neuen Ordner kopieren - kopieren, nicht verschieben: geht
    unterwegs etwas schief, ist im alten Ordner noch alles da. Was es im neuen
    Ordner schon gibt, wird nicht ueberschrieben."""
    import shutil
    if neu.resolve().is_relative_to(alt.resolve()):
        raise SpeicherFehler("Der neue Ordner liegt im alten - so lässt sich nichts mitnehmen")
    n = 0
    for quelle in alt.iterdir():
        if quelle.name.startswith(".") and quelle.name != PAPIERKORB:
            continue
        ziel = neu / quelle.name
        if ziel.exists():
            continue
        if quelle.is_dir():
            shutil.copytree(quelle, ziel)
        else:
            shutil.copy2(quelle, ziel)
        n += 1
    return n


def ordner_pruefen(roh: str) -> Path:
    """Taugt der Ordner als Ablage? Legt ihn an, wenn es ihn noch nicht gibt, und
    probiert einmal Schreiben - lieber jetzt scheitern als beim ersten Speichern."""
    roh = (roh or "").strip()
    if not roh:
        raise SpeicherFehler("Kein Ordner angegeben")
    p = Path(roh).expanduser()
    if not p.is_absolute():
        raise SpeicherFehler("Bitte einen vollständigen Pfad angeben, z. B. /home/name/Nextcloud/Notizen")
    if p.exists() and not p.is_dir():
        raise SpeicherFehler("Das ist eine Datei, kein Ordner")
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / f".schreibprobe-{uuid.uuid4().hex[:6]}"
        probe.write_text("ok")
        probe.unlink()
    except OSError as f:
        raise SpeicherFehler(f"In den Ordner lässt sich nicht schreiben: {f.strerror or f}")
    return p.resolve()


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


# --- Anhaenge -----------------------------------------------------------------
#
# Liegen neben der Seite in "<Seitenname>.anhang/". Also im selben Ordner, den der
# Sync-Client ohnehin traegt - kein zweiter Ablageort, der auseinanderlaufen kann,
# und im Dateimanager sieht man sofort, was zu welcher Seite gehoert.

ANHANG = ".anhang"
MAX_ANHANG = 25 * 1024 * 1024       # pro Datei


def anhang_ordner(buch: str, abschnitt: str, name: str) -> Path:
    return pfad_von([buch, abschnitt]) / f"{slug(name)}{ANHANG}"


def anhang_ablegen(buch: str, abschnitt: str, seite: str, dateiname: str, daten: bytes) -> dict:
    if len(daten) > MAX_ANHANG:
        raise SpeicherFehler(f"Datei ist groesser als {MAX_ANHANG // 1024 // 1024} MB")
    ordner = anhang_ordner(buch, abschnitt, seite)
    ordner.mkdir(parents=True, exist_ok=True)
    stamm, punkt, endung = slug(dateiname).rpartition(".")
    if not stamm:
        stamm, endung = slug(dateiname) or "Datei", ""
    endung = ("." + endung[:12]) if endung else ""
    # Namen, die diese Seite schon einmal hatte (jetzt im Papierkorb), nicht neu
    # vergeben: gleicher Name = gleiche Adresse, und die Webansicht zeigt dann
    # das alte Bild aus ihrem Speicher statt des neuen.
    korb = wurzel() / PAPIERKORB
    trenner = f" {seite} - "
    gehabt = ({d.name.split(trenner, 1)[1] for d in korb.iterdir() if trenner in d.name}
              if korb.is_dir() else set())
    stamm = stamm[:60]
    kandidat, n = stamm, 2
    while (ordner / (kandidat + endung)).exists() or (kandidat + endung) in gehabt:
        kandidat = f"{stamm} ({n})"
        n += 1
    name = kandidat + endung
    ziel = ordner / name
    tmp = ziel.with_name(f".{name}.neu")
    tmp.write_bytes(daten)
    os.replace(tmp, ziel)
    return {"datei": name, "groesse": len(daten)}


def anhang_lesen(buch: str, abschnitt: str, seite: str, datei: str) -> Path:
    name = slug(datei)
    if not name or name.startswith("."):
        raise SpeicherFehler("Unerlaubter Dateiname")
    pfad = anhang_ordner(buch, abschnitt, seite) / name
    # Noch einmal nachsehen, dass der Pfad wirklich im Anhangsordner liegt - slug()
    # soll das schon verhindern, aber hier wird eine Datei ausgeliefert.
    if not str(pfad.resolve()).startswith(str(anhang_ordner(buch, abschnitt, seite).resolve())):
        raise SpeicherFehler("Pfad verlaesst den Anhangsordner")
    if not pfad.is_file():
        raise SpeicherFehler("Anhang gibt es nicht")
    return pfad


def anhaenge_aufraeumen(buch: str, abschnitt: str, seite: str, elemente: list) -> int:
    """Dateien wegraeumen, auf die keine Seite mehr zeigt. In den Papierkorb, nicht
    weg - ein Fehler in der Oberflaeche soll keine Bilder vernichten."""
    ordner = anhang_ordner(buch, abschnitt, seite)
    if not ordner.is_dir():
        return 0
    benutzt = {e.get("datei") for e in elemente if isinstance(e, dict)}
    # Bilder, die mitten in einem Text stehen, zaehlen genauso als benutzt.
    for e in elemente:
        if isinstance(e, dict) and e.get("typ") == "text":
            benutzt |= reinigen.bilder_im_text(e.get("html") or "")
    korb = wurzel() / PAPIERKORB
    weg = 0
    for datei in ordner.iterdir():
        if not datei.is_file() or datei.name.startswith(".") or datei.name in benutzt:
            continue
        korb.mkdir(exist_ok=True)
        marke = time.strftime("%Y%m%d-%H%M%S")
        os.replace(datei, korb / frei(korb, f"{marke} {seite} - {datei.name}"))
        weg += 1
    try:
        ordner.rmdir()              # nur wenn leer
    except OSError:
        pass
    return weg


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
        # Die Anhaenge heissen nach der Seite - sonst findet sie danach niemand mehr.
        alt_ordner = datei.parent / f"{datei.stem}{ANHANG}"
        if alt_ordner.is_dir():
            os.replace(alt_ordner, datei.parent / f"{neuer}{ANHANG}")
        return neuer
    _schreiben(datei, daten)
    return datei.stem


def in_papierkorb(teile: list[str]) -> None:
    """Seiten bringen ihren Anhangsordner mit in den Papierkorb."""
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
    if quelle.suffix == ".json":
        mit = quelle.with_name(f"{quelle.stem}{ANHANG}")
        if mit.is_dir():
            os.replace(mit, korb / frei(korb, f"{marke} {quelle.stem}{ANHANG}"))


def stand(buch: str, abschnitt: str, name: str) -> dict:
    """Billiger Blick fuer den Browser: hat jemand von aussen reingeschrieben?"""
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    if not datei.is_file():
        return {"da": False}
    daten = seite_lesen(buch, abschnitt, name)
    return {"da": True, "rev": daten["rev"], "mtime": daten["mtime"], "geraet": daten.get("geraet", "")}
