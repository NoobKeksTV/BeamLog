# Server-Deploy: Debian mit nginx und systemd

Für einen dauerhaft laufenden Server (z. B. Raspberry Pi oder ein kleiner Debian-Rechner im Shack) liegt im Linux-ZIP der Ordner `deploy/` mit allem Nötigen. Python wird auf dem Server **nicht** benötigt.

## Schnellinstallation

```bash
unzip BeamLog-<version>-linux-x86_64.zip
cd BeamLog
sudo ./beamlogctl install
```

`beamlogctl` ist der eine Befehl für den Server: einrichten, starten, stoppen, Status, Log und Update. `install` fragt
nacheinander (Enter übernimmt den Vorschlag in `[ ]`):

1. **systemd-Dienst einrichten?** – BeamLog startet mit dem Server und nach einem Absturz neu.
2. **Nach `/opt/beamlog` kopieren?** (nur mit Dienst) – eigener Systemnutzer `beamlog`, gehärtete Unit; *Nein* = im
   aktuellen Ordner bleiben.
3. **nginx davor einrichten?** – Port 80 mit WebSocket-Weiterleitung; *Nein* z. B. bei eigenem Reverse-Proxy.
4. **Tägliches Backup?** – gepackte Sicherung um 03:15 Uhr, 30 Tage aufbewahrt.
5. **Adresse** für QR-Code und Links (z. B. `http://contest.local/`, Enter = unverändert).

Danach zeigt es die Auswahl und fragt „Weiter?“; ohne Dienst bietet es an, BeamLog gleich im Hintergrund zu starten.
Mit allen Teilen

- installiert es `nginx`, `sqlite3` und `rsync`,
- kopiert das Programm nach `/opt/beamlog` und legt den Systemnutzer `beamlog` an,
- legt die Konfiguration `/opt/beamlog/.env` an (Dienst auf `127.0.0.1:8000`, Datenbank in `/opt/beamlog/data/`, Backups alle 15 Minuten),
- richtet den Dienst `beamlog` ein (liest die Konfiguration, Neustart bei Absturz),
- legt die nginx-Site auf Port 80 mit WebSocket-Weiterleitung an,
- richtet ein tägliches gepacktes Backup (03:15 Uhr, 30 Tage) ein.

Danach läuft der Logger unter `http://<server-ip>/`. Die Arbeit macht `deploy/install.sh`, das sich weiterhin auch
direkt aufrufen lässt (`sudo bash deploy/install.sh --help`).

### Ohne Rückfragen: Optionen

Angegebene Teile werden nicht mehr gefragt, mit `-y` fragt `beamlogctl` gar nichts (für Skripte und Automatisierung).
Die Optionen sind beliebig kombinierbar:

| Option | Wirkung |
|---|---|
| `--no-nginx` / `--nginx` | nginx wird weder installiert noch eingerichtet – für einen eigenen Reverse-Proxy (z. B. ein vorhandenes nginx/Apache/Caddy mit anderen Seiten) oder `PORT=80` direkt. Eine früher angelegte BeamLog-Site wird entfernt; nginx selbst und andere Sites bleiben unberührt. `--nginx` richtet es wieder ein. |
| `--no-service` / `--service` | Kein systemd-Dienst – BeamLog läuft dann mit `./beamlogctl start` im Hintergrund (oder über eine eigene Unit, einen Container, ein Control Panel …). Ein früher angelegter Dienst `beamlog` wird angehalten und entfernt. |
| `--no-backup` / `--backup` | Kein täglicher Backup-Cron (ein vorhandener wird entfernt). Die Sicherungen des Servers selbst (`BACKUP_MIN`) laufen weiter. |
| `--here` | Nicht kopieren: BeamLog bleibt im aktuellen Ordner und läuft als dessen Besitzer; Daten in `./data`, Einstellungen in `./.env`. Dienst, nginx und Backup-Cron zeigen auf diesen Ordner. |
| `--system` | Gemerkte `--here`-Wahl aufheben und wieder nach `/opt/beamlog` installieren. |
| `--url ADRESSE` | Adresse, die im QR-Code und in Links erscheint (`PUBLIC_URL`). |
| `--deps-only` | Nur die Voraussetzungen installieren (Systempakete, beim Quellcode zusätzlich `./.venv`) – wie `--here --no-nginx --no-service --no-backup`. |
| `-y`, `--yes` | Keine Rückfragen: nicht angegebene Teile wie beim letzten Mal (beim ersten Mal: alles einrichten). |

