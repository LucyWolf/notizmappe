"""Die Verbindung zwischen Fenster und Programm - ohne Netz.

Die Oberflaeche ist HTML und laeuft in der Webansicht des Systems. Sie ruft diese
Methoden direkt auf (window.pywebview.api.xyz): kein Port, keine Adresse, kein
HTTP - ein Funktionsaufruf in denselben Prozess.

Alle Methoden geben ein Woerterbuch zurueck. Geht etwas schief, steht darin
"fehler" (und bei einem Schreibkonflikt zusaetzlich "art": "konflikt" mit der
Fassung, die auf der Platte liegt). Ausnahmen fliegen nicht durch die Bruecke:
auf der anderen Seite kaeme nur eine unverstaendliche Zeichenkette an.
"""
from __future__ import annotations

import base64
import functools
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import aktualisieren
import einfuhr
import konfig
import reinigen
import speicher
import tresor

HIER = Path(__file__).resolve().parent
VERSION = (HIER / "VERSION").read_text(encoding="utf-8").strip()
MAX_ELEMENTE = 500


class Abbruch(Exception):
    """Etwas, das der Benutzer wissen muss - kein Programmfehler."""

    def __init__(self, text: str, **mehr):
        super().__init__(text)
        self.mehr = mehr


_letzte_tat = time.time()
_minuten_geholt = (0.0, 0)


def _ruhe_minuten() -> int:
    """Wie lange ohne Benutzung bis zum Zusperren. 0 = gar nicht.

    Gepuffert: _takt() laeuft bei jedem Tastendruck mit, und die Einstellung
    jedes Mal von der Platte zu lesen waere Verschwendung."""
    global _minuten_geholt
    jetzt = time.time()
    if jetzt - _minuten_geholt[0] > 5:
        try:
            wert = int(konfig.lesen().get("sperre_minuten", 0) or 0)
        except (TypeError, ValueError):
            wert = 0
        _minuten_geholt = (jetzt, max(0, min(wert, 24 * 60)))
    return _minuten_geholt[1]


def _takt() -> None:
    global _letzte_tat
    jetzt = time.time()
    minuten = _ruhe_minuten()
    if minuten and tresor.offen() and jetzt - _letzte_tat > minuten * 60:
        zusperren()
    _letzte_tat = jetzt


def zusperren() -> None:
    """Schluessel aus dem Arbeitsspeicher - und die Klartextkopien weg, die zum
    Oeffnen von Anhaengen noetig waren."""
    tresor.sperren()
    global _klartext_ordner
    if _klartext_ordner:
        shutil.rmtree(_klartext_ordner, ignore_errors=True)
        _klartext_ordner = None


_klartext_ordner = None


def _woerterbuch(wert) -> dict:
    """Was aus der Oberflaeche kommt, ist nicht zwangslaeufig ein Woerterbuch.

    Kommt statt dessen eine Zahl oder eine Liste an, gaebe es ohne das hier
    einen rohen Programmfehler statt einer Meldung - und im Fenster stuende
    eine Zeile, die nach einem kaputten Programm aussieht.
    """
    return wert if isinstance(wert, dict) else {}


def _ins_protokoll(wo: str, x: Exception) -> None:
    """Fehler mit Spur in eine Datei schreiben.

    traceback.print_exc() allein nuetzt nichts: die Windows-Fassung ist ohne
    Konsole gebaut, dort geht die Ausgabe ins Leere. Uebrig bleibt im Fenster
    eine Zeile wie "TypeError: ..." - und niemand weiss, woher sie kommt. Genau
    danach habe ich einmal lange gesucht.
    """
    import traceback
    traceback.print_exc()
    try:
        import aktualisieren
        datei = aktualisieren.PROTOKOLL.with_name("fenster.log")
        datei.parent.mkdir(parents=True, exist_ok=True)
        if datei.exists() and datei.stat().st_size > 1024 * 1024:
            datei.unlink()                      # nicht endlos wachsen lassen
        with datei.open("a", encoding="utf-8") as p:
            p.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')}  bei {wo}\n")
            p.write(traceback.format_exc())
    except Exception:                           # noqa: BLE001 - Protokoll ist nett, nicht wichtig
        pass


