# BeamLog auf einem Debian-Server (portable Version)

Diese Dateien liegen im Linux-Release-ZIP unter `deploy/` und richten BeamLog als Dienst hinter nginx ein –
ohne Python auf dem Server. Das Linux-Binary wird auf Ubuntu 22.04 gebaut und läuft auf Debian 12 (Bookworm), Ubuntu 22.04 und neuer (glibc ≥ 2.35).

```bash
unzip BeamLog-<version>-linux-x86_64.zip
cd BeamLog
sudo bash deploy/install.sh --url http://contest.local/     # Erstinstallation
```

Danach läuft der Logger unter `http://<server-ip>/`. Enthalten:

| Datei | Zweck |
|---|---|
| `install.sh` | Kopiert das Programm nach `/opt/contestlogger`, legt den Nutzer `contestlogger` an, installiert Dienst, nginx-Site und Backup-Cron. `--update` spielt eine neue Version ein, `--url` setzt die öffentliche Adresse (QR-Code). |
| `contestlogger.env` | Vorlage für `/etc/contestlogger/contestlogger.env` – **alle Server-Einstellungen** (Host, Port, Datenbank, Backup-Takt, öffentliche Adresse, KST-Server, GitHub-Token). |
| `contestlogger.service` | systemd-Dienst: liest `/etc/contestlogger/contestlogger.env`, Neustart bei Absturz, gehärtet (PrivateTmp, ProtectSystem). |
| `contestlogger-port80.service` | Alternative Unit ohne nginx: Dienst direkt auf Port 80 (`CAP_NET_BIND_SERVICE`). |
| `nginx-contestlogger.conf` | nginx-Site auf Port 80 mit WebSocket-Weiterleitung. |
| `backup.sh` | Tägliche gepackte Sicherung nach `/var/lib/contestlogger/backup-daily/` (30 Tage). |

## Von Hand installieren (ohne install.sh)

```bash
# 1. Programm nach /opt kopieren und Nutzer anlegen
sudo mkdir -p /opt/contestlogger /var/lib/contestlogger
sudo cp -r ./* /opt/contestlogger/
sudo useradd --system --home /opt/contestlogger --shell /usr/sbin/nologin contestlogger
sudo chown -R contestlogger:contestlogger /opt/contestlogger /var/lib/contestlogger
sudo chmod +x /opt/contestlogger/BeamLog*

# 2. Konfiguration anlegen (Werte bei Bedarf anpassen: nano /etc/contestlogger/contestlogger.env)
sudo mkdir -p /etc/contestlogger
sudo cp /opt/contestlogger/deploy/contestlogger.env /etc/contestlogger/contestlogger.env
sudo chown root:contestlogger /etc/contestlogger/contestlogger.env && sudo chmod 640 /etc/contestlogger/contestlogger.env

# 3. systemd-Dienst kopieren, aktivieren und starten
sudo cp /opt/contestlogger/deploy/contestlogger.service /etc/systemd/system/contestlogger.service
sudo systemctl daemon-reload
sudo systemctl enable --now contestlogger

# 4. nginx-Site einrichten (Port 80 -> Dienst)
sudo apt-get install -y nginx
sudo cp /opt/contestlogger/deploy/nginx-contestlogger.conf /etc/nginx/sites-available/contestlogger
sudo ln -sf /etc/nginx/sites-available/contestlogger /etc/nginx/sites-enabled/contestlogger
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# 5. (optional) tägliches Backup
sudo apt-get install -y sqlite3
sudo cp /opt/contestlogger/deploy/backup.sh /usr/local/bin/contestlogger-backup
sudo chmod +x /usr/local/bin/contestlogger-backup
echo "15 3 * * * root /usr/local/bin/contestlogger-backup" | sudo tee /etc/cron.d/contestlogger-backup
```

## Einstellungen: /etc/contestlogger/contestlogger.env

Alle Server-Einstellungen stehen in **einer** Datei, die Unit enthält keine Optionen mehr:

```ini
HOST=127.0.0.1                                  # hinter nginx nur lokal
PORT=8000
DB=/var/lib/contestlogger/contestlogger.db
BACKUP_MIN=15                                   # automatische Sicherung alle N Minuten
PUBLIC_URL=http://contest.local/                # Adresse im QR-Code und in Links
#KST_HOST=www.on4kst.info
#KST_PORT=23000
#GITHUB_TOKEN=                                  # nur für ein privates Repo
```

Nach Änderungen: `sudo systemctl restart contestlogger`. `install.sh` legt die Datei beim ersten Lauf an und lässt sie bei Updates
unverändert; `--url` trägt nur `PUBLIC_URL` ein. Umgebungsvariablen `CONTESTLOGGER_<KEY>` und Kommandozeilen-Optionen
(`--port` …) überstimmen die Datei.

## Ohne nginx: Dienst direkt auf Port 80

Ein normaler Nutzer darf Port 80 nicht öffnen (`[Errno 13] permission denied`). Die Unit `contestlogger-port80.service`
gibt dem Dienst über `AmbientCapabilities=CAP_NET_BIND_SERVICE` genau diese Berechtigung und lauscht auf `0.0.0.0:80`:

```bash
sudo systemctl disable --now nginx            # falls nginx Port 80 belegt
sudo cp /opt/contestlogger/deploy/contestlogger-port80.service /etc/systemd/system/contestlogger.service
sudo systemctl daemon-reload
sudo systemctl restart contestlogger
```

Mit nginx dagegen bleibt der Dienst auf `127.0.0.1:8000` (Standard-Unit), nginx übernimmt Port 80.

## Dienst bedienen

```bash
sudo systemctl start contestlogger      # starten
sudo systemctl stop contestlogger       # stoppen
sudo systemctl restart contestlogger    # neu starten (z. B. nach Update)
systemctl status contestlogger          # Zustand
journalctl -u contestlogger -f          # Live-Log (auch das Aktionsprotokoll)
```

Update: neues ZIP entpacken, im entpackten Ordner `sudo bash deploy/install.sh --update`. Daten und Einstellungen bleiben erhalten.
