"""Nachweisen, dass hier kein Server steckt.

    .venv/bin/python tests/test_kein_server.py

Die Notizmappe ist ein Desktop-Programm: sie öffnet keinen Port, hört auf keine
Adresse und spricht kein HTTP mit sich selbst. Das lässt sich nicht einmal
einrichten und dann vergessen - es muss geprüft bleiben, sonst schleicht sich
beim nächsten Umbau wieder ein Webserver ein. Genau das ist passiert.

Geprüft wird der Quelltext, nicht das laufende Programm: was nicht im Code steht,
kann auch nicht lauschen.
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


def quellen(*muster):
    for m in muster:
        for p in sorted(WURZEL.glob(m)):
            if any(teil in p.parts for teil in (".git", ".venv", "dist", "output", "__pycache__")):
                continue
            if p.is_file():
                yield p


# --- Keine Webserver-Pakete --------------------------------------------------
VERBOTEN = ("fastapi", "uvicorn", "starlette", "flask", "jinja2", "aiohttp",
            "tornado", "bottle", "werkzeug", "waitress", "gunicorn")

# --- Der Webserver, der mit pywebview mitkommt -------------------------------
#
# pywebview haengt an bottle und laedt es beim Import mit - daran ist nichts zu
# aendern, ohne das Fenster zu verlieren. Gestartet wird dieser Server nur, wenn
# man pywebview eine Datei zu laden gibt statt fertigem HTML. Das tut dieses
# Programm nicht, und beim Start steht es zusaetzlich ausdruecklich da.
fenstertext = (WURZEL / "app/fenster.py").read_text(encoding="utf-8")
pruefe("das Fenster schaltet den mitgelieferten Webserver ausdruecklich ab",
       fenstertext.count("http_server=False") >= 2
       and "http_server=True" not in fenstertext)
pruefe("die Oberflaeche wird als fertiges HTML uebergeben, nicht als Datei",
       "html=" in fenstertext and "url=" not in fenstertext)

anforderungen = (WURZEL / "requirements.txt").read_text(encoding="utf-8").split()
# Eine knappe, ausdrueckliche Liste statt "nur pywebview": was hier nicht steht,
# kommt auch nicht herein. Nachschieben soll auffallen.
# pyOneNote/cabarchive lesen OneNote-Dateien beim Uebernehmen - reines Python,
# keine Netzpakete.
ERLAUBT = {"pywebview", "cryptography", "pyOneNote", "cabarchive"}
pruefe("requirements.txt enthaelt nur das Fenster und die Verschluesselung",
       set(anforderungen) <= ERLAUBT, anforderungen)

for p in quellen("app/*.py", "windows/*.py", "tools/*.py", "tests/*.py"):
    text = p.read_text(encoding="utf-8")
    code = "\n".join(z for z in text.splitlines() if not z.lstrip().startswith("#"))
    for paket in VERBOTEN:
        treffer = re.search(rf"^\s*(import|from)\s+{paket}\b", code, re.M)
        pruefe(f"{p.relative_to(WURZEL)} importiert kein {paket}", not treffer,
               treffer.group(0) if treffer else "")

# --- Nichts, was lauscht -----------------------------------------------------
for p in quellen("app/*.py", "windows/*.py"):
    code = "\n".join(z for z in p.read_text(encoding="utf-8").splitlines()
                     if not z.lstrip().startswith("#"))
    for was, muster in [
        ("bindet keinen Socket", r"\.bind\s*\("),
        ("lauscht nicht", r"\.listen\s*\("),
        ("startet keinen http.server", r"http\.server|HTTPServer|socketserver"),
        ("startet keinen uvicorn", r"uvicorn\.run|uvicorn\.Config"),
        ("nennt keine Lauschadresse", r"0\.0\.0\.0|host\s*=\s*[\"']"),
    ]:
        treffer = re.search(muster, code)
        pruefe(f"{p.relative_to(WURZEL)} {was}", not treffer, treffer.group(0) if treffer else "")

# --- Die Oberfläche redet nicht über das Netz --------------------------------
js = (WURZEL / "app/oberflaeche/mappe.js").read_text(encoding="utf-8")
html = (WURZEL / "app/oberflaeche/index.html").read_text(encoding="utf-8")
for was, muster, wo in [
    ("kein fetch", r"\bfetch\s*\(", js),
    ("kein XMLHttpRequest", r"XMLHttpRequest", js),
    ("kein WebSocket", r"\bWebSocket\b", js),
    ("keine Adresse im Skript", r"https?://127\.0\.0\.1|https?://localhost", js),
    ("keine Adresse in der Seite", r"https?://127\.0\.0\.1|https?://localhost", html),
    ("keine fremden Skripte in der Seite", r'<script[^>]+src=["\']https?:', html),
]:
    treffer = re.search(muster, wo)
    pruefe(f"Oberflaeche: {was}", not treffer, treffer.group(0) if treffer else "")

pruefe("Oberflaeche ruft die Bruecke", "pywebview.api" in js)

# Auch im Text: wer in den Code schaut, soll keine Adressen und keine Rede von
# Servern finden. Das ist keine Kosmetik - es war jedes Mal der Hinweis darauf,
# dass noch etwas uebrig war.
for p in list(quellen("app/*.py")) + list(quellen("app/oberflaeche/*.js", "app/oberflaeche/*.html")):
    text = p.read_text(encoding="utf-8")
    for was, muster in [("keine Adresse 127.0.0.1", r"127\.0\.0\.1"),
                        ("kein localhost", r"localhost"),
                        ("kein ping", r"\bping\b"),
                        # Nicht mehr das Wort allein - seit sie sich mit ihrer
                        # eigenen Notizmappe auf einem Server verbinden kann,
                        # kommt es in der Oberflaeche und in der Bruecke
                        # berechtigt vor. Verboten ist, was einen Server
                        # *macht*: ein Rahmenwerk, ein lauschender Socket.
                        ("nichts, was selbst Server spielt",
                         r"\b(fastapi|uvicorn|starlette|flask|bottle|tornado|waitress"
                         r"|HTTPServer|socketserver|ThreadingHTTPServer)\b"
                         r"|\.listen\(|\.bind\(")]:
        # Zwei Module duerfen ins Netz, und nur sie:
        #   aktualisieren.py  sieht bei GitHub nach Updates
        #   ferne.py          verbindet sich mit ihrer eigenen Notizmappe auf
        #                     einem Server - auf ihren ausdruecklichen Wunsch
        # Der Sinn dieser Pruefung bleibt derselbe: es gibt keinen Server *im*
        # Programm. Es gibt die Moeglichkeit, sich mit einem zu verbinden, und
        # die steht an genau einer Stelle.
        if p.name in ("aktualisieren.py", "ferne.py"):
            continue
        # "http_server=False" ist die Abschaltung selbst - die soll dastehen.
        geprueft = text.replace("http_server=False", "")
        treffer = re.search(muster, geprueft)
        text = geprueft
        pruefe(f"{p.relative_to(WURZEL)}: {was}", not treffer,
               text.splitlines()[text[:treffer.start()].count(chr(10))].strip() if treffer else "")

# --- Keine Server-Dateien ----------------------------------------------------
for name in ("Dockerfile", "docker-compose.yml", ".dockerignore", "starten.sh",
             "app/main.py", "app/konten.py", "app/verbindungen.py",
             "app/templates/anmelden.html", "requirements-server.txt"):
    pruefe(f"{name} gibt es nicht", not (WURZEL / name).exists())

# Der Kern bleibt voellig frei davon. Dort waere schon das Wort ein Zeichen,
# dass wieder etwas abgedriftet ist - diese Module haben mit Netz nichts zu tun.
for name in ("speicher.py", "tresor.py", "reinigen.py", "konfig.py", "einfuhr.py"):
    text = (WURZEL / "app" / name).read_text(encoding="utf-8")
    treffer = re.search(r"[Ss]erver", text)
    pruefe(f"app/{name}: keine Rede von Servern", not treffer,
           treffer.group(0) if treffer else "")

# --- Die Verbindung zum eigenen Server liegt an genau einer Stelle -----------
ferne = (WURZEL / "app/ferne.py").read_text(encoding="utf-8")
pruefe("ferne.py nimmt die Adresse von ihr entgegen, hat keine eingebaute",
       not re.search(r"https?://[a-z0-9.]+", ferne.replace("http://", "").replace("https://", ""))
       and 'konfig.lesen()' in ferne)
pruefe("ferne.py merkt sich kein Passwort",
       "ferne_passwort" not in ferne and "passwort=" not in ferne.replace('"passwort": passwort', ''))
netz = []
for p in quellen("app/*.py"):
    if p.name in ("aktualisieren.py", "ferne.py"):
        continue
    text = p.read_text(encoding="utf-8")
    if re.search(r"^\\s*(import|from)\\s+(urllib|socket|http\\.client|requests|httpx)\\b", text, re.M):
        netz.append(p.name)
pruefe("kein anderes Modul holt sich Netzwerkzeug", not netz, ", ".join(netz))
pruefe("die Bruecke leitet nur die bekannten Methoden weiter",
       "FERN = {" in (WURZEL / "app/bruecke.py").read_text(encoding="utf-8"))

# --- Das Einzige, was ins Netz darf, ist die Update-Prüfung ------------------
akt = (WURZEL / "app/aktualisieren.py").read_text(encoding="utf-8")
pruefe("Updates holen von GitHub, sonst nirgendwoher",
       "api.github.com" in akt and not re.search(r"https?://(?!api\.github\.com)[a-z]", akt))
andere = [p.relative_to(WURZEL) for p in quellen("app/*.py")
          if p.name not in ("aktualisieren.py", "ferne.py")
          and re.search(r"urllib|requests\.|httpx", p.read_text(encoding="utf-8"))]
pruefe("nur aktualisieren.py und ferne.py gehen ins Netz", not andere, andere)

print()
print("kein Server drin" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
sys.exit(1 if fehler else 0)
