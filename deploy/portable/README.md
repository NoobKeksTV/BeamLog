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

Nützliche Befehle: `systemctl status contestlogger`, `journalctl -u contestlogger -f`, `sudo systemctl restart contestlogger`.

Update: neues ZIP entpacken, im entpackten Ordner `sudo bash deploy/install.sh --update`. Daten und Einstellungen bleiben erhalten.
