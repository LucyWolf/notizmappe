"""Notizmappe - freie Notizflaeche, die auf Dateien in einem Sync-Ordner liegt.

Ein Prozess: FastAPI liefert die Oberflaeche und die API. Keine Anmeldung in
Stufe 1 - haengt hinter Reverse-Proxy oder im eigenen Netz. Soll es ins Internet,
kommt davor ein Passwort (siehe README).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import aktualisieren
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


@app.get("/")
async def start(request: Request):
    return vorlagen.TemplateResponse(request, "index.html", {
        "version": VERSION,
        "ordner": str(speicher.wurzel()),
    })


def _nur_hier(request: Request) -> None:
    """Update heisst: fremder Code wird heruntergeladen und ausgefuehrt. Solange es
    keine Anmeldung gibt, darf das nur von diesem Rechner aus angestossen werden -
    sonst genuegt ein Besuch im selben Netz, um Code einzuspielen."""
    gast = request.client.host if request.client else ""
    if gast not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "Aktualisieren geht nur direkt an diesem Rechner")


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


@app.get("/api/baum")
async def api_baum():
    return {"notizbuecher": speicher.baum(), "ordner": str(speicher.wurzel())}


@app.post("/api/notizbuch")
async def api_notizbuch(rumpf: dict):
    name = reinigen.text(rumpf.get("name"), 80)
    if not name:
        raise HTTPException(400, "Name fehlt")
    return {"name": speicher.notizbuch_anlegen(name)}


@app.post("/api/abschnitt")
async def api_abschnitt(rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    name = reinigen.text(rumpf.get("name"), 80)
    if not buch or not name:
        raise HTTPException(400, "Notizbuch oder Name fehlt")
    return {"name": speicher.abschnitt_anlegen(buch, name)}


@app.post("/api/seite")
async def api_seite_neu(rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    absch = reinigen.text(rumpf.get("abschnitt"), 80)
    titel = reinigen.text(rumpf.get("titel"), 120) or "Neue Seite"
    if not buch or not absch:
        raise HTTPException(400, "Notizbuch oder Abschnitt fehlt")
    return {"name": speicher.seite_anlegen(buch, absch, titel)}


@app.get("/api/seite")
async def api_seite_lesen(notizbuch: str, abschnitt: str, name: str):
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
        if not isinstance(e, dict) or e.get("typ") != "text":
            continue
        aus.append({
            "id": reinigen.text(e.get("id"), 40) or speicher.uuid.uuid4().hex[:12],
            "typ": "text",
            "x": reinigen.zahl(e.get("x"), 40, 0),
            "y": reinigen.zahl(e.get("y"), 40, 0),
            "b": reinigen.zahl(e.get("b"), 420, 80, 4000),
            "html": reinigen.html(e.get("html") or ""),
        })
    return aus


@app.put("/api/seite")
async def api_seite_speichern(rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    absch = reinigen.text(rumpf.get("abschnitt"), 80)
    name = reinigen.text(rumpf.get("name"), 120)
    if not (buch and absch and name):
        raise HTTPException(400, "Pfad unvollstaendig")
    try:
        rev = int(rumpf.get("rev"))
    except (TypeError, ValueError):
        raise HTTPException(400, "rev fehlt")
    return speicher.seite_speichern(
        buch, absch, name, rev,
        reinigen.text(rumpf.get("titel"), 120),
        _elemente(rumpf.get("elemente")),
        reinigen.text(rumpf.get("geraet"), 40),
    )


@app.post("/api/seite/titel")
async def api_seite_titel(rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    absch = reinigen.text(rumpf.get("abschnitt"), 80)
    name = reinigen.text(rumpf.get("name"), 120)
    titel = reinigen.text(rumpf.get("titel"), 120)
    if not (buch and absch and name and titel):
        raise HTTPException(400, "Angaben unvollstaendig")
    return {"name": speicher.seite_umbenennen(buch, absch, name, titel)}


@app.get("/api/stand")
async def api_stand(notizbuch: str, abschnitt: str, name: str):
    return speicher.stand(notizbuch, abschnitt, name)


@app.post("/api/loeschen")
async def api_loeschen(rumpf: dict):
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
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "8099")))
