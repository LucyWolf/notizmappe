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

# --- Der Menüeintrag unter Linux ---------------------------------------------
#
# Die Arbeitsfläche findet das Symbol nur, wenn Fenster und Menüeintrag
# denselben Namen tragen:
#
#   X11      WM_CLASS des Fensters  ==  StartupWMClass im .desktop
#   Wayland  die Kennung (app_id)   ==  Dateiname der .desktop
#
# Passt das nicht, malt die Arbeitsfläche einen Buchstaben in einen Kreis -
# so wie unter Linux bis 1.2.33. Beides steht an zwei Stellen, in fenster.py
# und in tools/install.sh, und läuft ohne diese Prüfung auseinander.
print("\nFenster und Menüeintrag heißen gleich")
import importlib.util as _il                                  # noqa: E402
_lade = _il.spec_from_file_location("fenster_probe", WURZEL / "app/fenster.py")
_f = _il.module_from_spec(_lade)
import sys as _sys                                            # noqa: E402
_sys.path.insert(0, str(WURZEL / "app"))
_lade.loader.exec_module(_f)
install = (WURZEL / "tools/install.sh").read_text(encoding="utf-8")

pruefe("das Fenster setzt seine Kennung selbst", "_kennung_setzen()" in
       (WURZEL / "app/fenster.py").read_text(encoding="utf-8"))
pruefe("und zwar bevor es aufgeht",
       (WURZEL / "app/fenster.py").read_text(encoding="utf-8").index("_kennung_setzen()")
       < (WURZEL / "app/fenster.py").read_text(encoding="utf-8").index("webview.create_window"))
pruefe("die Klasse steht so im Menüeintrag",
       f"StartupWMClass={_f.KLASSE}" in install, _f.KLASSE)
pruefe("und die Kennung ist der Dateiname der .desktop",
       f"/applications/{_f.KENNUNG}.desktop" in install, _f.KENNUNG)
pruefe("das Symbol liegt unter demselben Namen",
       f"/apps/{_f.KENNUNG}.png" in install and f"SYMBOL_NAME={_f.KENNUNG}" in install)
# Ohne gi passiert nichts - das Fenster laeuft dann ueber Qt oder den
# Browser. Umfallen darf es deswegen nicht.
pruefe("ohne PyGObject faellt nichts um", isinstance(_f._kennung_setzen(), str))

# --- Und wenn der Menüeintrag fehlt ------------------------------------------
#
# Der gleiche Name genügt nicht: zeigt der Eintrag auf ein Symbol, das es
# nicht gibt, bleibt der Platz leer - so wie in 1.2.34. Deshalb sieht das
# Fenster beim Start nach und legt nach, was fehlt. Hier läuft das in einem
# eigenen XDG_DATA_HOME, damit es den echten Menüordner nicht anfasst.
print("\nDas Fenster legt sein Symbol selbst nach")
import os as _os                                             # noqa: E402

_heim = Path(tempfile.mkdtemp(prefix="symbolprobe-"))
_vorher = _os.environ.get("XDG_DATA_HOME")
_os.environ["XDG_DATA_HOME"] = str(_heim)


def eintrag_legen(exec_zeile, icon=None, klasse=None):
    """Einen Menüeintrag hinlegen, wie ihn der Installer schreibt."""
    d = _f._menueintrag()
    d.parent.mkdir(parents=True, exist_ok=True)
    d.write_text("[Desktop Entry]\nType=Application\nName=Notizmappe\n"
                 f"StartupWMClass={klasse or _f.KLASSE}\n"
                 f"Exec={exec_zeile}\nTryExec={exec_zeile}\n"
                 f"Icon={icon or _f.KENNUNG}\nTerminal=false\n", encoding="utf-8")
    return d


