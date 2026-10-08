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
    "img",
}
LEER = {"br", "img"}
# Nur das, was der Editor selbst setzt. Kein style, kein class, kein on*.
# Bilder im Text zeigen nur auf einen eigenen Anhang (data-datei), nie per src
# irgendwohin - die Adresse setzt die Oberflaeche beim Anzeigen.
ATTRIBUTE = {"a": {"href"}, "img": {"data-datei", "alt"}}
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
