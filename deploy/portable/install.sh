#!/usr/bin/env bash
# Installiert die PORTABLE Linux-Version von BeamLog (aus dem Release-ZIP, kein Python nötig)
# auf Debian/Ubuntu/Raspberry Pi OS als systemd-Dienst hinter nginx.
#
#   unzip BeamLog-<version>-linux-x86_64.zip
#   cd BeamLog
#   sudo bash deploy/install.sh                 # Erstinstallation (nginx, Dienst, Backup-Cron)
#   sudo bash deploy/install.sh --update        # neue Version einspielen und Dienst neu starten
#   sudo bash deploy/install.sh --url http://contest.local/   # Adresse für QR-Code/Links setzen
#
# Alle Server-Einstellungen stehen in /etc/beamlog/beamlog.env (wird beim ersten Lauf angelegt).
# Ein Server aus Version 0.9 (Dienst „contestlogger“) wird dabei automatisch auf BeamLog umgestellt.
set -euo pipefail

APP_DIR=/opt/beamlog
DATA_DIR=/var/lib/beamlog
CONF=/etc/beamlog/beamlog.env
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"       # der entpackte BeamLog-Ordner
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
if [ ! -x "$SRC_DIR/BeamLog" ]; then echo "BeamLog-Binary nicht gefunden in $SRC_DIR – bitte aus dem entpackten ZIP-Ordner aufrufen."; exit 1; fi

# Server aus Version 0.9 (hieß „ContestLogger“): Dienst, Nutzer, Pfade und Dateien auf BeamLog umstellen.
# Die alten Daten in /var/lib/contestlogger bleiben als Sicherung liegen (kopiert, nicht verschoben).
MIGRATED=0
NGINX_FAILED=0
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
  echo "== Pakete installieren (nginx, sqlite3 für Backups)"
  apt-get update -qq
  apt-get install -y -qq nginx sqlite3 rsync
fi
migrate_from_contestlogger
id beamlog >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin beamlog

echo "== Programm nach $APP_DIR kopieren (Daten bleiben in $DATA_DIR)"
mkdir -p "$APP_DIR" "$DATA_DIR/lang"
rsync -a --delete --exclude data "$SRC_DIR/" "$APP_DIR/"
chmod +x "$APP_DIR"/BeamLog* "$APP_DIR"/*.sh 2>/dev/null || true
chown -R beamlog:beamlog "$APP_DIR" "$DATA_DIR"

echo "== Konfiguration $CONF"
mkdir -p "$(dirname "$CONF")"
if [ ! -f "$CONF" ]; then
  cp "$APP_DIR/deploy/beamlog.env" "$CONF"
  echo "   neu angelegt (Vorlage deploy/beamlog.env)"
else
  echo "   vorhanden, bleibt unverändert"
fi
if [ -n "$PUBLIC_URL" ]; then
  if grep -q '^#\?PUBLIC_URL=' "$CONF"; then
    sed -i "s#^\#\?PUBLIC_URL=.*#PUBLIC_URL=$PUBLIC_URL#" "$CONF"
  else
    echo "PUBLIC_URL=$PUBLIC_URL" >> "$CONF"
  fi
fi
chmod 640 "$CONF"; chown root:beamlog "$CONF"

echo "== systemd-Dienst"
cp "$APP_DIR/deploy/beamlog.service" /etc/systemd/system/beamlog.service
systemctl daemon-reload
systemctl enable beamlog >/dev/null
systemctl restart beamlog

if [ "$MODE" = install ] || [ "$MIGRATED" = 1 ]; then
  echo "== nginx (Port 80 -> Dienst auf 127.0.0.1:8000)"
  if [ "$MODE" = install ] || [ ! -f /etc/nginx/sites-available/beamlog ]; then
    cp "$APP_DIR/deploy/nginx-beamlog.conf" /etc/nginx/sites-available/beamlog
  fi
  ln -sf /etc/nginx/sites-available/beamlog /etc/nginx/sites-enabled/beamlog
  rm -f /etc/nginx/sites-enabled/default
  # nginx starten, falls es (noch) nicht läuft – ein reines „reload“ scheitert bei gestopptem nginx
  if nginx -t; then
    systemctl enable nginx >/dev/null 2>&1 || true
    systemctl reload-or-restart nginx || NGINX_FAILED=1
  else
    NGINX_FAILED=1
  fi
fi

# Tägliches Backup – bei jedem Lauf einrichten (fehlt sonst, falls ein früherer Lauf abgebrochen ist)
echo "== Tägliches Backup (03:15 Uhr) nach $DATA_DIR/backup-daily (30 Tage)"
cp "$APP_DIR/deploy/backup.sh" /usr/local/bin/beamlog-backup
chmod +x /usr/local/bin/beamlog-backup
echo "15 3 * * * root /usr/local/bin/beamlog-backup" > /etc/cron.d/beamlog-backup

sleep 1
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "Fertig. BeamLog läuft: http://${IP:-<server-ip>}/   (Status: systemctl status beamlog)"
echo "Datenbank: $DATA_DIR/beamlog.db   Logs: journalctl -u beamlog -f"
echo "Einstellungen: $CONF   (danach: sudo systemctl restart beamlog)"
echo "Update später: neues ZIP entpacken und dort  sudo bash deploy/install.sh --update"
if [ "$MIGRATED" = 1 ]; then echo "Umgestellt von ContestLogger – die alten Daten liegen noch in /var/lib/contestlogger und können gelöscht werden."; fi
if [ "$NGINX_FAILED" = 1 ]; then
  echo
  echo "!! nginx läuft nicht – BeamLog selbst läuft (127.0.0.1:8000), ist aber über Port 80 noch nicht erreichbar."
  echo "   Ursache ansehen:   sudo journalctl -u nginx -n 30 --no-pager"
  echo "   Port 80 belegt?    sudo ss -ltnp 'sport = :80'   (z. B. apache2: sudo systemctl disable --now apache2)"
  echo "   Danach:            sudo systemctl enable --now nginx"
fi
