#!/usr/bin/env bash
# Installiert die PORTABLE Linux-Version des ContestLoggers (aus dem Release-ZIP, kein Python nötig)
# auf Debian/Ubuntu/Raspberry Pi OS als systemd-Dienst hinter nginx.
#
#   unzip ContestLogger-<version>-linux-x86_64.zip
#   cd ContestLogger
#   sudo bash deploy/install.sh                 # Erstinstallation (nginx, Dienst, Backup-Cron)
#   sudo bash deploy/install.sh --update        # neue Version einspielen und Dienst neu starten
#   sudo bash deploy/install.sh --url http://contest.local/   # Adresse für QR-Code/Links setzen
set -euo pipefail

APP_DIR=/opt/contestlogger
DATA_DIR=/var/lib/contestlogger
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"       # der entpackte ContestLogger-Ordner
MODE=install
PUBLIC_URL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --update) MODE=update ;;
    --url) PUBLIC_URL="$2"; shift ;;
    *) echo "Unbekannte Option: $1"; exit 1 ;;
  esac
  shift
done

if [ "$(id -u)" -ne 0 ]; then echo "Bitte mit sudo ausführen."; exit 1; fi
if [ ! -x "$SRC_DIR/ContestLogger" ]; then echo "ContestLogger-Binary nicht gefunden in $SRC_DIR – bitte aus dem entpackten ZIP-Ordner aufrufen."; exit 1; fi

if [ "$MODE" = install ]; then
  echo "== Pakete installieren (nginx, sqlite3 für Backups)"
  apt-get update -qq
  apt-get install -y -qq nginx sqlite3 rsync
  id contestlogger >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin contestlogger
fi

echo "== Programm nach $APP_DIR kopieren (Daten bleiben in $DATA_DIR)"
mkdir -p "$APP_DIR" "$DATA_DIR/lang"
rsync -a --delete --exclude data "$SRC_DIR/" "$APP_DIR/"
chmod +x "$APP_DIR"/ContestLogger* "$APP_DIR"/*.sh 2>/dev/null || true
chown -R contestlogger:contestlogger "$APP_DIR" "$DATA_DIR"

echo "== systemd-Dienst"
cp "$APP_DIR/deploy/contestlogger.service" /etc/systemd/system/contestlogger.service
if [ -n "$PUBLIC_URL" ]; then
  sed -i "s#--public-url [^ ]*#--public-url $PUBLIC_URL#" /etc/systemd/system/contestlogger.service
fi
systemctl daemon-reload
systemctl enable contestlogger >/dev/null
systemctl restart contestlogger

if [ "$MODE" = install ]; then
  echo "== nginx (Port 80 -> Dienst auf 127.0.0.1:8000)"
  cp "$APP_DIR/deploy/nginx-contestlogger.conf" /etc/nginx/sites-available/contestlogger
  ln -sf /etc/nginx/sites-available/contestlogger /etc/nginx/sites-enabled/contestlogger
  rm -f /etc/nginx/sites-enabled/default
  nginx -t && systemctl reload nginx

  echo "== Tägliches Backup (03:15 Uhr) nach $DATA_DIR/backup-daily (30 Tage)"
  cp "$APP_DIR/deploy/backup.sh" /usr/local/bin/contestlogger-backup
  chmod +x /usr/local/bin/contestlogger-backup
  echo "15 3 * * * root /usr/local/bin/contestlogger-backup" > /etc/cron.d/contestlogger-backup
fi

sleep 1
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "Fertig. ContestLogger läuft: http://${IP:-<server-ip>}/   (Status: systemctl status contestlogger)"
echo "Datenbank: $DATA_DIR/contestlogger.db   Logs: journalctl -u contestlogger -f"
echo "Update später: neues ZIP entpacken und dort  sudo bash deploy/install.sh --update"
