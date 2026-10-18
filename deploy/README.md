# Deployment auf einem Debian-Server

Getestet gedacht für Debian 12 / Ubuntu 22.04+ / Raspberry Pi OS. Der Server steht im LAN
(z. B. ein Raspberry Pi oder ein kleiner Mini-PC am Contest-Standort), alle Rechner im
Netz erreichen den Logger per Browser über `http://<server-ip>/`.

## Schnellinstallation

```bash
sudo apt install -y git
git clone https://github.com/NoobKeksTV/BeamLog.git
cd BeamLog
sudo ./beamlogctl install
```

`beamlogctl install` fragt nacheinander (Enter übernimmt den Vorschlag in `[ ]`):

1. **systemd-Dienst einrichten?** – BeamLog startet mit dem Server und nach einem Absturz neu.
2. **Nach `/opt/beamlog` kopieren?** (nur mit Dienst) – eigener Systemnutzer `beamlog`, gehärtete Unit; *Nein* = im
   aktuellen Ordner bleiben (die Unit läuft dann als Besitzer des Ordners).
3. **nginx davor einrichten?** – Port 80 mit WebSocket-Weiterleitung; *Nein* z. B. bei eigenem Reverse-Proxy.
4. **Tägliches Backup?** – gepackte Sicherung um 03:15 Uhr nach `data/backup-daily/`, 30 Tage aufbewahrt.
5. **Adresse** für QR-Code und Links (z. B. `http://contest.local/`, Enter = unverändert).

Danach zeigt es die Auswahl („Wird eingerichtet: Dienst ja · nginx ja · Backup ja · Ort: /opt/beamlog“) und fragt
„Weiter?“. Ohne Dienst bietet es an, BeamLog gleich im Hintergrund zu starten. Die eigentliche Arbeit macht
`deploy/install.sh`: Python, nginx und mdbtools installieren, Code kopieren, Systembenutzer `beamlog` anlegen,
`/opt/beamlog/.env` schreiben, Dienst, nginx-Site und Backup-Cron einrichten.

### Ohne Rückfragen: Optionen

Angegebene Teile werden nicht mehr gefragt; mit `-y` fragt `beamlogctl` gar nichts (für Skripte und Automatisierung).
Beliebig kombinierbar; die Wahl wird in `.install.options` gemerkt und gilt auch für spätere Updates:

| Option | Wirkung |
|---|---|
| `--no-service` / `--service` | ohne bzw. mit systemd-Dienst; ein früherer Dienst `beamlog` wird bei `--no-service` angehalten und entfernt |
| `--no-nginx` / `--nginx` | nginx weder installieren noch einrichten (eigener Reverse-Proxy oder `PORT=80` direkt) bzw. einrichten; andere Sites bleiben unberührt |
| `--no-backup` / `--backup` | täglichen Backup-Cron weglassen bzw. einrichten |
| `--here` / `--system` | im aktuellen Ordner bleiben bzw. nach `/opt/beamlog` kopieren (nur mit Dienst; Standard: kopieren) |
| `--url ADRESSE` | Adresse für QR-Code und Links (`PUBLIC_URL`) |
| `--deps-only` | nur die Voraussetzungen installieren (Systempakete, beim Quellcode zusätzlich `./.venv`), nichts einrichten |
| `-y`, `--yes` | keine Rückfragen: nicht angegebene Teile wie beim letzten Mal (beim ersten Mal: alles einrichten) |

```bash
sudo ./beamlogctl install -y                           # alles einrichten, ohne Rückfrage
sudo ./beamlogctl install --no-nginx -y                # eigener Reverse-Proxy auf 127.0.0.1:8000
sudo ./beamlogctl install --no-service --no-nginx -y   # ohne Dienst: bleibt im Ordner, Start mit ./beamlogctl start
sudo ./beamlogctl install --deps-only                  # nur Python & Co. installieren
sudo ./beamlogctl install --here                       # im Ordner bleiben, aber mit Dienst
sudo ./beamlogctl install --nginx -y                   # nginx später doch einrichten, der Rest bleibt wie gemerkt
```

**Wohin installiert wird:** Mit Dienst wird BeamLog standardmäßig nach `/opt/beamlog` kopiert (Daten in
`/opt/beamlog/data`, Einstellungen in `/opt/beamlog/.env` – alles in einem Ordner): Der Dienst läuft dort als eigener
Systemnutzer `beamlog` mit gehärteter Unit, die keinen Zugriff auf `/home` hat. **Ohne Dienst wird nichts kopiert** –
BeamLog bleibt im aktuellen Ordner und läuft als dessen Besitzer.

## Bedienen und aktualisieren

