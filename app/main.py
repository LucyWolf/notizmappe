"""Notizmappe - freie Notizflaeche, die auf Dateien in einem Sync-Ordner liegt.

Ein Prozess: FastAPI liefert die Oberflaeche und die API. Anmeldung und Rechte
stehen in konten.py: auf dem eigenen Rechner aus, bis man ein Passwort festlegt;
als Server (Docker) immer an, mit Konten und Notizbuechern als Projekten.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import aktualisieren
import konfig
import konten
import reinigen
import speicher
import verbindungen

HIER = Path(__file__).parent
VERSION = (HIER / "VERSION").read_text().strip()
MAX_ELEMENTE = 500

app = FastAPI(title="Notizmappe", version=VERSION)
app.mount("/static", StaticFiles(directory=HIER / "static"), name="static")
vorlagen = Jinja2Templates(directory=str(HIER / "templates"))


@app.exception_handler(speicher.SpeicherFehler)
async def _speicherfehler(request: Request, exc: speicher.SpeicherFehler):
    return JSONResponse({"fehler": str(exc)}, status_code=400)


@app.exception_handler(speicher.KonfliktFehler)
async def _konflikt(request: Request, exc: speicher.KonfliktFehler):
    # 409 heisst fuer den Browser: nicht nochmal schicken, erst zeigen.
    return JSONResponse({"fehler": str(exc), "aktuell": exc.seite}, status_code=409)


@app.on_event("startup")
async def _einrichtung_ansagen():
    """Im Server-Betrieb ohne Konto: den Einrichtungscode ins Protokoll schreiben.
    Nur wer an das Protokoll kommt (docker logs), kann das erste Konto anlegen."""
    if konten.server_modus():
        code = konten.einrichtungscode()
        if code:
            print(f"\n  Notizmappe: noch kein Konto. Im Browser öffnen und mit diesem Code"
                  f" das Admin-Konto anlegen:\n\n      Einrichtungscode: {code}\n", flush=True)


@app.exception_handler(konten.KontoFehler)
async def _kontofehler(request: Request, exc: konten.KontoFehler):
    return JSONResponse({"fehler": str(exc)}, status_code=400)


# --- Anmeldung -----------------------------------------------------------------
# Alles, was ein Passwort prueft oder hasht (scrypt, ~30 ms), ist eine normale
# def-Route: FastAPI laesst sie im Threadpool laufen. Als async def stuende
# waehrenddessen der ganze Server - ein paar Rateversuche, und alle warten.

KEKS = "notizmappe"
# Ohne Anmeldung erreichbar. /geraet/anmelden kommt von der Desktop-Fassung, also
# von einer anderen Herkunft - deshalb auch ohne Herkunftspruefung.
OFFEN = {"/anmelden", "/api/anmelden", "/api/einrichten", "/api/geraet", "/geraet/anmelden",
         "/api/status", "/favicon.ico"}


def _gast(request: Request) -> str:
    return request.client.host if request.client else ""


@app.middleware("http")
async def _waechter(request: Request, call_next):
    pfad = request.url.path
    # Fremde Seiten duerfen nichts aendern: der Browser schickt bei solchen
    # Anfragen seine Herkunft mit. Zusammen mit SameSite=Strict am Keks reicht das
    # gegen untergeschobene Formulare.
    if request.method not in ("GET", "HEAD", "OPTIONS") and pfad != "/geraet/anmelden":
        herkunft = request.headers.get("origin")
        erlaubt = {request.headers.get("host"), request.headers.get("x-forwarded-host")}
        if herkunft and herkunft != "null" and urlparse(herkunft).netloc not in erlaubt:
            return JSONResponse({"fehler": "Anfrage von fremder Seite abgelehnt"}, status_code=403)
    request.state.konto = None
    if pfad.startswith("/static/") or pfad in OFFEN or not konten.aktiv():
        return await call_next(request)
    k = konten.sitzung(request.cookies.get(KEKS))
    if not k:
        if pfad.startswith("/api/"):
            return JSONResponse({"fehler": "Bitte anmelden", "anmelden": True}, status_code=401)
        return RedirectResponse("/anmelden", status_code=303)
    request.state.konto = k
    return await call_next(request)


def _konto(request: Request) -> dict:
    """Wer fragt. Ohne Anmeldung (eigener Rechner, keine Sperre): der Besitzer."""
    return getattr(request.state, "konto", None) or {"name": None, "admin": True}


def _admin(request: Request) -> None:
    if not _konto(request)["admin"]:
        raise HTTPException(403, "Das darf nur ein Admin")


def _sieht(request: Request, buch: str) -> bool:
    k = _konto(request)
    return k["admin"] or k["name"] in speicher.zugriff_lesen(buch)


def _darf(request: Request, buch: str) -> None:
    # 404 statt 403: wer nicht Mitglied ist, soll nicht einmal erfahren, dass es
    # das Notizbuch gibt.
    if not _sieht(request, buch):
        raise HTTPException(404, "Notizbuch gibt es nicht")


def _keks_setzen(antwort, request: Request, token: str) -> None:
    sicher = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    antwort.set_cookie(
        KEKS, token, httponly=True, samesite="strict", secure=sicher, path="/",
        # Auf dem eigenen Rechner ein Sitzungskeks: Fenster zu = gesperrt.
        max_age=konten.SITZUNG_SERVER if konten.server_modus() else None,
    )


@app.get("/")
async def start(request: Request):
    return vorlagen.TemplateResponse(request, "index.html", {
        "version": VERSION,
        "ordner": str(speicher.wurzel()) if _konto(request)["admin"] else "",
    })


@app.get("/anmelden")
async def anmelden_seite(request: Request):
    if not konten.aktiv() or konten.sitzung(request.cookies.get(KEKS)):
        return RedirectResponse("/", status_code=303)
    code = konten.einrichtungscode() if konten.server_modus() else None
    liste = konten.konten()
    art = "einrichten" if code else ("sperre" if len(liste) == 1 and not konten.server_modus() else "anmelden")
    return vorlagen.TemplateResponse(request, "anmelden.html", {"version": VERSION, "art": art})


@app.get("/api/status")
async def api_status():
    """Offen: fuer die Desktop-Fassung, um zu sehen, ob hier eine Notizmappe
    antwortet - auch wenn sie gesperrt ist."""
    return {"notizmappe": True, "version": VERSION, "anmeldung": konten.aktiv(),
            "server": konten.server_modus()}


@app.post("/api/anmelden")
def api_anmelden(request: Request, rumpf: dict):
    k = konten.pruefen(str(rumpf.get("name") or "").strip(), str(rumpf.get("passwort") or ""), _gast(request))
    antwort = JSONResponse({"ok": True, "name": k["name"]})
    _keks_setzen(antwort, request, konten.sitzung_anlegen(k["name"]))
    return antwort


@app.post("/api/abmelden")
async def api_abmelden(request: Request):
    konten.abmelden(request.cookies.get(KEKS))
    antwort = JSONResponse({"ok": True})
    antwort.delete_cookie(KEKS, path="/")
    return antwort


@app.post("/api/einrichten")
def api_einrichten(request: Request, rumpf: dict):
    if not konten.server_modus():
        raise HTTPException(404, "Nur im Server-Betrieb")
    k = konten.einrichten(str(rumpf.get("code") or ""), str(rumpf.get("name") or ""),
                          str(rumpf.get("passwort") or ""), _gast(request))
    antwort = JSONResponse({"ok": True, "name": k["name"]})
    _keks_setzen(antwort, request, konten.sitzung_anlegen(k["name"]))
    return antwort


@app.post("/api/geraet")
def api_geraet(request: Request, rumpf: dict):
    """Die Desktop-Fassung meldet sich einmal mit Name und Passwort an und bekommt
    einen Geraeteschluessel. Das Passwort wird dort nicht gespeichert."""
    k = konten.pruefen(str(rumpf.get("name") or "").strip(), str(rumpf.get("passwort") or ""), _gast(request))
    geraet = reinigen.text(rumpf.get("geraet"), 60) or "Desktop"
    return {"token": konten.sitzung_anlegen(k["name"], art="geraet", geraet=geraet), "name": k["name"]}


@app.post("/geraet/anmelden")
async def geraet_anmelden(request: Request, token: str = Form(...)):
    """Das Desktop-Fenster schickt seinen Geraeteschluessel als Formular hierher und
    bekommt dafuer eine normale Sitzung im Fenster."""
    s = konten.sitzung(token)
    if not s or s["art"] != "geraet":
        return HTMLResponse("<p>Dieses Gerät ist hier nicht (mehr) angemeldet. In der Notizmappe "
                            "unter Einstellungen → Server neu verbinden.</p>", status_code=401)
    # Weiter per Skript statt per Umleitung: die Umleitung zaehlte noch als von
    # fremder Seite ausgeloest, und der SameSite=Strict-Keks kaeme nicht mit.
    antwort = HTMLResponse('<!doctype html><meta charset="utf-8"><title>Notizmappe</title>'
                           '<script>location.replace("/")</script>')
    _keks_setzen(antwort, request, konten.sitzung_anlegen(s["name"]))
    return antwort


# --- Eigenes Konto und Sperre ---------------------------------------------------

@app.get("/api/ich")
async def api_ich(request: Request):
    k = _konto(request)
    return {
        "name": k["name"], "admin": k["admin"],
        "anmeldung": konten.aktiv(), "server": konten.server_modus(),
        "sperre_minuten": int(konfig.lesen().get("sperre_minuten", 15)),
        "geraete": konten.geraete(k["name"]) if k["name"] else [],
    }


@app.post("/api/ich/passwort")
def api_ich_passwort(request: Request, rumpf: dict):
    k = _konto(request)
    if not k["name"]:
        raise HTTPException(400, "Kein Konto angemeldet")
    konten.pruefen(k["name"], str(rumpf.get("alt") or ""), _gast(request))
    konten.passwort_setzen(k["name"], str(rumpf.get("neu") or ""))
    antwort = JSONResponse({"ok": True})
    _keks_setzen(antwort, request, konten.sitzung_anlegen(k["name"]))   # alle anderen sind jetzt raus
    return antwort


@app.post("/api/ich/geraete/entfernen")
async def api_ich_geraet_weg(request: Request, rumpf: dict):
    k = _konto(request)
    if k["name"]:
        konten.geraet_entfernen(k["name"], reinigen.text(rumpf.get("id"), 20))
    return {"ok": True}


@app.post("/api/sperre")
def api_sperre(request: Request, rumpf: dict):
    """Sperre auf dem eigenen Rechner einschalten: legt das eine Konto an."""
    _nur_hier(request)
    if konten.aktiv():
        raise HTTPException(409, "Die Anmeldung ist schon eingerichtet")
    import getpass
    try:
        name = reinigen.text(getpass.getuser(), 40) or "ich"
    except Exception:
        name = "ich"
    k = konten.anlegen(name if konten.NAME_MUSTER.match(name) else "ich",
                       str(rumpf.get("passwort") or ""), admin=True)
    antwort = JSONResponse({"ok": True, "name": k["name"]})
    _keks_setzen(antwort, request, konten.sitzung_anlegen(k["name"]))
    return antwort


@app.post("/api/sperre/zeit")
async def api_sperre_zeit(request: Request, rumpf: dict):
    _admin(request)
    minuten = int(reinigen.zahl(rumpf.get("minuten"), 15, 0, 24 * 60))
    konfig.aendern(sperre_minuten=minuten)
    return {"sperre_minuten": minuten}


@app.post("/api/sperre/aus")
def api_sperre_aus(request: Request, rumpf: dict):
    _nur_hier(request)
    k = _konto(request)
    liste = konten.konten()
    if len(liste) != 1 or not k["name"]:
        raise HTTPException(409, "Mit mehreren Konten wird die Anmeldung über die Kontenliste verwaltet")
    konten.pruefen(k["name"], str(rumpf.get("passwort") or ""), _gast(request))
    konten.loeschen(k["name"])
    antwort = JSONResponse({"ok": True})
    antwort.delete_cookie(KEKS, path="/")
    return antwort


# --- Konten und Projekte (Admin) -------------------------------------------------

@app.get("/api/konten")
async def api_konten(request: Request):
    _admin(request)
    buecher = [b["name"] for b in speicher.baum()]
    return {"konten": konten.konten(),
            "projekte": [{"notizbuch": b, "mitglieder": speicher.zugriff_lesen(b)} for b in buecher]}


@app.post("/api/konten")
def api_konto_neu(request: Request, rumpf: dict):
    _admin(request)
    return konten.anlegen(str(rumpf.get("name") or ""), str(rumpf.get("passwort") or ""),
                          bool(rumpf.get("admin")))


@app.post("/api/konten/loeschen")
async def api_konto_weg(request: Request, rumpf: dict):
    _admin(request)
    name = str(rumpf.get("name") or "")
    if name == _konto(request)["name"]:
        raise HTTPException(400, "Das eigene Konto kann man hier nicht löschen")
    konten.loeschen(name)
    return {"ok": True}


@app.post("/api/konten/passwort")
def api_konto_passwort(request: Request, rumpf: dict):
    _admin(request)
    konten.passwort_setzen(str(rumpf.get("name") or ""), str(rumpf.get("passwort") or ""))
    return {"ok": True}


@app.post("/api/konten/admin")
async def api_konto_admin(request: Request, rumpf: dict):
    _admin(request)
    konten.admin_setzen(str(rumpf.get("name") or ""), bool(rumpf.get("admin")))
    return {"ok": True}


@app.post("/api/zugriff")
async def api_zugriff(request: Request, rumpf: dict):
    _admin(request)
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    bekannt = {k["name"] for k in konten.konten()}
    mitglieder = [n for n in (rumpf.get("mitglieder") or []) if n in bekannt]
    return {"mitglieder": speicher.zugriff_setzen(buch, mitglieder)}


# --- Verbindungen zu Servern (Desktop-Fassung) -----------------------------------

@app.exception_handler(verbindungen.VerbindungsFehler)
async def _verbindungsfehler(request: Request, exc: verbindungen.VerbindungsFehler):
    return JSONResponse({"fehler": str(exc)}, status_code=400)


@app.get("/api/verbindungen")
async def api_verbindungen(request: Request):
    _nur_hier(request)
    return {"verbindungen": verbindungen.liste()}


@app.post("/api/verbindungen")
def api_verbinden(request: Request, rumpf: dict):
    _nur_hier(request)
    return verbindungen.verbinden(str(rumpf.get("adresse") or ""), str(rumpf.get("name") or "").strip(),
                                  str(rumpf.get("passwort") or ""))


@app.post("/api/verbindungen/entfernen")
async def api_verbindung_weg(request: Request, rumpf: dict):
    _nur_hier(request)
    verbindungen.entfernen(str(rumpf.get("id") or ""))
    return {"ok": True}


@app.post("/api/verbindungen/oeffnen")
async def api_verbindung_oeffnen(request: Request, rumpf: dict):
    """Eigenes Fenster fuer den Server. Ohne pywebview (z. B. im Browser geoeffnet)
    oeffnet die Oberflaeche die Adresse selbst in einem neuen Tab."""
    _nur_hier(request)
    v = verbindungen.finden(str(rumpf.get("id") or ""))
    weg = f"/verbinden/{v['id']}"
    import fenster
    if fenster.weiteres_fenster(f"http://127.0.0.1:{request.url.port or 8099}{weg}"):
        return {"fenster": True}
    return {"fenster": False, "weg": weg}


@app.get("/verbinden/{kennung}")
async def verbinden_seite(request: Request, kennung: str):
    """Schickt den Geraeteschluessel als Formular an den Server. Der setzt daraufhin
    seinen eigenen Sitzungskeks - im Fenster, nicht hier."""
    _nur_hier(request)
    v = verbindungen.finden(kennung)
    from html import escape
    return HTMLResponse(
        '<!doctype html><meta charset="utf-8"><title>Notizmappe</title>'
        '<link rel="stylesheet" href="/static/stil.css"><body class="anmeldeseite">'
        f'<form method="post" action="{escape(v["adresse"])}/geraet/anmelden" class="anmeldetafel">'
        f'<h1>Notizmappe</h1><p class="hinweis">Verbinde mit {escape(v["adresse"])} …</p>'
        f'<input type="hidden" name="token" value="{escape(v["token"])}">'
        '<noscript><button type="submit">Weiter</button></noscript></form>'
        '<script>document.forms[0].submit()</script></body>',
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


def _nur_hier(request: Request) -> None:
    """Update heisst: fremder Code wird heruntergeladen und ausgefuehrt; der Ordner-
    Dialog geht auf dem Rechner auf, auf dem der Server laeuft. Beides nur direkt an
    diesem Rechner - und nie im Server-Betrieb: hinter einem Proxy oder im Container
    sieht jede Anfrage aus, als kaeme sie von hier."""
    if konten.server_modus():
        raise HTTPException(403, "Im Server-Betrieb nicht verfügbar")
    if _gast(request) not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "Das geht nur direkt an diesem Rechner")
    _admin(request)


@app.get("/api/version")
async def api_version(frisch: bool = False):
    return aktualisieren.pruefen(frisch=frisch)


@app.post("/api/update")
async def api_update(request: Request):
    _nur_hier(request)
    try:
        return aktualisieren.einspielen()
    except RuntimeError as f:
        raise HTTPException(409, str(f))
    except Exception as f:
        raise HTTPException(502, f"Update fehlgeschlagen: {f}")


@app.get("/api/update/stand")
async def api_update_stand(request: Request):
    _nur_hier(request)
    return aktualisieren.protokoll()


@app.get("/api/einstellungen")
async def api_einstellungen(request: Request):
    """Was die Oberflaeche ueber die Installation wissen muss."""
    import shutil
    admin = _konto(request)["admin"]
    try:
        ordner = speicher.wurzel()
        fehlt = ""
    except speicher.SpeicherFehler as f:
        # Ordner nicht da: trotzdem antworten, sonst kommt man nicht einmal an die
        # Einstellung, mit der man ihn umstellt.
        ordner, fehlt = None, str(f)
    # Nur Seiten zaehlen (Notizbuch/Abschnitt/Seite.json), und nur in Notizbuechern,
    # die der Fragende sieht - nicht Papierkorb, Anhaenge oder .zugriff.json.
    gesamt = 0
    if ordner:
        for buch in speicher.baum():
            if _sieht(request, buch["name"]):
                gesamt += sum(len(a["seiten"]) for a in buch["abschnitte"])
    platz = shutil.disk_usage(ordner).free if ordner else 0
    korb = ordner / speicher.PAPIERKORB if ordner else None
    return {
        "version": VERSION,
        "ordner": (str(ordner) if ordner else speicher.gewaehlter_ordner()) if admin else "",
        "ordner_fehlt": fehlt,
        "ordner_quelle": speicher.ordner_quelle(),
        "ordner_waehlbar": bool(_ordnerdialog()),
        "seiten": gesamt,
        "frei": platz,
        "papierkorb": sum(1 for _ in korb.glob("*")) if korb and korb.is_dir() else 0,
        "aus_installation": aktualisieren.aus_installation(),
        "optionen": aktualisieren.optionen_lesen(),
        "hier": _gast(request) in {"127.0.0.1", "::1"} and not konten.server_modus() and admin,
        "quelle": aktualisieren.QUELLE,
    }


@app.post("/api/einstellungen")
async def api_einstellungen_setzen(request: Request, rumpf: dict):
    # Steuert, ob ungefragt fremder Code geholt und ausgefuehrt wird - also
    # dieselbe Schranke wie beim Update selbst.
    _nur_hier(request)
    try:
        return aktualisieren.optionen_schreiben(rumpf)
    except RuntimeError as f:
        raise HTTPException(500, str(f))


def _ordnerdialog() -> list[str] | None:
    """Der Ordner-Dialog des Systems, wenn es einen gibt. Er geht auf dem Rechner
    auf, auf dem der Server laeuft - deshalb nur zusammen mit _nur_hier."""
    import shutil
    if shutil.which("kdialog"):
        return ["kdialog", "--getexistingdirectory", str(Path.home()), "--title", "Ordner für die Notizen"]
    if shutil.which("zenity"):
        return ["zenity", "--file-selection", "--directory", "--title=Ordner für die Notizen"]
    return None


@app.post("/api/ordner/waehlen")
def api_ordner_waehlen(request: Request):
    _nur_hier(request)
    befehl = _ordnerdialog()
    if not befehl:
        raise HTTPException(404, "Kein Ordner-Dialog auf diesem System - bitte den Pfad eintippen")
    import subprocess
    try:
        lauf = subprocess.run(befehl, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as f:
        raise HTTPException(500, f"Ordner-Dialog ging nicht auf: {f}")
    gewaehlt = lauf.stdout.strip() if lauf.returncode == 0 else ""
    return {"ordner": gewaehlt or None}


@app.post("/api/ordner")
def api_ordner_setzen(request: Request, rumpf: dict):
    """Datenordner umstellen. Gilt sofort; die Oberflaeche laedt danach neu, damit
    keine offene Seite noch auf den alten Ordner zeigt."""
    _nur_hier(request)
    if speicher.ordner_quelle() == "umgebung":
        raise HTTPException(409, "Der Ordner ist über NOTIZEN_ORDNER fest vorgegeben")
    if rumpf.get("standard"):
        konfig.aendern(ordner=None)
        return {"ordner": str(speicher.wurzel()), "kopiert": 0}
    try:
        alt = speicher.wurzel()
    except speicher.SpeicherFehler:
        alt = None                      # alter Ordner nicht da - dann gibt es nichts mitzunehmen
    neu = speicher.ordner_pruefen(str(rumpf.get("ordner") or ""))
    kopiert = 0
    if rumpf.get("mitnehmen") and alt and neu != alt.resolve():
        kopiert = speicher.inhalt_kopieren(alt, neu)
    konfig.aendern(ordner=str(neu))
    return {"ordner": str(neu), "kopiert": kopiert}


@app.get("/api/baum")
async def api_baum(request: Request):
    sichtbar = [b for b in speicher.baum() if _sieht(request, b["name"])]
    return {"notizbuecher": sichtbar,
            "ordner": str(speicher.wurzel()) if _konto(request)["admin"] else ""}


@app.post("/api/notizbuch")
async def api_notizbuch(request: Request, rumpf: dict):
    name = reinigen.text(rumpf.get("name"), 80)
    if not name:
        raise HTTPException(400, "Name fehlt")
    neu = speicher.notizbuch_anlegen(name)
    k = _konto(request)
    if k["name"] and not k["admin"]:
        speicher.zugriff_setzen(neu, [k["name"]])    # wer es anlegt, ist drin
    return {"name": neu}


@app.post("/api/abschnitt")
async def api_abschnitt(request: Request, rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    name = reinigen.text(rumpf.get("name"), 80)
    if not buch or not name:
        raise HTTPException(400, "Notizbuch oder Name fehlt")
    _darf(request, buch)
    return {"name": speicher.abschnitt_anlegen(buch, name)}


@app.post("/api/seite")
async def api_seite_neu(request: Request, rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    absch = reinigen.text(rumpf.get("abschnitt"), 80)
    titel = reinigen.text(rumpf.get("titel"), 120) or "Neue Seite"
    if not buch or not absch:
        raise HTTPException(400, "Notizbuch oder Abschnitt fehlt")
    _darf(request, buch)
    return {"name": speicher.seite_anlegen(buch, absch, titel)}


@app.get("/api/seite")
async def api_seite_lesen(request: Request, notizbuch: str, abschnitt: str, name: str):
    _darf(request, notizbuch)
    return speicher.seite_lesen(notizbuch, abschnitt, name)


def _elemente(roh) -> list[dict]:
    """Nur bekannte Felder uebernehmen. Was der Browser sonst mitschickt, hat auf
    der Platte nichts zu suchen - spaetere Fassungen lesen die Datei wieder."""
    if not isinstance(roh, list):
        raise HTTPException(400, "elemente muss eine Liste sein")
    if len(roh) > MAX_ELEMENTE:
        raise HTTPException(400, f"Mehr als {MAX_ELEMENTE} Elemente auf einer Seite")
    aus = []
    for e in roh:
        if not isinstance(e, dict):
            continue
        art = e.get("typ")
        if art not in {"text", "bild", "datei"}:
            continue
        gemein = {
            "id": reinigen.text(e.get("id"), 40) or speicher.uuid.uuid4().hex[:12],
            "typ": art,
            "x": reinigen.zahl(e.get("x"), 40, 0),
            "y": reinigen.zahl(e.get("y"), 40, 0),
            "b": reinigen.zahl(e.get("b"), 420, 40, 4000),
        }
        if art == "text":
            gemein["html"] = reinigen.html(e.get("html") or "")
        else:
            # Der Dateiname kommt vom Browser zurueck. Beim Ablegen hat ihn slug()
            # schon geformt und genau so zurueckgegeben - kommt er veraendert
            # wieder, hat ihn nie diese Anwendung vergeben. Dann ist das Element
            # Muell (oder ein Versuch) und fliegt raus, statt als Leiche in der
            # Datei zu stehen und spaeter "Bild fehlt" anzuzeigen.
            roh = reinigen.text(e.get("datei"), 120)
            datei = speicher.slug(roh)
            if not datei or datei != roh or datei.startswith("."):
                continue
            gemein["datei"] = datei
            gemein["beschriftung"] = reinigen.text(e.get("beschriftung"), 200)
            if art == "datei":
                gemein["groesse"] = int(reinigen.zahl(e.get("groesse"), 0, 0, 10 ** 9))
        aus.append(gemein)
    return aus


@app.put("/api/seite")
async def api_seite_speichern(request: Request, rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    absch = reinigen.text(rumpf.get("abschnitt"), 80)
    name = reinigen.text(rumpf.get("name"), 120)
    if not (buch and absch and name):
        raise HTTPException(400, "Pfad unvollstaendig")
    _darf(request, buch)
    try:
        rev = int(rumpf.get("rev"))
    except (TypeError, ValueError):
        raise HTTPException(400, "rev fehlt")
    elemente = _elemente(rumpf.get("elemente"))
    ergebnis = speicher.seite_speichern(
        buch, absch, name, rev,
        reinigen.text(rumpf.get("titel"), 120),
        elemente,
        reinigen.text(rumpf.get("geraet"), 40),
    )
    # Erst nach dem erfolgreichen Schreiben: solange die Seite nicht auf der Platte
    # steht, zeigt sie noch auf die Dateien.
    ergebnis["aufgeraeumt"] = speicher.anhaenge_aufraeumen(buch, absch, name, elemente)
    return ergebnis


@app.post("/api/seite/titel")
async def api_seite_titel(request: Request, rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    absch = reinigen.text(rumpf.get("abschnitt"), 80)
    name = reinigen.text(rumpf.get("name"), 120)
    titel = reinigen.text(rumpf.get("titel"), 120)
    if not (buch and absch and name and titel):
        raise HTTPException(400, "Angaben unvollstaendig")
    _darf(request, buch)
    return {"name": speicher.seite_umbenennen(buch, absch, name, titel)}


@app.post("/api/anhang")
async def api_anhang_hoch(request: Request, notizbuch: str = Form(...), abschnitt: str = Form(...),
                          name: str = Form(...), datei: UploadFile = File(...)):
    buch = reinigen.text(notizbuch, 80)
    absch = reinigen.text(abschnitt, 80)
    seite = reinigen.text(name, 120)
    if not (buch and absch and seite):
        raise HTTPException(400, "Pfad unvollstaendig")
    _darf(request, buch)

    daten = await datei.read(speicher.MAX_ANHANG + 1)
    if len(daten) > speicher.MAX_ANHANG:
        raise HTTPException(413, f"Datei ist groesser als {speicher.MAX_ANHANG // 1024 // 1024} MB")
    if not daten:
        raise HTTPException(400, "Datei ist leer")

    abgelegt = speicher.anhang_ablegen(buch, absch, seite, datei.filename or "Datei", daten)
    typ = reinigen.bildtyp(daten)
    abgelegt["art"] = "bild" if typ else "datei"
    abgelegt["medientyp"] = typ or "application/octet-stream"
    return abgelegt


@app.get("/api/anhang")
async def api_anhang_runter(request: Request, notizbuch: str, abschnitt: str, name: str, datei: str):
    _darf(request, notizbuch)
    pfad = speicher.anhang_lesen(notizbuch, abschnitt, name, datei)
    kopf = pfad.read_bytes()[:16]
    typ = reinigen.bildtyp(kopf)
    # Alles, was kein erkanntes Bild ist, wird heruntergeladen statt angezeigt.
    # Sonst fuehrt eine hochgeladene HTML- oder SVG-Datei im Fenster eigenen Code
    # aus - mit Zugriff auf alles, was hier sonst noch offen ist.
    return FileResponse(
        pfad,
        media_type=typ or "application/octet-stream",
        filename=None if typ else pfad.name,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": (f'inline; filename="{pfad.name}"' if typ
                                    else f'attachment; filename="{pfad.name}"'),
            "Cache-Control": "no-cache",
        },
    )


@app.get("/api/stand")
async def api_stand(request: Request, notizbuch: str, abschnitt: str, name: str):
    _darf(request, notizbuch)
    return speicher.stand(notizbuch, abschnitt, name)


@app.post("/api/loeschen")
async def api_loeschen(request: Request, rumpf: dict):
    """Loescht Notizbuch, Abschnitt oder Seite - je nachdem, was in "art" steht.
    Die Art kommt vom Browser und wird nicht aus dem Pfad geraten, damit nicht ein
    Abschnitt namens "Seite" versehentlich als Datei behandelt wird."""
    art = reinigen.text(rumpf.get("art"), 20)
    teile = [reinigen.text(t, 120) for t in (rumpf.get("pfad") or []) if reinigen.text(t, 120)]
    erwartet = {"notizbuch": 1, "abschnitt": 2, "seite": 3}
    if art not in erwartet or len(teile) != erwartet[art]:
        raise HTTPException(400, "Art oder Pfad passt nicht")
    _darf(request, teile[0])
    if art == "notizbuch":
        _admin(request)          # ein ganzes Projekt wegwerfen nur als Admin
    if art == "seite":
        teile[-1] = speicher.slug(teile[-1]) + ".json"
    speicher.in_papierkorb(teile)
    return {"ok": True}


if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "8099")))
