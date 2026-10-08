"""Nachsehen, ob auf GitHub eine neuere Fassung liegt - und sie einspielen.

Geholt wird das neueste Release und daraus die angehaengte Installationsdatei.
Die bringt alles mit, also ist das Update derselbe Weg wie die Erstinstallation:
herunterladen, Pruefsumme vergleichen, Installer mit --update laufen lassen.

Nur mit urllib und hashlib - keine uebersetzten Pakete, damit das auch dort baut,
wo kein Compiler steht.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HIER = Path(__file__).resolve().parent
ORDNER = HIER.parent                      # Installationsordner (oder Quellordner)
QUELLE = os.environ.get("NOTIZMAPPE_QUELLE", "https://api.github.com/repos/LucyWolf/notizmappe")
FRIST = 3600                              # Sekunden, die eine Antwort gilt
NOTIZ = ORDNER / ".update-stand.json"     # letzte Antwort, damit nicht jeder Aufruf fragt
PROTOKOLL = ORDNER / ".update.log"
MAX_PAKET = 60 * 1024 * 1024              # Was groesser ist, ist nicht unser Installer


def version_tupel(roh: str) -> tuple[int, ...]:
    """'v1.0.10' -> (1, 0, 10). Stellenweise als Zahl, damit 1.0.9 kleiner als
    1.0.10 ist - ein Zeichenvergleich liegt da falsch."""
    teile = re.findall(r"\d+", str(roh or ""))
    return tuple(int(t) for t in teile[:4]) or (0,)


def installierte_version() -> str:
    try:
        return (HIER / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0"


def aus_installation() -> bool:
    """Laeuft das hier aus einer Installation (dann koennen wir aktualisieren) oder
    aus dem Quellordner (dann macht man das mit git)?"""
    return (ORDNER / ".einrichtung").is_file()


# --- Einstellungen zum Update ------------------------------------------------

OPTIONEN = ORDNER / ".optionen.json"
STANDARD = {"beim_start_pruefen": True, "automatisch_einspielen": False}


def optionen_lesen() -> dict:
    o = dict(STANDARD)
    try:
        gelesen = json.loads(OPTIONEN.read_text(encoding="utf-8"))
        for schluessel in STANDARD:
            if schluessel in gelesen:
                o[schluessel] = bool(gelesen[schluessel])
    except (OSError, ValueError):
        pass
    return o


def optionen_schreiben(neu: dict) -> dict:
    """Liegt bei der Installation, nicht bei den Notizen: es geht um das Programm,
    nicht um den Inhalt - und ein Sync soll das nicht zwischen Rechnern hin- und
    herschieben."""
    o = optionen_lesen()
    for schluessel in STANDARD:
        if schluessel in neu:
            o[schluessel] = bool(neu[schluessel])
    try:
        OPTIONEN.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as f:
        raise RuntimeError(f"Einstellungen ließen sich nicht sichern: {f}")
    return o


def _token() -> str | None:
    """Nur fuer ein privates Repo noetig. Steht er nicht in der Umgebung, darf er
    in einer Datei liegen - die sollte dann nur dem eigenen Benutzer gehoeren."""
    t = os.environ.get("NOTIZMAPPE_TOKEN", "").strip()
    if t:
        return t
    datei = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "notizmappe/token"
    try:
        return datei.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _abrufen(url: str, roh: bool = False, grenze: int = MAX_PAKET):
    anfrage = urllib.request.Request(url, headers={
        "Accept": "application/octet-stream" if roh else "application/vnd.github+json",
        "User-Agent": f"Notizmappe/{installierte_version()}",
    })
    t = _token()
    if t:
        anfrage.add_header("Authorization", f"Bearer {t}")
    with urllib.request.urlopen(anfrage, timeout=20) as antwort:
        daten = antwort.read(grenze + 1)
    if len(daten) > grenze:
        raise ValueError("Antwort ist groesser als erlaubt")
    return daten if roh else json.loads(daten)


def neuestes_release() -> dict:
    """{'version', 'marke', 'paket', 'pruefsumme', 'notizen'} vom neuesten Release."""
    r = _abrufen(f"{QUELLE}/releases/latest")
    anhaenge = {a.get("name", ""): a for a in r.get("assets") or []}
    # Es haengen zwei gleiche Pakete am Release: eins mit Versionsnummer im Namen
    # (fuer Menschen und fuer hier) und eins ohne (fuer releases/latest/download im
    # Doppelklick-Installer). Das versionierte ist eindeutiger.
    paket = (next((a for n, a in anhaenge.items() if re.search(r"-v[\d.]+-installer\.sh$", n)), None)
             or next((a for n, a in anhaenge.items() if n.endswith("-installer.sh")), None))
    pruef = next((a for n, a in anhaenge.items() if n.endswith("-installer.sh.sha256")), None)
    return {
        "version": re.sub(r"^v", "", r.get("tag_name") or ""),
        "marke": r.get("tag_name") or "",
        "notizen": (r.get("body") or "")[:4000],
        "paket": paket and paket.get("url"),
        "paket_name": paket and paket.get("name"),
        "pruefsumme": pruef and pruef.get("url"),
    }


def pruefen(frisch: bool = False) -> dict:
    """Stand melden. Antworten werden eine Stunde lang wiederverwendet, damit nicht
    jeder Seitenaufruf bei GitHub anklopft (und in die Bremse laeuft)."""
    jetzt = time.time()
    if not frisch:
        try:
            alt = json.loads(NOTIZ.read_text(encoding="utf-8"))
            if jetzt - alt.get("geprueft", 0) < FRIST:
                alt["installiert"] = installierte_version()
                alt["neuer"] = version_tupel(alt.get("verfuegbar")) > version_tupel(alt["installiert"])
                return alt
        except (OSError, ValueError):
            pass

    stand = {
        "installiert": installierte_version(),
        "verfuegbar": None,
        "neuer": False,
        "aktualisierbar": aus_installation(),
        "geprueft": jetzt,
        "fehler": None,
    }
    try:
        r = neuestes_release()
        stand["verfuegbar"] = r["version"] or None
        stand["notizen"] = r["notizen"]
        stand["neuer"] = version_tupel(r["version"]) > version_tupel(stand["installiert"])
        if stand["neuer"] and not r["paket"]:
            stand["fehler"] = "Am Release hängt keine Installationsdatei"
            stand["neuer"] = False
    except urllib.error.HTTPError as f:
        stand["fehler"] = ("Repo ist privat - ohne Token kein Zugriff (404)" if f.code == 404
                           else f"GitHub antwortet mit {f.code}")
    except (urllib.error.URLError, ValueError, TimeoutError) as f:
        stand["fehler"] = f"GitHub nicht erreichbar: {f}"
    try:
        NOTIZ.write_text(json.dumps(stand), encoding="utf-8")
    except OSError:
        pass
    return stand


def _erwartete_summe(url: str) -> str | None:
    try:
        text = _abrufen(url, roh=True, grenze=4096).decode("utf-8", "ignore")
    except Exception:
        return None
    treffer = re.search(r"\b([0-9a-f]{64})\b", text)
    return treffer.group(1) if treffer else None


def einspielen() -> dict:
    """Paket holen, pruefen, Installer starten.

    Der Installer startet den Dienst neu und wuerde damit diesen Prozess abschiessen -
    mitten im eigenen Update. Deshalb laeuft er abgekoppelt in einer eigenen Sitzung
    und schreibt sein Protokoll in eine Datei, die wir danach auslesen koennen.
    """
    if not aus_installation():
        raise RuntimeError("Läuft aus dem Quellordner - hier wird mit git aktualisiert.")

    r = neuestes_release()
    if version_tupel(r["version"]) <= version_tupel(installierte_version()):
        raise RuntimeError(f"Nichts Neueres da (installiert {installierte_version()}, "
                           f"im Release {r['version'] or '?'})")
    if not r["paket"]:
        raise RuntimeError("Am Release hängt keine Installationsdatei")

    rohdaten = _abrufen(r["paket"], roh=True)
    echt = hashlib.sha256(rohdaten).hexdigest()
    soll = _erwartete_summe(r["pruefsumme"]) if r["pruefsumme"] else None
    if soll and soll != echt:
        raise RuntimeError(f"Prüfsumme passt nicht (erwartet {soll}, geladen {echt})")

    ziel = Path(tempfile.mkdtemp(prefix="notizmappe-update-")) / (r["paket_name"] or "installer.sh")
    ziel.write_bytes(rohdaten)
    ziel.chmod(0o700)

    with PROTOKOLL.open("w", encoding="utf-8") as log:
        log.write(f"{time.strftime('%d.%m.%Y %H:%M:%S')}  "
                  f"{installierte_version()} -> {r['version']}  ({echt[:12]})\n")
        log.flush()
        subprocess.Popen(
            ["bash", str(ziel), "--update"],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,   # ueberlebt den Neustart des Dienstes
            cwd=str(ziel.parent),
            env={**os.environ, "NOTIZMAPPE_ZIEL": str(ORDNER)},
        )
    return {"von": installierte_version(), "nach": r["version"], "pruefsumme": echt}


def protokoll() -> dict:
    try:
        text = PROTOKOLL.read_text(encoding="utf-8")[-4000:]
    except OSError:
        return {"laeuft": False, "text": "", "fertig": False}
    return {
        "laeuft": True,
        "text": text,
        "fertig": "Fertig." in text,
        "fehler": "Fehler:" in text,
        "version": installierte_version(),
    }


if __name__ == "__main__":
    # Von Hand: python3 aktualisieren.py [--jetzt]
    if "--jetzt" in sys.argv:
        print(json.dumps(einspielen(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(pruefen(frisch=True), ensure_ascii=False, indent=1))
