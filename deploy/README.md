# Deployment auf einem Debian-Server

Getestet gedacht für Debian 12 / Ubuntu 22.04+ / Raspberry Pi OS. Der Server steht im LAN
(z. B. ein Raspberry Pi oder ein kleiner Mini-PC am Contest-Standort), alle Rechner im
Netz erreichen den Logger per Browser über `http://<server-ip>/`.

## Schnellinstallation

```bash
sudo apt install -y git
git clone https://github.com/NoobKeksTV/BeamLog.git
cd BeamLog
sudo bash deploy/install.sh
```

Das Skript installiert Python, nginx und mdbtools, kopiert den Code nach `/opt/beamlog`,
legt den Systembenutzer `beamlog` an, schreibt die Konfiguration `/etc/beamlog/.env`,
richtet den systemd-Dienst und die nginx-Site ein und aktiviert ein tägliches Backup nach
`/var/lib/beamlog/backup/` (30 Tage Aufbewahrung). `--url http://contest.local/` setzt die öffentliche Adresse.

### Teile weglassen und im Ordner bleiben

**Wohin installiert wird:** Mit Dienst kopiert das Skript BeamLog nach `/opt/beamlog` (Daten in `/var/lib/beamlog`,
Einstellungen in `/etc/beamlog/.env`): Der Dienst läuft dort als eigener Systemnutzer `beamlog` mit gehärteter
Unit, die keinen Zugriff auf `/home` hat, und ein neu entpacktes ZIP lässt sich per `--update` einfach darüberspielen.
Das Skript kündigt das Kopieren deutlich an. **Ohne Dienst (`--no-service`) wird nichts kopiert** – BeamLog bleibt
automatisch im aktuellen Ordner. Mit `--here` bleibt es auch mit Dienst dort (die Unit läuft dann als dein Nutzer).

Beliebig kombinierbar; die Wahl wird in `/etc/beamlog/install.options` gemerkt und gilt auch für `--update`:

| Option | Wirkung |
|---|---|
| `--no-nginx` | nginx weder installieren noch einrichten (eigener Reverse-Proxy oder `PORT=80` direkt); eine frühere BeamLog-Site wird entfernt, andere Sites bleiben |
| `--no-service` | kein systemd-Dienst – das Skript zeigt den Startbefehl; ein früherer Dienst `beamlog` wird angehalten und entfernt |
| `--no-backup` | kein täglicher Backup-Cron (ein vorhandener wird entfernt) |
| `--with-nginx` / `--with-service` / `--with-backup` | wieder einrichten |
| `--here` | Nicht kopieren: BeamLog bleibt im aktuellen Ordner und läuft als der aufrufende Nutzer; Daten in `./data`, Einstellungen in `./.env`. Dienst, nginx und Backup-Cron zeigen auf diesen Ordner. |
| `--deps-only` | Nur die Voraussetzungen installieren (Systempakete, beim Quellcode zusätzlich `./.venv`) – wie `--here --no-nginx --no-service --no-backup`; danach selbst starten. |
| `--system` | Gemerkte `--here`-Wahl aufheben und wieder nach `/opt/beamlog` installieren. |

```bash
sudo bash deploy/install.sh --no-nginx                 # ohne nginx (eigener Reverse-Proxy auf 127.0.0.1:8000)
sudo bash deploy/install.sh --no-service               # ohne systemd-Dienst (BeamLog selbst starten)
sudo bash deploy/install.sh --no-nginx --no-backup     # mehrere gleichzeitig
sudo bash deploy/install.sh --deps-only                # nur Python & Co. installieren, im Ordner bleiben, selbst starten
sudo bash deploy/install.sh --here                     # im Ordner bleiben, aber mit Dienst, nginx und Backup
sudo bash deploy/install.sh --update --with-nginx      # einen Teil später wieder einrichten
sudo bash deploy/install.sh --help                     # alle Optionen
```

## Einstellungen: /etc/beamlog/.env

Alle Server-Einstellungen stehen in dieser Datei (`.env`-Format), die Unit selbst enthält keine Optionen:

