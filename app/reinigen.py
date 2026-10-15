"""HTML aus dem Editor saeubern, bevor es auf die Platte geht.

Der Editor ist ein contenteditable: der Browser darf da einfuegen, was er will,
und wer eine Webseite kopiert, bringt deren <script> und onerror= mit. Gereinigt
wird beim Speichern, nicht beim Anzeigen - sonst steht der Dreck erst mal in der
Datei und jeder spaetere Weg (Export, Suche, zweite Oberflaeche) sieht ihn wieder.
"""
from __future__ import annotations

import re
from html import escape, unescape
from html.parser import HTMLParser

ERLAUBT = {
    "p", "br", "div", "span", "b", "strong", "i", "em", "u", "s", "strike",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "blockquote", "code", "pre", "a",
    "font", "mark", "sub", "sup",
    "img",
}
LEER = {"br", "img"}
# Nur das, was der Editor selbst setzt. Kein style, kein class, kein on*.
# Bilder im Text zeigen nur auf einen eigenen Anhang (data-datei), nie per src
# irgendwohin - die Adresse setzt die Oberflaeche beim Anzeigen.
ATTRIBUTE = {"a": {"href"}, "img": {"data-datei", "alt"}, "font": {"size", "face", "color"}}

# <font> ist aus der Mode, aber genau das, was der Editor fuer Groesse und Art
# erzeugt - und es traegt nur zwei feste Werte statt beliebigem CSS. Ein style-
# Attribut waere bequemer und zugleich ein Einfallstor: damit liesse sich ein
# Element ueber die ganze Seite legen und alles darunter abfangen.
#
# Nur was im Auswahlfeld steht; andere Angaben fliegen raus, damit niemand ueber
# den Namen einer Schrift etwas anderes hineinschreibt.
# Die vier Gruppen stehen oben im Auswahlfeld; darunter kommen die Schriften,
# die auf dem Rechner wirklich installiert sind.
SCHRIFT_GRUPPEN = [
    ["system-ui", "Standard"],
    ["Georgia, serif", "Serife"],
    ["ui-monospace, monospace", "Feste Breite"],
    ["Segoe Script, Comic Sans MS, cursive", "Handschrift"],
]

# Vorschlaege: Schriften, die auf vielen Rechnern liegen und sich fuer das
# jeweilige Fach bewaehrt haben. Angeboten wird davon nur, was wirklich
# installiert ist - der Rest steht hier nur als Wunschliste.
EMPFEHLUNGEN = {
    "schreiben": [
        "Segoe UI", "Calibri", "Arial", "Helvetica", "Helvetica Neue", "Verdana",
        "Tahoma", "Trebuchet MS", "Open Sans", "Roboto", "Noto Sans", "Lato",
        "Source Sans Pro", "Source Sans 3", "Inter", "DejaVu Sans",
        "Liberation Sans", "Ubuntu", "Cantarell", "Segoe UI Variable",
    ],
    "lesen": [
        "Georgia", "Times New Roman", "Cambria", "Constantia", "Garamond",
        "EB Garamond", "Palatino Linotype", "Book Antiqua", "Merriweather",
        "Noto Serif", "Source Serif Pro", "Liberation Serif", "DejaVu Serif",
        "Charis SIL", "Bitstream Charter",
    ],
    "code": [
        "JetBrains Mono", "Fira Code", "FiraCode Nerd Font", "Cascadia Code",
        "Cascadia Mono", "Consolas", "Source Code Pro", "IBM Plex Mono", "Hack",
        "Inconsolata", "Courier New", "DejaVu Sans Mono", "Liberation Mono",
        "Noto Sans Mono", "Ubuntu Mono", "Roboto Mono", "Monaco", "Menlo",
        "SF Mono", "Iosevka", "Victor Mono", "Anonymous Pro",
    ],
}

FACHNAMEN = {"schreiben": "Zum Schreiben", "lesen": "Zum Lesen", "code": "Zum Programmieren"}

