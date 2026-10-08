"""Notizmappe - freie Notizflaeche, die auf Dateien in einem Sync-Ordner liegt.

Ein Prozess: FastAPI liefert die Oberflaeche und die API. Keine Anmeldung in
Stufe 1 - haengt hinter Reverse-Proxy oder im eigenen Netz. Soll es ins Internet,
kommt davor ein Passwort (siehe README).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
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


@app.get("/api/einstellungen")
async def api_einstellungen(request: Request):
    """Was die Oberflaeche ueber die Installation wissen muss."""
    import shutil
    ordner = speicher.wurzel()
    gesamt = sum(1 for _ in ordner.rglob("*.json"))
    platz = shutil.disk_usage(ordner)
    return {
        "version": VERSION,
        "ordner": str(ordner),
        "seiten": gesamt,
        "frei": platz.free,
        "papierkorb": sum(1 for _ in (ordner / speicher.PAPIERKORB).glob("*")) if (ordner / speicher.PAPIERKORB).is_dir() else 0,
        "aus_installation": aktualisieren.aus_installation(),
        "hier": (request.client.host if request.client else "") in {"127.0.0.1", "::1"},
        "quelle": aktualisieren.QUELLE,
    }


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
async def api_seite_titel(rumpf: dict):
    buch = reinigen.text(rumpf.get("notizbuch"), 80)
    absch = reinigen.text(rumpf.get("abschnitt"), 80)
    name = reinigen.text(rumpf.get("name"), 120)
    titel = reinigen.text(rumpf.get("titel"), 120)
    if not (buch and absch and name and titel):
        raise HTTPException(400, "Angaben unvollstaendig")
    return {"name": speicher.seite_umbenennen(buch, absch, name, titel)}


@app.post("/api/anhang")
async def api_anhang_hoch(notizbuch: str = Form(...), abschnitt: str = Form(...),
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
async def api_anhang_runter(notizbuch: str, abschnitt: str, name: str, datei: str):
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
