"""OneNote-Dateien einlesen und als Notizbuch ablegen.

Eingelesen wird, nicht geöffnet: aus einer `.one`-Datei (ein Abschnitt) oder
einer `.onepkg` (ein ganzes Notizbuch, innen ein CAB-Archiv) entstehen hier
Notizbücher, Abschnitte und Seiten im eigenen Format. Zurück nach OneNote
schreibt das Programm nichts - das Format ist nirgends sauber beschrieben, und
ein halb geschriebenes Notizbuch wäre schlimmer als gar keins.

Gerettet wird der **Inhalt**, nicht das Aussehen: Text, Bilder, angehängte
Dateien. Die genaue Lage der Kästen auf der Seite, Tabellen, Freihand und Tags
gehen verloren. Passwortgeschützte Abschnitte lassen sich gar nicht lesen.

Das ist keine Nachlässigkeit, sondern die Grenze des frei verfügbaren Lesers:
pyOneNote ist für die Virenanalyse gebaut, nicht für originalgetreues Umwandeln.
Ein besserer Leser müsste für jedes Betriebssystem übersetzt mitgeliefert
werden - und das soll dieses Programm gerade nicht.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import reinigen
import speicher

# Die Kennung am Dateianfang. Kostet nichts und erspart eine unverstaendliche
# Meldung aus dem Leser, wenn jemand die falsche Datei erwischt.
KENNUNG_ONE = bytes.fromhex("e4525c7b8cd8a74daeb15378d02996d3")
KENNUNG_TOC = bytes.fromhex("a12fff43d9ef764c9ee210ea5722765f")

MAX_SEITEN = 500                    # je Abschnitt - gegen Ausreisser
MAX_TEXT = 100_000                  # Zeichen je Textblock
SEITE_BREIT = 560

# Die Namen aus dem Dateiformat. "jcid" ist OneNotes Art, einen Knotentyp zu
# benennen; die Eigenschaft mit dem lesbaren Text heisst RichEditTextUnicode.
SEITENANFANG = ("jcidPageManifestNode", "jcidPageNode")
TEXTFELD = "RichEditTextUnicode"
TITELFELD = "CachedTitleString"


class EinfuhrFehler(Exception):
    """Falsche Datei, kaputte Datei, kein Leser da."""


def _leser():
    try:
        # Ja, ohne "u": die Klasse heisst in der Bibliothek wirklich so.
        from pyOneNote.OneDocument import OneDocment
    except ImportError:
        raise EinfuhrFehler("Zum Einlesen von OneNote fehlt das Paket pyOneNote")
    return OneDocment


def art_von(pfad: Path) -> str:
    """one, onetoc2, onepkg - oder nichts davon."""
    if pfad.suffix.lower() == ".onepkg":
        return "onepkg"
    try:
        with pfad.open("rb") as f:
            kopf = f.read(16)
    except OSError as f_:
        raise EinfuhrFehler(f"Datei nicht lesbar: {f_}")
    if kopf == KENNUNG_ONE:
        return "one"
    if kopf == KENNUNG_TOC:
        return "onetoc2"
    return "unbekannt"


def _text(roh) -> str:
    """Aus einem Textfeld eine Zeile machen, die sich anzeigen laesst."""
    if isinstance(roh, bytes):
        roh = roh.decode("utf-16-le", "replace")
    text = str(roh)
    # OneNote trennt Absaetze mit Wagenruecklauf und streut Steuerzeichen ein.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text[:MAX_TEXT].strip()


def _durchsuchen(wert, feld: str) -> list[str]:
    """Alle Werte zu einem Feldnamen einsammeln, egal wie tief sie liegen."""
    aus = []
    if isinstance(wert, dict):
        for k, v in wert.items():
            if feld in str(k) and isinstance(v, (str, bytes)):
                aus.append(_text(v))
            else:
                aus.extend(_durchsuchen(v, feld))
    elif isinstance(wert, list):
        for v in wert:
            aus.extend(_durchsuchen(v, feld))
    return aus


def abschnitt_lesen(pfad: Path) -> dict:
    """Eine .one-Datei zu Seiten machen.

    Die Eigenschaften kommen als flache Liste in der Reihenfolge, in der sie in
    der Datei stehen. Ein neuer Seitenknoten beginnt eine neue Seite, alles
    danach gehoert dazu. Das ist naeherungsweise - die Baumstruktur ueber die
    Verweise nachzubilden waere genauer, faellt aber bei der kleinsten
    Abweichung im Format auf die Nase. Lieber eine Seite zu viel als
    verschluckter Text.
    """
    art = art_von(pfad)
    if art == "onetoc2":
        raise EinfuhrFehler("Das ist nur das Inhaltsverzeichnis eines Notizbuchs - "
                            "die Seiten stehen in den .one-Dateien daneben")
    if art != "one":
        raise EinfuhrFehler("Das ist keine OneNote-Datei (die Kennung am Anfang fehlt)")

    OneDocment = _leser()
    with pfad.open("rb") as f:
        try:
            dok = OneDocment(f)
            eigenschaften = dok.get_properties() or []
            dateien = dok.get_files() or {}
        except EinfuhrFehler:
            raise
        except Exception as f_:                     # noqa: BLE001 - fremder Leser
            raise EinfuhrFehler(f"Der Leser kommt mit der Datei nicht zurecht "
                                f"({type(f_).__name__}: {f_})")

    seiten: list[dict] = []
    offen: dict | None = None
    for eintrag in eigenschaften:
        if not isinstance(eintrag, dict):
            continue
        typ = str(eintrag.get("type", ""))
        werte = eintrag.get("val")

        if any(a in typ for a in SEITENANFANG):
            if offen and (offen["texte"] or offen["titel"]):
                seiten.append(offen)
            offen = {"titel": "", "texte": []}
            if len(seiten) >= MAX_SEITEN:
                break

        if offen is None:
            offen = {"titel": "", "texte": []}

        for titel in _durchsuchen(werte, TITELFELD):
            if titel and not offen["titel"]:
                offen["titel"] = titel.splitlines()[0][:120]
        for text in _durchsuchen(werte, TEXTFELD):
            if text:
                offen["texte"].append(text)

    if offen and (offen["texte"] or offen["titel"]):
        seiten.append(offen)

    anhaenge = []
    for guid, datei in (dateien or {}).items():
        if not isinstance(datei, dict):
            continue
        inhalt = datei.get("content") or b""
        if isinstance(inhalt, str):
            try:
                inhalt = bytes.fromhex(inhalt)
            except ValueError:
                continue
        if not inhalt:
            continue
        endung = (datei.get("extension") or "").strip()
        if endung and not endung.startswith("."):
            endung = "." + endung
        anhaenge.append({"name": f"{str(guid)[:8]}{endung or '.bin'}", "inhalt": inhalt})

    return {"name": pfad.stem, "seiten": seiten, "anhaenge": anhaenge}


def paket_lesen(pfad: Path) -> list[dict]:
    """.onepkg ist ein CAB-Archiv mit den Abschnitten darin."""
    try:
        import cabarchive
    except ImportError:
        raise EinfuhrFehler("Zum Auspacken von .onepkg fehlt das Paket cabarchive")
    try:
        archiv = cabarchive.CabArchive(pfad.read_bytes())
    except Exception as f_:                         # noqa: BLE001
        raise EinfuhrFehler(f"Das Paket liess sich nicht auspacken ({f_})")

    ordner = Path(tempfile.mkdtemp(prefix="onepkg-"))
    aus = []
    for name, eintrag in archiv.items():
        if not str(name).lower().endswith(".one"):
            continue                                # .onetoc2 und Beiwerk
        ziel = ordner / Path(str(name)).name
        ziel.write_bytes(eintrag.buf)
        try:
            aus.append(abschnitt_lesen(ziel))
        except EinfuhrFehler as f_:
            # Ein Abschnitt, der klemmt, darf nicht das ganze Notizbuch kosten.
            aus.append({"name": ziel.stem, "seiten": [], "anhaenge": [],
                        "fehler": str(f_)})
    if not aus:
        raise EinfuhrFehler("In dem Paket steckt kein Abschnitt (.one)")
    return aus


def lesen(pfad: Path) -> list[dict]:
    """Eine Datei einlesen - einzeln oder als Paket."""
    if art_von(pfad) == "onepkg":
        return paket_lesen(pfad)
    return [abschnitt_lesen(pfad)]


# --- Ablegen -----------------------------------------------------------------

def seitentitel(seite: dict, nr: int) -> str:
    """Seiten ohne Titel bekommen ihre erste Zeile.

    Steht das beim Lesen statt hier, hilft es nur dem einen Weg dorthin -
    "Seite" dreissigmal untereinander hilft beim Wiederfinden gar nicht.
    """
    titel = (seite.get("titel") or "").strip()
    if titel:
        return titel[:120]
    texte = seite.get("texte") or []
    erste = texte[0].splitlines()[0].strip() if texte else ""
    return erste[:80] or f"Seite {nr}"


def _elemente(texte: list[str]) -> list[dict]:
    """Textbloecke untereinander auf die Seite legen.

    Die Lage aus OneNote koennen wir nicht uebernehmen, also werden die Bloecke
    gestapelt - mit Abstand nach der geschaetzten Hoehe, damit sie sich nicht
    ueberdecken.
    """
    aus = []
    y = 40
    for text in texte:
        zeilen = sum(max(1, len(z) // 70 + 1) for z in text.split("\n")) or 1
        html = reinigen.html("<br>".join(zeile.strip() for zeile in text.split("\n")))
        aus.append({"id": speicher.uuid.uuid4().hex[:12], "typ": "text",
                    "x": 40, "y": y, "b": SEITE_BREIT, "html": html})
        y += max(60, zeilen * 22 + 30)
    return aus


def anlegen(buchname: str, abschnitte: list[dict]) -> dict:
    """Aus dem Gelesenen ein Notizbuch bauen. Legt immer ein **neues** an.

    Nichts wird ueberschrieben: ein Einlesen, das vorhandene Notizen anfasst,
    waere im Zweifel nicht rueckgaengig zu machen.
    """
    buch = speicher.notizbuch_anlegen(buchname or "OneNote")
    bericht = {"notizbuch": buch, "abschnitte": 0, "seiten": 0, "anhaenge": 0,
               "uebersprungen": []}

    for abschnitt in abschnitte:
        name = speicher.abschnitt_anlegen(buch, abschnitt.get("name") or "Abschnitt")
        bericht["abschnitte"] += 1
        if abschnitt.get("fehler"):
            bericht["uebersprungen"].append(f"{abschnitt.get('name')}: {abschnitt['fehler']}")

        for nr, seite in enumerate(abschnitt.get("seiten", []), 1):
            titel = seitentitel(seite, nr)
            seitenname = speicher.seite_anlegen(buch, name, titel)
            vorher = speicher.seite_lesen(buch, name, seitenname)
            speicher.seite_speichern(buch, name, seitenname, vorher["rev"], titel,
                                     _elemente(seite.get("texte") or []), "OneNote")
            bericht["seiten"] += 1

        anhaenge = abschnitt.get("anhaenge") or []
        if anhaenge:
            # Welcher Anhang zu welcher Seite gehoert, gibt das Format nicht
            # verlaesslich her. Lieber alle auf einer eigenen Seite sammeln, als
            # sie wegzuwerfen oder wahllos zu verteilen.
            titel = "Dateien aus OneNote"
            sammelseite = speicher.seite_anlegen(buch, name, titel)
            elemente = []
            y = 40
            for anhang in anhaenge:
                try:
                    abgelegt = speicher.anhang_ablegen(buch, name, sammelseite,
                                                       anhang["name"], anhang["inhalt"])
                except speicher.SpeicherFehler:
                    continue
                typ = reinigen.bildtyp(anhang["inhalt"])
                elemente.append({"id": speicher.uuid.uuid4().hex[:12],
                                 "typ": "bild" if typ else "datei",
                                 "x": 40, "y": y, "b": 320,
                                 "datei": abgelegt["datei"], "beschriftung": "",
                                 **({} if typ else {"groesse": len(anhang["inhalt"])})})
                y += 260 if typ else 70
                bericht["anhaenge"] += 1
            vorher = speicher.seite_lesen(buch, name, sammelseite)
            speicher.seite_speichern(buch, name, sammelseite, vorher["rev"], titel,
                                     elemente, "OneNote")
            bericht["seiten"] += 1

    return bericht


def einlesen(pfad: Path, buchname: str = "") -> dict:
    gelesen = lesen(pfad)
    name = buchname or pfad.stem or "OneNote"
    bericht = anlegen(name, gelesen)
    bericht["quelle"] = pfad.name
    return bericht