```ini
HOST=127.0.0.1                                  # hinter nginx nur lokal
PORT=8000
DB=/var/lib/beamlog/beamlog.db
BACKUP_MIN=15                                   # automatische Sicherung alle N Minuten
PUBLIC_URL=http://contest.local/                # Adresse im QR-Code und in Links
#KST_HOST=www.on4kst.info
#KST_PORT=23000
#GITHUB_TOKEN=                                  # nur für ein privates Repo
#MAINTAINER=1                                   # Betreuer-Modus (Quellen-Importe der Stationsdatenbank)
#DEMO=1                                         # öffentliche Demo-Instanz (löscht täglich alles, siehe Wiki „Server-Deploy“)
#DEMO_RESET=03:00                               # Uhrzeit des täglichen Zurücksetzens
```

Nach Änderungen `sudo systemctl restart beamlog`. Die Datei bleibt bei `--update` unverändert; Umgebungsvariablen
`BEAMLOG_<KEY>` und Kommandozeilen-Optionen überstimmen sie.

Update auf eine neue Version:

```bash
cd BeamLog && git pull            # ältere Installationen: Ordner ContestLogger
sudo bash deploy/install.sh --update
```

## Dateien

| Datei | Zweck |
|---|---|
| `beamlog.service` | systemd-Dienst, läuft als Benutzer `beamlog`, liest `/etc/beamlog/.env` (Standard: nur 127.0.0.1:8000) |
| `portable/` | Dateien für die portable Version (Binary statt venv) inkl. `.env`-Vorlage und Port-80-Unit |
| `nginx-beamlog.conf` | nginx-Site auf Port 80, Reverse-Proxy inkl. WebSocket, statische Dateien direkt |
| `nginx-beamlog-ssl.conf` | optionale HTTPS-Variante mit selbstsigniertem Zertifikat |
| `install.sh` | Installation / Update in einem Rutsch; `--no-nginx`, `--no-service`, `--no-backup` lassen Teile weg (kombinierbar) |
| `backup.sh` | Konsistentes SQLite-Backup (Cron) |

Pfade: Code `/opt/beamlog`, Datenbank `/var/lib/beamlog/beamlog.db`.

## Nützliche Befehle

```bash
sudo systemctl status beamlog        # läuft der Dienst?
sudo journalctl -u beamlog -f        # Log live
sudo systemctl restart beamlog
sudo nginx -t && sudo systemctl reload nginx
```

## Hostname statt IP

Damit `http://contest.local/` funktioniert, auf dem Server `avahi-daemon` installieren
(`sudo apt install avahi-daemon`) und den Hostnamen auf `contest` setzen
(`sudo hostnamectl set-hostname contest`). Windows/macOS/iOS finden `.local`-Namen automatisch.

## Wiederherstellen aus einem Backup

```bash
sudo systemctl stop beamlog
sudo gunzip -c /var/lib/beamlog/backup/beamlog-XXXX.db.gz > /var/lib/beamlog/beamlog.db
sudo chown beamlog:beamlog /var/lib/beamlog/beamlog.db
sudo systemctl start beamlog
```

Zusätzlich sichert der Server selbst alle 15 Minuten (nur bei Änderungen) nach
`/var/lib/beamlog/backup/` und beim Beenden; „Jetzt sichern“ in der Verwaltung legt
eine manuelle Sicherung an derselben Stelle an.

## Ohne nginx

Für den schnellen Einsatz reicht auch `./start.sh` im Repo-Ordner (richtet `.venv` ein, lauscht auf 0.0.0.0:8000) – nginx
bringt nur Port 80, HTTPS-Option und das Ausliefern statischer Dateien.

## Umstieg von ContestLogger 0.9 (Server)

Bis Version 0.9 hieß BeamLog „ContestLogger“; Dienst, Nutzer und Pfade hießen entsprechend `contestlogger`.
Im aktualisierten Checkout (`git pull`) `sudo bash deploy/install.sh --update` ausführen – das Skript stellt den Server
automatisch um:

- Dienst `contestlogger` wird gestoppt und entfernt, `beamlog` eingerichtet und gestartet,
- Daten werden von `/var/lib/contestlogger/` nach `/var/lib/beamlog/` **kopiert** (Datenbank heißt dann `beamlog.db`),
- `/etc/contestlogger/contestlogger.env` wird zu `/etc/beamlog/.env` (Pfade darin werden angepasst),
- die nginx-Site (auch eine eigene HTTPS-Anpassung) und das tägliche Backup werden übernommen.

Die alten Daten bleiben in `/var/lib/contestlogger/` als Sicherung liegen und können danach gelöscht werden.
Ältere Umgebungsvariablen `CONTESTLOGGER_<KEY>` werden weiterhin verstanden.