```bash
./beamlogctl status          # läuft? Exit-Code 0 = ja, sonst 1 – die Zeile sagt warum
./beamlogctl start | stop | restart
./beamlogctl log 50          # letzte Ausgaben (mit Dienst aus dem Journal)
sudo ./beamlogctl update     # neuen Stand holen und neu starten
```

Mit Dienst steuert `beamlogctl` den Dienst `beamlog` (über systemctl), ohne Dienst startet es `./start.sh` im
Hintergrund (Ausgabe in `data/beamlog.log`). Nach der Installation mit Kopie liegt es auch unter
`/opt/beamlog/beamlogctl`. `status` beendet die eigene Shell nicht und eignet sich für Control Panels
(z. B. ServerController: Start `sh ./beamlogctl start`, Stopp `sh ./beamlogctl stop`, Status `sh ./beamlogctl status`).

`update` holt im Git-Checkout den neuen Stand (`git pull`), spielt ihn ein (`install.sh --update`: Pakete, Dienst,
nginx) und startet neu. Liegt der Dienst in `/opt/beamlog`, fragt es im Quellordner bzw. im neu entpackten ZIP, ob
dieser Stand dorthin eingespielt werden soll (ohne Rückfrage: `update --service`). Ein zweites BeamLog in einem anderen
Ordner, etwa eine Demo, steuert nie den Dienst.

`deploy/install.sh` lässt sich weiterhin direkt aufrufen (`sudo bash deploy/install.sh --update`, alle Optionen mit
`--help`).

## Einstellungen: /opt/beamlog/.env

Alle Server-Einstellungen stehen in dieser Datei (`.env`-Format), die Unit selbst enthält keine Optionen:

```ini
HOST=127.0.0.1                                  # hinter nginx nur lokal
PORT=8000
#DB=/opt/beamlog/data/beamlog.db                # Standard: data/ im Programmordner
BACKUP_MIN=15                                   # automatische Sicherung alle N Minuten
PUBLIC_URL=http://contest.local/                # Adresse im QR-Code und in Links
#KST_HOST=www.on4kst.info
#KST_PORT=23000
#GITHUB_TOKEN=                                  # nur für ein privates Repo
#MAINTAINER=1                                   # Betreuer-Modus (Quellen-Importe der Stationsdatenbank)
#DEMO=1                                         # öffentliche Demo-Instanz (löscht täglich alles, siehe Wiki „Server-Deploy“)
#DEMO_RESET=03:00                               # Uhrzeit des täglichen Zurücksetzens
```

Nach Änderungen `sudo ./beamlogctl restart`. Die Datei bleibt bei `--update` unverändert; Umgebungsvariablen
`BEAMLOG_<KEY>` und Kommandozeilen-Optionen überstimmen sie.

Update auf eine neue Version:

```bash
cd BeamLog                        # ältere Installationen: Ordner ContestLogger
sudo ./beamlogctl update          # git pull, einspielen, neu starten
```

## Dateien

| Datei | Zweck |
|---|---|
| `beamlog.service` | systemd-Dienst für `/opt/beamlog`, läuft als Benutzer `beamlog`, liest die `.env` daneben (Standard: nur 127.0.0.1:8000); anderer Ordner: siehe unten |
| `portable/` | Dateien für die portable Version (Binary statt venv) inkl. `.env`-Vorlage und Port-80-Unit |
| `nginx-beamlog.conf` | nginx-Site auf Port 80, Reverse-Proxy inkl. WebSocket, statische Dateien direkt |
| `nginx-beamlog-ssl.conf` | optionale HTTPS-Variante mit selbstsigniertem Zertifikat |
| `install.sh` | Installation / Update in einem Rutsch (Unterbau von `beamlogctl install` und `update`); `--no-nginx`, `--no-service`, `--no-backup` lassen Teile weg |
| `backup.sh` | Konsistentes SQLite-Backup (Cron) |

Pfade: Code `/opt/beamlog`, Datenbank `/opt/beamlog/data/beamlog.db`.

## Dienst in einem eigenen Ordner statt /opt/beamlog

Die mitgelieferte Unit `deploy/beamlog.service` ist auf `/opt/beamlog` eingestellt. BeamLog liest seine Einstellungen
aus der `.env` **neben dem Programm** (im Arbeitsordner des Dienstes) und schreibt die Datenbank nach `data/` daneben –
ein `--config`-Pfad ist nicht nötig. Liegt BeamLog woanders, z. B. `/srv/beamlog`:

- **Einfach:** im Ordner `sudo ./beamlogctl install --here` – das schreibt die Unit mit diesem Ordner und dem Besitzer
  des Ordners als Benutzer.
