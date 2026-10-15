"""Die Sperre von beiden Seiten: Tresor allein und die ganze Kette durch die Brücke.

    .venv/bin/python tests/test_sperre.py

Worauf es ankommt: zugesperrt heißt **wirklich** zu. Nicht "die Oberfläche zeigt
nichts", sondern: wer die Datei auf der Platte liest, findet keinen Notiztext,
und wer die Brücke aufruft, bekommt eine Abfuhr statt Inhalt. Beides wird hier am
fertigen Ergebnis geprüft, nicht an Zwischenschritten.
"""
import base64
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DATEN = Path(tempfile.mkdtemp(prefix="notizen-sperre-"))
KONFIG = Path(tempfile.mkdtemp(prefix="notizen-sperre-konfig-"))
os.environ["NOTIZEN_ORDNER"] = str(DATEN)
os.environ["NOTIZMAPPE_KONFIG"] = str(KONFIG)
os.environ["NOTIZMAPPE_OPTIONEN"] = str(KONFIG / "optionen.json")
os.environ["NOTIZMAPPE_QUELLE"] = "http://127.0.0.1:1"
sys.path.insert(0, str(WURZEL / "app"))

import bruecke as bruecke_modul
import speicher
import tresor

b = bruecke_modul.Bruecke()
fehler = []
GEHEIM = "Mein Tagebuch, Zeile mit Inhalt"


def pruefe(was, bedingung, extra=""):
    print(("  ok  " if bedingung else "FEHLER") + "  " + was + (f"   {extra}" if extra and not bedingung else ""))
    if not bedingung:
        fehler.append(was)


# --- Der Tresor allein -------------------------------------------------------
print("Tresor")
t = Path(tempfile.mkdtemp(prefix="notizen-tresor-"))
rettung = tresor.einrichten(t, "passwort123")
pruefe("Wiederherstellungsschlüssel kommt zurück", len(rettung) > 20 and "-" in rettung)
pruefe("Tresordatei liegt im Datenordner", (t / ".tresor.json").is_file())
pruefe("Passwort selbst steht nicht in der Tresordatei",
       "passwort123" not in (t / ".tresor.json").read_text(encoding="utf-8"))
pruefe("Wiederherstellungsschlüssel steht nicht in der Tresordatei",
       rettung not in (t / ".tresor.json").read_text(encoding="utf-8"))

kapsel = tresor.verschluesseln(GEHEIM.encode())
pruefe("Verschlüsseltes enthält den Text nicht", GEHEIM.encode() not in kapsel)
pruefe("Zweimal verschlüsseln gibt nicht dasselbe (eigener Nonce)",
       tresor.verschluesseln(b"x") != tresor.verschluesseln(b"x"))
tresor.sperren()
try:
    tresor.entschluesseln(kapsel)
    pruefe("Zugesperrt lässt sich nichts entschlüsseln", False)
except tresor.TresorFehler:
    pruefe("Zugesperrt lässt sich nichts entschlüsseln", True)

try:
    tresor.entsperren(t, "passwort124")
    pruefe("Falsches Passwort wird abgewiesen", False)
except tresor.TresorFehler:
    pruefe("Falsches Passwort wird abgewiesen", True)

tresor.entsperren(t, "passwort123")
pruefe("Mit Passwort wieder lesbar", tresor.entschluesseln(kapsel).decode() == GEHEIM)
tresor.sperren()
tresor.entsperren(t, rettung)
pruefe("Mit Wiederherstellungsschlüssel wieder lesbar", tresor.entschluesseln(kapsel).decode() == GEHEIM)

tresor.passwort_aendern(t, "passwort123", "ganzneu999")
tresor.sperren()
tresor.entsperren(t, "ganzneu999")
pruefe("Nach Passwortwechsel öffnet das neue Passwort", tresor.entschluesseln(kapsel).decode() == GEHEIM)
try:
    tresor.entsperren(t, "passwort123")
    pruefe("Nach Passwortwechsel ist das alte wertlos", False)
except tresor.TresorFehler:
    pruefe("Nach Passwortwechsel ist das alte wertlos", True)
# Der Datenschluessel bleibt derselbe - sonst muessten alle Notizen neu geschrieben werden
tresor.sperren(); tresor.entsperren(t, rettung)
pruefe("Rettungsschlüssel gilt nach Passwortwechsel weiter",
       tresor.entschluesseln(kapsel).decode() == GEHEIM)

neu_rettung = tresor.rettung_erneuern(t, "ganzneu999")
tresor.sperren()
try:
    tresor.entsperren(t, rettung)
    pruefe("Erneuerter Schlüssel macht den alten wertlos", False)