# Statt einer festen Liste ein strenges Muster: Schriftnamen bestehen aus
# Buchstaben, Ziffern, Leerzeichen und ein paar Satzzeichen. Alles, womit sich
# aus einem face="..." etwas anderes machen liesse - Anfuehrungszeichen,
# Semikolon, spitze Klammern - faellt damit weg.
SCHRIFT_MUSTER = re.compile(r"^[A-Za-z0-9 ,.\-_()\u00c0-\u024f]{1,80}$")


# --- Striche vom Stift -------------------------------------------------------
#
# Eine Zeichnung ist eine Liste von Strichen, ein Strich eine flache Liste aus
# x, y, Druck. Flach, weil das in der Datei etwa die Haelfte spart gegenueber
# einer Liste von Woerterbuechern - und eine Seite voller Handschrift hat
# schnell hunderttausend Zahlen.
MAX_STRICHE = 4000
MAX_PUNKTE = 1400                   # je Strich
# Deckel ueber allem. Ohne ihn duerfte eine Seite rechnerisch 96 MB gross
# werden - und die wird bei jedem Autosave neu geschrieben, verschluesselt,
# vom Sync uebertragen und alle zehn Minuten als Fassung abgelegt. Echte
# Handschrift braucht etwa 400 KB fuer 250 Striche; 400.000 Zahlen sind rund
# 3 MB und damit das Zehnfache davon.
MAX_ZAHLEN_GESAMT = 400_000
WEIT = 50000                        # weiter als so kann keine Seite sein
FARBE_MUSTER = re.compile(r"^#[0-9a-fA-F]{6}$")


def striche(roh) -> list[dict]:
    """Nur Zahlen, nur bekannte Felder, mit Deckel.

    Was hier durchgeht, landet unveraendert in der Seite und wird beim naechsten
    Oeffnen gezeichnet. Eine Liste mit einer Million Punkten wuerde die Datei
    aufblaehen und das Zeichnen zaeh machen, also wird abgeschnitten statt
    abgelehnt: lieber ein gekuerzter Strich als eine verlorene Seite.
    """
    if not isinstance(roh, list):
        return []
    aus = []
    gesamt = 0
    for strich in roh[:MAX_STRICHE]:
        if gesamt >= MAX_ZAHLEN_GESAMT:
            break                               # die Seite ist voll
        if not isinstance(strich, dict):
            continue
        p = strich.get("p")
        if not isinstance(p, list) or len(p) < 3:
            continue
        punkte = []
        for i in range(0, min(len(p), MAX_PUNKTE * 3) - 2, 3):
            try:
                x, y, druck = float(p[i]), float(p[i + 1]), float(p[i + 2])
            except (TypeError, ValueError):
                continue                    # einzelner kaputter Punkt: ueberspringen
            if x != x or y != y:            # NaN
                continue
            punkte.append(round(max(-WEIT, min(WEIT, x)), 1))
            punkte.append(round(max(-WEIT, min(WEIT, y)), 1))
            punkte.append(round(max(0.0, min(1.0, druck)), 2))
        if len(punkte) < 3:
            continue
        farbe = str(strich.get("f") or "")
        try:
            dicke = float(strich.get("d") or 4)
        except (TypeError, ValueError):
            dicke = 4
        gesamt += len(punkte)
        aus.append({
            "f": farbe.lower() if FARBE_MUSTER.match(farbe) else "#1d1d1f",
            "d": round(max(1.0, min(60.0, dicke)), 1),
            "a": "marker" if strich.get("a") == "marker" else "stift",
            "p": punkte,
        })
    return aus


def schriftname_ok(name: str) -> bool:
    name = str(name or "").strip()
    if not name or not SCHRIFT_MUSTER.match(name):
        return False
    # Keine CSS-Funktionen oder Kommentare hineinschmuggeln
    return not any(z in name for z in ("url(", "/*", "*/", "expression"))

# Dieselbe Idee bei den Farben: nur was in der Palette steht. Eine beliebige
# Farbe waere harmlos, aber die Pruefung kostet nichts und haelt die Liste der
# erlaubten Werte an einer Stelle.
FARBEN = {
    "#1f1d1a", "#b23b2e", "#c2690a", "#2f7d32", "#1565c0", "#7a5cff", "#78736a",
}
SCHEMA_OK = ("http://", "https://", "mailto:", "notiz:")


