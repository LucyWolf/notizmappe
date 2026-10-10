"""Notizmappe - freie Notizflaeche, die auf Dateien in einem Sync-Ordner liegt.

Ein Prozess: FastAPI liefert die Oberflaeche und die API, das Fenster steht in
fenster.py. Ein Desktop-Programm - keine Konten, keine Anmeldung, nichts im Netz.
Es hoert ausschliesslich auf 127.0.0.1, und das nur, weil die Oberflaeche HTML
ist und eine Webansicht sie ueber HTTP laden muss.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import aktualisieren
import konfig
import reinigen
import speicher

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


def _host_ok(host: str) -> bool:
    """Auf dem eigenen Rechner nur IP-Adressen und localhost als Host. Sonst kann
    eine fremde Webseite ihren Namen auf 127.0.0.1 umbiegen (DNS-Rebinding) und
    gilt dann als "gleiche Herkunft" - ohne Sperre heisst das: alle Notizen lesen
    und schreiben. Ein Rebinding braucht immer einen Namen, eine IP nie."""
    import ipaddress
    name = (host or "").rsplit(":", 1)[0] if not (host or "").endswith("]") else host
    name = name.strip("[]").lower()
    if name == "localhost":
        return True
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


@app.middleware("http")
async def _waechter(request: Request, call_next):
    pfad = request.url.path
    if not _host_ok(request.headers.get("host", "")):
        return JSONResponse({"fehler": "Unbekannter Host - die Notizmappe antwortet hier nur auf "
                                       "127.0.0.1 und localhost"}, status_code=421)
    # Fremde Seiten duerfen nichts aendern: der Browser schickt bei solchen
    # Anfragen seine Herkunft mit. Zusammen mit SameSite=Strict am Keks reicht das
    # gegen untergeschobene Formulare. "null" (Sandbox-iframe, file://) ist fremd.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        herkunft = request.headers.get("origin")
        erlaubt = {request.headers.get("host"), request.headers.get("x-forwarded-host")}
        if herkunft and (herkunft == "null" or urlparse(herkunft).netloc not in erlaubt):
            return JSONResponse({"fehler": "Anfrage von fremder Seite abgelehnt"}, status_code=403)
    return await call_next(request)


@app.get("/")
async def start(request: Request):
    return vorlagen.TemplateResponse(request, "index.html", {
        "version": VERSION,
        "ordner": str(speicher.wurzel()),
    })


def _von_hier(request: Request) -> bool:
    return (request.client.host if request.client else "") in {"127.0.0.1", "::1", "localhost"}


def _nur_hier(request: Request) -> None:
    """Update heisst: fremder Code wird heruntergeladen und ausgefuehrt; der
    Ordner-Dialog geht auf dem Bildschirm dieses Rechners auf. Beides nur direkt
    hier. Das Programm hoert zwar ohnehin nur auf 127.0.0.1 - aber die Schranke
    steht da, wo sie hingehoert, und nicht nur in der Startzeile."""
    if not _von_hier(request):
        raise HTTPException(403, "Das geht nur direkt an diesem Rechner")


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
    try:
        ordner = speicher.wurzel()
        fehlt = ""
    except speicher.SpeicherFehler as f:
        # Ordner nicht da: trotzdem antworten, sonst kommt man nicht einmal an die
        # Einstellung, mit der man ihn umstellt.
        ordner, fehlt = None, str(f)
    # Nur Seiten zaehlen (Notizbuch/Abschnitt/Seite.json), und nur in Notizbuechern,
    # nicht Papierkorb oder Anhaenge mitzaehlen.
    gesamt = 0
    if ordner:
        for buch in speicher.baum():
            gesamt += sum(len(a["seiten"]) for a in buch["abschnitte"])
    platz = shutil.disk_usage(ordner).free if ordner else 0
    korb = ordner / speicher.PAPIERKORB if ordner else None
    return {
        "version": VERSION,
        "ordner": str(ordner) if ordner else speicher.gewaehlter_ordner(),
        "ordner_fehlt": fehlt,
        "ordner_quelle": speicher.ordner_quelle(),
        "ordner_waehlbar": bool(_ordnerdialog()),
        "seiten": gesamt,
        "frei": platz,
        "papierkorb": sum(1 for _ in korb.glob("*")) if korb and korb.is_dir() else 0,
        "aus_installation": aktualisieren.aus_installation(),
        "optionen": aktualisieren.optionen_lesen(),
        "hier": _von_hier(request),
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
    auf, auf dem die Notizmappe laeuft - deshalb nur zusammen mit _nur_hier."""
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
    sichtbar = speicher.baum()
    return {"notizbuecher": sichtbar,
            "ordner": str(speicher.wurzel())}


