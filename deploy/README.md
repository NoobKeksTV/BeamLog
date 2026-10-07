# Deployment auf einem Debian-Server

Getestet gedacht für Debian 12 / Ubuntu 22.04+ / Raspberry Pi OS. Der Server steht im LAN
(z. B. ein Raspberry Pi oder ein kleiner Mini-PC am Contest-Standort), alle Rechner im
Netz erreichen den Logger per Browser über `http://<server-ip>/`.

## Schnellinstallation

```bash
sudo apt install -y git
git clone https://github.com/NoobKeksTV/ContestLogger.git
cd ContestLogger
sudo bash deploy/install.sh
```

Das Skript installiert Python, nginx und mdbtools, kopiert den Code nach `/opt/contestlogger`,
legt den Systembenutzer `contestlogger` an, schreibt die Konfiguration `/etc/contestlogger/contestlogger.env`,
richtet den systemd-Dienst und die nginx-Site ein und aktiviert ein tägliches Backup nach
`/var/lib/contestlogger/backup/` (30 Tage Aufbewahrung). `--url http://contest.local/` setzt die öffentliche Adresse.

## Einstellungen: /etc/contestlogger/contestlogger.env

Alle Server-Einstellungen stehen in dieser Datei (`.env`-Format), die Unit selbst enthält keine Optionen:

```ini
HOST=127.0.0.1                                  # hinter nginx nur lokal
PORT=8000
DB=/var/lib/contestlogger/contestlogger.db
BACKUP_MIN=15                                   # automatische Sicherung alle N Minuten
PUBLIC_URL=http://contest.local/                # Adresse im QR-Code und in Links
#KST_HOST=www.on4kst.info
#KST_PORT=23000
#GITHUB_TOKEN=                                  # nur für ein privates Repo
#MAINTAINER=1                                   # Betreuer-Modus (Quellen-Importe der Stationsdatenbank)
```

Nach Änderungen `sudo systemctl restart contestlogger`. Die Datei bleibt bei `--update` unverändert; Umgebungsvariablen
`CONTESTLOGGER_<KEY>` und Kommandozeilen-Optionen überstimmen sie.

Update auf eine neue Version:

```bash
cd ContestLogger && git pull
sudo bash deploy/install.sh --update
```

## Dateien

| Datei | Zweck |
|---|---|
| `contestlogger.service` | systemd-Dienst, läuft als Benutzer `contestlogger`, liest `/etc/contestlogger/contestlogger.env` (Standard: nur 127.0.0.1:8000) |
| `portable/` | Dateien für die portable Version (Binary statt venv) inkl. `contestlogger.env`-Vorlage und Port-80-Unit |
| `nginx-contestlogger.conf` | nginx-Site auf Port 80, Reverse-Proxy inkl. WebSocket, statische Dateien direkt |
| `nginx-contestlogger-ssl.conf` | optionale HTTPS-Variante mit selbstsigniertem Zertifikat |
| `install.sh` | Installation / Update in einem Rutsch |
| `backup.sh` | Konsistentes SQLite-Backup (Cron) |

Pfade: Code `/opt/contestlogger`, Datenbank `/var/lib/contestlogger/contestlogger.db`.

## Nützliche Befehle

```bash
sudo systemctl status contestlogger        # läuft der Dienst?
sudo journalctl -u contestlogger -f        # Log live
sudo systemctl restart contestlogger
sudo nginx -t && sudo systemctl reload nginx
```

## Hostname statt IP

Damit `http://contest.local/` funktioniert, auf dem Server `avahi-daemon` installieren
(`sudo apt install avahi-daemon`) und den Hostnamen auf `contest` setzen
(`sudo hostnamectl set-hostname contest`). Windows/macOS/iOS finden `.local`-Namen automatisch.

## Wiederherstellen aus einem Backup

```bash
sudo systemctl stop contestlogger
sudo gunzip -c /var/lib/contestlogger/backup/contestlogger-XXXX.db.gz > /var/lib/contestlogger/contestlogger.db
sudo chown contestlogger:contestlogger /var/lib/contestlogger/contestlogger.db
sudo systemctl start contestlogger
```

Zusätzlich sichert der Server selbst alle 15 Minuten (nur bei Änderungen) nach
`/var/lib/contestlogger/backup/` und beim Beenden; „Jetzt sichern“ in der Verwaltung legt
eine manuelle Sicherung an derselben Stelle an.

## Ohne nginx

Für den schnellen Einsatz reicht auch `python run.py` (lauscht auf 0.0.0.0:8000) – nginx
bringt nur Port 80, HTTPS-Option und das Ausliefern statischer Dateien.
