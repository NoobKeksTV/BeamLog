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
- legt die Konfiguration `/etc/beamlog/.env` an (Dienst auf `127.0.0.1:8000`, Datenbank in `/var/lib/beamlog/`, Backups alle 15 Minuten),
- richtet den Dienst `beamlog` ein (liest die Konfiguration, Neustart bei Absturz),
- legt die nginx-Site auf Port 80 mit WebSocket-Weiterleitung an,
- richtet ein tägliches gepacktes Backup (03:15 Uhr, 30 Tage) ein.

Danach läuft der Logger unter `http://<server-ip>/`. `--url` setzt die Adresse, die im QR-Code und in Links erscheint.

### Teile weglassen: ohne nginx, ohne Dienst, ohne Backup-Cron

Jeder Teil lässt sich abschalten, die Optionen sind beliebig kombinierbar:

| Option | Wirkung |
|---|---|
| `--no-nginx` | nginx wird weder installiert noch eingerichtet – für einen eigenen Reverse-Proxy (z. B. ein vorhandenes nginx/Apache/Caddy mit anderen Seiten) oder `PORT=80` direkt. Eine früher angelegte BeamLog-Site wird entfernt; nginx selbst und andere Sites bleiben unberührt. |
| `--no-service` | Kein systemd-Dienst – BeamLog startest du selbst (eigene Unit, Container, Supervisor …); das Skript zeigt am Ende den Startbefehl. Ein früher angelegter Dienst `beamlog` wird angehalten und entfernt. |
| `--no-backup` | Kein täglicher Backup-Cron (ein vorhandener wird entfernt). Die Sicherungen des Servers selbst (`BACKUP_MIN`) laufen weiter. |
| `--with-nginx`, `--with-service`, `--with-backup` | Schalten den jeweiligen Teil wieder ein. |
| `--here` | Nicht kopieren: BeamLog bleibt im aktuellen Ordner und läuft als der aufrufende Nutzer; Daten in `./data`, Einstellungen in `./.env`. Dienst, nginx und Backup-Cron zeigen auf diesen Ordner. |
| `--deps-only` | Nur die Voraussetzungen installieren (Systempakete, beim Quellcode zusätzlich `./.venv`) – wie `--here --no-nginx --no-service --no-backup`; danach selbst starten. |
| `--system` | Gemerkte `--here`-Wahl aufheben und wieder nach `/opt/beamlog` installieren. |

```bash
sudo bash deploy/install.sh --no-nginx                 # eigener Reverse-Proxy auf 127.0.0.1:8000
sudo bash deploy/install.sh --no-nginx --no-backup     # mehrere gleichzeitig
sudo bash deploy/install.sh --deps-only                # nur Python & Co. installieren, im Ordner bleiben, selbst starten
sudo bash deploy/install.sh --here                     # im Ordner bleiben, aber mit Dienst, nginx und Backup
sudo bash deploy/install.sh --update --with-nginx      # nginx später doch wieder einrichten
sudo bash deploy/install.sh --help                     # alle Optionen
```

Die Wahl wird in `/etc/beamlog/install.options` gemerkt – ein späteres `--update` hält sich daran, ohne dass die
Optionen erneut angegeben werden müssen. Ohne nginx und mit dem Standard `HOST=127.0.0.1` ist BeamLog nur am Server
selbst erreichbar (richtig für einen eigenen Reverse-Proxy); direkt im LAN: `HOST=0.0.0.0` in `.env`.

**Wohin installiert wird:** Mit Dienst kopiert das Skript BeamLog nach `/opt/beamlog` (Daten in `/var/lib/beamlog`,
Einstellungen in `/etc/beamlog/.env`): Der Dienst läuft dort als eigener Systemnutzer `beamlog` mit gehärteter
Unit, die keinen Zugriff auf `/home` hat, und ein neu entpacktes ZIP lässt sich per `--update` einfach darüberspielen.
Das Skript kündigt das Kopieren deutlich an. **Ohne Dienst (`--no-service`) wird nichts kopiert** – BeamLog bleibt
automatisch im aktuellen Ordner. Mit `--here` bleibt es auch mit Dienst dort (die Unit läuft dann als dein Nutzer).

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

# 2. Konfiguration anlegen (Werte bei Bedarf anpassen: nano /etc/beamlog/.env)
sudo mkdir -p /etc/beamlog
sudo cp /opt/beamlog/deploy/server.env /etc/beamlog/.env
sudo chown root:beamlog /etc/beamlog/.env && sudo chmod 640 /etc/beamlog/.env

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

