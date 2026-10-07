#!/usr/bin/env bash
# Installiert den ContestLogger auf Debian/Ubuntu (auch Raspberry Pi OS) als systemd-Dienst hinter nginx.
#   sudo bash deploy/install.sh            # aus dem Repo-Verzeichnis
#   sudo bash deploy/install.sh --update   # Code aktualisieren und Dienst neu starten
#   sudo bash deploy/install.sh --url http://contest.local/   # Adresse für QR-Code/Links setzen
#
# Alle Server-Einstellungen stehen in /etc/contestlogger/contestlogger.env (wird beim ersten Lauf angelegt).
set -euo pipefail

APP_DIR=/opt/contestlogger
DATA_DIR=/var/lib/contestlogger
CONF=/etc/contestlogger/contestlogger.env
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
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

if [ "$MODE" = install ]; then
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

echo "== Konfiguration $CONF"
mkdir -p "$(dirname "$CONF")"
if [ ! -f "$CONF" ]; then
  cp "$APP_DIR/deploy/portable/contestlogger.env" "$CONF"
  echo "   neu angelegt (Vorlage deploy/portable/contestlogger.env)"
else
  echo "   vorhanden, bleibt unverändert"
fi
if [ -n "$PUBLIC_URL" ]; then
  if grep -q '^#\?PUBLIC_URL=' "$CONF"; then sed -i "s#^\#\?PUBLIC_URL=.*#PUBLIC_URL=$PUBLIC_URL#" "$CONF"; else echo "PUBLIC_URL=$PUBLIC_URL" >> "$CONF"; fi
fi
chmod 640 "$CONF"; chown root:contestlogger "$CONF"
# alte Unit mit Optionen in ExecStart? -> öffentliche Adresse in die env-Datei übernehmen
OLD_UNIT=/etc/systemd/system/contestlogger.service
if [ -f "$OLD_UNIT" ] && grep -q -- '--public-url' "$OLD_UNIT" && [ -z "$PUBLIC_URL" ]; then
  OLD_URL=$(grep -o -- '--public-url [^ ]*' "$OLD_UNIT" | awk '{print $2}')
  [ -n "$OLD_URL" ] && sed -i "s#^\#\?PUBLIC_URL=.*#PUBLIC_URL=$OLD_URL#" "$CONF"
fi

echo "== systemd-Dienst"
cp "$APP_DIR/deploy/contestlogger.service" /etc/systemd/system/contestlogger.service
systemctl daemon-reload
systemctl enable contestlogger >/dev/null
systemctl restart contestlogger

if [ "$MODE" = install ]; then
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
echo "Einstellungen: $CONF   (danach: sudo systemctl restart contestlogger)"