except tresor.TresorFehler:
    pruefe("Erneuerter Schlüssel macht den alten wertlos", True)
tresor.entsperren(t, neu_rettung)
pruefe("Der neue Rettungsschlüssel öffnet", tresor.entschluesseln(kapsel).decode() == GEHEIM)
tresor.sperren()
shutil.rmtree(t, ignore_errors=True)

# --- Die ganze Kette durch die Brücke ----------------------------------------
print("\nBrücke: Notizen anlegen, dann zusperren")
buch = b.notizbuch_anlegen("Privat")["name"]
absch = b.abschnitt_anlegen(buch, "Tagebuch")["name"]
seite = b.seite_anlegen(buch, absch, "Montag")["name"]
gelesen = b.seite_lesen(buch, absch, seite)
b.seite_speichern({"notizbuch": buch, "abschnitt": absch, "name": seite, "rev": gelesen["rev"],
                   "titel": "Montag",
                   "elemente": [{"typ": "text", "x": 10, "y": 10, "b": 300, "html": GEHEIM}]})
bild = base64.b64encode(bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 40 + b"GEHEIMESBILD").decode()
anhang = b.anhang_ablegen(buch, absch, seite, "bild.png", bild)
pruefe("Anhang abgelegt", "fehler" not in anhang, anhang)

seitendatei = DATEN / buch / absch / f"{seite}.json"
anhangdatei = DATEN / buch / absch / f"{seite}.anhang" / anhang["datei"]
pruefe("Ohne Sperre steht der Text im Klartext auf der Platte",
       GEHEIM.encode() in seitendatei.read_bytes())

stand = b.sperre_stand()
pruefe("Vorher: keine Sperre eingerichtet", stand["eingerichtet"] is False, stand)
pruefe("Zu kurzes Passwort wird abgelehnt", "fehler" in b.sperre_einrichten({"passwort": "kurz"}))
pruefe("Nach abgelehntem Passwort ist nichts eingerichtet", not speicher.verschluesselt())

an = b.sperre_einrichten({"passwort": "notizmappe!1"})
pruefe("Sperre eingeschaltet", "fehler" not in an, an)
pruefe("Rettungsschlüssel kommt mit", bool(an.get("rettung")))
pruefe("Vorhandene Dateien wurden umgestellt", an.get("umgestellt", 0) >= 2, an)
pruefe("Seitendatei enthält den Text nicht mehr", GEHEIM.encode() not in seitendatei.read_bytes())
pruefe("Seitendatei ist als verschlüsselt erkennbar",
       tresor.ist_verschluesselt(seitendatei.read_bytes()))
pruefe("Anhang enthält seinen Inhalt nicht mehr", b"GEHEIMESBILD" not in anhangdatei.read_bytes())

print("\nOffen weiterarbeiten")
auf = b.seite_lesen(buch, absch, seite)
pruefe("Seite lesen geht weiter", auf["elemente"][0]["html"].find("Inhalt") > 0, auf)
pruefe("Titel im Baum stimmt noch",
       any(s["titel"] == "Montag" for bu in b.baum()["notizbuecher"]
           for a in bu["abschnitte"] for s in a["seiten"]))
pruefe("Bild kommt durch die Brücke", "daten" in b.anhang_bild(buch, absch, seite, anhang["datei"]))
b.seite_speichern({"notizbuch": buch, "abschnitt": absch, "name": seite, "rev": auf["rev"],
                   "titel": "Montag",
                   "elemente": [{"typ": "text", "x": 1, "y": 1, "b": 200, "html": "Neu geschrieben"}]})
pruefe("Neu Geschriebenes landet verschlüsselt",
       b"Neu geschrieben" not in seitendatei.read_bytes()
       and tresor.ist_verschluesselt(seitendatei.read_bytes()))

print("\nZugesperrt")
b.sperren()
pruefe("Stand sagt: zu", b.sperre_stand()["offen"] is False)
for was, antwort in (("Baum", b.baum()),
                     ("Seite lesen", b.seite_lesen(buch, absch, seite)),
                     ("Seite schreiben", b.seite_speichern(
                         {"notizbuch": buch, "abschnitt": absch, "name": seite, "rev": 1,
                          "titel": "x", "elemente": []})),
                     ("Bild holen", b.anhang_bild(buch, absch, seite, anhang["datei"])),
                     ("Anhang ablegen", b.anhang_ablegen(buch, absch, seite, "z.png", bild)),
                     ("Notizbuch anlegen", b.notizbuch_anlegen("Heimlich")),
                     ("Abschnitt anlegen", b.abschnitt_anlegen(buch, "Heimlich")),
                     ("Seite anlegen", b.seite_anlegen(buch, absch, "Heimlich")),
                     ("Umbenennen", b.seite_umbenennen(buch, absch, seite, "Anders")),
                     ("Löschen", b.loeschen("seite", [buch, absch, seite]))):
    pruefe(f"{was} abgewiesen", antwort.get("art") == "zu", antwort)