def _gefasst(f):
    """Fehler als Antwort, nicht als Ausnahme."""
    @functools.wraps(f)
    def innen(*args, **kwargs):
        _takt()
        try:
            return f(*args, **kwargs)
        except tresor.TresorFehler as x:
            # "art" sagt der Oberflaeche, dass sie den Sperrschirm zeigen soll -
            # und nicht etwa einen roten Fehlerbalken ueber leeren Notizen.
            return {"fehler": str(x), "art": "zu"}
        except Abbruch as x:
            return {"fehler": str(x), **x.mehr}
        except speicher.KonfliktFehler as x:
            return {"fehler": str(x), "art": "konflikt", "aktuell": x.seite}
        except speicher.SpeicherFehler as x:
            return {"fehler": str(x)}
        except Exception as x:                      # noqa: BLE001 - nichts soll durchfallen
            _ins_protokoll(f.__name__, x)
            return {"fehler": f"{type(x).__name__}: {x}", "wo": f.__name__}
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
        if art not in {"text", "bild", "datei", "stift"}:
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
        elif art == "stift":
            # Die Zeichenebene der Seite. Steht einmal pro Seite da und hat
            # keine Groesse - sie liegt ueber allem.
            gemein["striche"] = reinigen.striche(e.get("striche"))
            if not gemein["striche"]:
                continue                    # leere Zeichnung nicht mitschleppen
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
        rumpf = _woerterbuch(rumpf)
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
        teile = [reinigen.text(t, 120) for t in (pfad if isinstance(pfad, list) else []) if reinigen.text(t, 120)]
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
        daten = speicher.anhang_inhalt(notizbuch, abschnitt, name, datei)
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
        pfad = self._zum_oeffnen(notizbuch, abschnitt, name, datei)
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
        Path(ziel).write_bytes(speicher.anhang_inhalt(notizbuch, abschnitt, name, datei))
        return {"ok": True, "ziel": str(ziel)}

    def _zum_oeffnen(self, notizbuch: str, abschnitt: str, name: str, datei: str) -> Path:
        """Pfad, den ein anderes Programm oeffnen kann.

        Ohne Sperre ist das die Datei selbst. Mit Sperre kann kein fremdes
        Programm etwas damit anfangen, also muss eine lesbare Kopie her. Sie
        liegt in einem Ordner nur fuer diesen Benutzer und verschwindet, sobald
        wieder zugesperrt wird."""
        pfad = speicher.anhang_lesen(notizbuch, abschnitt, name, datei)
        if not speicher.verschluesselt():
            return pfad
        global _klartext_ordner
        if not _klartext_ordner:
            _klartext_ordner = tempfile.mkdtemp(prefix="notizmappe-offen-")
        kopie = Path(_klartext_ordner) / pfad.name
        kopie.write_bytes(speicher.anhang_inhalt(notizbuch, abschnitt, name, datei))
        return kopie

    # --- Sperre -----------------------------------------------------------

    @_gefasst
    def sperre_stand(self) -> dict:
        return {
            "eingerichtet": speicher.verschluesselt(),
            "offen": tresor.offen(),
            "minuten": _ruhe_minuten(),
        }

    @_gefasst
    def sperre_einrichten(self, rumpf: dict) -> dict:
        """Sperre anlegen und vorhandene Notizen verschluesseln."""
        passwort = str(_woerterbuch(rumpf).get("passwort") or "")
        if speicher.verschluesselt():
            raise Abbruch("Die Sperre ist schon eingerichtet")
        try:
            rettung = tresor.einrichten(speicher.wurzel(), passwort)
        except tresor.TresorFehler as f:
            raise Abbruch(str(f))
        return {"rettung": rettung, "umgestellt": speicher.umstellen(True)}

    @_gefasst
    def entsperren(self, rumpf: dict) -> dict:
        geheim = str(_woerterbuch(rumpf).get("geheim") or "").strip()
        if not speicher.verschluesselt():
            return {"ok": True}
        try:
            tresor.entsperren(speicher.wurzel(), geheim)
        except tresor.TresorFehler as f:
            # Nicht verraten, ob das Passwort oder der Benutzername "fast" stimmte,
            # und etwas bremsen: ohne das waere Durchprobieren nur eine Schleife.
            time.sleep(0.5)
            raise Abbruch(str(f))
        return {"ok": True}

    @_gefasst
    def sperren(self) -> dict:
        zusperren()
        return {"ok": True}

    @_gefasst
    def sperre_passwort(self, rumpf: dict) -> dict:
        d = _woerterbuch(rumpf)
        try:
            tresor.passwort_aendern(speicher.wurzel(), str(d.get("alt") or ""),
                                    str(d.get("neu") or ""))
        except tresor.TresorFehler as f:
            raise Abbruch(str(f))
        return {"ok": True}

    @_gefasst
    def sperre_zuruecksetzen(self, rumpf: dict) -> dict:
        """Neues Passwort mit dem Wiederherstellungsschluessel."""
        d = _woerterbuch(rumpf)
        try:
            tresor.passwort_zuruecksetzen(speicher.wurzel(), str(d.get("rettung") or ""),
                                          str(d.get("neu") or ""))
        except tresor.TresorFehler as f:
            time.sleep(0.5)
            raise Abbruch(str(f))
        return {"ok": True}

    @_gefasst
    def sperre_rettung_neu(self, rumpf: dict) -> dict:
        try:
            neu = tresor.rettung_erneuern(speicher.wurzel(), str(_woerterbuch(rumpf).get("passwort") or ""))
        except tresor.TresorFehler as f:
            raise Abbruch(str(f))
        return {"rettung": neu}

    @_gefasst
    def sperre_aus(self, rumpf: dict) -> dict:
        """Sperre abschalten: alles wieder im Klartext auf die Platte."""
        passwort = str(_woerterbuch(rumpf).get("passwort") or "")
        if not speicher.verschluesselt():
            return {"ok": True}
        wurzel = speicher.wurzel()
        try:
            tresor.entsperren(wurzel, passwort)        # erst beweisen, dann aufmachen
            offen = speicher.umstellen(False)
            tresor.abschalten(wurzel, passwort)
        except tresor.TresorFehler as f:
            raise Abbruch(str(f))
        return {"ok": True, "umgestellt": offen}

    @_gefasst
    def sperre_minuten(self, rumpf: dict) -> dict:
        try:
            minuten = max(0, min(int(_woerterbuch(rumpf).get("minuten") or 0), 24 * 60))
        except (TypeError, ValueError):
            raise Abbruch("Keine Zahl")
        konfig.aendern(sperre_minuten=minuten)
        global _minuten_geholt
        _minuten_geholt = (0.0, 0)
        return {"minuten": minuten}

    RETTUNGSDATEI = "notizmappe-wiederherstellungsschluessel.txt"

    @_gefasst
    def rettung_ziel(self) -> dict:
        """Wo die Schluesseldatei vorgeschlagen wird: Dokumente im eigenen Ordner.
        Nicht der Datenordner - ein Schluessel neben dem Schloss ist keiner."""
        return {"pfad": str(speicher.dokumentenordner() / self.RETTUNGSDATEI)}

    @_gefasst
    def rettung_speichern(self, rumpf: dict) -> dict:
        """Den Wiederherstellungsschluessel in eine Datei legen.

        Mit "pfad" genau dorthin, sonst ueber den Dialog des Systems."""
        d = _woerterbuch(rumpf)
        schluessel = str(d.get("rettung") or "").strip()
        if not schluessel:
            raise Abbruch("Kein Schlüssel übergeben")

        roh = str(d.get("pfad") or "").strip()
        if roh:
            ziel = Path(roh).expanduser()
            if ziel.is_dir():
                ziel = ziel / self.RETTUNGSDATEI          # Ordner angegeben: Name dran
            if not ziel.name:
                raise Abbruch("Da fehlt ein Dateiname")
            if not ziel.parent.is_dir():
                # Nicht stillschweigend anlegen: ein Tippfehler im Pfad legt sonst
                # einen Ordner an, und die Datei liegt irgendwo, wo niemand sucht.
                raise Abbruch(f"Den Ordner gibt es nicht: {ziel.parent}")
        else:
            gewaehlt = self._dialog_speichern(self.RETTUNGSDATEI)
            if not gewaehlt:
                return {"abgebrochen": True}
            ziel = Path(gewaehlt)

        warnung = ""
        try:
            # Liegt die Datei im Datenordner, nuetzt sie nichts: wer dorthin kommt,
            # hat ohnehin alles. Nicht verbieten - sagen.
            ziel.resolve().relative_to(speicher.wurzel().resolve())
            warnung = ("Achtung: Die Datei liegt im Notizordner selbst. "
                       "Wer dorthin kommt, hat damit auch den Schlüssel.")
        except (ValueError, speicher.SpeicherFehler, OSError):
            pass

        try:
            ziel.write_text(
                "Notizmappe - Wiederherstellungsschlüssel\n\n"
                f"{schluessel}\n\n"
                "Damit lässt sich das Passwort neu setzen, wenn es verloren ist.\n"
                "Nicht im selben Ordner aufbewahren wie die Notizen.\n",
                encoding="utf-8")
        except OSError as f:
            raise Abbruch(f"Ließ sich nicht schreiben: {f}")
        return {"ok": True, "ziel": str(ziel), "warnung": warnung}

    @_gefasst
    def schriften(self) -> dict:
        """Die Schriften, die auf diesem Rechner installiert sind.

        Eine feste Liste im Programm waere immer falsch: sie enthielte Schriften,
        die hier fehlen, und kennte die nicht, die da sind.
        """
        gefunden = set()

        if sys.platform == "win32":
            try:
                import winreg
                pfad = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, pfad) as k:
                    for i in range(winreg.QueryInfoKey(k)[1]):
                        name = winreg.EnumValue(k, i)[0]
                        # "Arial (TrueType)" -> "Arial"; Schnitte zusammenfassen
                        name = re.sub(r"\s*\((TrueType|OpenType)\)$", "", name)
                        name = re.sub(r"\s+(Bold|Italic|Bold Italic|Regular)$", "", name)
                        for teil in name.split("&"):
                            gefunden.add(teil.strip())
            except Exception:
                pass
        else:
            try:
                lauf = subprocess.run(["fc-list", "--format", "%{family[0]}\n"],
                                      capture_output=True, text=True, timeout=20)
                for zeile in lauf.stdout.splitlines():
                    gefunden.add(zeile.strip())
            except (OSError, subprocess.TimeoutExpired):
                pass

        sauber = sorted({n for n in gefunden
                         if n and reinigen.schriftname_ok(n)}, key=str.lower)
        vorhanden = {n.lower() for n in sauber}

        # Nur vorschlagen, was es hier auch gibt - eine Schrift, die nicht
        # installiert ist, sieht im Auswahlfeld aus wie ein Angebot und waere
        # beim Anklicken wirkungslos.
        empfohlen = {}
        for fach, namen in reinigen.EMPFEHLUNGEN.items():
            da = [n for n in namen if n.lower() in vorhanden]
            if da:
                empfohlen[fach] = {"name": reinigen.FACHNAMEN[fach], "schriften": da}

        return {
            "schriften": sauber,
            "vorschlaege": reinigen.SCHRIFT_GRUPPEN,
            "empfohlen": empfohlen,
            "favoriten": self._favoriten_lesen(),
        }

    @staticmethod
    def _favoriten_lesen() -> list:
        roh = konfig.lesen().get("schrift_favoriten")
        if not isinstance(roh, list):
            return []
        return [n for n in roh if isinstance(n, str) and reinigen.schriftname_ok(n)]

    @_gefasst
    def favorit_setzen(self, name: str, an: bool) -> dict:
        """Einen Stern setzen oder wegnehmen. Favoriten stehen oben im Auswahlfeld."""
        name = str(name or "").strip()
        if not reinigen.schriftname_ok(name):
            raise Abbruch("Das ist kein gültiger Schriftname")
        liste = self._favoriten_lesen()
        if an and name not in liste:
            liste.append(name)
        elif not an and name in liste:
            liste.remove(name)
        konfig.aendern(schrift_favoriten=liste)
        return {"favoriten": liste}

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
            # Sitzt die Oberflaeche auf demselben Rechner wie das Programm? Im
            # Fenster immer ja. Die Oberflaeche haengt daran, ob sie den
            # Datenordner umstellen und Updates einspielen laesst - fehlt das
            # Feld, ist das Ordnerfeld stillschweigend weg (genau das war es).
            "hier": True,
            "ordner": str(ordner) if ordner else speicher.gewaehlter_ordner(),
            "ordner_fehlt": fehlt,
            "ordner_quelle": speicher.ordner_quelle(),
            "ordner_waehlbar": True,          # der Dialog kommt vom Fenster selbst
            "seiten": gesamt,
            "frei": shutil.disk_usage(ordner).free if ordner else 0,
            "papierkorb": sum(1 for _ in korb.glob("*")) if korb and korb.is_dir() else 0,
            # Wenn hier nichts liegt: wo liegt dann etwas? Ein leerer Ordner
            # heisst meistens nicht, dass alles weg ist.
            "andere_orte": speicher.andere_orte(ordner) if ordner and not gesamt else [],
            "aus_installation": aktualisieren.aus_installation(),
            "optionen": aktualisieren.optionen_lesen(),
            "quelle": aktualisieren.QUELLE,
        }

    @_gefasst
    def optionen_setzen(self, rumpf: dict) -> dict:
        try:
            return aktualisieren.optionen_schreiben(_woerterbuch(rumpf))
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

    # --- Verlauf ----------------------------------------------------------

    @_gefasst
    def versionen(self, notizbuch: str, abschnitt: str, name: str) -> dict:
        return {"versionen": speicher.verlauf_liste(notizbuch, abschnitt, name)}

    @_gefasst
    def version_lesen(self, notizbuch: str, abschnitt: str, name: str, marke: str) -> dict:
        return speicher.verlauf_lesen(notizbuch, abschnitt, name, reinigen.text(marke, 40))

    @_gefasst
    def version_zurueck(self, rumpf: dict) -> dict:
        d = _woerterbuch(rumpf)
        return speicher.verlauf_zurueck(d.get("notizbuch", ""), d.get("abschnitt", ""),
                                        d.get("name", ""), reinigen.text(d.get("marke"), 40))

    @_gefasst
    def papierkorb(self) -> dict:
        return {"eintraege": speicher.papierkorb_liste()}

    @_gefasst
    def papierkorb_zurueck(self, rumpf: dict) -> dict:
        eintrag = str(_woerterbuch(rumpf).get("eintrag") or "")
        if not eintrag:
            raise Abbruch("Kein Eintrag angegeben")
        return speicher.papierkorb_zurueck(eintrag)

    @_gefasst
    def papierkorb_weg(self, rumpf: dict) -> dict:
        eintrag = str(_woerterbuch(rumpf).get("eintrag") or "")
        if not eintrag:
            raise Abbruch("Kein Eintrag angegeben")
        return speicher.papierkorb_weg(eintrag)

    @_gefasst
    def papierkorb_leeren(self) -> dict:
        return speicher.papierkorb_leeren()

    # --- Aus OneNote einlesen ---------------------------------------------

    @_gefasst
    def onenote_einlesen(self, rumpf: dict | None = None) -> dict:
        """Eine .one- oder .onepkg-Datei als neues Notizbuch anlegen.

        Immer als **neues** Notizbuch: ein Einlesen, das vorhandene Notizen
        anfasst, waere im Zweifel nicht rueckgaengig zu machen.
        """
        pfad = str(_woerterbuch(rumpf).get("pfad") or "").strip()
        if not pfad:
            pfad = self._dialog_oeffnen(("OneNote (*.one;*.onepkg)", "Alle Dateien (*.*)"))
            if not pfad:
                return {"abgebrochen": True}
        quelle = Path(pfad).expanduser()
        if not quelle.is_file():
            raise Abbruch(f"Gibt es nicht: {quelle}")
        if quelle.stat().st_size > 500 * 1024 * 1024:
            raise Abbruch("Die Datei ist größer als 500 MB")
        try:
            bericht = einfuhr.einlesen(quelle, reinigen.text(_woerterbuch(rumpf).get("name"), 80))
        except einfuhr.EinfuhrFehler as f:
            raise Abbruch(str(f))
        if not bericht["seiten"]:
            # Nicht mit "fertig" antworten, wenn nichts herausgekommen ist - das
            # ist der Fall, der nach Erfolg aussieht und keiner ist.
            raise Abbruch("Aus der Datei ließ sich kein Text lesen. Ist der Abschnitt "
                          "mit einem Passwort geschützt?")
        return bericht

    # --- Dialoge des Fensters ---------------------------------------------

    def _dialog_ordner(self) -> str | None:
        import webview
        if not self.fenster:
            return None
        gewaehlt = self.fenster.create_file_dialog(webview.FOLDER_DIALOG)
        return gewaehlt[0] if gewaehlt else None

    def _dialog_oeffnen(self, muster: tuple[str, ...] | None = None) -> str | None:
        import webview
        if not self.fenster:
            return None
        gewaehlt = self.fenster.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=muster or ("Alle Dateien (*.*)",))
        if not gewaehlt:
            return None
        return gewaehlt if isinstance(gewaehlt, str) else gewaehlt[0]

    def _dialog_speichern(self, vorschlag: str) -> str | None:
        import webview
        if not self.fenster:
            return None
        gewaehlt = self.fenster.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=vorschlag)
        if not gewaehlt:
            return None
        return gewaehlt if isinstance(gewaehlt, str) else gewaehlt[0]