```bash
sudo ./beamlogctl install -y                           # alles einrichten, ohne Rückfrage
sudo ./beamlogctl install --no-nginx -y                # eigener Reverse-Proxy auf 127.0.0.1:8000
sudo ./beamlogctl install --no-nginx --no-backup -y    # mehrere gleichzeitig
sudo ./beamlogctl install --no-service --no-nginx -y   # ohne Dienst: bleibt im Ordner, Start mit ./beamlogctl start
sudo ./beamlogctl install --deps-only                  # nur Python & Co. installieren
sudo ./beamlogctl install --here                       # im Ordner bleiben, aber mit Dienst, nginx und Backup
sudo ./beamlogctl install --nginx -y                   # nginx später doch wieder einrichten
./beamlogctl help                                      # alle Befehle und Optionen
```

Die Wahl wird in `/opt/beamlog/.install.options` (bzw. `.install.options` im Ordner) gemerkt – ein späteres Update
hält sich daran, ohne dass die Optionen erneut angegeben werden müssen. Ohne nginx und mit dem Standard
`HOST=127.0.0.1` ist BeamLog nur am Server selbst erreichbar (richtig für einen eigenen Reverse-Proxy); direkt im LAN:
`HOST=0.0.0.0` in `.env`.

**Wohin installiert wird:** Mit Dienst wird BeamLog standardmäßig nach `/opt/beamlog` kopiert (Daten in
`/opt/beamlog/data`, Einstellungen in `/opt/beamlog/.env` – alles in einem Ordner): Der Dienst läuft dort als eigener
Systemnutzer `beamlog` mit gehärteter Unit, die keinen Zugriff auf `/home` hat, und ein neu entpacktes ZIP lässt sich
per Update einfach darüberspielen. Das Skript kündigt das Kopieren deutlich an. **Ohne Dienst wird nichts kopiert** –
BeamLog bleibt im aktuellen Ordner. Mit `--here` bleibt es auch mit Dienst dort (die Unit läuft dann als Besitzer des
Ordners).

Die Sicherungen des Servers lassen sich in der Verwaltung einsehen und anstoßen:

![Backups auf dem Server](img/backups.png)

**Update später:** neues ZIP entpacken und im entpackten Ordner `sudo ./beamlogctl update` (spielt den neuen Stand nach `/opt/beamlog` ein und startet neu). Daten und Einstellungen bleiben erhalten. Alternativ aktualisiert sich der Server selbst über Verwaltung → Updates, siehe [Updates](Updates.md).

## Von Hand installieren

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
#    (anderer Ordner als /opt/beamlog: vorher in der Unit WorkingDirectory, ExecStart und ReadWritePaths anpassen, siehe unten)
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

## Einstellungen: `/opt/beamlog/.env`

Alle Server-Einstellungen stehen in einer Datei im `.env`-Format; die Unit selbst enthält keine Optionen mehr:

```ini
HOST=127.0.0.1                                  # hinter nginx nur lokal
PORT=8000
#DB=/opt/beamlog/data/beamlog.db                # Standard: data/ im Programmordner
BACKUP_MIN=15                                   # automatische Sicherung alle N Minuten (0 = aus)
PUBLIC_URL=http://contest.local/                # Adresse im QR-Code und in Links
#KST_HOST=www.on4kst.info                       # ON4KST-Server (normalerweise unverändert)
#KST_PORT=23000
#GITHUB_TOKEN=                                  # nur für ein privates Repo (Updates, Stationsdatenbank)
#MAINTAINER=1                                   # Betreuer-Modus: Quellen-Importe für die zentrale Stationsdatenbank
#DEMO=1                                         # öffentliche Demo-Instanz (siehe unten) – löscht täglich alles!
```

