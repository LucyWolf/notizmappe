"""Das Windows-Setup: was installer.conf anstellt.

    .venv/bin/python tests/test_setup.py

Die setup.exe entsteht erst im Workflow auf einem Windows-Läufer. Was dort
hineingeht, entsteht aber hier: template/generate.py baut aus
template/setup.iss und installer.conf das Skript. Fällt dabei etwas aus,
merkt man es erst am fertigen Release - und dann hat die Versionsnummer
schon jemand.

Geprüft wird deshalb das erzeugte Skript, nicht die exe.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
fehler = []


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was
          + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


def bauen(autostart):
    """generate.py in einer Kopie laufen lassen, mit diesem WINDOWS_AUTOSTART.

    In einer Kopie, weil generate.py neben installer.conf nach output/
    schreibt - der Arbeitsbaum soll davon nichts abbekommen.
    """
    ordner = Path(tempfile.mkdtemp(prefix="setupprobe-"))
    shutil.copytree(WURZEL / "template", ordner / "template")
    text = (WURZEL / "installer.conf").read_text(encoding="utf-8")
    text = re.sub(r'^#?WINDOWS_AUTOSTART=.*$', "", text, flags=re.M)
    if autostart is not None:
        text += f'\nWINDOWS_AUTOSTART="{autostart}"\n'
    (ordner / "installer.conf").write_text(text, encoding="utf-8")
    lauf = subprocess.run([sys.executable, str(ordner / "template/generate.py"),
                           "windows", "LucyWolf/notizmappe", "v9.9.9"],
                          capture_output=True, text=True)
    datei = ordner / "output/setup.iss"
    aus = datei.read_text(encoding="utf-8-sig") if datei.is_file() else ""
    shutil.rmtree(ordner, ignore_errors=True)
    return lauf, aus


print("Autostart beim Anmelden")
lauf, an = bauen("an")
pruefe("das Skript entsteht", lauf.returncode == 0, lauf.stderr[-300:])
# Ein übrig gebliebenes @PLATZHALTER@ lässt generate.py selbst auffliegen -
# hier wird nur nachgesehen, dass das auch wirklich so ist.
pruefe("und es steht kein Platzhalter mehr drin",
       not re.search(r"@[A-Z_]+@", an), re.findall(r"@[A-Z_]+@", an))
pruefe("es gibt die Aufgabe autostart", 'Name: "autostart"' in an)
pruefe("mit der eingebauten Meldung, also in beiden Sprachen",
       "{cm:AutoStartProgram,{#AppName}}" in an)
pruefe('bei "an" ist der Haken vorgesetzt',
       not re.search(r'Name: "autostart".*unchecked', an), an)
# Eine Verknüpfung im Autostart-Ordner, kein Run-Schlüssel: Inno führt jedes
# [Icons] mit und räumt es beim Deinstallieren weg. Ein Registrierungs-
# eintrag bliebe stehen und startete ein Programm, das es nicht mehr gibt.
pruefe("die Verknüpfung liegt im Autostart-Ordner des Benutzers",
       r"Name: \"{userstartup}\{#AppName}\"" in an.replace('"', '\\"'), None)
pruefe("sie hängt an der Aufgabe", "Tasks: autostart" in an)
pruefe("und es wird nichts in die Registrierung geschrieben",
       "[Registry]" not in an and "CurrentVersion\\Run" not in an)

print("\nUnd wenn man ihn nicht will")
_, frage = bauen("frage")
pruefe('bei "frage" steht der Haken da, aber leer',
       bool(re.search(r'Name: "autostart".*unchecked', frage)), frage)
_, aus = bauen(None)
pruefe("ohne Eintrag gibt es die Aufgabe nicht", 'Name: "autostart"' not in aus)
pruefe("und auch keine Verknüpfung", "userstartup" not in aus)
pruefe("der Rest bleibt, wie er war",
       "{cm:CreateDesktopIcon}" in aus and "[Icons]" in aus)

# --- Versionsressource -------------------------------------------------------
#
# Eine .exe ohne Versionsressource hat weder Firmen- noch Produktnamen - in
# den Eigenschaften steht nichts. Für die Heuristik von Defender ist das ein
# Signal, und zusammen mit "unsigniert, frisch gebaut, kaum verbreitet"
# reicht es für einen Fehlalarm. Das nimmt die Erkennung nicht von selbst
# weg - dafür muss die Datei bei Microsoft eingereicht werden -, aber es
# nimmt einen der Gründe.
print("\nVersionsressource der exe")
import importlib.util                                         # noqa: E402
lade = importlib.util.spec_from_file_location("versionsdatei", WURZEL / "tools/versionsdatei.py")
vd = importlib.util.module_from_spec(lade)
lade.loader.exec_module(vd)

pruefe("1.2.31 wird zu vier Zahlen", vd.vierer("1.2.31") == (1, 2, 31, 0), vd.vierer("1.2.31"))
pruefe("auch mit weniger Stellen", vd.vierer("2") == (2, 0, 0, 0), vd.vierer("2"))
pruefe("und mit zu vielen", vd.vierer("1.2.3.4.5") == (1, 2, 3, 4), vd.vierer("1.2.3.4.5"))
# Eine Fassung mit Buchstaben darf die Datei nicht unbrauchbar machen -
# PyInstaller wertet sie als Python aus, ein 'beta' darin bricht den Bau ab.
pruefe("Buchstaben fliegen raus statt den Bau umzuwerfen",
       vd.vierer("1.2.3beta") == (1, 2, 3, 0), vd.vierer("1.2.3beta"))

fassung = (WURZEL / "app/VERSION").read_text(encoding="utf-8").strip()
roh = vd.text(fassung)
# PyInstaller liest die Datei als Python mit seinen eigenen Klassen. Hier
# werden sie nachgebaut: faellt dabei etwas um, faellt es auch dort um.
gebaut = {}


def merker(name):
    def innen(*args, **kwargs):
        gebaut.setdefault(name, []).append((args, kwargs))
        return (name, args, kwargs)
    return innen


raum = {n: merker(n) for n in ("VSVersionInfo", "FixedFileInfo", "StringFileInfo",
                               "StringTable", "StringStruct", "VarFileInfo", "VarStruct")}
try:
    exec(compile(roh, "version.txt", "exec"), raum)           # noqa: S102
    ging = True
except Exception as f:                                        # noqa: BLE001
    ging = False
    print("   ", f)
pruefe("die Datei lässt sich auswerten, so wie PyInstaller es tut", ging)

felder = {a[0]: a[1] for (a, _) in gebaut.get("StringStruct", [])}
for name in ("CompanyName", "ProductName", "FileDescription", "FileVersion",
             "LegalCopyright", "OriginalFilename", "ProductVersion"):
    pruefe(f"{name} steht drin", bool(felder.get(name)), felder.get(name))
pruefe("die Nummer stimmt mit app/VERSION überein",
       felder.get("FileVersion") == fassung, (felder.get("FileVersion"), fassung))
# Ohne den Translation-Block zeigt Windows die Felder gar nicht an.
pruefe("und die Sprachangabe fehlt nicht", bool(gebaut.get("VarStruct")))

print("\nDie exe wird damit gebaut")
lauf_yml = (WURZEL / ".github/workflows/release.yml").read_text(encoding="utf-8")
pruefe("der Workflow erzeugt die Datei", "tools/versionsdatei.py" in lauf_yml)
pruefe("und gibt sie PyInstaller mit", "--version-file windows/version.txt" in lauf_yml)
# UPX packt die exe und sieht damit noch mehr nach Packer aus. PyInstaller
# nimmt es, wenn es es findet - auf dem Laeufer also mal so, mal so.
pruefe("und packt nicht zusätzlich mit UPX", "--noupx" in lauf_yml)

print("\nUnd das Setup selbst")
pruefe("setup.exe bekommt eine Versionsnummer", "VersionInfoVersion=" in an)
pruefe("einen Herausgeber", "VersionInfoCompany=LucyWolf" in an and "AppPublisher=LucyWolf" in an)
pruefe("und einen Produktnamen", "VersionInfoProductName=" in an)

print("\nWas in installer.conf steht")
conf = (WURZEL / "installer.conf").read_text(encoding="utf-8")
pruefe("Autostart ist für die Notizmappe eingeschaltet",
       bool(re.search(r'^WINDOWS_AUTOSTART="(an|frage)"', conf, re.M)),
       [z for z in conf.splitlines() if "AUTOSTART" in z])

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
sys.exit(1 if fehler else 0)
