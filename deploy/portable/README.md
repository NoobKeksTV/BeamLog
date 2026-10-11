# BeamLog auf einem Debian-Server (portable Version)

Diese Dateien liegen im Linux-Release-ZIP unter `deploy/` und richten BeamLog als Dienst hinter nginx ein –
ohne Python auf dem Server. Das Linux-Binary wird auf Ubuntu 22.04 gebaut und läuft auf Debian 12 (Bookworm), Ubuntu 22.04 und neuer (glibc ≥ 2.35).

```bash
unzip BeamLog-<version>-linux-x86_64.zip
cd BeamLog
sudo bash deploy/install.sh --url http://contest.local/     # Erstinstallation
```

Danach läuft der Logger unter `http://<server-ip>/`.

Teile weglassen – beliebig kombinierbar, die Wahl wird in `/opt/beamlog/.install.options` gemerkt und gilt auch für `--update`:

```bash
sudo bash deploy/install.sh --no-nginx                 # ohne nginx (eigener Reverse-Proxy auf 127.0.0.1:8000)
sudo bash deploy/install.sh --no-service               # ohne systemd-Dienst (BeamLog selbst starten)
sudo bash deploy/install.sh --no-nginx --no-backup     # mehrere gleichzeitig
sudo bash deploy/install.sh --deps-only                # nur Python & Co. installieren, im Ordner bleiben, selbst starten
sudo bash deploy/install.sh --here                     # im Ordner bleiben, aber mit Dienst, nginx und Backup
sudo bash deploy/install.sh --update --with-nginx      # einen Teil später wieder einrichten
sudo bash deploy/install.sh --help                     # alle Optionen
```

**Wohin installiert wird:** Mit Dienst kopiert das Skript BeamLog nach `/opt/beamlog` (Daten in `/opt/beamlog/data`,
Einstellungen in `/opt/beamlog/.env` – alles in einem Ordner): Der Dienst läuft dort als eigener Systemnutzer `beamlog` mit gehärteter
Unit, die keinen Zugriff auf `/home` hat, und ein neu entpacktes ZIP lässt sich per `--update` einfach darüberspielen.
Das Skript kündigt das Kopieren deutlich an. **Ohne Dienst (`--no-service`) wird nichts kopiert** – BeamLog bleibt
automatisch im aktuellen Ordner. Mit `--here` bleibt es auch mit Dienst dort (die Unit läuft dann als dein Nutzer).
`--system` hebt eine gemerkte `--here`-Wahl wieder auf.

`--no-nginx` entfernt nur eine frühere BeamLog-Site (nginx selbst und andere Sites bleiben), `--no-service` hält einen
früheren Dienst `beamlog` an und entfernt ihn, `--no-backup` entfernt den Backup-Cron.

Enthalten:

| Datei | Zweck |
|---|---|
| `install.sh` | Kopiert das Programm nach `/opt/beamlog`, legt den Nutzer `beamlog` an, installiert Dienst, nginx-Site und Backup-Cron. `--update` spielt eine neue Version ein, `--url` setzt die öffentliche Adresse (QR-Code). `--no-nginx`, `--no-service`, `--no-backup` lassen Teile weg (kombinierbar, für Updates gemerkt; `--with-…` schaltet wieder ein, `--help` zeigt alles). |
| `.env` | Vorlage für `/opt/beamlog/.env` – **alle Server-Einstellungen** (Host, Port, Datenbank, Backup-Takt, öffentliche Adresse, KST-Server, GitHub-Token). |
| `beamlog.service` | systemd-Dienst: liest `/opt/beamlog/.env`, Neustart bei Absturz, gehärtet (PrivateTmp, ProtectSystem). |
| `nginx-beamlog.conf` | nginx-Site auf Port 80 mit WebSocket-Weiterleitung. |
| `backup.sh` | Tägliche gepackte Sicherung nach `/opt/beamlog/data/backup-daily/` (30 Tage). |

## Von Hand installieren (ohne install.sh)

