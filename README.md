# ContestLogger

Lokaler, webbasierter Contest-Logger für UKW-Contests (DARC/IARU Region 1) –
gedacht als Nachfolger von DD3KU WinContest. Ein kleiner Python-Server im LAN
ist der zentrale Speicher; geloggt wird von beliebig vielen Rechnern, Tablets
oder Handys im Browser. Kein Internet nötig, keine Accounts.

© Lars Hölker

## Funktionen

- **Mehrere Stationen pro Contest** (z. B. 2 m und 70 cm), jede mit eigenem Rufzeichen,
  Locator, Band, Passwort und Seriennummer. Freischalten per Passwort, Umschalten jederzeit.
- **Live-Scoreboard**: alle Stationen sehen gegenseitig QSOs, Punkte, Großfelder, ODX, Rate.
- **Loggen**: Rufzeichen, Locator, RST gegeben/erhalten, Nr. gegeben (automatisch hochzählend,
  pro Station rücksetzbar), Nr. erhalten, Kommentar. Zeit immer **UTC**.
- **Vorschläge beim Tippen** aus dem Call-Buch und allen eigenen (alten und aktuellen) Logs –
  mit Locator, Entfernung, Richtung, „schon gearbeitet“-Hinweis. Das Call-Buch wächst mit jedem QSO.
- **Entfernung in km und Richtung in Grad** vom eigenen Locator, Dupe-Erkennung je Band, Punkte
  wie WinContest (1 Punkt pro angefangenem km – gegen echte WinContest-Logs verifiziert).
- **Bearbeiten und Löschen** von QSOs, Punkte/Dupes werden neu berechnet.
- **Chat** für alle Angemeldeten (nur ein Nickname, kein Account), Anwesenheitsliste.
- **Statistik**: QSOs/Punkte pro Stunde, Entfernungsverteilung, Richtungsrose, Großfelder,
  Länder, Top-10-ODX, Operatoren.
- **Import**: WinContest `Datenbank/*.txt`, `*.mdb` (rein in Python, auch verschlüsselte Jet4-Dateien), `DD3KU/*.EXP`, EDI/REG1TEST,
  ADIF, Call-Listen (`Call;Locator;Name`).
- **Export**: EDI (REG1TEST für die Abgabe), ADIF, CSV, Call-Buch-CSV.
- **Multi-Band-Gesamtwertung** pro Contest (alle Stationen/Bänder zusammen), Countdown bis Contest-Ende.
- **CAT-Anbindung**: `tools/cat_bridge.py` meldet die Frequenz des Funkgeräts (Hamlib rigctld oder flrig)
  an den Server; sie wird bei der Station angezeigt und je QSO gespeichert (ADIF `FREQ`).
- **Backup** automatisch auf dem Server (alle 15 min bei Änderungen, beim Beenden, manuell per Knopf);
  SQLite im WAL-Modus mit synchronem Schreiben – ein Stromausfall beschädigt die Datenbank nicht.
- **Karte** (OpenStreetMap, Leaflet lokal gebündelt): Großkreis-Pfeil vom eigenen zum Partner-Locator mit
  km/Grad, alle QSOs als Punkte; Kachel-Server einstellbar (lokaler Tile-Server für reinen Offline-Betrieb).
- **Tastatur-Makros F1–F8** mit Platzhaltern (`{mycall} {call} {nr} {rst} …`), F9 zeigt die Übersicht,
  Esc stoppt; mit CAT-Bridge `--cw` werden sie als CW über Hamlib gegeben.
- **Töne** (QSO, Dupe, Chat, QSO einer anderen Station), abschaltbar.
- **Contest-Ansicht**: globale Zahlen über alle Stationen/Bänder, Stundenverlauf je Band, Live-Feed,
  Großanzeige-Modus für einen Monitor.
