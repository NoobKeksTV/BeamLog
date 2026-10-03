#!/usr/bin/env bash
# Installiert den ContestLogger auf Debian/Ubuntu (auch Raspberry Pi OS) als systemd-Dienst hinter nginx.
#   sudo bash deploy/install.sh            # aus dem Repo-Verzeichnis
#   sudo bash deploy/install.sh --update   # Code aktualisieren und Dienst neu starten
set -euo pipefail

APP_DIR=/opt/contestlogger
DATA_DIR=/var/lib/contestlogger
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$(id -u)" -ne 0 ]; then echo "Bitte mit sudo ausführen."; exit 1; fi

if [ "${1:-}" != "--update" ]; then
  echo "== Pakete installieren"
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip nginx mdbtools rsync
  id contestlogger >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin contestlogger
fi

echo "== Code nach $APP_DIR kopieren"
mkdir -p "$APP_DIR" "$DATA_DIR"
rsync -a --delete --exclude .git --exclude .venv --exclude data --exclude __pycache__ "$SRC_DIR/" "$APP_DIR/"

echo "== Python-Umgebung"
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R contestlogger:contestlogger "$APP_DIR" "$DATA_DIR"

echo "== systemd-Dienst"
cp "$APP_DIR/deploy/contestlogger.service" /etc/systemd/system/contestlogger.service
systemctl daemon-reload
systemctl enable contestlogger >/dev/null
systemctl restart contestlogger

if [ "${1:-}" != "--update" ]; then
  echo "== nginx"
  cp "$APP_DIR/deploy/nginx-contestlogger.conf" /etc/nginx/sites-available/contestlogger
  ln -sf /etc/nginx/sites-available/contestlogger /etc/nginx/sites-enabled/contestlogger
  rm -f /etc/nginx/sites-enabled/default
  nginx -t && systemctl reload nginx

  echo "== Tägliches Backup (03:15 Uhr) nach $DATA_DIR/backup"
  cp "$APP_DIR/deploy/backup.sh" /usr/local/bin/contestlogger-backup
  chmod +x /usr/local/bin/contestlogger-backup
  echo "15 3 * * * root /usr/local/bin/contestlogger-backup" > /etc/cron.d/contestlogger-backup
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "Fertig. ContestLogger läuft: http://${IP:-<server-ip>}/"
echo "Datenbank: $DATA_DIR/contestlogger.db   Logs: journalctl -u contestlogger -f"
