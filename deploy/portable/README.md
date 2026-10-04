# ContestLogger auf einem Debian-Server (portable Version)

Diese Dateien liegen im Linux-Release-ZIP unter `deploy/` und richten den ContestLogger als Dienst hinter nginx ein –
ohne Python auf dem Server. Das Linux-Binary wird auf Ubuntu 22.04 gebaut und läuft auf Debian 12 (Bookworm), Ubuntu 22.04 und neuer (glibc ≥ 2.35).

```bash
unzip ContestLogger-<version>-linux-x86_64.zip
cd ContestLogger
sudo bash deploy/install.sh --url http://contest.local/     # Erstinstallation
```

Danach läuft der Logger unter `http://<server-ip>/`. Enthalten:

| Datei | Zweck |
|---|---|
| `install.sh` | Kopiert das Programm nach `/opt/contestlogger`, legt den Nutzer `contestlogger` an, installiert Dienst, nginx-Site und Backup-Cron. `--update` spielt eine neue Version ein, `--url` setzt die öffentliche Adresse (QR-Code). |
| `contestlogger.service` | systemd-Dienst: Binary auf `127.0.0.1:8000`, Datenbank in `/var/lib/contestlogger/`, automatische Backups alle 15 min, Neustart bei Absturz. |
| `nginx-contestlogger.conf` | nginx-Site auf Port 80 mit WebSocket-Weiterleitung. |
| `backup.sh` | Tägliche gepackte Sicherung nach `/var/lib/contestlogger/backup-daily/` (30 Tage). |

## Von Hand installieren (ohne install.sh)

```bash
# 1. Programm nach /opt kopieren und Nutzer anlegen
sudo mkdir -p /opt/contestlogger /var/lib/contestlogger
sudo cp -r ./* /opt/contestlogger/
sudo useradd --system --home /opt/contestlogger --shell /usr/sbin/nologin contestlogger
sudo chown -R contestlogger:contestlogger /opt/contestlogger /var/lib/contestlogger
sudo chmod +x /opt/contestlogger/ContestLogger*

# 2. systemd-Dienst kopieren, aktivieren und starten
sudo cp /opt/contestlogger/deploy/contestlogger.service /etc/systemd/system/contestlogger.service
sudo systemctl daemon-reload
sudo systemctl enable --now contestlogger

# 3. nginx-Site einrichten (Port 80 -> Dienst)
sudo apt-get install -y nginx
sudo cp /opt/contestlogger/deploy/nginx-contestlogger.conf /etc/nginx/sites-available/contestlogger
sudo ln -sf /etc/nginx/sites-available/contestlogger /etc/nginx/sites-enabled/contestlogger
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# 4. (optional) tägliches Backup
sudo apt-get install -y sqlite3
sudo cp /opt/contestlogger/deploy/backup.sh /usr/local/bin/contestlogger-backup
sudo chmod +x /usr/local/bin/contestlogger-backup
echo "15 3 * * * root /usr/local/bin/contestlogger-backup" | sudo tee /etc/cron.d/contestlogger-backup
```

Öffentliche Adresse (QR-Code, Links) in `/etc/systemd/system/contestlogger.service` bei `--public-url` eintragen,
danach `sudo systemctl daemon-reload && sudo systemctl restart contestlogger`.

## Dienst bedienen

```bash
sudo systemctl start contestlogger      # starten
sudo systemctl stop contestlogger       # stoppen
sudo systemctl restart contestlogger    # neu starten (z. B. nach Update)
systemctl status contestlogger          # Zustand
journalctl -u contestlogger -f          # Live-Log (auch das Aktionsprotokoll)
```

Update: neues ZIP entpacken, im entpackten Ordner `sudo bash deploy/install.sh --update`. Daten und Einstellungen bleiben erhalten.
