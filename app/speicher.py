"""Ablage auf der Platte: Notizbuch = Ordner, Abschnitt = Unterordner, Seite = JSON.

Absichtlich keine Datenbank. Der Datenordner liegt im Nextcloud-/NAS-Sync-Ordner,
und SQLite-Dateien ueberleben einen Dateisync nicht zuverlaessig. Alles, was schnell
sein muss (Suche), kommt spaeter in einen Index ausserhalb des Sync-Ordners.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

import konfig
import reinigen
import tresor

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


def dokumentenordner() -> Path:
    """Der Dokumentenordner des Benutzers - dort gehoeren Dateien eines normalen
    Programms hin, nicht in ein eigenes Verzeichnis neben dem Heimatordner.

    Windows nennt ihn je nach Sprache "Documents" oder "Dokumente"; unter Linux
    steht er in ~/.config/user-dirs.dirs, wenn die Arbeitsumgebung ihn gesetzt hat.
    """
    heim = Path.home()
    if sys.platform == "win32":
        # Windows fuehrt den Dokumentenordner in der Registry. Wer OneDrive
        # benutzt, hat ihn dort liegen und nicht unter %USERPROFILE%\Documents -
        # dann entstuende daneben ein zweiter, leerer Ordner.
        try:
            import winreg
            pfad = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, pfad) as k:
                roh = winreg.QueryValueEx(k, "Personal")[0]
            weg = Path(os.path.expandvars(roh))
            if weg.is_dir():
                return weg
        except Exception:
            pass
        for name in ("Documents", "Dokumente", "OneDrive/Dokumente", "OneDrive/Documents"):
            if (heim / name).is_dir():
                return heim / name
        return heim / "Documents"

    datei = Path(os.environ.get("XDG_CONFIG_HOME", heim / ".config")) / "user-dirs.dirs"
    try:
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            if zeile.startswith("XDG_DOCUMENTS_DIR"):
                roh = zeile.split("=", 1)[1].strip().strip('"')
                weg = Path(roh.replace("$HOME", str(heim))).expanduser()
                if weg.is_dir():
                    return weg
    except OSError:
        pass
    for name in ("Dokumente", "Documents"):
        if (heim / name).is_dir():
            return heim / name
    return heim / "Dokumente"


def standard_ordner() -> Path:
    """Wo die Notizen liegen, solange nichts anderes gewaehlt ist.

    Frueher war das ~/Notizen. Wer schon damit arbeitet, behaelt es: ein
    Programm, das nach einem Update woanders hinschreibt, sieht aus, als haette
    es alles verloren.
    """
    alt = Path.home() / "Notizen"
    if alt.is_dir() and any(alt.iterdir()):
        return alt
    return dokumentenordner() / "Notizmappe"


def sieht_nach_notizen_aus(p: Path) -> bool:
    """Liegt dort eine Notizmappe-Ablage? Also ein Ordner mit mindestens einer
    Seite darin (Notizbuch/Abschnitt/Seite.json)."""
    try:
        if not p.is_dir():
            return False
        for buch in p.iterdir():
            if not buch.is_dir() or buch.name.startswith("."):
                continue
            for abschnitt in buch.iterdir():
                if abschnitt.is_dir() and any(abschnitt.glob("*.json")):
                    return True
    except OSError:
        pass
    return False


def andere_orte(ausser: Path | None = None) -> list[str]:
    """Wo sonst noch Notizen liegen koennten.

    Wenn das Programm in einen leeren Ordner schaut, ist die haeufigste Erklaerung
    nicht, dass alles weg ist, sondern dass es woanders hinschaut - nach einem
    Update, einem Umzug nach OneDrive oder einem Wechsel des Standards.
    """
    heim = Path.home()
    kandidaten = [
        heim / "Notizen",
        dokumentenordner() / "Notizmappe",
        heim / "Documents" / "Notizmappe",
        heim / "Dokumente" / "Notizmappe",
        heim / "OneDrive" / "Dokumente" / "Notizmappe",
        heim / "OneDrive" / "Documents" / "Notizmappe",
        heim / "Nextcloud" / "Notizen",
    ]
    gefunden = []
    for k in kandidaten:
        if ausser and k.resolve() == ausser.resolve():
            continue
        if sieht_nach_notizen_aus(k) and str(k) not in gefunden:
            gefunden.append(str(k))
    return gefunden


def ordner_quelle() -> str:
    """Woher der Datenordner kommt: "umgebung" (NOTIZEN_ORDNER, fest), "gewaehlt"
    (in den Einstellungen) oder "standard"."""
    if os.environ.get("NOTIZEN_ORDNER"):
        return "umgebung"
    return "gewaehlt" if konfig.lesen().get("ordner") else "standard"


def wurzel() -> Path:
    # NOTIZEN_ORDNER vor der Einstellung: die Tests muessen sich darauf
    # verlassen koennen, dass nichts anderes angefasst wird.
    if not os.environ.get("NOTIZEN_ORDNER"):
        gewaehlt = konfig.lesen().get("ordner")
        if gewaehlt:
            p = Path(gewaehlt).expanduser()
            # Nicht anlegen: liegt der Ordner auf einem NAS oder USB-Laufwerk, das
            # gerade nicht eingehaengt ist, entstuende sonst still ein leerer Ordner
            # auf der lokalen Platte - und die Notizen landeten dort statt dort.
            if not p.is_dir():
                raise SpeicherFehler(
                    f"Der gewählte Datenordner {p} ist nicht da - ist das Laufwerk eingehängt? "
                    "Unter Einstellungen → Daten lässt er sich umstellen.")
            return p
    p = Path(os.environ["NOTIZEN_ORDNER"]).expanduser() if os.environ.get("NOTIZEN_ORDNER") \
        else standard_ordner()
    p.mkdir(parents=True, exist_ok=True)
    return p


def gewaehlter_ordner() -> str:
    """Der eingestellte Ordner als Text, auch wenn er gerade nicht da ist."""
    return os.environ.get("NOTIZEN_ORDNER") or konfig.lesen().get("ordner") or str(standard_ordner())


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
    wach()
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


def verschluesselt() -> bool:
    """Ist fuer diesen Datenordner eine Sperre eingerichtet?"""
    try:
        return tresor.eingerichtet(wurzel())
    except Exception:                       # noqa: BLE001 - Ordner weg o.ae.
        return False


def wach() -> None:
    """Steht die Sperre, kommt hier niemand vorbei. Das sitzt bewusst in der
    Ablage und nicht in der Oberflaeche: eine Pruefung, die man nur im Fenster
    macht, ist keine."""
    if verschluesselt() and not tresor.offen():
        raise tresor.TresorFehler("Zugesperrt")


def _roh_lesen(datei: Path) -> bytes:
    """Dateiinhalt im Klartext. Nicht verschluesselte Dateien kommen unveraendert
    zurueck - waehrend des Umstellens liegen beide Arten nebeneinander."""
    return tresor.entschluesseln(datei.read_bytes())


def _roh_schreiben(datei: Path, roh: bytes, chiffrieren: bool | None = None) -> None:
    """Erst daneben schreiben, dann umbenennen. Sonst steht bei einem Absturz
    mitten im Schreiben eine halbe Seite auf der Platte - und der Sync-Client
    traegt sie auch noch weiter."""
    if chiffrieren is None:
        chiffrieren = verschluesselt()
    if chiffrieren:
        roh = tresor.verschluesseln(roh)
    tmp = datei.with_name(f".{datei.name}.neu")
    with tmp.open("wb") as f:
        f.write(roh)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, datei)


def _json_lesen(datei: Path) -> dict:
    return json.loads(_roh_lesen(datei).decode("utf-8"))


def _titel_aus(datei: Path) -> str:
    try:
        return _json_lesen(datei).get("titel") or datei.stem
    except (OSError, ValueError, tresor.TresorFehler):
        return datei.stem


def baum() -> list[dict]:
    """Notizbuecher -> Abschnitte -> Seiten. Flach genug, um sie in einem Rutsch
    an den Browser zu geben; bei tausend Seiten wird daraus ein Lazy-Load."""
    wach()
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
    wach()
    name = frei(wurzel(), slug(name))
    pfad_von([name]).mkdir()
    return name


def abschnitt_anlegen(buch: str, name: str) -> str:
    wach()
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
    _roh_schreiben(ziel, daten)
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


SCHONFRIST = 600   # Sekunden: so jung wird ein Anhang nicht weggeraeumt


def anhang_inhalt(buch: str, abschnitt: str, seite: str, datei: str) -> bytes:
    """Der Anhang im Klartext. Alles, was den Inhalt braucht, geht hier durch -
    bei eingeschalteter Sperre liegt auf der Platte nur Kauderwelsch."""
    return _roh_lesen(anhang_lesen(buch, abschnitt, seite, datei))


def anhaenge_aufraeumen(buch: str, abschnitt: str, seite: str, elemente: list) -> int:
    """Dateien wegraeumen, auf die keine Seite mehr zeigt. In den Papierkorb, nicht
    weg - ein Fehler in der Oberflaeche soll keine Bilder vernichten.

    Frische Dateien bleiben liegen: waehrend ein Bild hochlaedt, kann schon ein
    Speichern mit dem Stand davor unterwegs sein - das kennt die Datei noch nicht
    und haette sie sonst sofort in den Papierkorb geschoben."""
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
        if time.time() - datei.stat().st_mtime < SCHONFRIST:
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


# --- Verlauf: frühere Fassungen einer Seite ----------------------------------
#
# Eine Datei je Fassung, in einem Ordner neben der Seite. Keine Datenbank: der
# Datenordner liegt im Sync, und die Fassungen sollen dort genauso ankommen wie
# die Seiten selbst.
VERLAUF = ".verlauf"
VERLAUF_ABSTAND = 10 * 60           # höchstens alle 10 Minuten eine Fassung
VERLAUF_TAGE = 90
VERLAUF_ANZAHL = 50                 # je Seite


def verlauf_ordner(datei: Path) -> Path:
    return datei.parent / VERLAUF / datei.stem


def verlauf_liste(buch: str, abschnitt: str, name: str) -> list[dict]:
    """Die Fassungen einer Seite, neueste zuerst."""
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    ordner = verlauf_ordner(datei)
    if not ordner.is_dir():
        return []
    aus = []
    for p in sorted(ordner.glob("*.json"), reverse=True):
        try:
            aus.append({"marke": p.stem, "zeit": p.stat().st_mtime, "groesse": p.stat().st_size})
        except OSError:
            continue
    return aus


def _ausduennen(ordner: Path) -> int:
    """Alte Fassungen wegräumen: erst alle, dann eine je Tag, dann eine je Woche.

    Nicht einfach "die ältesten weg": sonst bleiben nach einem langen Arbeitstag
    nur die letzten zwei Stunden übrig und der Stand von vorletzter Woche ist
    fort - und genau den sucht man.
    """
    fassungen = sorted(ordner.glob("*.json"), reverse=True)
    if not fassungen:
        return 0
    jetzt = time.time()
    behalten, gesehen_tag, gesehen_woche = [], set(), set()
    weg = []
    for p in fassungen:
        try:
            alter = jetzt - p.stat().st_mtime
        except OSError:
            continue
        if alter > VERLAUF_TAGE * 86400:
            weg.append(p)
            continue
        if alter < 86400:                       # letzter Tag: alles behalten
            behalten.append(p)
            continue
        tag = time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime))
        woche = time.strftime("%Y-%W", time.localtime(p.stat().st_mtime))
        if alter < 30 * 86400:
            if tag in gesehen_tag:
                weg.append(p)
                continue
            gesehen_tag.add(tag)
        else:
            if woche in gesehen_woche:
                weg.append(p)
                continue
            gesehen_woche.add(woche)
        behalten.append(p)

    # Immer noch zu viele? Dann von hinten, also von den ältesten.
    while len(behalten) > VERLAUF_ANZAHL:
        weg.append(behalten.pop())

    for p in weg:
        try:
            p.unlink()
        except OSError:
            pass
    return len(weg)


def verlauf_merken(datei: Path, erzwingen: bool = False) -> bool:
    """Den aktuellen Stand einer Seite als Fassung beiseitelegen.

    Gespeichert wird automatisch alle paar Sekunden - eine Fassung je Speichern
    wären hunderte am Tag. Deshalb höchstens alle zehn Minuten eine; so
    entspricht eine Fassung ungefähr einem Arbeitsabschnitt. Vor einem
    Konflikt wird immer eine abgelegt, egal wie kurz das her ist.
    """
    if not datei.is_file():
        return False
    ordner = verlauf_ordner(datei)
    try:
        ordner.mkdir(parents=True, exist_ok=True)
        neueste = max((p.stat().st_mtime for p in ordner.glob("*.json")), default=0)
        if not erzwingen and time.time() - neueste < VERLAUF_ABSTAND:
            return False
        marke = time.strftime("%Y%m%d-%H%M%S")
        ziel = ordner / f"{marke}.json"
        if ziel.exists():
            return False
        # Roh kopieren, nicht neu schreiben: so bleibt die Fassung genau das,
        # was auf der Platte stand - verschlüsselt, wenn die Sperre an ist.
        ziel.write_bytes(datei.read_bytes())
        _ausduennen(ordner)
        return True
    except OSError:
        return False                            # Verlauf ist nett, nicht wichtig


def verlauf_lesen(buch: str, abschnitt: str, name: str, marke: str) -> dict:
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    sicher = slug(marke)
    if not sicher or sicher != marke:
        raise SpeicherFehler("Unerlaubte Fassung")
    quelle = verlauf_ordner(datei) / f"{sicher}.json"
    if not quelle.is_file():
        raise SpeicherFehler("Die Fassung gibt es nicht mehr")
    daten = _json_lesen(quelle)
    daten.setdefault("elemente", [])
    daten["marke"] = sicher
    daten["zeit"] = quelle.stat().st_mtime
    return daten


def verlauf_zurueck(buch: str, abschnitt: str, name: str, marke: str) -> dict:
    """Eine alte Fassung wieder zur aktuellen machen.

    Der jetzige Stand wird vorher als Fassung abgelegt - Zurückholen darf nie
    etwas kosten, sonst traut sich niemand, es auszuprobieren.
    """
    alt = verlauf_lesen(buch, abschnitt, name, marke)
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    verlauf_merken(datei, erzwingen=True)
    jetzt = seite_lesen(buch, abschnitt, name)
    neu = dict(alt)
    for raus in ("marke", "zeit", "name", "mtime"):
        neu.pop(raus, None)
    neu["rev"] = int(jetzt.get("rev", 1)) + 1
    neu["geaendert"] = time.time()
    _schreiben(datei, neu)
    return {"rev": neu["rev"], "titel": neu.get("titel", ""), "marke": marke}


def seite_lesen(buch: str, abschnitt: str, name: str) -> dict:
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    if not datei.is_file():
        raise SpeicherFehler("Seite gibt es nicht")
    daten = _json_lesen(datei)
    daten.setdefault("elemente", [])
    daten.setdefault("rev", 1)
    daten["name"] = datei.stem
    daten["mtime"] = datei.stat().st_mtime
    return daten


def _schreiben(datei: Path, daten: dict) -> None:
    _roh_schreiben(datei, json.dumps(daten, ensure_ascii=False, indent=1).encode("utf-8"))


def seite_speichern(buch: str, abschnitt: str, name: str, rev: int,
                    titel: str, elemente: list, geraet: str = "") -> dict:
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    if not datei.is_file():
        raise SpeicherFehler("Seite gibt es nicht")
    alt = seite_lesen(buch, abschnitt, name)
    if int(alt.get("rev", 1)) != int(rev):
        # Jemand anders (oder der Sync) war schneller. Nichts ueberschreiben.
        raise KonfliktFehler(alt)
    verlauf_merken(datei)
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
    daten = _json_lesen(datei)
    daten["titel"] = titel
    daten["rev"] = int(daten.get("rev", 1)) + 1
    neuer = slug(titel)
    if neuer != datei.stem:
        # Frei heisst: weder die Seite noch ihr Anhangsordner gibt es schon. Lag
        # ein verwaister "Neu.anhang" im Weg, scheiterte das Verschieben der
        # Anhaenge, nachdem die Seite schon umbenannt war - Bilder weg, Fehler 500.
        stamm, n = neuer, 2
        while (datei.parent / f"{neuer}.json").exists() or (datei.parent / f"{neuer}{ANHANG}").exists():
            neuer = f"{stamm} ({n})"
            n += 1
        _schreiben(datei.parent / f"{neuer}.json", daten)
        datei.unlink()
        # Die Anhaenge heissen nach der Seite - sonst findet sie danach niemand mehr.
        alt_ordner = datei.parent / f"{datei.stem}{ANHANG}"
        if alt_ordner.is_dir():
            os.replace(alt_ordner, datei.parent / f"{neuer}{ANHANG}")
        # Der Verlauf heisst auch nach der Seite. Bleibt er unter dem alten
        # Namen liegen, sind alle frueheren Fassungen unerreichbar - und die
        # Seite sieht aus, als haette sie nie eine gehabt.
        alt_verlauf = verlauf_ordner(datei)
        if alt_verlauf.is_dir():
            ziel_verlauf = datei.parent / VERLAUF / neuer
            ziel_verlauf.parent.mkdir(parents=True, exist_ok=True)
            if not ziel_verlauf.exists():
                os.replace(alt_verlauf, ziel_verlauf)
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
    # Woher es kam, ausdruecklich festhalten. Aus dem Namen laesst sich das zwar
    # meist ablesen, aber nicht, wenn ein Notizbuch selbst " - " im Namen hat -
    # und beim Zurueckholen darf nicht geraten werden.
    try:
        (korb / f".{ziel.name}.herkunft").write_text(
            json.dumps({"teile": teile, "zeit": time.time()}, ensure_ascii=False),
            encoding="utf-8")
    except OSError:
        pass
    if quelle.suffix == ".json":
        # Anhaenge und frueheren Fassungen gehen mit - wer eine Seite
        # zurueckholt, will beides nicht verloren haben. Auch sie bekommen
        # ihren Herkunftsvermerk, sonst waeren sie nachher nicht zuzuordnen.
        for ordner_, endung in ((quelle.with_name(f"{quelle.stem}{ANHANG}"), ANHANG),
                                (verlauf_ordner(quelle), VERLAUF)):
            if not ordner_.is_dir():
                continue
            mitziel = korb / frei(korb, f"{marke} {quelle.stem}{endung}")
            os.replace(ordner_, mitziel)
            try:
                (korb / f".{mitziel.name}.herkunft").write_text(
                    json.dumps({"teile": teile[:-1] + [f"{quelle.stem}{endung}"],
                                "zeit": time.time()}, ensure_ascii=False),
                    encoding="utf-8")
            except OSError:
                pass


def inhalte() -> list[Path]:
    """Alle Dateien, die Notizen enthalten - Seiten, Anhaenge, Papierkorb.
    Nicht die Tresordatei selbst und keine halbfertigen .neu-Dateien."""
    aus = []
    for pfad in wurzel().rglob("*"):
        if not pfad.is_file() or pfad.name.startswith("."):
            continue
        if pfad.suffix == ".json" or pfad.parent.name.endswith(ANHANG) \
                or PAPIERKORB in pfad.parts:
            aus.append(pfad)
    return aus


def umstellen(chiffrieren: bool) -> int:
    """Bestehende Notizen ver- oder entschluesseln. Jede Datei einzeln und mit
    Umbenennen - bricht es dazwischen ab, ist keine Datei halb geschrieben, und
    der naechste Lauf macht da weiter, wo dieser stehen geblieben ist."""
    getan = 0
    for pfad in inhalte():
        try:
            roh = pfad.read_bytes()
            if tresor.ist_verschluesselt(roh) == chiffrieren:
                continue                                # schon so, wie es sein soll
            _roh_schreiben(pfad, tresor.entschluesseln(roh), chiffrieren)
            getan += 1
        except (OSError, tresor.TresorFehler):
            continue
    return getan


# --- Papierkorb --------------------------------------------------------------
#
# Geleert wird nur auf Knopfdruck. Nichts verschwindet hinter dem Rücken des
# Benutzers - das ist der ganze Sinn eines Papierkorbs.

def _herkunft(korb: Path, name: str) -> list[str] | None:
    try:
        daten = json.loads((korb / f".{name}.herkunft").read_text(encoding="utf-8"))
        teile = daten.get("teile")
        return [str(t) for t in teile] if isinstance(teile, list) and teile else None
    except (OSError, ValueError, TypeError):
        return None


def _aus_namen(name: str) -> list[str]:
    """Notbehelf für Einträge ohne Herkunftsvermerk (von vor dieser Fassung)."""
    ohne_marke = name.split(" ", 1)[1] if " " in name else name
    stamm = ohne_marke[:-5] if ohne_marke.endswith(".json") else ohne_marke
    teile = [t for t in stamm.split(" - ") if t]
    return teile or [stamm]


def papierkorb_liste() -> list[dict]:
    """Was im Papierkorb liegt, neueste zuerst."""
    korb = wurzel() / PAPIERKORB
    if not korb.is_dir():
        return []
    aus = []
    for p in sorted(korb.iterdir(), reverse=True):
        if p.name.startswith("."):
            continue                            # Herkunftsvermerke
        teile = _herkunft(korb, p.name) or _aus_namen(p.name)
        if p.is_dir():
            art = "anhaenge" if p.name.endswith(ANHANG) else (
                "verlauf" if p.name.endswith(VERLAUF) else "ordner")
        else:
            art = "seite"
        aus.append({
            "eintrag": p.name,
            "art": art,
            "titel": " / ".join(teile),
            "zeit": p.stat().st_mtime,
            "genau": _herkunft(korb, p.name) is not None,
        })
    return aus


def _korbeintrag(eintrag: str) -> Path:
    korb = wurzel() / PAPIERKORB
    name = slug(eintrag) if "/" in eintrag or "\\" in eintrag else eintrag
    ziel = (korb / name).resolve()
    if not str(ziel).startswith(str(korb.resolve())) or not ziel.exists():
        raise SpeicherFehler("Den Eintrag gibt es im Papierkorb nicht")
    return ziel


def papierkorb_zurueck(eintrag: str) -> dict:
    """Einen Eintrag an seinen alten Platz zurücklegen.

    Fehlen Notizbuch oder Abschnitt inzwischen, werden sie neu angelegt - sonst
    liesse sich eine Seite nicht zurückholen, nur weil der Abschnitt darüber
    auch gelöscht wurde.
    """
    korb = wurzel() / PAPIERKORB
    quelle = _korbeintrag(eintrag)
    teile = _herkunft(korb, quelle.name) or _aus_namen(quelle.name)

    if quelle.is_dir() and not quelle.name.endswith((ANHANG, VERLAUF)):
        ziel = wurzel() / slug(teile[-1] if teile else quelle.name)
        if len(teile) >= 2:
            buch = wurzel() / slug(teile[0])
            buch.mkdir(parents=True, exist_ok=True)
            ziel = buch / slug(teile[-1])
        if ziel.exists():
            ziel = ziel.with_name(frei(ziel.parent, ziel.name))
        ziel.parent.mkdir(parents=True, exist_ok=True)
        os.replace(quelle, ziel)
    else:
        if len(teile) < 3:
            raise SpeicherFehler("Zu diesem Eintrag ist nicht bekannt, wohin er gehört")
        ordner = wurzel() / slug(teile[0]) / slug(teile[1])
        ordner.mkdir(parents=True, exist_ok=True)
        roh = teile[2]
        for endung in (".json", ANHANG, VERLAUF):
            if roh.endswith(endung):
                roh = roh[: -len(endung)]
                break
        stamm = slug(roh) or "Wiederhergestellt"
        # Die Endung richtet sich danach, was wirklich im Papierkorb liegt -
        # nicht danach, was im Namen steht.
        if quelle.is_file():
            endung = ".json"
        elif quelle.name.endswith(ANHANG):
            endung = ANHANG
        else:
            endung = VERLAUF
        if endung == VERLAUF:
            ordner = ordner / VERLAUF
            ordner.mkdir(parents=True, exist_ok=True)
            endung = ""
        ziel = ordner / (frei(ordner, stamm, endung) + endung)
        os.replace(quelle, ziel)

    try:
        (korb / f".{quelle.name}.herkunft").unlink(missing_ok=True)
    except OSError:
        pass
    return {"zurueck": str(ziel.relative_to(wurzel()))}


def papierkorb_weg(eintrag: str) -> dict:
    """Einen Eintrag endgültig löschen."""
    korb = wurzel() / PAPIERKORB
    ziel = _korbeintrag(eintrag)
    if ziel.is_dir():
        shutil.rmtree(ziel, ignore_errors=True)
    else:
        ziel.unlink(missing_ok=True)
    try:
        (korb / f".{ziel.name}.herkunft").unlink(missing_ok=True)
    except OSError:
        pass
    return {"weg": ziel.name}


def papierkorb_leeren() -> dict:
    korb = wurzel() / PAPIERKORB
    if not korb.is_dir():
        return {"weg": 0}
    weg = 0
    for p in list(korb.iterdir()):
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink()
            if not p.name.startswith("."):
                weg += 1
        except OSError:
            continue
    return {"weg": weg}


def stand(buch: str, abschnitt: str, name: str) -> dict:
    """Billiger Blick fuer den Browser: hat jemand von aussen reingeschrieben?"""
    datei = pfad_von([buch, abschnitt, f"{slug(name)}.json"])
    if not datei.is_file():
        return {"da": False}
    daten = seite_lesen(buch, abschnitt, name)
    return {"da": True, "rev": daten["rev"], "mtime": daten["mtime"], "geraet": daten.get("geraet", "")}