```bash
# 1. Programm nach /opt kopieren und Nutzer anlegen
sudo mkdir -p /opt/beamlog/data
sudo cp -r ./* /opt/beamlog/
sudo useradd --system --home /opt/beamlog --shell /usr/sbin/nologin beamlog
sudo chown -R beamlog:beamlog /opt/beamlog
sudo chmod +x /opt/beamlog/BeamLog*

# 2. Konfiguration anlegen (Werte bei Bedarf anpassen: nano /opt/beamlog/.env)
sudo cp /opt/beamlog/deploy/server.env /opt/beamlog/.env
sudo chown beamlog:beamlog /opt/beamlog/.env && sudo chmod 640 /opt/beamlog/.env

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

## Einstellungen: /opt/beamlog/.env

Alle Server-Einstellungen stehen in **einer** Datei, die Unit enthält keine Optionen mehr:

```ini
HOST=127.0.0.1                                  # hinter nginx nur lokal
PORT=8000
#DB=/opt/beamlog/data/beamlog.db                # Standard: data/ im Programmordner
BACKUP_MIN=15                                   # automatische Sicherung alle N Minuten
PUBLIC_URL=http://contest.local/                # Adresse im QR-Code und in Links
#KST_HOST=www.on4kst.info
#KST_PORT=23000
#GITHUB_TOKEN=                                  # nur für ein privates Repo
#DEMO=1                                         # öffentliche Demo-Instanz (löscht täglich alles, siehe Wiki „Server-Deploy“)
#DEMO_RESET=03:00                               # Uhrzeit des täglichen Zurücksetzens
```

Nach Änderungen: `sudo systemctl restart beamlog`. `install.sh` legt die Datei beim ersten Lauf an und lässt sie bei Updates
unverändert; `--url` trägt nur `PUBLIC_URL` ein. Umgebungsvariablen `BEAMLOG_<KEY>` und Kommandozeilen-Optionen
(`--port` …) überstimmen die Datei.

## Ohne nginx: Dienst direkt auf Port 80

Port und Adresse stehen nur in `/opt/beamlog/.env` – das Install-Skript richtet sich danach:

- **`PORT=80`** (mit `HOST=0.0.0.0`): BeamLog ist direkt erreichbar, **ohne nginx**. Das Skript schaltet nginx dann ab
  (es würde Port 80 belegen); der Dienst darf Port 80 öffnen (`CAP_NET_BIND_SERVICE` in der Unit).
- **jeder andere Port** (Standard `8000`, `HOST=127.0.0.1`): nginx nimmt Port 80 an und leitet an diesen Port weiter.

```bash
sudo nano /opt/beamlog/.env            # PORT=80 und HOST=0.0.0.0 eintragen
sudo bash deploy/install.sh --update          # im entpackten BeamLog-Ordner: stellt nginx und Dienst passend ein
```

Nur `sudo systemctl restart beamlog` reicht beim Wechsel zwischen den beiden Varianten nicht, weil dann nginx weiter Port 80 belegt.
Läuft auf dem Server schon ein anderer Webserver/Reverse-Proxy, den das Skript nicht anfassen soll: mit `--no-nginx`
installieren und dort an `127.0.0.1:8000` weiterleiten (WebSocket `/ws` nicht vergessen, Vorlage: `nginx-beamlog.conf`).

## Dienst bedienen

```bash
sudo systemctl start beamlog      # starten
sudo systemctl stop beamlog       # stoppen
sudo systemctl restart beamlog    # neu starten (z. B. nach Update)
systemctl status beamlog          # Zustand
journalctl -u beamlog -f          # Live-Log (auch das Aktionsprotokoll)
```

Update: neues ZIP entpacken, im entpackten Ordner `sudo bash deploy/install.sh --update`. Daten und Einstellungen bleiben erhalten.

## Alles in einem Ordner (Umzug älterer Installationen)

Auf dem Server liegt jetzt alles unter `/opt/beamlog`: Programm, `data/` (Datenbank, Backups, Sprachen) und `.env`
(Einstellungen) – ein Ordner, ein Besitzer (`beamlog`), keine verstreuten Rechte. Bis 1.0.0 lagen die Daten in
`/var/lib/beamlog` und die Einstellungen in `/etc/beamlog/beamlog.env`. `sudo bash deploy/install.sh --update` holt
alles automatisch in den neuen Ordner:

- Einstellungen `/etc/beamlog/beamlog.env` (bzw. `.env`) und die gemerkte Wahl werden nach `/opt/beamlog/` **verschoben**,
  Pfade darin (z. B. `DB=/var/lib/beamlog/…`) auf `/opt/beamlog/data/` umgestellt,
- die Daten aus `/var/lib/beamlog` werden nach `/opt/beamlog/data/` **kopiert** (der Dienst wird dafür kurz angehalten);
  das Original bleibt als Sicherung liegen und kann nach Prüfung gelöscht werden (`sudo rm -r /var/lib/beamlog`),
- Dienst-Unit und Backup-Cron werden auf die neuen Pfade umgeschrieben, die Rechte im Ordner neu gesetzt.

Läuft eine ältere Installation ohne dieses Update weiter (z. B. nur über Verwaltung → Updates aktualisiert), funktioniert
sie unverändert mit den alten Pfaden. Fehlt der Datenordner oder ein Unterordner (`backup/`, `lang/`), legt BeamLog ihn
beim Start selbst an; fehlen Schreibrechte, nennt es Nutzer, Ordner und den passenden `chown`-Befehl statt abzustürzen.
Fehlt eine Vorlage aus `deploy/`, legt `install.sh` eine Standardversion an.

## Umstieg von ContestLogger 0.9 (Server)

Bis Version 0.9 hieß BeamLog „ContestLogger“; Dienst, Nutzer und Pfade hießen entsprechend `contestlogger`.
Das neue ZIP entpacken und dort `sudo bash deploy/install.sh --update` ausführen – das Skript stellt den Server
automatisch um:

- Dienst `contestlogger` wird gestoppt und entfernt, `beamlog` eingerichtet und gestartet,
- Daten werden von `/var/lib/contestlogger/` nach `/opt/beamlog/data/` **kopiert** (Datenbank heißt dann `beamlog.db`),
- `/etc/contestlogger/contestlogger.env` wird zu `/opt/beamlog/.env` (Pfade darin werden angepasst),
- die nginx-Site (auch eine eigene HTTPS-Anpassung) und das tägliche Backup werden übernommen.

Die alten Daten bleiben in `/var/lib/contestlogger/` als Sicherung liegen und können danach gelöscht werden.
Ältere Umgebungsvariablen `CONTESTLOGGER_<KEY>` werden weiterhin verstanden.
