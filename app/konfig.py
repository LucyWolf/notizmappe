"""Einstellungen dieses Rechners: vor allem, welcher Datenordner benutzt wird.

Liegt bewusst nicht im Datenordner. Der wird mit Nextcloud geteilt und kann
umgestellt werden - die Angabe, wo er liegt, kann nicht in ihm selbst stehen.

    Linux:   ~/.config/notizmappe/einstellungen.json
    Windows: %APPDATA%/notizmappe/einstellungen.json
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

# RLock: aendern() haelt sie ueber Lesen und Schreiben, schreiben() nimmt sie
# darin noch einmal.
_sperre = threading.RLock()


def ordner() -> Path:
    gesetzt = os.environ.get("NOTIZMAPPE_KONFIG")
    if gesetzt:
        p = Path(gesetzt).expanduser()
    elif sys.platform.startswith("win") and os.environ.get("APPDATA"):
        p = Path(os.environ["APPDATA"]) / "notizmappe"
    else:
        p = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "notizmappe"
    p.mkdir(parents=True, exist_ok=True)
    return p


def datei(name: str = "einstellungen.json") -> Path:
    return ordner() / name


def lesen(name: str = "einstellungen.json") -> dict:
    try:
        roh = json.loads(datei(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return roh if isinstance(roh, dict) else {}


def schreiben(daten: dict, name: str = "einstellungen.json") -> None:
    """Atomar und nur fuer den eigenen Benutzer lesbar - hier stehen auch
    Passwort-Hashes und Geraeteschluessel."""
    ziel = datei(name)
    tmp = ziel.with_name(f".{ziel.name}.neu")
    with _sperre:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=1)
        os.replace(tmp, ziel)


def aendern(name: str = "einstellungen.json", **werte) -> dict:
    """Lesen, aendern, schreiben - unter einer Sperre. Vorher lag nur das
    Schreiben darunter: zwei gleichzeitige Aenderungen lasen denselben Stand,
    und die zweite schrieb die erste wieder weg."""
    with _sperre:
        d = lesen(name)
        for k, v in werte.items():
            if v is None:
                d.pop(k, None)
            else:
                d[k] = v
        schreiben(d, name)
    return d
