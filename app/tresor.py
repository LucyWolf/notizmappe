"""Notizen verschliessen.

Es gibt zwei Schluessel, und das hat einen Grund: Der **Datenschluessel** ist
zufaellig und verschluesselt die Dateien. Er selbst liegt doppelt verschlossen in
.tresor.json - einmal mit dem Passwort, einmal mit dem Wiederherstellungs-
schluessel. Dadurch kostet ein Passwortwechsel nur das Umschliessen dieser einen
Datei und nicht das Neuschreiben aller Notizen, und ein zweiter Weg hinein
bedeutet keine zweite Tuer in der Verschluesselung selbst.

Einen Hauptcode, der ueberall passt, gibt es bewusst nicht: wer ihn kennt oder
aus dem Programm liest, kaeme in jede Notizmappe. Der Wiederherstellungs-
schluessel wird einmal erzeugt, einmal angezeigt und gehoert dem, der ihn
aufschreibt.

Geht das Passwort und der Wiederherstellungsschluessel verloren, sind die Notizen
verloren. Das ist keine Luecke, sondern der Sinn der Sache.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Erkennungszeichen am Dateianfang. Ohne das waere nicht zu unterscheiden, ob eine
# Datei verschluesselt ist oder einfach kaputt - und waehrend des Umstellens
# liegen beide Arten nebeneinander.
MARKE = b"NMV1"
TRESORDATEI = ".tresor.json"

# scrypt: 2^16 braucht hier etwa 130 ms. Langsam genug, dass Durchprobieren nicht
# lohnt, schnell genug, dass das Entsperren nicht stoert.
SCRYPT_N = 2 ** 16
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_SPEICHER = 160 * 1024 * 1024


class TresorFehler(Exception):
    """Falsches Passwort, kaputte Datei, zugesperrt."""


# Der offene Datenschluessel lebt nur im Arbeitsspeicher dieses Prozesses.
_schluessel: bytes | None = None
_offen_seit: float = 0.0


def _b64(roh: bytes) -> str:
    return base64.b64encode(roh).decode("ascii")


def _roh(text: str) -> bytes:
    return base64.b64decode(text)


def _ableiten(geheim: str, salz: bytes) -> bytes:
    return hashlib.scrypt(geheim.encode("utf-8"), salt=salz, n=SCRYPT_N, r=SCRYPT_R,
                          p=SCRYPT_P, dklen=32, maxmem=SCRYPT_SPEICHER)


def _huelle(datenschluessel: bytes, geheim: str) -> dict:
    """Den Datenschluessel mit einem Geheimnis verschliessen."""
    salz = os.urandom(16)
    nonce = os.urandom(12)
    kapsel = AESGCM(_ableiten(geheim, salz)).encrypt(nonce, datenschluessel, None)
    return {"salz": _b64(salz), "nonce": _b64(nonce), "kapsel": _b64(kapsel)}


def _oeffnen(huelle: dict, geheim: str) -> bytes:
    try:
        schluessel = _ableiten(geheim, _roh(huelle["salz"]))
        return AESGCM(schluessel).decrypt(_roh(huelle["nonce"]), _roh(huelle["kapsel"]), None)
    except (InvalidTag, KeyError, ValueError, TypeError):
        raise TresorFehler("Passt nicht")


# --- Die Tresordatei ---------------------------------------------------------

def datei(ordner: Path) -> Path:
    return ordner / TRESORDATEI


def eingerichtet(ordner: Path) -> bool:
    return datei(ordner).is_file()


def _lesen(ordner: Path) -> dict:
    try:
        return json.loads(datei(ordner).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise TresorFehler("Die Tresordatei fehlt oder ist beschädigt")


def _schreiben(ordner: Path, inhalt: dict) -> None:
    ziel = datei(ordner)
    tmp = ziel.with_name(f".{ziel.name}.neu")
    tmp.write_text(json.dumps(inhalt, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ziel)


def rettungsschluessel_erzeugen() -> str:
    """Vier Bloecke aus Base32 - gut abzuschreiben, kein O/0-Durcheinander."""
    roh = secrets.token_bytes(20)
    text = base64.b32encode(roh).decode("ascii").rstrip("=")
    return "-".join(text[i:i + 5] for i in range(0, len(text), 5))


def einrichten(ordner: Path, passwort: str) -> str:
    """Tresor anlegen. Gibt den Wiederherstellungsschluessel zurueck - danach
    steht er nirgends mehr, auch nicht hier."""
    if len(passwort) < 8:
        raise TresorFehler("Das Passwort braucht mindestens 8 Zeichen")
    if eingerichtet(ordner):
        raise TresorFehler("Hier ist schon ein Tresor eingerichtet")

    datenschluessel = os.urandom(32)
    rettung = rettungsschluessel_erzeugen()
    _schreiben(ordner, {
        "version": 1,
        "angelegt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "passwort": _huelle(datenschluessel, passwort),
        "rettung": _huelle(datenschluessel, rettung),
    })
    global _schluessel, _offen_seit
    _schluessel, _offen_seit = datenschluessel, time.time()
    return rettung


def entsperren(ordner: Path, geheim: str) -> None:
    """Mit Passwort oder Wiederherstellungsschluessel aufschliessen."""
    inhalt = _lesen(ordner)
    global _schluessel, _offen_seit
    for art in ("passwort", "rettung"):
        if art not in inhalt:
            continue
        try:
            _schluessel = _oeffnen(inhalt[art], geheim)
            _offen_seit = time.time()
            return
        except TresorFehler:
            continue
    raise TresorFehler("Passwort oder Wiederherstellungsschlüssel stimmt nicht")


def passwort_aendern(ordner: Path, alt: str, neu: str) -> None:
    if len(neu) < 8:
        raise TresorFehler("Das Passwort braucht mindestens 8 Zeichen")
    inhalt = _lesen(ordner)
    datenschluessel = _oeffnen(inhalt["passwort"], alt)
    inhalt["passwort"] = _huelle(datenschluessel, neu)
    _schreiben(ordner, inhalt)


def passwort_zuruecksetzen(ordner: Path, rettung: str, neu: str) -> None:
    """Neues Passwort mit dem Wiederherstellungsschluessel setzen."""
    if len(neu) < 8:
        raise TresorFehler("Das Passwort braucht mindestens 8 Zeichen")
    inhalt = _lesen(ordner)
    if "rettung" not in inhalt:
        raise TresorFehler("Für diesen Tresor gibt es keinen Wiederherstellungsschlüssel")
    datenschluessel = _oeffnen(inhalt["rettung"], rettung.strip().upper())
    inhalt["passwort"] = _huelle(datenschluessel, neu)
    _schreiben(ordner, inhalt)
    global _schluessel, _offen_seit
    _schluessel, _offen_seit = datenschluessel, time.time()


def rettung_erneuern(ordner: Path, passwort: str) -> str:
    """Neuen Wiederherstellungsschluessel ausgeben, der alte gilt dann nicht mehr."""
    inhalt = _lesen(ordner)
    datenschluessel = _oeffnen(inhalt["passwort"], passwort)
    neu = rettungsschluessel_erzeugen()
    inhalt["rettung"] = _huelle(datenschluessel, neu)
    _schreiben(ordner, inhalt)
    return neu


def abschalten(ordner: Path, passwort: str) -> None:
    """Tresordatei entfernen. Die Dateien muessen vorher entschluesselt sein."""
    inhalt = _lesen(ordner)
    _oeffnen(inhalt["passwort"], passwort)       # nur mit richtigem Passwort
    datei(ordner).unlink(missing_ok=True)
    sperren()


# --- Auf- und zugesperrt -----------------------------------------------------

def offen() -> bool:
    return _schluessel is not None


def sperren() -> None:
    global _schluessel, _offen_seit
    _schluessel, _offen_seit = None, 0.0


def offen_seit() -> float:
    return _offen_seit


# --- Inhalte -----------------------------------------------------------------

def verschluesseln(daten: bytes) -> bytes:
    if _schluessel is None:
        raise TresorFehler("Zugesperrt")
    nonce = os.urandom(12)
    return MARKE + nonce + AESGCM(_schluessel).encrypt(nonce, daten, None)


def entschluesseln(daten: bytes) -> bytes:
    if not ist_verschluesselt(daten):
        return daten                      # noch im Klartext (Umstellung laeuft)
    if _schluessel is None:
        raise TresorFehler("Zugesperrt")
    try:
        return AESGCM(_schluessel).decrypt(daten[4:16], daten[16:], None)
    except InvalidTag:
        raise TresorFehler("Die Datei gehört zu einem anderen Schlüssel")


def ist_verschluesselt(daten: bytes) -> bool:
    return daten[:4] == MARKE
