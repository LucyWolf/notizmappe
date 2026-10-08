"""Konten, Anmeldung und Sperre.

Zwei Betriebsarten:
  * Auf dem eigenen Rechner ist die Anmeldung aus, bis jemand in den Einstellungen
    ein Passwort festlegt. Ab dann ist es ein Sperrbildschirm: beim Start und nach
    einer Weile ohne Benutzung.
  * Als Server (NOTIZMAPPE_SERVER=1, so laeuft der Docker-Container) ist sie immer
    an. Gibt es noch kein Konto, legt man das erste ueber die Weboberflaeche an -
    mit einem Einrichtungscode aus dem Protokoll, damit nicht der Erstbeste, der
    die Adresse findet, sich zum Admin macht.

Gespeichert wird in konten.json im Einstellungsordner (konfig.py), nie im
Datenordner: der wird geteilt und synchronisiert. Passwoerter als scrypt-Hash,
Sitzungen und Geraeteschluessel nur als SHA-256 - wer die Datei liest, kann sich
damit nicht anmelden.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time

import konfig

DATEI = "konten.json"
SITZUNG_SERVER = 30 * 24 * 3600      # angemeldet bleiben im Browser
SITZUNG_LOKAL = 12 * 3600            # Sperre auf dem eigenen Rechner: Rueckfall,
                                     # die eigentliche Zeit macht die Oberflaeche
GERAET = 365 * 24 * 3600             # Schluessel fuer die Desktop-Fassung
NAME_MUSTER = re.compile(r"^[\w.\- ]{1,40}$")
MIN_PASSWORT = 8

_sperre = threading.RLock()
_fehlversuche: dict[str, list[float]] = {}
_einrichtungscode: str | None = None


class KontoFehler(Exception):
    pass


def server_modus() -> bool:
    return os.environ.get("NOTIZMAPPE_SERVER") == "1"


# --- Passwoerter --------------------------------------------------------------

def _hash(passwort: str, salz: bytes | None = None) -> str:
    salz = salz or secrets.token_bytes(16)
    h = hashlib.scrypt(passwort.encode("utf-8"), salt=salz, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salz.hex()}${h.hex()}"


def _passt(passwort: str, gespeichert: str) -> bool:
    try:
        art, n, r, p, salz, h = gespeichert.split("$")
        if art != "scrypt":
            return False
        neu = hashlib.scrypt(passwort.encode("utf-8"), salt=bytes.fromhex(salz),
                             n=int(n), r=int(r), p=int(p), dklen=len(h) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(neu.hex(), h)


def _passwort_ok(passwort: str) -> str:
    if not isinstance(passwort, str) or len(passwort) < MIN_PASSWORT:
        raise KontoFehler(f"Das Passwort braucht mindestens {MIN_PASSWORT} Zeichen")
    if len(passwort) > 200:
        raise KontoFehler("Das Passwort ist zu lang")
    return passwort


def _schluessel(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Datei --------------------------------------------------------------------

def _laden() -> dict:
    d = konfig.lesen(DATEI)
    d.setdefault("konten", {})
    d.setdefault("sitzungen", {})
    return d


def _sichern(d: dict) -> None:
    jetzt = time.time()
    d["sitzungen"] = {k: s for k, s in d["sitzungen"].items()
                      if s.get("bis", 0) > jetzt and s.get("name") in d["konten"]}
    konfig.schreiben(d, DATEI)


def aktiv() -> bool:
    """Muss man sich anmelden?"""
    return server_modus() or bool(_laden()["konten"])


def konten() -> list[dict]:
    d = _laden()
    return [{"name": n, "admin": bool(k.get("admin")), "angelegt": k.get("angelegt")}
            for n, k in sorted(d["konten"].items(), key=lambda x: x[0].lower())]


def konto(name: str) -> dict | None:
    k = _laden()["konten"].get(name)
    return {"name": name, "admin": bool(k.get("admin"))} if k else None


# --- Verwaltung ---------------------------------------------------------------

def anlegen(name: str, passwort: str, admin: bool = False) -> dict:
    name = (name or "").strip()
    if not NAME_MUSTER.match(name):
        raise KontoFehler("Name: 1-40 Zeichen, Buchstaben, Ziffern, Leerzeichen, . _ -")
    _passwort_ok(passwort)
    with _sperre:
        d = _laden()
        if any(n.lower() == name.lower() for n in d["konten"]):
            raise KontoFehler("Den Namen gibt es schon")
        d["konten"][name] = {"hash": _hash(passwort), "admin": bool(admin), "angelegt": int(time.time())}
        _sichern(d)
    return {"name": name, "admin": bool(admin)}


def loeschen(name: str) -> None:
    with _sperre:
        d = _laden()
        if name not in d["konten"]:
            raise KontoFehler("Konto gibt es nicht")
        rest_admins = [n for n, k in d["konten"].items() if k.get("admin") and n != name]
        if d["konten"][name].get("admin") and not rest_admins and (server_modus() or len(d["konten"]) > 1):
            raise KontoFehler("Das letzte Admin-Konto kann nicht weg - sonst verwaltet niemand mehr")
        del d["konten"][name]
        _sichern(d)        # nimmt dessen Sitzungen und Geraete gleich mit


def passwort_setzen(name: str, passwort: str) -> None:
    _passwort_ok(passwort)
    with _sperre:
        d = _laden()
        if name not in d["konten"]:
            raise KontoFehler("Konto gibt es nicht")
        d["konten"][name]["hash"] = _hash(passwort)
        # Neues Passwort: ueberall sonst abmelden, auch die Geraete.
        d["sitzungen"] = {k: s for k, s in d["sitzungen"].items() if s.get("name") != name}
        _sichern(d)


def admin_setzen(name: str, admin: bool) -> None:
    with _sperre:
        d = _laden()
        if name not in d["konten"]:
            raise KontoFehler("Konto gibt es nicht")
        if not admin and not [n for n, k in d["konten"].items() if k.get("admin") and n != name]:
            raise KontoFehler("Mindestens ein Konto muss Admin bleiben")
        d["konten"][name]["admin"] = bool(admin)
        _sichern(d)


# --- Anmelden -----------------------------------------------------------------

def _gebremst(schluessel: str, frei: int = 5) -> float:
    """Sekunden, die noch gewartet werden muss. Nach 5 Fehlversuchen in 15 Minuten
    wird es mit jedem weiteren laenger - Raten lohnt sich nicht."""
    jetzt = time.time()
    liste = [t for t in _fehlversuche.get(schluessel, []) if jetzt - t < 900]
    _fehlversuche[schluessel] = liste
    if len(liste) < frei:
        return 0
    return max(0.0, liste[-1] + min(300, 2 ** (len(liste) - frei + 1)) - jetzt)


def pruefen(name: str, passwort: str, wer: str = "") -> dict:
    """Name und Passwort pruefen, mit Bremse. Liefert das Konto oder wirft."""
    with _sperre:
        d = _laden()
        if not name and len(d["konten"]) == 1 and not server_modus():
            name = next(iter(d["konten"]))           # Sperrbildschirm: nur Passwort
        # Pro Absender und Name - und pro Name allein, mit mehr Spielraum: hinter
        # einem Proxy laesst sich die Absenderadresse faelschen.
        bremse = f"{wer}|{(name or '').lower()}"
        nur_name = f"*|{(name or '').lower()}"
        warten = max(_gebremst(bremse), _gebremst(nur_name, 15))
        if warten:
            raise KontoFehler(f"Zu viele Fehlversuche - bitte {int(warten) + 1} Sekunden warten")
        k = d["konten"].get(name or "")
        # Auch bei unbekanntem Namen einmal hashen, damit die Antwortzeit nicht
        # verraet, ob es das Konto gibt.
        if not _passt(passwort or "", k["hash"] if k else _hash("x")):
            _fehlversuche.setdefault(bremse, []).append(time.time())
            _fehlversuche.setdefault(nur_name, []).append(time.time())
            raise KontoFehler("Name oder Passwort stimmt nicht")
        _fehlversuche.pop(bremse, None)
        return {"name": name, "admin": bool(k.get("admin"))}


def sitzung_anlegen(name: str, art: str = "sitzung", geraet: str = "") -> str:
    token = secrets.token_urlsafe(32)
    dauer = GERAET if art == "geraet" else (SITZUNG_SERVER if server_modus() else SITZUNG_LOKAL)
    with _sperre:
        d = _laden()
        d["sitzungen"][_schluessel(token)] = {
            "name": name, "art": art, "geraet": geraet[:60],
            "seit": int(time.time()), "bis": int(time.time() + dauer),
        }
        _sichern(d)
    return token


def sitzung(token: str | None) -> dict | None:
    if not token:
        return None
    d = _laden()
    s = d["sitzungen"].get(_schluessel(token))
    if not s or s.get("bis", 0) < time.time():
        return None
    k = d["konten"].get(s.get("name"))
    if not k:
        return None
    return {"name": s["name"], "admin": bool(k.get("admin")), "art": s.get("art", "sitzung")}


def abmelden(token: str | None) -> None:
    if not token:
        return
    with _sperre:
        d = _laden()
        if d["sitzungen"].pop(_schluessel(token), None):
            _sichern(d)


def geraete(name: str) -> list[dict]:
    d = _laden()
    return [{"id": k[:12], "geraet": s.get("geraet") or "?", "seit": s.get("seit")}
            for k, s in d["sitzungen"].items() if s.get("name") == name and s.get("art") == "geraet"]


def geraet_entfernen(name: str, kennung: str) -> None:
    with _sperre:
        d = _laden()
        d["sitzungen"] = {k: s for k, s in d["sitzungen"].items()
                          if not (s.get("name") == name and s.get("art") == "geraet" and k.startswith(kennung))}
        _sichern(d)


# --- Ersteinrichtung im Server-Betrieb -----------------------------------------

def einrichtungscode() -> str | None:
    """Solange es kein Konto gibt: ein Code, der nur im Protokoll des Servers
    steht. Wer ihn hat, hat Zugriff auf den Rechner - und darf das erste Konto
    anlegen."""
    global _einrichtungscode
    if _laden()["konten"]:
        _einrichtungscode = None
        return None
    if not _einrichtungscode:
        _einrichtungscode = os.environ.get("NOTIZMAPPE_EINRICHTUNGSCODE") or \
            "-".join(secrets.token_hex(2) for _ in range(3))
    return _einrichtungscode


def einrichten(code: str, name: str, passwort: str, wer: str = "") -> dict:
    with _sperre:
        erwartet = einrichtungscode()
        if not erwartet:
            raise KontoFehler("Es gibt schon ein Konto")
        bremse = f"einrichten|{wer}"
        warten = _gebremst(bremse)
        if warten:
            raise KontoFehler(f"Zu viele Fehlversuche - bitte {int(warten) + 1} Sekunden warten")
        if not hmac.compare_digest((code or "").strip().lower(), erwartet.lower()):
            _fehlversuche.setdefault(bremse, []).append(time.time())
            raise KontoFehler("Einrichtungscode stimmt nicht - er steht im Protokoll des Servers")
        _fehlversuche.pop(bremse, None)
        return anlegen(name, passwort, admin=True)