- **Von Hand:** in `/etc/systemd/system/beamlog.service` den Ordner an **allen** Stellen ändern –
  `WorkingDirectory=`, `ExecStart=` und `ReadWritePaths=` (bei einem Ordner unter `/home` zusätzlich `ProtectHome=false`
  und `User=`/`Group=` auf den Besitzer des Ordners); danach `sudo systemctl daemon-reload && sudo systemctl restart beamlog`.

```ini
WorkingDirectory=/srv/beamlog
ExecStart=/srv/beamlog/BeamLog                  # Quellcode: /srv/beamlog/.venv/bin/python run.py
ReadWritePaths=/srv/beamlog
```

Ältere Units (bis 1.0.1) hatten `--config /etc/beamlog/beamlog.env` bzw. `--config /opt/beamlog/.env` im `ExecStart` –
dann gilt diese Datei und eine `.env` daneben wird **nicht** gelesen (die Startzeile „Konfiguration: …“ und ein Hinweis
zeigen das). Im Programmordner `sudo ./beamlogctl update` (läuft der Dienst schon aus diesem Ordner, bleibt er dort)
bzw. `sudo ./beamlogctl install --here` schreibt die Unit ohne `--config` neu und zieht eine Einrichtung mit
`/etc/beamlog` und `/var/lib/beamlog` in den Ordner um: Daten werden kopiert (das Original bleibt liegen), fehlende
Einstellungen in die vorhandene `.env` ergänzt, die alte Datei bleibt als `beamlog.env.migriert` liegen.

## Nützliche Befehle

```bash
./beamlogctl status                  # läuft BeamLog? (mit und ohne Dienst)
./beamlogctl log 100                 # letzte Ausgaben
sudo journalctl -u beamlog -f        # Log des Dienstes live
sudo ./beamlogctl restart
sudo nginx -t && sudo systemctl reload nginx
```

## Hostname statt IP

Damit `http://contest.local/` funktioniert, auf dem Server `avahi-daemon` installieren
(`sudo apt install avahi-daemon`) und den Hostnamen auf `contest` setzen
(`sudo hostnamectl set-hostname contest`). Windows/macOS/iOS finden `.local`-Namen automatisch.

## Wiederherstellen aus einem Backup

```bash
sudo ./beamlogctl stop
sudo gunzip -c /opt/beamlog/data/backup/beamlog-XXXX.db.gz > /opt/beamlog/data/beamlog.db
sudo chown beamlog:beamlog /opt/beamlog/data/beamlog.db
sudo ./beamlogctl start
```

Zusätzlich sichert der Server selbst alle 15 Minuten (nur bei Änderungen) nach
`/opt/beamlog/data/backup/` und beim Beenden; „Jetzt sichern“ in der Verwaltung legt
eine manuelle Sicherung an derselben Stelle an.

## Ohne nginx

Für den schnellen Einsatz reicht auch `./start.sh` im Repo-Ordner (richtet `.venv` ein, lauscht auf 0.0.0.0:8000) bzw.
`./beamlogctl start` im Hintergrund – nginx bringt nur Port 80, HTTPS-Option und das Ausliefern statischer Dateien.

## Alles in einem Ordner (Umzug älterer Installationen)

Auf dem Server liegt jetzt alles unter `/opt/beamlog`: Programm, `data/` (Datenbank, Backups, Sprachen) und `.env`
(Einstellungen) – ein Ordner, ein Besitzer (`beamlog`), keine verstreuten Rechte. Bis 1.0.0 lagen die Daten in
`/var/lib/beamlog` und die Einstellungen in `/etc/beamlog/beamlog.env`. `sudo ./beamlogctl update` (bzw.
`sudo bash deploy/install.sh --update`) holt alles automatisch in den neuen Ordner:

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
Im Checkout `git pull` und danach `sudo ./beamlogctl update` (bzw. `sudo bash deploy/install.sh --update`) ausführen –
das stellt den Server automatisch um:

- Dienst `contestlogger` wird gestoppt und entfernt, `beamlog` eingerichtet und gestartet,
- Daten werden von `/var/lib/contestlogger/` nach `/opt/beamlog/data/` **kopiert** (Datenbank heißt dann `beamlog.db`),
- `/etc/contestlogger/contestlogger.env` wird zu `/opt/beamlog/.env` (Pfade darin werden angepasst),
- die nginx-Site (auch eine eigene HTTPS-Anpassung) und das tägliche Backup werden übernommen.

Die alten Daten bleiben in `/var/lib/contestlogger/` als Sicherung liegen und können danach gelöscht werden.
Ältere Umgebungsvariablen `CONTESTLOGGER_<KEY>` werden weiterhin verstanden.