Nach Änderungen `sudo ./beamlogctl restart` (bzw. `sudo systemctl restart beamlog`). `install.sh` legt die Datei beim ersten Lauf aus `deploy/server.env` an und lässt sie bei `--update` unverändert; `--url` trägt nur `PUBLIC_URL` ein. Reihenfolge der Quellen: Kommandozeile überstimmt Umgebungsvariablen `BEAMLOG_<KEY>`, diese überstimmen die Datei.

Die Unit `deploy/beamlog.service` (Auszug):

```ini
[Service]
User=beamlog
WorkingDirectory=/opt/beamlog
ExecStart=/opt/beamlog/BeamLog                  # liest die .env daneben (/opt/beamlog/.env)
Restart=always
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/beamlog
```

## Dienst in einem eigenen Ordner statt /opt/beamlog

Die mitgelieferte Unit `deploy/beamlog.service` (im Linux-ZIP) ist auf `/opt/beamlog` eingestellt. BeamLog liest seine Einstellungen
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

## Ohne nginx: direkt auf Port 80

Port und Adresse stehen nur in `/opt/beamlog/.env` – das Install-Skript richtet sich danach:

- **`PORT=80`** (mit `HOST=0.0.0.0`): BeamLog ist direkt erreichbar, **ohne nginx**. Das Skript schaltet nginx dann ab
  (es würde Port 80 belegen); der Dienst darf Port 80 öffnen (`CAP_NET_BIND_SERVICE` in der Unit).
- **jeder andere Port** (Standard `8000`, `HOST=127.0.0.1`): nginx nimmt Port 80 an und leitet an diesen Port weiter.

```bash
sudo nano /opt/beamlog/.env            # PORT=80 und HOST=0.0.0.0 eintragen
sudo ./beamlogctl update                      # im entpackten BeamLog-Ordner: stellt nginx und Dienst passend ein
```

Nur ein Neustart reicht beim Wechsel zwischen den beiden Varianten nicht, weil dann nginx weiter Port 80 belegt.

## nginx-Site

`deploy/nginx-beamlog.conf` reicht alles an `127.0.0.1:8000` durch; wichtig ist der WebSocket-Block für `/ws` (Live-Updates, Chat, Operator-Fenster) und `client_max_body_size 50m` für Importe. Für HTTPS liegt im Quellcode unter `deploy/nginx-beamlog-ssl.conf` eine Vorlage (Zertifikat z. B. per certbot oder selbstsigniert).

## Bedienen: start, stop, status, log, update

```bash
./beamlogctl status               # läuft? Exit-Code 0 = ja, sonst 1 – die Zeile sagt warum
sudo ./beamlogctl start|stop|restart
./beamlogctl log 100              # letzte Ausgaben (mit Dienst aus dem Journal, enthält auch das Aktionsprotokoll)
sudo ./beamlogctl update          # neuen Stand einspielen und neu starten
journalctl -u beamlog -f          # Live-Log des Dienstes
```

Mit Dienst steuert `beamlogctl` den Dienst `beamlog` (über systemctl), ohne Dienst startet es `./start.sh` bzw. das
Programm im Hintergrund (Ausgabe in `data/beamlog.log`). Nach der Installation liegt es auch unter
`/opt/beamlog/beamlogctl`. `status` beendet die eigene Shell nicht und eignet sich für Control Panels (z. B.
ServerController: Start `sh ./beamlogctl start`, Stopp `sh ./beamlogctl stop`, Status `sh ./beamlogctl status`).

`update` holt im Git-Checkout zuerst den neuen Stand (`git pull`). Liegt der Dienst in `/opt/beamlog`, fragt es im
Quellordner bzw. im neu entpackten ZIP, ob dieser Stand dorthin eingespielt werden soll (ohne Rückfrage:
`update --service`). Ohne Dienst startet es ein laufendes BeamLog mit dem neuen Stand neu. Ein zweites BeamLog in einem
anderen Ordner (etwa eine Demo) steuert nie den Dienst.

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

## Datenbank und Backups

