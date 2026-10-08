"""Verbindungen der Desktop-Fassung zu Notizmappe-Servern (Docker).

Man gibt einmal Adresse, Name und Passwort ein. Damit holt sich dieser Rechner beim
Server einen Geraeteschluessel; gespeichert wird nur der, nie das Passwort. Zum
Oeffnen geht ein eigenes Fenster auf, das sich mit dem Schluessel anmeldet - die
Oberflaeche darin kommt vom Server, mit dessen Konten und Projekten.
"""
from __future__ import annotations

import json
import secrets
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

import konfig


class VerbindungsFehler(Exception):
    pass


def adresse_ordnen(roh: str) -> str:
    roh = (roh or "").strip().rstrip("/")
    if not roh:
        raise VerbindungsFehler("Adresse fehlt")
    if "://" not in roh:
        roh = "https://" + roh
    teile = urlparse(roh)
    if teile.scheme not in ("http", "https") or not teile.netloc:
        raise VerbindungsFehler("Die Adresse sieht nicht aus wie notizen.example.de oder https://…")
    if teile.path not in ("", "/") or teile.query:
        raise VerbindungsFehler("Bitte nur die Adresse des Servers, ohne Pfad")
    return f"{teile.scheme}://{teile.netloc}"


def _rufen(url: str, rumpf: dict | None = None) -> dict:
    daten = json.dumps(rumpf).encode() if rumpf is not None else None
    anfrage = urllib.request.Request(url, data=daten, headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "Notizmappe-Desktop",
    })
    try:
        with urllib.request.urlopen(anfrage, timeout=10) as a:
            return json.loads(a.read(100_000))
    except urllib.error.HTTPError as f:
        try:
            grund = json.loads(f.read(10_000)).get("fehler")
        except (ValueError, AttributeError):
            grund = None
        raise VerbindungsFehler(grund or f"Server antwortet mit {f.code}")
    except (urllib.error.URLError, OSError, TimeoutError) as f:
        grund = getattr(f, "reason", f)
        raise VerbindungsFehler(f"Server nicht erreichbar: {grund}")
    except ValueError:
        raise VerbindungsFehler("Unter der Adresse antwortet keine Notizmappe")


def liste(mit_token: bool = False) -> list[dict]:
    aus = []
    for v in konfig.lesen().get("verbindungen", []):
        if not isinstance(v, dict) or not v.get("id"):
            continue
        eintrag = {"id": v["id"], "adresse": v.get("adresse", ""), "name": v.get("name", "")}
        if mit_token:
            eintrag["token"] = v.get("token", "")
        aus.append(eintrag)
    return aus


def finden(kennung: str) -> dict:
    for v in liste(mit_token=True):
        if v["id"] == kennung:
            return v
    raise VerbindungsFehler("Verbindung gibt es nicht")


def verbinden(adresse: str, name: str, passwort: str) -> dict:
    adresse = adresse_ordnen(adresse)
    status = _rufen(adresse + "/api/status")
    if not status.get("notizmappe"):
        raise VerbindungsFehler("Unter der Adresse antwortet keine Notizmappe")
    if not status.get("anmeldung"):
        raise VerbindungsFehler("Der Server hat keine Anmeldung eingerichtet")
    try:
        geraet = socket.gethostname()[:60] or "Desktop"
    except OSError:
        geraet = "Desktop"
    antwort = _rufen(adresse + "/api/geraet", {"name": name, "passwort": passwort, "geraet": geraet})
    token = antwort.get("token")
    if not token:
        raise VerbindungsFehler("Der Server hat keinen Geräteschlüssel geschickt")
    neu = {"id": secrets.token_hex(4), "adresse": adresse, "name": antwort.get("name") or name, "token": token}
    alle = [v for v in konfig.lesen().get("verbindungen", [])
            if not (v.get("adresse") == adresse and v.get("name") == neu["name"])]
    konfig.aendern(verbindungen=alle + [neu])
    return {k: neu[k] for k in ("id", "adresse", "name")}


def entfernen(kennung: str) -> None:
    alle = [v for v in konfig.lesen().get("verbindungen", []) if v.get("id") != kennung]
    konfig.aendern(verbindungen=alle)