pruefe("Zugesperrt wurde nichts angelegt", not (DATEN / "Heimlich").exists())

print("\nWieder auf")
pruefe("Falsches Passwort abgewiesen", "fehler" in b.entsperren({"geheim": "notizmappe!2"}))
pruefe("Nach Fehlversuch immer noch zu", b.sperre_stand()["offen"] is False)
pruefe("Richtiges Passwort öffnet", "fehler" not in b.entsperren({"geheim": "notizmappe!1"}))
pruefe("Und die Notiz ist unversehrt",
       b.seite_lesen(buch, absch, seite)["elemente"][0]["html"] == "Neu geschrieben")

b.sperren()
pruefe("Zurücksetzen mit falschem Schlüssel abgewiesen",
       "fehler" in b.sperre_zuruecksetzen({"rettung": "AAAAA-BBBBB", "neu": "dochnicht1"}))
pruefe("Zurücksetzen mit dem Rettungsschlüssel geht",
       "fehler" not in b.sperre_zuruecksetzen({"rettung": an["rettung"], "neu": "dochnicht1"}))
pruefe("Danach ist offen und lesbar",
       b.seite_lesen(buch, absch, seite)["elemente"][0]["html"] == "Neu geschrieben")
b.sperren()
pruefe("Das neu gesetzte Passwort öffnet", "fehler" not in b.entsperren({"geheim": "dochnicht1"}))

print("\nSchlüsseldatei")
vorschlag = b.rettung_ziel()
pruefe("Vorschlag steht in den eigenen Dokumenten",
       vorschlag.get("pfad", "").endswith("notizmappe-wiederherstellungsschluessel.txt")
       and str(Path.home()) in vorschlag["pfad"], vorschlag)
irgendwo = Path(tempfile.mkdtemp(prefix="notizen-schluessel-"))
g = b.rettung_speichern({"rettung": "ABCDE-FGHIJ", "pfad": str(irgendwo / "mein schluessel.txt")})
pruefe("Speichert an den eingegebenen Pfad", "fehler" not in g, g)
pruefe("Der Schlüssel steht wirklich in der Datei",
       "ABCDE-FGHIJ" in (irgendwo / "mein schluessel.txt").read_text(encoding="utf-8"))
g2 = b.rettung_speichern({"rettung": "ABCDE-FGHIJ", "pfad": str(irgendwo)})
pruefe("Nur ein Ordner angegeben: Dateiname kommt dran",
       g2.get("ziel", "").endswith("notizmappe-wiederherstellungsschluessel.txt"), g2)
g3 = b.rettung_speichern({"rettung": "ABCDE-FGHIJ", "pfad": str(irgendwo / "tippfehler" / "k.txt")})
pruefe("Ordner, den es nicht gibt, wird gemeldet statt angelegt",
       "fehler" in g3 and not (irgendwo / "tippfehler").exists(), g3)
g4 = b.rettung_speichern({"rettung": "ABCDE-FGHIJ", "pfad": str(DATEN / "k.txt")})
pruefe("Im Notizordner selbst gibt es eine Warnung", bool(g4.get("warnung")), g4)
pruefe("Gespeichert wird trotzdem - ihre Entscheidung", (DATEN / "k.txt").is_file())
(DATEN / "k.txt").unlink()
pruefe("Ohne Schlüssel wird nichts geschrieben", "fehler" in b.rettung_speichern({"pfad": str(irgendwo)}))
shutil.rmtree(irgendwo, ignore_errors=True)

print("\nZeitsperre und Abschalten")
pruefe("Minuten lassen sich setzen", b.sperre_minuten({"minuten": 15}).get("minuten") == 15)
pruefe("Minuten stehen in den Einstellungen dieses Rechners",
       bruecke_modul.konfig.lesen().get("sperre_minuten") == 15)
pruefe("Unsinn wird gekappt", b.sperre_minuten({"minuten": 99999}).get("minuten") == 24 * 60)

