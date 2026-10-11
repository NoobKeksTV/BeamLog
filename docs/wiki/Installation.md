# Installation

BeamLog gibt es als **portable Version** (kein Python nötig) für Windows, Linux und macOS sowie als Quellcode.
BeamLog hieß bis Version 0.9 „ContestLogger“. **Umstieg von 0.9.x:** Version 1.0 einmal von Hand laden und entpacken – liegt der neue Ordner `BeamLog` neben dem alten Ordner `ContestLogger` (oder darin), übernimmt BeamLog beim ersten Start automatisch eine Kopie von `data/` und `contestlogger.env` (die Datenbank heißt danach `beamlog.db`, die Einstellungen `.env`). Sonst den Ordner `data/` einfach von Hand hinüberkopieren. Ab 1.0 aktualisiert sich BeamLog wieder selbst.

## Portable Version (empfohlen)

1. Das passende ZIP vom [Release](https://github.com/NoobKeksTV/BeamLog/releases/latest) laden:
   `BeamLog-<version>-windows-x86_64.zip`, `…-linux-x86_64.zip` oder `…-macos-arm64.zip`.
2. ZIP entpacken. Im Ordner liegen:

   | Datei | Zweck |
   |---|---|
   | `BeamLog(.exe)` | Server und Oberfläche – das Hauptprogramm |
   | `BeamLog-CAT(.exe)` | Bridge zum Funkgerät (Hamlib rigctld / flrig), meldet Frequenz, sendet CW |
   | `BeamLog-Import(.exe)` | Kommandozeilen-Import eines alten WinContest-Ordners |
   | `start.sh` / `BeamLog-Port8080.bat` | Startskripte |
   | `data/` | Datenbank, Backups, eigene Sprachdateien – **das ist alles, was gesichert werden muss** |
   | `.env.example` | Vorlage für dauerhafte Einstellungen (als `.env` daneben ablegen) |
   | `deploy/` (nur Linux) | Dienst- und nginx-Dateien für einen Debian-Server, siehe [Deploy](Deploy.md) |
   | `START.txt`, `README.md` | Kurzanleitung |

3. `BeamLog.exe` doppelklicken (Windows) bzw. `./BeamLog` starten (Linux/macOS). Der Server läuft auf Port 8000, unter Windows öffnet sich der Browser automatisch.
4. Andere Rechner im LAN: die beim Start angezeigte Adresse eingeben (z. B. `http://192.168.1.10:8000`) oder den QR-Code über das 📱-Symbol im Kopf scannen.

Beim allerersten Start fragt die Oberfläche nach einem **Admin-Passwort**. Damit werden Stationen und Contests verwaltet; Operatoren brauchen es nicht.

![Erster Start: Admin-Passwort](img/erster-start.png)

Der QR-Code (📱 im Kopf) zeigt die Adresse für Handy und Tablet:

![QR-Code](img/qr-code.png)

### Optionen

```
BeamLog --port 8080                  # anderer Port
BeamLog --host 127.0.0.1             # nur lokal (z. B. hinter nginx)
BeamLog --db D:\Contest\data\log.db  # andere Datenbank
BeamLog --backup-min 5               # Sicherung alle 5 Minuten (0 = aus, Standard 15)
BeamLog --public-url http://contest.local/   # Adresse für QR-Code und Links
```

### Dauerhafte Einstellungen: `.env`

Statt jedes Mal Optionen anzugeben, `.env.example` nach `.env` kopieren (neben das Programm) und die Werte eintragen.
Unter Windows im Explorer als `.env.` eingeben (der Punkt am Ende verschwindet) oder in der Eingabeaufforderung
`copy .env.example .env`; unter macOS/Linux sind Dateien mit Punkt vorne versteckt (`ls -a`, im Finder `⌘⇧.`).

> Bis Version 1.0.3 hieß die Datei `beamlog.env`. Eine vorhandene `beamlog.env` benennt BeamLog beim Start
> automatisch in `.env` um (ebenso `install.sh --update` auf dem Server: `/etc/beamlog/beamlog.env` → `/etc/beamlog/.env`).


```ini
HOST=0.0.0.0          # 127.0.0.1 = nur lokal
PORT=8000
#DB=D:\Contest\log.db
BACKUP_MIN=15
#PUBLIC_URL=http://contest.local/
OPEN_BROWSER=1        # Windows: Browser beim Start öffnen
#MAINTAINER=1         # nur für den Betreuer der zentralen Stationsdatenbank
```

Die Datei wird beim Start gemeldet („Konfiguration: …“). Reihenfolge: Kommandozeile überstimmt Umgebungsvariablen `BEAMLOG_<KEY>` (z. B. `BEAMLOG_PORT=8080`), diese überstimmen die Datei. Ein anderer Ort geht mit `--config /pfad/datei.env` oder `BEAMLOG_CONFIG`. Auf einem Server liegt die Datei unter `/etc/beamlog/.env`, siehe [Deploy](Deploy.md).

Umzug auf einen anderen Rechner: einfach den ganzen Ordner kopieren. Die Datenbank liegt in `data/beamlog.db`, Sicherungen in `data/backup/`.

### Linux: Hinweis zu glibc

Das Linux-Binary wird auf Ubuntu 22.04 gebaut und läuft auf Debian 12 (Bookworm), Ubuntu 22.04 und allem Neueren. Auf älteren Systemen (Debian 11) erscheint ein `GLIBC`-Fehler; dort die Quellcode-Variante nutzen.

### macOS

Beim ersten Start blockiert Gatekeeper eventuell das Programm: Rechtsklick → Öffnen, oder `xattr -d com.apple.quarantine BeamLog`.

## Aus dem Quellcode

```bash
git clone https://github.com/NoobKeksTV/BeamLog.git
cd BeamLog
./start.sh                                         # Windows: start.bat – http://localhost:8000
```

`start.sh`/`start.bat` legen beim ersten Mal die virtuelle Umgebung `.venv` an und installieren die Pakete aus
`requirements.txt`; ändert sich die Datei (z. B. nach `git pull`), wird beim nächsten Start nachinstalliert. Optionen
gehen durch, z. B. `./start.sh --port 8080`. Danach funktioniert auch `python run.py` – fehlen dem aufrufenden Python
die Pakete, nimmt `run.py` automatisch `.venv`. Fehlt `python3-venv` (Debian/Ubuntu): `sudo apt install python3-venv`
oder `sudo bash deploy/install.sh --deps-only` (installiert Systempakete und `.venv`, bleibt im Ordner).

Von Hand ohne Startskript:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt      # Windows: .venv\Scripts\python -m pip …
.venv/bin/python run.py
```

Voraussetzung: Python 3.11 oder neuer. Tests: `python -m pytest -q`. Portable Pakete selbst bauen: `python build_tools/build.py` (erzeugt `dist/BeamLog-<version>-<os>-<arch>.zip`).

## Firewall

Der Server lauscht auf TCP-Port 8000 (bzw. dem gewählten Port). Unter Windows erscheint beim ersten Start die Firewall-Abfrage; „privates Netzwerk“ zulassen, sonst kommen andere Rechner nicht drauf.
