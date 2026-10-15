"""Verbindung zu einer Notizmappe, die auf einem Server läuft.

Das ist das **einzige** Modul des Programms, das eine Adresse kennt und über
das Netz spricht - neben `aktualisieren.py`, das bei GitHub nach Updates sieht.
Alles andere arbeitet weiter mit Dateien auf der Platte, und die Prüfung
`tests/test_kein_server.py` hält das fest.

Der Gedanke dahinter: Es gibt keinen Server **im** Programm. Es gibt die
Möglichkeit, sich mit einem zu **verbinden** - mit einem, der ihr gehört, dessen
Adresse sie selbst einträgt. Verbunden arbeitet das Fenster gegen den Server
statt gegen den eigenen Ordner, und zwar ganz: derselbe Baum, dieselben Seiten,
dieselben Methoden. Umgeschaltet wird in den Einstellungen.

Gemerkt werden Adresse und Benutzername. Das **Passwort nicht** - gemerkt wird
das Sitzungs-Kennzeichen, das der Server ausgibt. Es läuft nach zwei Wochen ab,
gilt nur für diesen Server, und ein Passwortwechsel dort beendet es sofort.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import konfig

ZEIT = 20                       # Sekunden, bis eine Antwort da sein muss
MAX_ANTWORT = 64 * 1024 * 1024  # ein Anhang kommt als Base64 zurueck
KEKS = "notizmappe"


class FerneFehler(Exception):
    """Keine Verbindung, falsche Anmeldung, der Server mag nicht."""


def _einstellung() -> dict:
    d = konfig.lesen()
    return {
        "adresse": str(d.get("ferne_adresse") or "").strip(),
        "benutzer": str(d.get("ferne_benutzer") or "").strip(),
        "keks": str(d.get("ferne_keks") or "").strip(),
        "aktiv": bool(d.get("ferne_aktiv")),
    }


def aktiv() -> bool:
    """Arbeitet das Fenster gerade gegen einen Server?"""
    e = _einstellung()
    return bool(e["aktiv"] and e["adresse"] and e["keks"])


def stand() -> dict:
    e = _einstellung()
    return {"adresse": e["adresse"], "benutzer": e["benutzer"],
            "angemeldet": bool(e["keks"]), "aktiv": aktiv()}


def _adresse_pruefen(roh: str) -> str:
    """Aus dem, was sie eintippt, eine brauchbare Adresse machen."""
    adresse = (roh or "").strip().rstrip("/")
    if not adresse:
        raise FerneFehler("Keine Adresse angegeben")
    if "://" not in adresse:
        adresse = "http://" + adresse          # ohne Angabe: im eigenen Netz
    teile = urllib.parse.urlparse(adresse)
    if teile.scheme not in ("http", "https"):
        raise FerneFehler("Die Adresse muss mit http:// oder https:// anfangen")
    if not teile.netloc:
        raise FerneFehler("In der Adresse fehlt der Rechnername")
    return f"{teile.scheme}://{teile.netloc}{teile.path}".rstrip("/")


def _kopf(roh) -> dict:
    """Kopfzeilen mit kleingeschriebenen Namen.

    Welche Gross- und Kleinschreibung ein Server waehlt, ist ihm ueberlassen -
    "Location" und "location" sind dasselbe. Wer auf einen davon prueft, baut
    einen Fehler ein, den der eigene Testserver nicht zeigt und der echte
    sofort: die Anmeldung fand ihren Keks nicht und schlug immer fehl.
    """
    aus = {}
    for name, wert in roh.items():
        klein = name.lower()
        aus[klein] = f"{aus[klein]}, {wert}" if klein in aus else wert
    return aus


def _schicken(adresse: str, weg: str, daten: bytes | None, kopf: dict,
              methode: str = "GET") -> tuple[int, bytes, dict]:
    anfrage = urllib.request.Request(adresse + weg, data=daten, method=methode)
    for k, v in kopf.items():
        anfrage.add_header(k, v)
    try:
        # Keine Umleitungen verfolgen: eine Anmeldung, die woandershin zeigt,
        # soll auffallen und nicht stillschweigend woanders landen.
        with urllib.request.urlopen(anfrage, timeout=ZEIT) as antwort:
            return antwort.status, antwort.read(MAX_ANTWORT), _kopf(antwort.headers)
    except urllib.error.HTTPError as f:
        return f.code, f.read(MAX_ANTWORT), _kopf(f.headers)
    except urllib.error.URLError as f:
        grund = getattr(f, "reason", f)
        raise FerneFehler(f"Keine Verbindung zu {adresse}: {grund}")
    except (TimeoutError, OSError) as f:
        raise FerneFehler(f"Keine Verbindung zu {adresse}: {f}")


class _OhneUmleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_oeffner = urllib.request.build_opener(_OhneUmleitung)
urllib.request.install_opener(_oeffner)


def anmelden(adresse: str, benutzer: str, passwort: str) -> dict:
    """Am Server anmelden und das Sitzungs-Kennzeichen merken."""
    adresse = _adresse_pruefen(adresse)
    benutzer = (benutzer or "").strip().lower()
    if not benutzer or not passwort:
        raise FerneFehler("Benutzername und Passwort angeben")

    daten = urllib.parse.urlencode({"name": benutzer, "passwort": passwort}).encode()
    lage, rumpf, kopf = _schicken(
        adresse, "/anmelden", daten,
        {"Content-Type": "application/x-www-form-urlencoded"}, "POST")

    keks = ""
    for teil in (kopf.get("set-cookie") or "").split(","):
        for stueck in teil.split(";"):
            stueck = stueck.strip()
            if stueck.startswith(KEKS + "="):
                keks = stueck[len(KEKS) + 1:]
    if lage == 303 and keks:
        konfig.aendern(ferne_adresse=adresse, ferne_benutzer=benutzer,
                       ferne_keks=keks, ferne_aktiv=True)
        return {"ok": True, "adresse": adresse, "benutzer": benutzer}

    wohin = kopf.get("location") or ""
    if "fehler=" in wohin:
        grund = urllib.parse.unquote_plus(wohin.split("fehler=", 1)[1])
        raise FerneFehler(grund)
    if lage == 200 and b"einrichten" in rumpf:
        raise FerneFehler("Dort ist noch kein Zugang eingerichtet - "
                          "die Adresse einmal im Browser aufrufen und einen anlegen")
    raise FerneFehler(f"Anmeldung abgelehnt (Antwort {lage})")


def abmelden() -> dict:
    konfig.aendern(ferne_keks=None, ferne_aktiv=False)
    return {"ok": True}


def umschalten(an: bool) -> dict:
    """Zwischen den eigenen Notizen und dem Server wechseln."""
    e = _einstellung()
    if an and not e["keks"]:
        raise FerneFehler("Erst anmelden")
    konfig.aendern(ferne_aktiv=bool(an))
    return stand()


def ruf(methode: str, args: list) -> dict:
    """Eine Brücken-Methode auf dem Server ausführen."""
    e = _einstellung()
    if not e["adresse"] or not e["keks"]:
        raise FerneFehler("Nicht mit einem Server verbunden")
    daten = json.dumps({"args": list(args)}).encode("utf-8")
    lage, rumpf, _ = _schicken(
        e["adresse"], "/bruecke/" + urllib.parse.quote(methode), daten,
        {"Content-Type": "application/json", "X-Notizmappe": "1",
         "Cookie": f"{KEKS}={e['keks']}"}, "POST")
    if lage == 401:
        # Abgelaufen oder das Passwort dort geaendert: nicht stillschweigend
        # weiterwursteln, sondern sagen, dass neu angemeldet werden muss.
        konfig.aendern(ferne_keks=None)
        raise FerneFehler("Die Anmeldung am Server gilt nicht mehr - bitte neu anmelden")
    try:
        antwort = json.loads(rumpf.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise FerneFehler(f"Der Server antwortet nicht verständlich (Antwort {lage})")
    if not isinstance(antwort, dict):
        raise FerneFehler("Der Server antwortet nicht verständlich")
    return antwort


def anhang_holen(notizbuch: str, abschnitt: str, name: str, datei: str) -> bytes:
    """Einen Anhang vom Server holen - zum Öffnen oder Ablegen hier."""
    e = _einstellung()
    if not e["adresse"] or not e["keks"]:
        raise FerneFehler("Nicht mit einem Server verbunden")
    felder = urllib.parse.urlencode({"notizbuch": notizbuch, "abschnitt": abschnitt,
                                     "name": name, "datei": datei})
    lage, rumpf, _ = _schicken(e["adresse"], "/anhang?" + felder, None,
                               {"Cookie": f"{KEKS}={e['keks']}"})
    if lage != 200:
        raise FerneFehler(f"Der Anhang ließ sich nicht holen (Antwort {lage})")
    return rumpf