# Die Zeitsperre selbst: nicht warten, sondern den Zeitstempel der letzten
# Benutzung zurueckdrehen. Der naechste Aufruf muss dann zusperren.
b.sperre_minuten({"minuten": 5})
bruecke_modul._letzte_tat = bruecke_modul.time.time() - 6 * 60
pruefe("Nach Zeit ohne Benutzung sperrt der nächste Aufruf zu",
       b.baum().get("art") == "zu")
pruefe("Und der Schlüssel ist aus dem Arbeitsspeicher", not tresor.offen())
b.entsperren({"geheim": "dochnicht1"})
bruecke_modul._letzte_tat = bruecke_modul.time.time()
pruefe("Innerhalb der Zeit bleibt es offen", "fehler" not in b.baum())
b.sperre_minuten({"minuten": 0})
bruecke_modul._letzte_tat = bruecke_modul.time.time() - 10 * 60 * 60
pruefe("Ohne Zeitsperre bleibt es auch nach Stunden offen", "fehler" not in b.baum())

pruefe("Abschalten mit falschem Passwort abgewiesen", "fehler" in b.sperre_aus({"passwort": "nein"}))
pruefe("Nach dem Fehlversuch ist die Sperre noch da", speicher.verschluesselt())
aus = b.sperre_aus({"passwort": "dochnicht1"})
pruefe("Abschalten geht mit dem richtigen Passwort", "fehler" not in aus, aus)
pruefe("Tresordatei ist weg", not (DATEN / ".tresor.json").exists())
pruefe("Seite liegt wieder im Klartext", b"Neu geschrieben" in seitendatei.read_bytes())
pruefe("Anhang liegt wieder im Klartext", b"GEHEIMESBILD" in anhangdatei.read_bytes())
pruefe("Und ist weiter lesbar",
       b.seite_lesen(buch, absch, seite)["elemente"][0]["html"] == "Neu geschrieben")
pruefe("Ohne Sperre ist alles offen", b.sperre_stand()["eingerichtet"] is False)

print("\nAbschalten, wenn eine Datei klemmt")
klemm_buch = b.notizbuch_anlegen("Klemmt")["name"]
klemm_ab = b.abschnitt_anlegen(klemm_buch, "A")["name"]
klemm_seite = b.seite_anlegen(klemm_buch, klemm_ab, "Festgefahren")["name"]
b.sperre_einrichten({"passwort": "klemmpasswort"})
klemmt = DATEN / klemm_buch / klemm_ab / f"{klemm_seite}.json"
os.chmod(klemmt.parent, 0o555)
aus = b.sperre_aus({"passwort": "klemmpasswort"})
os.chmod(klemmt.parent, 0o755)
pruefe("Abschalten bricht ab, wenn etwas klemmt", "fehler" in aus, aus)
pruefe("Und sagt, dass die Sperre an bleibt", "bleibt an" in aus.get("fehler", ""), aus)
pruefe("Der Tresorschlüssel ist NICHT gelöscht", (DATEN / ".tresor.json").exists())
pruefe("Die Notizen sind weiter lesbar",
       "elemente" in b.seite_lesen(klemm_buch, klemm_ab, klemm_seite))
aus = b.sperre_aus({"passwort": "klemmpasswort"})
pruefe("Und wenn es nicht mehr klemmt, geht es", "fehler" not in aus, aus)
pruefe("Jetzt ist der Schlüssel weg", not (DATEN / ".tresor.json").exists())

print("\nHalb umgestellt (Abbruch mitten im Verschlüsseln)")
an2 = b.sperre_einrichten({"passwort": "nochmal!!12"})
pruefe("Zweites Einschalten geht", "fehler" not in an2, an2)
# Eine Datei absichtlich auf Klartext zuruecksetzen: so sieht es aus, wenn das
# Umstellen mitten im Lauf abgebrochen ist. Lesen muss trotzdem gehen.
seitendatei.write_bytes(b'{"titel": "Montag", "elemente": [], "rev": 9}')
pruefe("Eine Klartextdatei im verschlüsselten Ordner ist weiter lesbar",
       b.seite_lesen(buch, absch, seite).get("rev") == 9)
pruefe("Der zweite Lauf holt sie nach", speicher.umstellen(True)["getan"] == 1)
pruefe("Jetzt ist sie verschlüsselt", tresor.ist_verschluesselt(seitendatei.read_bytes()))

print()
print("alles gruen" if not fehler else f"{len(fehler)} FEHLER:\n - " + "\n - ".join(fehler))
shutil.rmtree(DATEN, ignore_errors=True)
shutil.rmtree(KONFIG, ignore_errors=True)
sys.exit(1 if fehler else 0)
