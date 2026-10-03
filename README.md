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
- **Import**: WinContest `Datenbank/*.txt`, `*.mdb` (mit mdbtools), `DD3KU/*.EXP`, EDI/REG1TEST,
  ADIF, Call-Listen (`Call;Locator;Name`).
- **Export**: EDI (REG1TEST für die Abgabe), ADIF, CSV, Call-Buch-CSV.
- Responsives Layout (Fenster beliebig skalierbar, auch Handy), hell/dunkel.

## Installation und Start

Voraussetzung: Python 3.10+ auf dem Rechner, der als Server dient (Laptop, Raspberry Pi …).

```bash
pip install -r requirements.txt
python run.py                # http://localhost:8000 – die LAN-Adresse wird beim Start angezeigt
```

Optional: `python run.py --port 8080 --db /pfad/zu/log.db`.
Alle Daten liegen in **einer** SQLite-Datei (`data/contestlogger.db`) – zum Sichern einfach kopieren.

Für den Import von Access-`.mdb`-Dateien wird `mdbtools` benötigt (`apt install mdbtools`);
ohne mdbtools die parallele `.txt` aus dem `Datenbank`-Ordner nehmen.

## Ablauf

1. Beim ersten Aufruf das **Admin-Passwort** festlegen.
2. Jeder Browser gibt einen **Nickname** ein (wird im Chat und je QSO als Operator gespeichert).
3. Unter **Verwaltung** (Admin) Contest anlegen und Stationen mit Passwort einrichten.
   Die Angaben für die EDI-Abgabe (Standort, Verantwortlicher, Antenne …) stehen dort pro Station.
4. Im Reiter **Loggen** Station wählen, mit Stations-Passwort freischalten, loslegen.

Tastatur: `Enter` springt zum nächsten Feld bzw. loggt, `Leertaste` im Rufzeichen springt
zum Locator / zur Nr., `↑`/`↓` wählt Vorschläge, `Esc` leert die Eingabe.

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

## Technik

- Backend: Python, FastAPI, SQLite, WebSockets (`contestlogger/`)
- Frontend: reines HTML/CSS/JS ohne Build-Schritt (`contestlogger/static/`)
- Tests: `python -m pytest`

Die Versionsnummer steht in `contestlogger/__init__.py` und wird in der Oberfläche angezeigt.
