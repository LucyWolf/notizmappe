"""Jeden Namen in der Oberfläche gegengeprüft.

    .venv/bin/python tests/test_namen.py

"textBilderZeigen is not defined" - ein Aufruf blieb stehen, als die Funktion
beim Umbau wegfiel. Das sieht man weder beim Lesen noch an der Syntax: die Datei
ist gültiges Javascript, sie bricht erst beim Benutzen ab. Und weil sie mitten im
Aufbau abbricht, ist danach die halbe Oberfläche tot.

Deshalb hier: alle aufgerufenen Namen sammeln, alle deklarierten dagegenhalten.
Was übrig bleibt, muss ein bekannter Name des Browsers sein - oder es ist ein
Fehler.
"""
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"\n        {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


# Was der Browser von sich aus mitbringt. Keine vollständige Liste - nur das, was
# hier benutzt wird; alles andere soll ja gerade auffallen.
BEKANNT = {
    "window", "document", "console", "navigator", "location", "history", "screen",
    "setTimeout", "clearTimeout", "setInterval", "clearInterval", "requestAnimationFrame",
    "alert", "confirm", "prompt", "fetch", "Promise", "Error", "TypeError", "Object",
    "Array", "String", "Number", "Boolean", "Math", "JSON", "Date", "Map", "Set",
    "RegExp", "Symbol", "Infinity", "NaN", "undefined", "null", "true", "false",
    "parseInt", "parseFloat", "isNaN", "encodeURIComponent", "decodeURIComponent",
    "URLSearchParams", "URL", "FormData", "FileReader", "Blob", "File", "Uint8Array",
    "ArrayBuffer", "TextEncoder", "TextDecoder", "btoa", "atob", "structuredClone",
    "localStorage", "sessionStorage", "Event", "CustomEvent", "Range", "Selection",
    "Intl", "performance", "crypto", "queueMicrotask", "AbortController",
    "if", "for", "while", "switch", "catch", "return", "typeof", "function", "new",
    "await", "async", "of", "in", "do", "else", "try", "finally", "throw", "case",
}

js = (WURZEL / "app/oberflaeche/mappe.js").read_text(encoding="utf-8")

# Richtig parsen statt Textsuche: ein Regex haelt Parameter, Objektfelder und
# Zerlegungen nicht auseinander und meldet dann Fehler, wo keine sind.
import esprima

baum = esprima.parseScript(js, {"range": True})
deklariert, gerufen = set(), set()


def namen_aus(ziel):
    """Alle Namen, die eine Zuweisung oder ein Parameter einfuehrt."""
    if ziel is None:
        return
    art = getattr(ziel, "type", None)
    if art == "Identifier":
        deklariert.add(ziel.name)
    elif art == "ObjectPattern":
        for e in ziel.properties or []:
            namen_aus(getattr(e, "value", None) or getattr(e, "argument", None))
    elif art == "ArrayPattern":
        for e in ziel.elements or []:
            namen_aus(e)
    elif art in ("AssignmentPattern",):
        namen_aus(ziel.left)
    elif art == "RestElement":
        namen_aus(ziel.argument)


def gehen(knoten):
    art = getattr(knoten, "type", None)
    if art in ("FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression"):
        namen_aus(getattr(knoten, "id", None))
        for p_ in knoten.params or []:
            namen_aus(p_)
    elif art == "VariableDeclarator":
        namen_aus(knoten.id)
    elif art == "ClassDeclaration":
        namen_aus(getattr(knoten, "id", None))
    elif art == "CatchClause":
        namen_aus(getattr(knoten, "param", None))
    elif art == "Property" and not getattr(knoten, "computed", False):
        # Objektfelder sind keine freien Namen - merker.holen() ist kein Aufruf
        # einer Funktion namens "holen".
        namen_aus(getattr(knoten, "key", None))
    elif art == "CallExpression":
        ziel = knoten.callee
        if getattr(ziel, "type", None) == "Identifier":
            gerufen.add(ziel.name)

    for feld in dir(knoten):
        if feld.startswith("_") or feld in ("type", "range", "name", "value", "raw"):
            continue
        wert = getattr(knoten, feld, None)
        if isinstance(wert, list):
            for e in wert:
                if hasattr(e, "type"):
                    gehen(e)
        elif hasattr(wert, "type"):
            gehen(wert)