try:
    sitzt, warum = _f._symbol_pruefen()
    pruefe("ohne Eintrag sitzt nichts", not sitzt, warum)
    getan = _f._symbol_nachlegen()
    pruefe("das Symbol liegt trotzdem schon bereit", _f._symboldatei().is_file(), getan)
    # 1.2.35 hat hier selbst einen Eintrag geschrieben, mit einem Exec, das
    # es sich ausgedacht hat - im Menue stand dann ein zweites "Notizmappe",
    # das nichts aufmachte. Welcher Weg wirklich startet, weiss nur der
    # Installer.
    pruefe("aber kein Menüeintrag wird erfunden", not _f._menueintrag().is_file(), getan)
    pruefe("und es steht im Protokoll, warum nicht", "Installer" in getan, getan)

    # Der Notnagel des Installers: liegt im Paket kein Symbol, schreibt er
    # einen fremden Namen aus dem Symbolthema. Ob der aufgeht, weiss hier
    # niemand - also wird er durch unseren ersetzt, der Rest bleibt stehen.
    vorlage = eintrag_legen(sys.executable, icon="accessories-text-editor")
    alt = vorlage.read_text(encoding="utf-8")
    _f._symboldatei().unlink()
    sitzt, warum = _f._symbol_pruefen()
    pruefe("ein fremder Symbolname gilt nicht als in Ordnung", not sitzt, warum)
    _f._symbol_nachlegen()
    neu = vorlage.read_text(encoding="utf-8")
    pruefe("der fremde Name wird ersetzt", f"\nIcon={_f.KENNUNG}\n" in neu, neu)
    pruefe("das Symbol liegt wieder da", _f._symboldatei().is_file())
    pruefe("der Rest des Eintrags bleibt stehen",
           neu.replace(f"Icon={_f.KENNUNG}", "Icon=accessories-text-editor") == alt)
    sitzt, warum = _f._symbol_pruefen()
    pruefe("jetzt sitzt es", sitzt, warum)
    pruefe("und ein zweiter Lauf ändert nichts mehr",
           _f._symbol_nachlegen() == "nichts zu tun", _f._symbol_nachlegen())

    # --- Den Eintrag von 1.2.35 wieder loswerden ---------------------------
    print("\nEin Menüeintrag, der nichts startet, kommt weg")
    pruefe("ein Eintrag, der etwas startet, bleibt stehen",
           _f._toten_eintrag_entfernen() == "" and vorlage.is_file())
    eintrag_legen(str(_heim / "gibtsnicht/notizmappe"))
    getan = _f._toten_eintrag_entfernen()
    pruefe("einer mit totem Exec kommt weg", not _f._menueintrag().is_file(), getan)
    pruefe("und es steht da, woran es lag", "gibtsnicht" in getan, getan)
    # Ein Eintrag, der nicht von uns stammt, wird nicht angefasst - auch
    # dann nicht, wenn sein Exec ins Leere zeigt. Das ist nicht unsere Datei.
    eintrag_legen(str(_heim / "gibtsnicht/fremd"), klasse="EtwasAnderes")
    pruefe("ein fremder Eintrag bleibt unangetastet",
           _f._toten_eintrag_entfernen() == "" and _f._menueintrag().is_file())
    # Ein Befehl ohne Pfad wird im PATH gesucht, so wie die Arbeitsflaeche
    # es auch tut - sonst flöge jeder Eintrag raus, der "sh" aufruft.
    eintrag_legen("sh")
    pruefe("ein Befehl aus dem PATH zählt als vorhanden",
           _f._toten_eintrag_entfernen() == "" and _f._menueintrag().is_file())
finally:
    if _vorher is None:
        _os.environ.pop("XDG_DATA_HOME", None)
    else:
        _os.environ["XDG_DATA_HOME"] = _vorher
    shutil.rmtree(_heim, ignore_errors=True)

# Das Symbol, das pywebview ans Fenster haengt, ist unter Wayland unsichtbar -
# der Weg ueber den Menueeintrag ist der einzige, der dort traegt. Beides steht
# im Protokoll, sonst ist "das Symbol fehlt" wieder eine Frage ans Raten.
quelle = (WURZEL / "app/fenster.py").read_text(encoding="utf-8")
pruefe("beim Start wird nachgesehen", "_symbol_pruefen()" in quelle)
pruefe("und zwar bevor das Fenster aufgeht",
       quelle.index("_symbol_pruefen()") < quelle.index("webview.create_window"))
pruefe("das Symbol liegt im Paket", (WURZEL / "app/oberflaeche/icon.png").is_file())
# 1.2.35 hing daran: ging beim Symbol etwas schief, ging gar kein Fenster
# auf. Ein Programm ohne Bild im Menue ist unschoen, eines das nicht startet
# ist kaputt. Deshalb steht der ganze Block in einem Netz.
_ab = quelle.index('notieren("Fensterkennung: "')
pruefe("und das Fenster geht auf, auch wenn dabei etwas schiefgeht",
       "except Exception" in quelle[_ab:quelle.index("webview.create_window")],
       quelle[_ab:quelle.index("webview.create_window")])

print("\nWas in installer.conf steht")
conf = (WURZEL / "installer.conf").read_text(encoding="utf-8")
pruefe("Autostart ist für die Notizmappe eingeschaltet",
       bool(re.search(r'^WINDOWS_AUTOSTART="(an|frage)"', conf, re.M)),
       [z for z in conf.splitlines() if "AUTOSTART" in z])

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
sys.exit(1 if fehler else 0)