## Einstellungen: `/etc/beamlog/.env`

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
#DEMO=1                                         # öffentliche Demo-Instanz (siehe unten) – löscht täglich alles!
```

Nach Änderungen `sudo systemctl restart beamlog`. `install.sh` legt die Datei beim ersten Lauf aus `deploy/server.env` an und lässt sie bei `--update` unverändert; `--url` trägt nur `PUBLIC_URL` ein. Reihenfolge der Quellen: Kommandozeile überstimmt Umgebungsvariablen `BEAMLOG_<KEY>`, diese überstimmen die Datei.

Die Unit `deploy/beamlog.service` (Auszug):

```ini
[Service]
User=beamlog
WorkingDirectory=/opt/beamlog
ExecStart=/opt/beamlog/BeamLog --config /etc/beamlog/.env
Restart=always
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/beamlog
```

## Ohne nginx: direkt auf Port 80

Port und Adresse stehen nur in `/etc/beamlog/.env` – das Install-Skript richtet sich danach:

- **`PORT=80`** (mit `HOST=0.0.0.0`): BeamLog ist direkt erreichbar, **ohne nginx**. Das Skript schaltet nginx dann ab
  (es würde Port 80 belegen); der Dienst darf Port 80 öffnen (`CAP_NET_BIND_SERVICE` in der Unit).
- **jeder andere Port** (Standard `8000`, `HOST=127.0.0.1`): nginx nimmt Port 80 an und leitet an diesen Port weiter.

```bash
sudo nano /etc/beamlog/.env            # PORT=80 und HOST=0.0.0.0 eintragen
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

Wer lieber aus dem Repo installiert (Python-venv statt Binary), nutzt `deploy/install.sh` aus dem Quellcode-Checkout; dort entsteht `/opt/beamlog/.venv`. Auch diese Unit liest alle Einstellungen aus `/etc/beamlog/.env` (`run.py --config …`), das Skript legt die Datei beim ersten Lauf an und `--url` setzt die öffentliche Adresse. Updates dann mit `git pull` und `sudo bash deploy/install.sh --update`.

## Öffentliche Demo-Instanz

Für eine Vorführ-Instanz im Internet (wie [beamlogdemo.lhprinting.de](https://beamlogdemo.lhprinting.de/)) gibt es den
Demo-Modus. In `/etc/beamlog/.env`:

```ini
DEMO=1
DEMO_RESET=03:00                                # tägliches Zurücksetzen (Serverzeit)
DB=/var/lib/beamlog/beamlog-demo.db             # eigene, leere Datenbank
PUBLIC_URL=https://beamlogdemo.lhprinting.de/
```

Was der Demo-Modus macht:

- **Beispieldaten:** Beim Start und jeden Tag um `DEMO_RESET` wird **alles gelöscht** und neu angelegt: ein laufender
  „Demo-Contest UKW“ mit `DN0DEMO/P` (JO51DT, Brocken) auf 2 m, 70 cm und 23 cm, rund 95 QSOs aus der
  Stationsdatenbank, zwei Begrüßungen im Team-Chat und die mitgelieferte Stationsdatenbank. Offene Browser laden danach
  von selbst neu.
- **Feste Zugangsdaten:** Admin- und Stations-Passwort sind `demo`. Eine Leiste unter der Kopfzeile nennt sie, die
  Uhrzeit des Zurücksetzens und bittet, keine echten Zugangsdaten einzutragen; Anmelde- und Freischalt-Feld sind
  vorausgefüllt.
- **Gesperrt** (Meldung „In der Demo-Instanz gesperrt …“): Admin-Passwort ändern, Server-Einstellungen, Updates
  einspielen, ON4KST-Verbindungen und KST-Zugangsdaten, Kacheln vorab laden, Rufzeichen-Abfrage (HamQTH/QRZ), Backups,
  CW über das Funkgerät, Übersetzungen speichern, Betreuer-Importe, Importe über 5 MB. Der Beispiel-Contest, seine
  Stationen und die globale Station lassen sich nicht löschen, ihr Rufzeichen und Passwort nicht ändern.
- **Erlaubt:** loggen, bearbeiten, Karte, Flugzeug-Scatter, Statistik, Operator-Fenster, Team-Chat, eigene Contests und
  Stationen anlegen und löschen, Dateien importieren, EDI/Cabrillo/ADIF exportieren, Log-Prüfung.
- Keine automatischen Backups; das Aktionsprotokoll beginnt mit jedem Zurücksetzen neu.

**Sicherung gegen Versehen:** Enthält die Datenbank bereits Contests, die nicht aus der Demo stammen, startet BeamLog
im Demo-Modus nicht („Demo-Modus verweigert …“). Trotzdem: `DEMO=1` nie auf einer echten Contest-Installation setzen.
Updates der Demo spielt der Betreiber wie gewohnt mit `sudo bash deploy/install.sh --update` ein.

## Umstieg von ContestLogger 0.9 (Server)

Bis Version 0.9 hieß BeamLog „ContestLogger“; Dienst, Nutzer und Pfade hießen entsprechend `contestlogger`.
Das neue ZIP entpacken und dort `sudo bash deploy/install.sh --update` ausführen – das Skript stellt den Server
automatisch um:

- Dienst `contestlogger` wird gestoppt und entfernt, `beamlog` eingerichtet und gestartet,
- Daten werden von `/var/lib/contestlogger/` nach `/var/lib/beamlog/` **kopiert** (Datenbank heißt dann `beamlog.db`),
- `/etc/contestlogger/contestlogger.env` wird zu `/etc/beamlog/.env` (Pfade darin werden angepasst),
- die nginx-Site (auch eine eigene HTTPS-Anpassung) und das tägliche Backup werden übernommen.

Die alten Daten bleiben in `/var/lib/contestlogger/` als Sicherung liegen und können danach gelöscht werden.
Ältere Umgebungsvariablen `CONTESTLOGGER_<KEY>` werden weiterhin verstanden.
