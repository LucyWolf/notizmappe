"""Die Verbindung zwischen Fenster und Programm - ohne Netz.

Die Oberflaeche ist HTML und laeuft in der Webansicht des Systems. Frueher lag
dazwischen ein kleiner Webserver auf 127.0.0.1: die Seite holte ihre Daten per
HTTP. Das hiess, dass ein Desktop-Programm einen Port offen hielt, den jedes
andere Programm auf dem Rechner htte ansprechen koennen.

Jetzt ruft die Seite diese Methoden direkt auf (window.pywebview.api.xyz). Kein
Port, keine Adresse, kein HTTP - nur ein Funktionsaufruf in denselben Prozess.

Alle Methoden geben ein Woerterbuch zurueck. Geht etwas schief, steht darin
"fehler" (und bei einem Schreibkonflikt zusaetzlich "art": "konflikt" mit der
Fassung, die auf der Platte liegt). Ausnahmen fliegen nicht durch die Bruecke:
auf der anderen Seite kaeme nur eine unverstaendliche Zeichenkette an.
"""
from __future__ import annotations

import base64
import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path

import aktualisieren
import konfig
import reinigen
import speicher

HIER = Path(__file__).resolve().parent
VERSION = (HIER / "VERSION").read_text(encoding="utf-8").strip()
MAX_ELEMENTE = 500


class Abbruch(Exception):
    """Etwas, das der Benutzer wissen muss - kein Programmfehler."""

    def __init__(self, text: str, **mehr):
        super().__init__(text)
        self.mehr = mehr