gehen(baum)

offen = sorted(n for n in gerufen if n not in deklariert and n not in BEKANNT)
pruefe("jeder Aufruf in mappe.js hat eine Funktion dazu", not offen,
       "ohne Definition: " + ", ".join(offen) if offen else "")
pruefe("es wird ueberhaupt etwas geprueft", len(gerufen) > 40, f"{len(gerufen)} Aufrufe gefunden")


# --- Jede benutzte Farbe muss es geben ---------------------------------------
#
# Eine Farbe, die es nicht gibt, ist kein Fehler: die Regel faellt einfach aus,
# und das Element bekommt die Vorgabe des Browsers. In einer dunklen
# Oberflaeche heisst das weiss. Genau so ist --flaeche sechs Stellen lang
# unbemerkt geblieben.
css = (WURZEL / "app/oberflaeche/stil.css").read_text(encoding="utf-8")
definiert = set(re.findall(r"^\s*(--[a-z-]+)\s*:", css, re.M))
benutzt = set(re.findall(r"var\((--[a-z-]+)", css))
# Was die Oberflaeche selbst setzt (etwa die Farbe eines Stifts), steht nicht
# im Stil - das hat einen Ersatzwert und ist in Ordnung.
mit_ersatz = set(re.findall(r"var\((--[a-z-]+)\s*,", css))
fehlend = sorted(benutzt - definiert - mit_ersatz - {"--stiftfarbe"})
pruefe("jede benutzte Farbe ist auch definiert", not fehlend, ", ".join(fehlend))
pruefe("es werden ueberhaupt Farben geprueft", len(benutzt) > 5, f"{len(benutzt)} benutzt")

# --- Kein Weg zweimal --------------------------------------------------------
#
# In JavaScript ist ein doppelter Schluessel im Woerterbuch kein Fehler: der
# spaetere gewinnt stillschweigend. So hat "GET /api/version" (Updatepruefung)
# den Weg zur Seitenfassung bekommen - und die Updatepruefung meldete einen
# TypeError, der nach einem Fehler im Updater aussah und keiner war.
block = js[js.index("const WEGE = {"):js.index("};", js.index("const WEGE = {"))]
wege = re.findall(r"^\s*'([^']+)':", block, re.M)
doppelt = sorted({w for w in wege if wege.count(w) > 1})
pruefe("kein Weg steht zweimal in der Tabelle", not doppelt, ", ".join(doppelt))
pruefe("es gibt ueberhaupt Wege", len(wege) > 15, f"{len(wege)} gefunden")

# --- Kennungen: $('#knopf') muss es in index.html wirklich geben --------------
#
# Steht da ein Tippfehler, wirft addEventListener beim Laden "of null" - und das
# reisst das ganze Skript mit, nicht nur den einen Knopf. Dann ist das Fenster
# leer und nichts sagt, warum. Statisches Nachsehen ist hier billig.
html = (WURZEL / "app/oberflaeche/index.html").read_text(encoding="utf-8")
vorhanden = set(re.findall(r'id="([^"]+)"', html))
# Was die Oberflaeche selbst zur Laufzeit baut und erst danach anspricht.
GEBAUT = {"schwebe"}
gesucht = set(re.findall(r"""\$\(['"]#([A-Za-z0-9_-]+)['"]\)""", js))
fehlende = sorted(gesucht - vorhanden - GEBAUT)
pruefe("jede angesprochene Kennung steht in index.html", not fehlende,
       "fehlt: " + ", ".join(fehlende) if fehlende else "")
pruefe("es werden ueberhaupt Kennungen geprueft", len(gesucht) > 20, f"{len(gesucht)} gefunden")

print()
print("alle Namen gehen auf" if not fehler else f"{len(fehler)} FEHLER")
sys.exit(1 if fehler else 0)
