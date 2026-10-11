#!/usr/bin/env bash
# Installiert BeamLog auf Debian/Ubuntu (auch Raspberry Pi OS) als systemd-Dienst hinter nginx.
#   sudo bash deploy/install.sh            # aus dem Repo-Verzeichnis
#   sudo bash deploy/install.sh --update   # Code aktualisieren und Dienst neu starten
#   sudo bash deploy/install.sh --url http://contest.local/   # Adresse für QR-Code/Links setzen
#
# Alle Server-Einstellungen stehen in /etc/beamlog/beamlog.env (wird beim ersten Lauf angelegt).
# Ein Server aus Version 0.9 (Dienst „contestlogger“) wird dabei automatisch auf BeamLog umgestellt.
set -euo pipefail

APP_DIR=/opt/beamlog
DATA_DIR=/var/lib/beamlog
CONF=/etc/beamlog/beamlog.env
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

# Server aus Version 0.9 (hieß „ContestLogger“): Dienst, Nutzer, Pfade und Dateien auf BeamLog umstellen.
# Die alten Daten in /var/lib/contestlogger bleiben als Sicherung liegen (kopiert, nicht verschoben).
MIGRATED=0
migrate_from_contestlogger() {
  [ -e /etc/systemd/system/contestlogger.service ] || [ -d /etc/contestlogger ] || return 0
  echo "== Umstellung von ContestLogger auf BeamLog"
  MIGRATED=1
  systemctl disable --now contestlogger >/dev/null 2>&1 || true
  id beamlog >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin beamlog
  if [ -d /var/lib/contestlogger ] && [ ! -e "$DATA_DIR/beamlog.db" ]; then
    mkdir -p "$DATA_DIR"
    cp -a /var/lib/contestlogger/. "$DATA_DIR/"
    for s in "" -wal -shm; do
      if [ -e "$DATA_DIR/contestlogger.db$s" ]; then mv "$DATA_DIR/contestlogger.db$s" "$DATA_DIR/beamlog.db$s"; fi
    done
    echo "   Daten: /var/lib/contestlogger -> $DATA_DIR (das Original bleibt als Sicherung liegen)"
  fi
  if [ -f /etc/contestlogger/contestlogger.env ] && [ ! -f "$CONF" ]; then
    mkdir -p "$(dirname "$CONF")"
    sed -e 's#/var/lib/contestlogger/contestlogger\.db#/var/lib/beamlog/beamlog.db#g' -e 's#/var/lib/contestlogger#/var/lib/beamlog#g' \
        -e 's/CONTESTLOGGER_/BEAMLOG_/g' /etc/contestlogger/contestlogger.env > "$CONF"
    echo "   Einstellungen: /etc/contestlogger/contestlogger.env -> $CONF"
  fi
  # ganz alte Unit mit --public-url in ExecStart: Adresse in die env-Datei übernehmen
  local unit=/etc/systemd/system/contestlogger.service
  if [ -f "$unit" ] && [ -f "$CONF" ] && grep -q -- '--public-url' "$unit"; then
    local url; url=$(grep -o -- '--public-url [^ ]*' "$unit" | awk '{print $2}')
    if [ -n "$url" ]; then sed -i "s#^\#\?PUBLIC_URL=.*#PUBLIC_URL=$url#" "$CONF"; fi
  fi
  rm -f "$unit"
  if [ -f /etc/nginx/sites-available/contestlogger ]; then   # eigene Anpassungen (z. B. HTTPS) bleiben erhalten
    sed -e 's#/opt/contestlogger/#/opt/beamlog/#g' \
        /etc/nginx/sites-available/contestlogger > /etc/nginx/sites-available/beamlog
    rm -f /etc/nginx/sites-enabled/contestlogger /etc/nginx/sites-available/contestlogger
    ln -sf /etc/nginx/sites-available/beamlog /etc/nginx/sites-enabled/beamlog
  fi
  rm -f /etc/cron.d/contestlogger-backup /usr/local/bin/contestlogger-backup
  case "$SRC_DIR" in /opt/contestlogger*) ;; *) rm -rf /opt/contestlogger ;; esac   # nie das Verzeichnis löschen, aus dem gerade installiert wird
  rm -rf /etc/contestlogger
  userdel contestlogger >/dev/null 2>&1 || true
  systemctl daemon-reload
}

if [ "$MODE" = install ]; then
  echo "== Pakete installieren"
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip nginx mdbtools rsync
fi
migrate_from_contestlogger
id beamlog >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin beamlog

echo "== Code nach $APP_DIR kopieren"
mkdir -p "$APP_DIR" "$DATA_DIR"
rsync -a --delete --exclude .git --exclude .venv --exclude data --exclude __pycache__ "$SRC_DIR/" "$APP_DIR/"

echo "== Python-Umgebung"
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R beamlog:beamlog "$APP_DIR" "$DATA_DIR"

echo "== Konfiguration $CONF"
mkdir -p "$(dirname "$CONF")"
if [ ! -f "$CONF" ]; then
  cp "$APP_DIR/deploy/portable/beamlog.env" "$CONF"
  echo "   neu angelegt (Vorlage deploy/portable/beamlog.env)"
else
  echo "   vorhanden, bleibt unverändert"
fi
if [ -n "$PUBLIC_URL" ]; then
  if grep -q '^#\?PUBLIC_URL=' "$CONF"; then sed -i "s#^\#\?PUBLIC_URL=.*#PUBLIC_URL=$PUBLIC_URL#" "$CONF"; else echo "PUBLIC_URL=$PUBLIC_URL" >> "$CONF"; fi
fi
chmod 640 "$CONF"; chown root:beamlog "$CONF"

echo "== systemd-Dienst"
cp "$APP_DIR/deploy/beamlog.service" /etc/systemd/system/beamlog.service
systemctl daemon-reload
systemctl enable beamlog >/dev/null
systemctl restart beamlog

if [ "$MODE" = install ] || [ "$MIGRATED" = 1 ]; then
  echo "== nginx"
  if [ "$MODE" = install ] || [ ! -f /etc/nginx/sites-available/beamlog ]; then
    cp "$APP_DIR/deploy/nginx-beamlog.conf" /etc/nginx/sites-available/beamlog
  fi
  ln -sf /etc/nginx/sites-available/beamlog /etc/nginx/sites-enabled/beamlog
  rm -f /etc/nginx/sites-enabled/default
  nginx -t && systemctl reload nginx

  echo "== Tägliches Backup (03:15 Uhr) nach $DATA_DIR/backup"
  cp "$APP_DIR/deploy/backup.sh" /usr/local/bin/beamlog-backup
  chmod +x /usr/local/bin/beamlog-backup
  echo "15 3 * * * root /usr/local/bin/beamlog-backup" > /etc/cron.d/beamlog-backup
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "Fertig. BeamLog läuft: http://${IP:-<server-ip>}/"
echo "Datenbank: $DATA_DIR/beamlog.db   Logs: journalctl -u beamlog -f"
echo "Einstellungen: $CONF   (danach: sudo systemctl restart beamlog)"
if [ "$MIGRATED" = 1 ]; then echo "Umgestellt von ContestLogger – die alten Daten liegen noch in /var/lib/contestlogger und können gelöscht werden."; fi