def _gefasst(f):
    """Fehler als Antwort, nicht als Ausnahme."""
    @functools.wraps(f)
    def innen(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Abbruch as x:
            return {"fehler": str(x), **x.mehr}
        except speicher.KonfliktFehler as x:
            return {"fehler": str(x), "art": "konflikt", "aktuell": x.seite}
        except speicher.SpeicherFehler as x:
            return {"fehler": str(x)}
        except Exception as x:                      # noqa: BLE001 - nichts soll durchfallen
            import traceback
            traceback.print_exc()
            return {"fehler": f"{type(x).__name__}: {x}"}
    return innen


def _elemente(roh) -> list[dict]:
    """Nur bekannte Felder uebernehmen. Was die Oberflaeche sonst mitschickt, hat
    auf der Platte nichts zu suchen - spaetere Fassungen lesen die Datei wieder."""
    if not isinstance(roh, list):
        raise Abbruch("elemente muss eine Liste sein")
    if len(roh) > MAX_ELEMENTE:
        raise Abbruch(f"Mehr als {MAX_ELEMENTE} Elemente auf einer Seite")
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
            # Der Dateiname kommt von der Oberflaeche zurueck. Beim Ablegen hat ihn
            # slug() schon geformt und genau so zurueckgegeben - kommt er veraendert
            # wieder, hat ihn nie dieses Programm vergeben. Dann ist das Element
            # Muell (oder ein Versuch) und fliegt raus, statt als Leiche in der
            # Datei zu stehen und spaeter "Bild fehlt" anzuzeigen.
            roh_name = reinigen.text(e.get("datei"), 120)
            datei = speicher.slug(roh_name)
            if not datei or datei != roh_name or datei.startswith("."):
                continue
            gemein["datei"] = datei
            gemein["beschriftung"] = reinigen.text(e.get("beschriftung"), 200)
            if art == "datei":
                gemein["groesse"] = int(reinigen.zahl(e.get("groesse"), 0, 0, 10 ** 9))
        aus.append(gemein)
    return aus


class Bruecke:
    """Was die Oberflaeche aufrufen darf. Das Fenster haengt daran."""

    def __init__(self):
        self.fenster = None            # setzt fenster.py, fuer die Datei-Dialoge

    # --- Notizbuecher, Abschnitte, Seiten ---------------------------------

    @_gefasst
    def baum(self) -> dict:
        return {"notizbuecher": speicher.baum(), "ordner": str(speicher.wurzel())}

    @_gefasst
    def notizbuch_anlegen(self, name: str) -> dict:
        name = reinigen.text(name, 80)
        if not name:
            raise Abbruch("Name fehlt")
        return {"name": speicher.notizbuch_anlegen(name)}

    @_gefasst
    def abschnitt_anlegen(self, notizbuch: str, name: str) -> dict:
        buch = reinigen.text(notizbuch, 80)
        name = reinigen.text(name, 80)
        if not buch or not name:
            raise Abbruch("Notizbuch oder Name fehlt")
        return {"name": speicher.abschnitt_anlegen(buch, name)}

    @_gefasst
    def seite_anlegen(self, notizbuch: str, abschnitt: str, titel: str = "") -> dict:
        buch = reinigen.text(notizbuch, 80)
        absch = reinigen.text(abschnitt, 80)
        titel = reinigen.text(titel, 120) or "Neue Seite"
        if not buch or not absch:
            raise Abbruch("Notizbuch oder Abschnitt fehlt")
        return {"name": speicher.seite_anlegen(buch, absch, titel)}

    @_gefasst
    def seite_lesen(self, notizbuch: str, abschnitt: str, name: str) -> dict:
        return speicher.seite_lesen(notizbuch, abschnitt, name)

    @_gefasst
    def seite_speichern(self, rumpf: dict) -> dict:
        buch = reinigen.text(rumpf.get("notizbuch"), 80)
        absch = reinigen.text(rumpf.get("abschnitt"), 80)
        name = reinigen.text(rumpf.get("name"), 120)
        if not (buch and absch and name):
            raise Abbruch("Pfad unvollstaendig")
        try:
            rev = int(rumpf.get("rev"))
        except (TypeError, ValueError):
            raise Abbruch("rev fehlt")
        elemente = _elemente(rumpf.get("elemente"))
        ergebnis = speicher.seite_speichern(
            buch, absch, name, rev,
            reinigen.text(rumpf.get("titel"), 120),
            elemente,
            reinigen.text(rumpf.get("geraet"), 40),
        )
        # Erst nach dem erfolgreichen Schreiben: solange die Seite nicht auf der
        # Platte steht, zeigt sie noch auf die Dateien.
        ergebnis["aufgeraeumt"] = speicher.anhaenge_aufraeumen(buch, absch, name, elemente)
        return ergebnis

    @_gefasst
    def seite_umbenennen(self, notizbuch: str, abschnitt: str, name: str, titel: str) -> dict:
        buch = reinigen.text(notizbuch, 80)
        absch = reinigen.text(abschnitt, 80)
        name = reinigen.text(name, 120)
        titel = reinigen.text(titel, 120)
        if not (buch and absch and name and titel):
            raise Abbruch("Angaben unvollstaendig")
        return {"name": speicher.seite_umbenennen(buch, absch, name, titel)}

    @_gefasst
    def stand(self, notizbuch: str, abschnitt: str, name: str) -> dict:
        return speicher.stand(notizbuch, abschnitt, name)

    @_gefasst
    def loeschen(self, art: str, pfad: list) -> dict:
        """Loescht Notizbuch, Abschnitt oder Seite - je nachdem, was in "art" steht.
        Die Art kommt von der Oberflaeche und wird nicht aus dem Pfad geraten, damit
        nicht ein Abschnitt namens "Seite" versehentlich als Datei behandelt wird."""
        art = reinigen.text(art, 20)
        teile = [reinigen.text(t, 120) for t in (pfad or []) if reinigen.text(t, 120)]
        erwartet = {"notizbuch": 1, "abschnitt": 2, "seite": 3}
        if art not in erwartet or len(teile) != erwartet[art]:
            raise Abbruch("Art oder Pfad passt nicht")
        if art == "seite":
            teile[-1] = speicher.slug(teile[-1]) + ".json"
        speicher.in_papierkorb(teile)
        return {"ok": True}

    # --- Anhaenge ---------------------------------------------------------

    @_gefasst
    def anhang_ablegen(self, notizbuch: str, abschnitt: str, name: str,
                       dateiname: str, daten_b64: str) -> dict:
        buch = reinigen.text(notizbuch, 80)
        absch = reinigen.text(abschnitt, 80)
        seite = reinigen.text(name, 120)
        if not (buch and absch and seite):
            raise Abbruch("Pfad unvollstaendig")
        try:
            daten = base64.b64decode(daten_b64 or "", validate=True)
        except Exception:
            raise Abbruch("Die Datei kam beschädigt an")
        if len(daten) > speicher.MAX_ANHANG:
            raise Abbruch(f"Datei ist größer als {speicher.MAX_ANHANG // 1024 // 1024} MB")
        if not daten:
            raise Abbruch("Datei ist leer")

        abgelegt = speicher.anhang_ablegen(buch, absch, seite, dateiname or "Datei", daten)
        typ = reinigen.bildtyp(daten)
        abgelegt["art"] = "bild" if typ else "datei"
        abgelegt["medientyp"] = typ or "application/octet-stream"
        return abgelegt

    @_gefasst
    def anhang_bild(self, notizbuch: str, abschnitt: str, name: str, datei: str) -> dict:
        """Bilddaten fuer die Anzeige. Als data:-Adresse, nicht als Dateipfad: eine
        Seite, die beliebige lokale Dateien laden darf, kann auch solche laden, die
        sie nichts angehen."""
        pfad = speicher.anhang_lesen(notizbuch, abschnitt, name, datei)
        daten = pfad.read_bytes()
        typ = reinigen.bildtyp(daten)
        if not typ:
            # Kein erkanntes Bild: nicht anzeigen. Sonst fuehrt eine hochgeladene
            # SVG- oder HTML-Datei im Fenster eigenen Code aus.
            raise Abbruch("Das ist kein Bild")
        return {"medientyp": typ, "daten": base64.b64encode(daten).decode("ascii")}

    @_gefasst
    def anhang_oeffnen(self, notizbuch: str, abschnitt: str, name: str, datei: str) -> dict:
        """Mit dem Programm oeffnen, das das System dafuer vorsieht. Ein Download
        waere hier sinnlos - die Datei liegt ja schon auf dieser Platte."""
        pfad = speicher.anhang_lesen(notizbuch, abschnitt, name, datei)
        try:
            if sys.platform == "win32":
                os.startfile(str(pfad))                      # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(pfad)])
            else:
                subprocess.Popen(["xdg-open", str(pfad)])
        except OSError as f:
            raise Abbruch(f"Ließ sich nicht öffnen: {f}")
        return {"ok": True, "pfad": str(pfad)}

    @_gefasst
    def anhang_speichern_unter(self, notizbuch: str, abschnitt: str, name: str, datei: str) -> dict:
        """Kopie irgendwohin legen, wo der Benutzer sie haben will."""
        pfad = speicher.anhang_lesen(notizbuch, abschnitt, name, datei)
        ziel = self._dialog_speichern(pfad.name)
        if not ziel:
            return {"abgebrochen": True}
        shutil.copy2(pfad, ziel)
        return {"ok": True, "ziel": str(ziel)}

    # --- Einstellungen, Ordner, Updates -----------------------------------

    @_gefasst
    def einstellungen(self) -> dict:
        try:
            ordner = speicher.wurzel()
            fehlt = ""
        except speicher.SpeicherFehler as f:
            # Ordner nicht da: trotzdem antworten, sonst kommt man nicht einmal an
            # die Einstellung, mit der man ihn umstellt.
            ordner, fehlt = None, str(f)
        gesamt = 0
        if ordner:
            for buch in speicher.baum():
                gesamt += sum(len(a["seiten"]) for a in buch["abschnitte"])
        korb = ordner / speicher.PAPIERKORB if ordner else None
        return {
            "version": VERSION,
            "ordner": str(ordner) if ordner else speicher.gewaehlter_ordner(),
            "ordner_fehlt": fehlt,
            "ordner_quelle": speicher.ordner_quelle(),
            "ordner_waehlbar": True,          # der Dialog kommt vom Fenster selbst
            "seiten": gesamt,
            "frei": shutil.disk_usage(ordner).free if ordner else 0,
            "papierkorb": sum(1 for _ in korb.glob("*")) if korb and korb.is_dir() else 0,
            "aus_installation": aktualisieren.aus_installation(),
            "optionen": aktualisieren.optionen_lesen(),
            "quelle": aktualisieren.QUELLE,
        }

    @_gefasst
    def optionen_setzen(self, rumpf: dict) -> dict:
        try:
            return aktualisieren.optionen_schreiben(rumpf or {})
        except RuntimeError as f:
            raise Abbruch(str(f))

    @_gefasst
    def ordner_waehlen(self) -> dict:
        """Der Ordner-Dialog der Webansicht - kein kdialog, kein zenity."""
        gewaehlt = self._dialog_ordner()
        return {"ordner": gewaehlt or None}

    @_gefasst
    def ordner_setzen(self, rumpf: dict) -> dict:
        """Datenordner umstellen. Gilt sofort; die Oberflaeche laedt danach neu,
        damit keine offene Seite noch auf den alten Ordner zeigt."""
        if speicher.ordner_quelle() == "umgebung":
            raise Abbruch("Der Ordner ist über NOTIZEN_ORDNER fest vorgegeben")
        if rumpf.get("standard"):
            konfig.aendern(ordner=None)
            return {"ordner": str(speicher.wurzel()), "kopiert": 0}
        try:
            alt = speicher.wurzel()
        except speicher.SpeicherFehler:
            alt = None            # alter Ordner nicht da - dann gibt es nichts mitzunehmen
        neu = speicher.ordner_pruefen(str(rumpf.get("ordner") or ""))
        kopiert = 0
        if rumpf.get("mitnehmen") and alt and neu != alt.resolve():
            kopiert = speicher.inhalt_kopieren(alt, neu)
        konfig.aendern(ordner=str(neu))
        return {"ordner": str(neu), "kopiert": kopiert}

    @_gefasst
    def version(self, frisch: bool = False) -> dict:
        return aktualisieren.pruefen(frisch=bool(frisch))

    @_gefasst
    def update(self) -> dict:
        try:
            return aktualisieren.einspielen()
        except RuntimeError as f:
            raise Abbruch(str(f))

    @_gefasst
    def update_stand(self) -> dict:
        return aktualisieren.protokoll()

    # --- Dialoge des Fensters ---------------------------------------------

    def _dialog_ordner(self) -> str | None:
        import webview
        if not self.fenster:
            return None
        gewaehlt = self.fenster.create_file_dialog(webview.FOLDER_DIALOG)
        return gewaehlt[0] if gewaehlt else None

    def _dialog_speichern(self, vorschlag: str) -> str | None:
        import webview
        if not self.fenster:
            return None
        gewaehlt = self.fenster.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=vorschlag)
        if not gewaehlt:
            return None
        return gewaehlt if isinstance(gewaehlt, str) else gewaehlt[0]
