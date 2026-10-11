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
legt den Systembenutzer `beamlog` an, schreibt die Konfiguration `/etc/beamlog/beamlog.env`,
richtet den systemd-Dienst und die nginx-Site ein und aktiviert ein tägliches Backup nach
`/var/lib/beamlog/backup/` (30 Tage Aufbewahrung). `--url http://contest.local/` setzt die öffentliche Adresse.

## Einstellungen: /etc/beamlog/beamlog.env

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
| `beamlog.service` | systemd-Dienst, läuft als Benutzer `beamlog`, liest `/etc/beamlog/beamlog.env` (Standard: nur 127.0.0.1:8000) |
| `portable/` | Dateien für die portable Version (Binary statt venv) inkl. `beamlog.env`-Vorlage und Port-80-Unit |
| `nginx-beamlog.conf` | nginx-Site auf Port 80, Reverse-Proxy inkl. WebSocket, statische Dateien direkt |
| `nginx-beamlog-ssl.conf` | optionale HTTPS-Variante mit selbstsigniertem Zertifikat |
| `install.sh` | Installation / Update in einem Rutsch |
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

Für den schnellen Einsatz reicht auch `python run.py` (lauscht auf 0.0.0.0:8000) – nginx
bringt nur Port 80, HTTPS-Option und das Ausliefern statischer Dateien.

## Umstieg von ContestLogger 0.9 (Server)

Bis Version 0.9 hieß BeamLog „ContestLogger“; Dienst, Nutzer und Pfade hießen entsprechend `contestlogger`.
Im aktualisierten Checkout (`git pull`) `sudo bash deploy/install.sh --update` ausführen – das Skript stellt den Server
automatisch um:

- Dienst `contestlogger` wird gestoppt und entfernt, `beamlog` eingerichtet und gestartet,
- Daten werden von `/var/lib/contestlogger/` nach `/var/lib/beamlog/` **kopiert** (Datenbank heißt dann `beamlog.db`),
- `/etc/contestlogger/contestlogger.env` wird zu `/etc/beamlog/beamlog.env` (Pfade darin werden angepasst),
- die nginx-Site (auch eine eigene HTTPS-Anpassung) und das tägliche Backup werden übernommen.

Die alten Daten bleiben in `/var/lib/contestlogger/` als Sicherung liegen und können danach gelöscht werden.
Ältere Umgebungsvariablen `CONTESTLOGGER_<KEY>` werden weiterhin verstanden.
