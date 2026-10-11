# Server-Deploy: Debian mit nginx und systemd

Für einen dauerhaft laufenden Server (z. B. Raspberry Pi oder ein kleiner Debian-Rechner im Shack) liegt im Linux-ZIP der Ordner `deploy/` mit allem Nötigen. Python wird auf dem Server **nicht** benötigt.

## Schnellinstallation

```bash
unzip BeamLog-<version>-linux-x86_64.zip
cd BeamLog
sudo bash deploy/install.sh --url http://contest.local/
```

Das Script

- installiert `nginx`, `sqlite3` und `rsync`,
- kopiert das Programm nach `/opt/beamlog` und legt den Systemnutzer `beamlog` an,
- legt die Konfiguration `/etc/beamlog/beamlog.env` an (Dienst auf `127.0.0.1:8000`, Datenbank in `/var/lib/beamlog/`, Backups alle 15 Minuten),
- richtet den Dienst `beamlog` ein (liest die Konfiguration, Neustart bei Absturz),
- legt die nginx-Site auf Port 80 mit WebSocket-Weiterleitung an,
- richtet ein tägliches gepacktes Backup (03:15 Uhr, 30 Tage) ein.

Danach läuft der Logger unter `http://<server-ip>/`. `--url` setzt die Adresse, die im QR-Code und in Links erscheint.

Die Sicherungen des Servers lassen sich in der Verwaltung einsehen und anstoßen:

![Backups auf dem Server](img/backups.png)

**Update später:** neues ZIP entpacken und im entpackten Ordner `sudo bash deploy/install.sh --update`. Daten und Einstellungen bleiben erhalten. Alternativ aktualisiert sich der Server selbst über Verwaltung → Updates, siehe [Updates](Updates.md).

## Von Hand installieren

```bash
# 1. Programm nach /opt kopieren und Nutzer anlegen
sudo mkdir -p /opt/beamlog /var/lib/beamlog
sudo cp -r ./* /opt/beamlog/
sudo useradd --system --home /opt/beamlog --shell /usr/sbin/nologin beamlog
sudo chown -R beamlog:beamlog /opt/beamlog /var/lib/beamlog
sudo chmod +x /opt/beamlog/BeamLog*

# 2. Konfiguration anlegen (Werte bei Bedarf anpassen: nano /etc/beamlog/beamlog.env)
sudo mkdir -p /etc/beamlog
sudo cp /opt/beamlog/deploy/beamlog.env /etc/beamlog/beamlog.env
sudo chown root:beamlog /etc/beamlog/beamlog.env && sudo chmod 640 /etc/beamlog/beamlog.env

# 3. systemd-Dienst kopieren, aktivieren und starten
sudo cp /opt/beamlog/deploy/beamlog.service /etc/systemd/system/beamlog.service
sudo systemctl daemon-reload
sudo systemctl enable --now beamlog

# 4. nginx-Site einrichten (Port 80 -> Dienst)
sudo apt-get install -y nginx
sudo cp /opt/beamlog/deploy/nginx-beamlog.conf /etc/nginx/sites-available/beamlog
sudo ln -sf /etc/nginx/sites-available/beamlog /etc/nginx/sites-enabled/beamlog
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# 5. (optional) tägliches Backup
sudo apt-get install -y sqlite3
sudo cp /opt/beamlog/deploy/backup.sh /usr/local/bin/beamlog-backup
sudo chmod +x /usr/local/bin/beamlog-backup
echo "15 3 * * * root /usr/local/bin/beamlog-backup" | sudo tee /etc/cron.d/beamlog-backup
```

## Einstellungen: `/etc/beamlog/beamlog.env`

Alle Server-Einstellungen stehen in einer Datei im `.env`-Format; die Unit selbst enthält keine Optionen mehr:

```ini
HOST=127.0.0.1                                  # hinter nginx nur lokal
PORT=8000
DB=/var/lib/beamlog/beamlog.db
BACKUP_MIN=15                                   # automatische Sicherung alle N Minuten (0 = aus)
PUBLIC_URL=http://contest.local/                # Adresse im QR-Code und in Links
#KST_HOST=www.on4kst.info                       # ON4KST-Server (normalerweise unverändert)
#KST_PORT=23000
#GITHUB_TOKEN=                                  # nur für ein privates Repo (Updates, Stationsdatenbank)
#MAINTAINER=1                                   # Betreuer-Modus: Quellen-Importe für die zentrale Stationsdatenbank
```