- Datenbank: `/opt/beamlog/data/beamlog.db` (SQLite, WAL-Modus, synchrones Schreiben – ein Stromausfall beschädigt sie nicht).
- Automatische Sicherungen des Servers: `/opt/beamlog/data/backup/` (nur wenn sich etwas geändert hat, plus beim Beenden und vor jedem Update).
- Tägliche gepackte Sicherung des Cron-Jobs: `/opt/beamlog/data/backup-daily/`.
- Eigene Sprachdateien: `/opt/beamlog/data/lang/<code>.json`.

Wiederherstellen: Dienst stoppen, Sicherung nach `beamlog.db` kopieren, Dienst starten.

## Quellcode-Variante auf dem Server

Wer lieber aus dem Repo installiert (Python-venv statt Binary), ruft `sudo ./beamlogctl install` im Quellcode-Checkout auf; dort entsteht `/opt/beamlog/.venv`. Auch diese Unit liest alle Einstellungen aus der `.env` neben dem Programm (`/opt/beamlog/.env`), das Skript legt die Datei beim ersten Lauf an und `--url` setzt die öffentliche Adresse. Updates dann mit `sudo ./beamlogctl update` (holt per `git pull` und spielt ein).

## Öffentliche Demo-Instanz

Für eine Vorführ-Instanz im Internet (wie [beamlogdemo.lhprinting.de](https://beamlogdemo.lhprinting.de/)) gibt es den
Demo-Modus. In `/opt/beamlog/.env`:

```ini
DEMO=1
DEMO_RESET=03:00                                # tägliches Zurücksetzen (Serverzeit)
DB=/opt/beamlog/data/beamlog-demo.db             # eigene, leere Datenbank
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
  Übersetzungen speichern, Betreuer-Importe, Importe über 5 MB. Der Beispiel-Contest, seine
  Stationen und die globale Station lassen sich nicht löschen, ihr Rufzeichen und Passwort nicht ändern.
- **Erlaubt:** loggen, bearbeiten, Karte, Flugzeug-Scatter, Statistik, Operator-Fenster, Team-Chat, eigene Contests und
  Stationen anlegen und löschen, Dateien importieren, EDI/Cabrillo/ADIF exportieren, Log-Prüfung.
- Keine automatischen Backups; das Aktionsprotokoll beginnt mit jedem Zurücksetzen neu.

**Sicherung gegen Versehen:** Enthält die Datenbank bereits Contests, die nicht aus der Demo stammen, startet BeamLog
im Demo-Modus nicht („Demo-Modus verweigert …“). Trotzdem: `DEMO=1` nie auf einer echten Contest-Installation setzen.
Updates der Demo spielt der Betreiber wie gewohnt mit `sudo ./beamlogctl update` ein. Läuft die Demo ohne eigenen Dienst
neben einem anderen BeamLog (z. B. in `/opt/apps/beamlogdemo`), steuert man sie mit `./beamlogctl` in ihrem Ordner.

## Umstieg von ContestLogger 0.9 (Server)

Bis Version 0.9 hieß BeamLog „ContestLogger“; Dienst, Nutzer und Pfade hießen entsprechend `contestlogger`.
Das neue ZIP entpacken und dort `sudo ./beamlogctl update` (bzw. `sudo bash deploy/install.sh --update`) ausführen –
das stellt den Server automatisch um:

- Dienst `contestlogger` wird gestoppt und entfernt, `beamlog` eingerichtet und gestartet,
- Daten werden von `/var/lib/contestlogger/` nach `/opt/beamlog/data/` **kopiert** (Datenbank heißt dann `beamlog.db`),
- `/etc/contestlogger/contestlogger.env` wird zu `/opt/beamlog/.env` (Pfade darin werden angepasst),
- die nginx-Site (auch eine eigene HTTPS-Anpassung) und das tägliche Backup werden übernommen.

Die alten Daten bleiben in `/var/lib/contestlogger/` als Sicherung liegen und können danach gelöscht werden.
Ältere Umgebungsvariablen `CONTESTLOGGER_<KEY>` werden weiterhin verstanden.