class _Reiniger(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.teile: list[str] = []
        self.offen: list[str] = []
        self.weg = 0  # Tiefe innerhalb eines verbotenen Containers

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "object", "embed", "svg", "math"}:
            self.weg += 1
            return
        if self.weg or tag not in ERLAUBT:
            return
        gut = []
        for name, wert in attrs:
            if name not in ATTRIBUTE.get(tag, set()) or not wert:
                continue
            if name == "href" and not wert.lower().startswith(SCHEMA_OK):
                continue
            if name == "data-datei" and not anhangname_ok(wert):
                continue
            if name == "size" and wert not in {"1", "2", "3", "4", "5", "6", "7"}:
                continue
            if name == "face" and not schriftname_ok(wert):
                continue
            if name == "color" and wert.lower() not in FARBEN:
                continue
            gut.append(f' {name}="{escape(wert, quote=True)}"')
        if tag == "img" and not any(g.startswith(" data-datei=") for g in gut):
            return
        if tag in LEER:
            self.teile.append(f"<{tag}{''.join(gut)}>")
        else:
            self.teile.append(f"<{tag}{''.join(gut)}>")
            self.offen.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in LEER:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "iframe", "object", "embed", "svg", "math"}:
            self.weg = max(0, self.weg - 1)
            return
        if self.weg or tag not in ERLAUBT or tag in LEER:
            return
        if tag in self.offen:
            # Alles schliessen, was ueber dem Tag noch offen steht - ein fremdes
            # </div> zu viel darf nicht die halbe Seite verschlucken.
            while self.offen:
                auf = self.offen.pop()
                self.teile.append(f"</{auf}>")
                if auf == tag:
                    break

    def handle_data(self, daten):
        if not self.weg:
            self.teile.append(escape(daten, quote=False))

    def ergebnis(self) -> str:
        while self.offen:
            self.teile.append(f"</{self.offen.pop()}>")
        return "".join(self.teile)


def anhangname_ok(name: str) -> bool:
    """Ein blosser Dateiname im Anhangsordner - kein Pfad, nichts Verstecktes."""
    return (0 < len(name) <= 120 and not name.startswith(".")
            and not any(z in name for z in "/\\\x00"))


_BILD_IM_TEXT = re.compile(r'<img [^>]*data-datei="([^"]*)"')


def bilder_im_text(sauber: str) -> set[str]:
    """Dateinamen der Bilder, die in gereinigtem Text-HTML stecken."""
    return {unescape(n) for n in _BILD_IM_TEXT.findall(sauber)}


def html(roh: str, grenze: int = 200_000) -> str:
    r = _Reiniger()
    r.feed(str(roh)[:grenze])
    r.close()
    return r.ergebnis()


def text(roh, grenze: int = 500) -> str:
    return str(roh or "").replace("\x00", "")[:grenze].strip()


def zahl(roh, standard: float = 0.0, klein: float = -200_000, gross: float = 200_000) -> float:
    try:
        w = float(roh)
    except (TypeError, ValueError):
        return standard
    if w != w or w in (float("inf"), float("-inf")):
        return standard
    return max(klein, min(gross, round(w, 1)))


# --- Hochgeladene Dateien -----------------------------------------------------

# An den ersten Bytes erkannt, nicht am Dateinamen und nicht am Content-Type des
# Browsers: beides sagt, was der Absender behauptet, nicht was drin ist.
BILDMARKEN = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)


def bildtyp(daten: bytes) -> str | None:
    """Liefert den Medientyp, wenn es wirklich ein Bild ist - sonst None.

    Absichtlich ohne SVG: das ist XML mit <script> darin und waere im Dashboard
    dasselbe Loch wie fremdes HTML. SVG darf hochgeladen werden, wird aber als
    Datei zum Herunterladen behandelt, nicht als Bild angezeigt.
    """
    for marke, typ in BILDMARKEN:
        if daten.startswith(marke):
            return typ
    if daten[:4] == b"RIFF" and daten[8:12] == b"WEBP":
        return "image/webp"
    return None