Nach Änderungen `sudo systemctl restart beamlog`. `install.sh` legt die Datei beim ersten Lauf aus `deploy/beamlog.env` an und lässt sie bei `--update` unverändert; `--url` trägt nur `PUBLIC_URL` ein. Reihenfolge der Quellen: Kommandozeile überstimmt Umgebungsvariablen `BEAMLOG_<KEY>`, diese überstimmen die Datei.

Die Unit `deploy/beamlog.service` (Auszug):

```ini
[Service]
User=beamlog
WorkingDirectory=/opt/beamlog
ExecStart=/opt/beamlog/BeamLog --config /etc/beamlog/beamlog.env
Restart=always
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/beamlog
```

## Ohne nginx: direkt auf Port 80

Port und Adresse stehen nur in `/etc/beamlog/beamlog.env` – das Install-Skript richtet sich danach:

- **`PORT=80`** (mit `HOST=0.0.0.0`): BeamLog ist direkt erreichbar, **ohne nginx**. Das Skript schaltet nginx dann ab
  (es würde Port 80 belegen); der Dienst darf Port 80 öffnen (`CAP_NET_BIND_SERVICE` in der Unit).
- **jeder andere Port** (Standard `8000`, `HOST=127.0.0.1`): nginx nimmt Port 80 an und leitet an diesen Port weiter.

```bash
sudo nano /etc/beamlog/beamlog.env            # PORT=80 und HOST=0.0.0.0 eintragen
sudo bash deploy/install.sh --update          # im entpackten BeamLog-Ordner: stellt nginx und Dienst passend ein
```

Nur `sudo systemctl restart beamlog` reicht beim Wechsel zwischen den beiden Varianten nicht, weil dann nginx weiter Port 80 belegt.

## nginx-Site

`deploy/nginx-beamlog.conf` reicht alles an `127.0.0.1:8000` durch; wichtig ist der WebSocket-Block für `/ws` (Live-Updates, Chat, Operator-Fenster) und `client_max_body_size 50m` für Importe. Für HTTPS liegt im Quellcode unter `deploy/nginx-beamlog-ssl.conf` eine Vorlage (Zertifikat z. B. per certbot oder selbstsigniert).

## Dienst bedienen

```bash
sudo systemctl start|stop|restart beamlog
systemctl status beamlog
journalctl -u beamlog -f          # Live-Log, enthält auch das Aktionsprotokoll
```

## Datenbank und Backups

- Datenbank: `/var/lib/beamlog/beamlog.db` (SQLite, WAL-Modus, synchrones Schreiben – ein Stromausfall beschädigt sie nicht).
- Automatische Sicherungen des Servers: `/var/lib/beamlog/backup/` (nur wenn sich etwas geändert hat, plus beim Beenden und vor jedem Update).
- Tägliche gepackte Sicherung des Cron-Jobs: `/var/lib/beamlog/backup-daily/`.
- Eigene Sprachdateien: `/var/lib/beamlog/lang/<code>.json`.

Wiederherstellen: Dienst stoppen, Sicherung nach `beamlog.db` kopieren, Dienst starten.

## Quellcode-Variante auf dem Server

Wer lieber aus dem Repo installiert (Python-venv statt Binary), nutzt `deploy/install.sh` aus dem Quellcode-Checkout; dort entsteht `/opt/beamlog/.venv`. Auch diese Unit liest alle Einstellungen aus `/etc/beamlog/beamlog.env` (`run.py --config …`), das Skript legt die Datei beim ersten Lauf an und `--url` setzt die öffentliche Adresse. Updates dann mit `git pull` und `sudo bash deploy/install.sh --update`.

## Umstieg von ContestLogger 0.9 (Server)

Bis Version 0.9 hieß BeamLog „ContestLogger“; Dienst, Nutzer und Pfade hießen entsprechend `contestlogger`.
Das neue ZIP entpacken und dort `sudo bash deploy/install.sh --update` ausführen – das Skript stellt den Server
automatisch um:

- Dienst `contestlogger` wird gestoppt und entfernt, `beamlog` eingerichtet und gestartet,
- Daten werden von `/var/lib/contestlogger/` nach `/var/lib/beamlog/` **kopiert** (Datenbank heißt dann `beamlog.db`),
- `/etc/contestlogger/contestlogger.env` wird zu `/etc/beamlog/beamlog.env` (Pfade darin werden angepasst),
- die nginx-Site (auch eine eigene HTTPS-Anpassung) und das tägliche Backup werden übernommen.

Die alten Daten bleiben in `/var/lib/contestlogger/` als Sicherung liegen und können danach gelöscht werden.
Ältere Umgebungsvariablen `CONTESTLOGGER_<KEY>` werden weiterhin verstanden.