@app.post("/api/notizbuch")
async def api_notizbuch(request: Request, rumpf: dict):
    name = reinigen.text(rumpf.get("name"), 80)
    if not name:
        raise HTTPException(400, "Name fehlt")
    return {"name": speicher.notizbuch_anlegen(name)}


@app.post("/api/abschnitt")
async def api_abschnitt(request: Request, rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    name = reinigen.text(rumpf.get("name"), 80)
    if not buch or not name:
        raise HTTPException(400, "Notizbuch oder Name fehlt")
    return {"name": speicher.abschnitt_anlegen(buch, name)}


@app.post("/api/seite")
async def api_seite_neu(request: Request, rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    absch = reinigen.text(rumpf.get("abschnitt"), 80)
    titel = reinigen.text(rumpf.get("titel"), 120) or "Neue Seite"
    if not buch or not absch:
        raise HTTPException(400, "Notizbuch oder Abschnitt fehlt")
    return {"name": speicher.seite_anlegen(buch, absch, titel)}


@app.get("/api/seite")
async def api_seite_lesen(request: Request, notizbuch: str, abschnitt: str, name: str):
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
    return {"name": speicher.seite_umbenennen(buch, absch, name, titel)}


@app.post("/api/anhang")
async def api_anhang_hoch(request: Request, notizbuch: str = Form(...), abschnitt: str = Form(...),
                          name: str = Form(...), datei: UploadFile = File(...)):
    buch = reinigen.text(notizbuch, 80)
    absch = reinigen.text(abschnitt, 80)
    seite = reinigen.text(name, 120)
    if not (buch and absch and seite):
        raise HTTPException(400, "Pfad unvollstaendig")

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
    pfad = speicher.anhang_lesen(notizbuch, abschnitt, name, datei)
    kopf = pfad.read_bytes()[:16]
    typ = reinigen.bildtyp(kopf)
    # Alles, was kein erkanntes Bild ist, wird heruntergeladen statt angezeigt.
    # Sonst fuehrt eine hochgeladene HTML- oder SVG-Datei im Fenster eigenen Code
    # aus - mit Zugriff auf alles, was hier sonst noch offen ist.
    return FileResponse(
        pfad,
        media_type=typ or "application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": _dateiname_kopf("inline" if typ else "attachment", pfad.name),
            "Cache-Control": "no-cache",
        },
    )


def _dateiname_kopf(art: str, name: str) -> str:
    """Content-Disposition mit Umlauten, Emoji usw. Header sind Latin-1 - ein
    "Plan → 2026.pdf" roh hineingeschrieben gab einen Fehler. Deshalb nach
    RFC 5987: ASCII-Ersatz fuer alte Programme, dazu filename* in UTF-8."""
    from urllib.parse import quote
    ersatz = "".join(z if 32 <= ord(z) < 127 and z not in '"\\' else "_" for z in name) or "Datei"
    return f"{art}; filename=\"{ersatz}\"; filename*=UTF-8''{quote(name, safe='')}"


@app.get("/api/stand")
async def api_stand(request: Request, notizbuch: str, abschnitt: str, name: str):
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
    if art == "seite":
        teile[-1] = speicher.slug(teile[-1]) + ".json"
    speicher.in_papierkorb(teile)
    return {"ok": True}


if __name__ == "__main__":
    import os
    import uvicorn
    # Fest auf dem eigenen Rechner. Keine Variable, mit der sich das aufmachen
    # liesse: ein Desktop-Programm hat im Netz nichts zu suchen, und sobald etwas
    # auf 0.0.0.0 lauscht, fragt Windows nach einer Firewall-Freigabe.
    uvicorn.run(app, host="127.0.0.1",
                port=int(os.environ.get("PORT", "8099")))
