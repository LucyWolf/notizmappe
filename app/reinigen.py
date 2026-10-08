"""HTML aus dem Editor saeubern, bevor es auf die Platte geht.

Der Editor ist ein contenteditable: der Browser darf da einfuegen, was er will,
und wer eine Webseite kopiert, bringt deren <script> und onerror= mit. Gereinigt
wird beim Speichern, nicht beim Anzeigen - sonst steht der Dreck erst mal in der
Datei und jeder spaetere Weg (Export, Suche, zweite Oberflaeche) sieht ihn wieder.
"""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser

ERLAUBT = {
    "p", "br", "div", "span", "b", "strong", "i", "em", "u", "s", "strike",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "blockquote", "code", "pre", "a",
}
LEER = {"br"}
# Nur das, was der Editor selbst setzt. Kein style, kein class, kein on*.
ATTRIBUTE = {"a": {"href"}}
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
            gut.append(f' {name}="{escape(wert, quote=True)}"')
        if tag in LEER:
            self.teile.append(f"<{tag}>")
        else:
            self.teile.append(f"<{tag}{''.join(gut)}>")
            self.offen.append(tag)

    def handle_startendtag(self, tag, attrs):
        if not self.weg and tag in LEER:
            self.teile.append(f"<{tag}>")

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