- **Log-Prüfung (Pflicht)** vor dem EDI-Export: Locator/RST/Nummern/Zeiten/Contestzeitraum/EDI-Kopfdaten,
  Klick auf den Fehler öffnet das QSO; Export aller Bänder eines Contests als ZIP.
- **QR-Code** mit der Server-Adresse für Handy/Tablet.
- **Mehrsprachig** (Deutsch, Englisch); eigene Sprachen per JSON-Datei in `data/lang/` (Vorlage in der Verwaltung).
- **Stationsdatenbank** mit Startdaten, wächst mit jedem QSO/Import; Locator/km/Grad werden beim Eingeben
  des Rufzeichens automatisch gesetzt. Optional **externe Abfrage** bei HamQTH oder QRZ.com (wie Wavelog),
  Ergebnisse werden gespeichert. **Ergebnislisten-Import** (DARC/IARU/UKW-CC als HTML, PDF, Text oder URL) mit
  Vorschau füllt die Stationsdatenbank. **Plausibilitätsprüfung** Rufzeichen-Land ↔ Locator (live und bei der Log-Prüfung).
- **DARC-Contest-Hub direkt**: Verwaltung → „DARC-Contest-Hub“ lädt die offiziellen `result.csv` aller
  UKW-Conteste (2017–heute, 500–900 Calls je Contest inkl. ODX-Gegenstationen) in die Stationsdatenbank.
- **ON4KST-Chat** im Chat-Fenster (Reiter KST / An mich / DM): Server hält die Telnet-Verbindung, alle Browser
  chatten unter dem Stations-Call; Nutzerliste mit km/Grad, Antworten per ↩ (`/CQ CALL`), DM-Ansicht je Nutzer,
  Textbausteine mit Platzhaltern per Knopf, Klick auf ein Rufzeichen übernimmt Call + Locator in den Logger.
- **Chat als eigenes Fenster** (↗) – auch von dort landen Klicks auf Rufzeichen im Logger des Hauptfensters.
- Länderkennung weltweit (DXCC-Präfixe), responsives Layout (Fenster beliebig skalierbar, auch Handy), hell/dunkel.

## Installation und Start

Voraussetzung: Python 3.10+ auf dem Rechner, der als Server dient (Laptop, Raspberry Pi …).

```bash
pip install -r requirements.txt
python run.py                # http://localhost:8000 – die LAN-Adresse wird beim Start angezeigt
```

Optional: `python run.py --port 8080 --db /pfad/zu/log.db`.
Alle Daten liegen in **einer** SQLite-Datei (`data/contestlogger.db`) – zum Sichern einfach kopieren.

Access-`.mdb`-Dateien werden ohne Zusatzprogramme gelesen (eingebauter Jet4-Leser).

## Ablauf

1. Beim ersten Aufruf das **Admin-Passwort** festlegen.
2. Jeder Browser gibt einen **Nickname** ein (wird im Chat und je QSO als Operator gespeichert).
3. Unter **Verwaltung** (Admin) Contest anlegen und Stationen mit Passwort einrichten.
   Die Angaben für die EDI-Abgabe (Standort, Verantwortlicher, Antenne …) stehen dort pro Station.
4. Im Reiter **Loggen** Station wählen, mit Stations-Passwort freischalten, loslegen.

Tastatur: `Enter` springt zum nächsten Feld bzw. loggt, `Leertaste` springt Rufzeichen → Nr. erhalten → Locator → Kommentar, `↑`/`↓` wählt Vorschläge, `Esc` leert die Eingabe, `F1`–`F8` Makros, `F9` Makro-Übersicht.

## Eigene Sprache hinzufügen

Verwaltung → Sprachen → „Übersetzungsvorlage herunterladen“. Die Datei enthält alle deutschen
Originaltexte als Schlüssel; die Werte übersetzen, `_name` setzen und als `data/lang/<code>.json`
(z. B. `data/lang/nl.json`) neben der Datenbank speichern, Server neu starten. Leere Werte bleiben deutsch.

## Alte WinContest-Logs komplett übernehmen

```bash
python tools/import_dd3ku.py "D:\Contest"            # ganzer WinContest-Ordner
python tools/import_dd3ku.py "D:\Contest" --callbook-only
```

Jedes Log wird als archivierter Contest mit Station angelegt; alle Rufzeichen und Locator
landen im Call-Buch und erscheinen danach als Vorschläge.

Hinweis: Die Datei `Contest.dat` von WinContest (Call-Datenbank) ist verschlüsselt und kann
nicht direkt gelesen werden. Das Call-Buch wird stattdessen aus den eigenen Logs aufgebaut
und kann zusätzlich mit jeder Call/Locator-Liste (CSV) gefüttert werden.

## Portable Version bauen (ohne Python auf dem Zielrechner)

```bash
build.bat          # Windows  → dist\ContestLogger-<version>-windows-x86_64.zip
./build.sh         # Linux / macOS / Raspberry Pi
```

Das ZIP enthält `ContestLogger[.exe]` (Server + Oberfläche), `ContestLogger-CAT` (CAT-Bridge),
`ContestLogger-Import` (WinContest-Import), `START.txt` und einen leeren `data/`-Ordner. Alles liegt
in einem Ordner, der ganze Ordner ist umziehbar (USB-Stick, anderer Rechner). Doppelklick auf
`ContestLogger.exe` startet den Server und öffnet den Browser; Datenbank, Backups und eigene
Sprachen landen in `data/` neben dem Programm.

Gebaut wird mit PyInstaller **auf dem jeweiligen Betriebssystem** (Windows-Build auf Windows usw.).
Der GitHub-Workflow `.github/workflows/build.yml` baut bei einem Tag `v*` automatisch für
Windows, Linux und macOS und hängt die ZIPs an das Release.

## Als Dienst auf einem Debian-Server (nginx + systemd)

```bash
git clone https://github.com/NoobKeksTV/ContestLogger.git && cd ContestLogger
sudo bash deploy/install.sh
```

Details, HTTPS-Variante, Update und Wiederherstellung: siehe [`deploy/README.md`](deploy/README.md).

## CAT / Frequenz vom Funkgerät

Auf dem Rechner mit dem Transceiver (Hamlib `rigctld` muss laufen, z. B. `rigctld -m 3081 -r COM5`):

```bash
python tools/cat_bridge.py --server http://192.168.1.10:8000 --station 1 --password 70cm --cw
```

`--cw` gibt die F-Tasten-Makros als CW über `rigctld` aus (Hamlib `send_morse`).

Die Stations-ID steht in der Verwaltung. Alternativ `--flrig http://localhost:12345` für flrig.

## ON4KST-Chat

Verwaltung → „ON4KST-Chat“: KST-Rufzeichen, Passwort (eigenes Passwort verwenden – Telnet überträgt es im
Klartext), Raum (2 = 144/432 MHz, 3 = Mikrowelle …), optional „beim Start verbinden“, dann „Verbinden“.
Im Chat-Fenster erscheinen die Reiter **KST** (alles), **An mich** (`/CQ` an das eigene Call oder Call im
Text) und **DM** (nur ein Gesprächspartner). Der Server fragt die Nutzerliste automatisch ab (KST erlaubt
ein Kommando pro Minute); jeder Nutzer mit Locator landet in der Stationsdatenbank.

## Roadmap

- Rotor-Steuerung (Hamlib `rotctld`), Lücken-Liste aus früheren Contests, weitere Wertungsregeln, Cabrillo.

## Technik

- Backend: Python, FastAPI, SQLite, WebSockets (`contestlogger/`)
- Frontend: reines HTML/CSS/JS ohne Build-Schritt (`contestlogger/static/`)
- Tests: `python -m pytest`

Die Versionsnummer steht in `contestlogger/__init__.py` und wird in der Oberfläche angezeigt.
