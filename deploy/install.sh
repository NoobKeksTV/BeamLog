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

# Wert aus der env-Datei lesen (letzte Zeile gewinnt, Kommentare/Anführungszeichen entfernt)
conf_get() { { grep -E "^[[:space:]]*$1=" "$CONF" 2>/dev/null || true; } | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]#.*$//' -e "s/^[[:space:]\"']*//" -e "s/[[:space:]\"']*\$//"; }
conf_set() { if grep -qE "^[[:space:]]*#?[[:space:]]*$1=" "$CONF"; then sed -i -E "s|^[[:space:]]*#?[[:space:]]*$1=.*|$1=$2|" "$CONF"; else echo "$1=$2" >> "$CONF"; fi; }
# Optionen --port/--host/--public-url aus einer (alten) Dienst-Unit in die env-Datei übernehmen – die neue Unit hat keine
adopt_unit_options() {
  local unit=$1 opt key val
  [ -f "$unit" ] && [ -f "$CONF" ] || return 0
  for opt in port host public-url; do
    val=$({ grep -o -- "--$opt [^ ]*" "$unit" || true; } | awk '{print $2}' | tail -1)
    key=$(echo "$opt" | tr 'a-z-' 'A-Z_')
    if [ -n "$val" ] && [ "$(conf_get "$key")" != "$val" ]; then conf_set "$key" "$val"; echo "   $key=$val aus $(basename "$unit") übernommen"; fi
  done
}

# Server aus Version 0.9 (hieß „ContestLogger“): Dienst, Nutzer, Pfade und Dateien auf BeamLog umstellen.
# Die alten Daten in /var/lib/contestlogger bleiben als Sicherung liegen (kopiert, nicht verschoben).
MIGRATED=0
NGINX_FAILED=0
SERVICE_FAILED=0
DIRECT=0
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
  # Port/Adresse aus der alten Unit übernehmen (z. B. die Port-80-Variante mit --host 0.0.0.0 --port 80)
  local unit=/etc/systemd/system/contestlogger.service
  adopt_unit_options "$unit"
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

# Port und Adresse kommen aus der env-Datei. PORT=80: BeamLog direkt erreichbar, ohne nginx davor.
# Jeder andere Port: nginx auf Port 80 leitet an 127.0.0.1:<PORT> weiter.
adopt_unit_options /etc/systemd/system/beamlog.service   # von Hand eingespielte Unit mit --port 80 o. ä.
CONF_PORT=$(conf_get PORT); CONF_PORT=${CONF_PORT:-8000}
CONF_HOST=$(conf_get HOST); CONF_HOST=${CONF_HOST:-0.0.0.0}
if [ "$CONF_PORT" = 80 ]; then
  DIRECT=1
  if [ "$CONF_HOST" = 127.0.0.1 ] || [ "$CONF_HOST" = localhost ]; then
    conf_set HOST 0.0.0.0; CONF_HOST=0.0.0.0
    echo "   PORT=80 ohne nginx: HOST auf 0.0.0.0 gesetzt (sonst wäre BeamLog nur am Server selbst erreichbar)"
  fi
fi

if [ "$DIRECT" = 1 ]; then
  echo "== nginx: nicht nötig, BeamLog läuft direkt auf Port 80"
  rm -f /etc/nginx/sites-enabled/beamlog
  if systemctl is-active --quiet nginx 2>/dev/null; then
    echo "   nginx belegt Port 80 und wird angehalten (wieder einschalten: sudo systemctl enable --now nginx)"
    systemctl disable --now nginx >/dev/null 2>&1 || true
  fi
elif [ "$MODE" = install ] || [ "$MIGRATED" = 1 ] || [ ! -e /etc/nginx/sites-enabled/beamlog ]; then
  echo "== nginx (Port 80 -> Dienst auf 127.0.0.1:$CONF_PORT)"
  if [ "$MODE" = install ] || [ ! -f /etc/nginx/sites-available/beamlog ]; then
    cp "$APP_DIR/deploy/nginx-beamlog.conf" /etc/nginx/sites-available/beamlog
  fi
  sed -i -E "s#proxy_pass http://127\.0\.0\.1:[0-9]+#proxy_pass http://127.0.0.1:$CONF_PORT#g" /etc/nginx/sites-available/beamlog
  ln -sf /etc/nginx/sites-available/beamlog /etc/nginx/sites-enabled/beamlog
  rm -f /etc/nginx/sites-enabled/default
  # nginx starten, falls es (noch) nicht läuft – ein reines „reload“ scheitert bei gestopptem nginx
  if nginx -t; then
    systemctl enable nginx >/dev/null 2>&1 || true
    systemctl reload-or-restart nginx || NGINX_FAILED=1
  else
    NGINX_FAILED=1
  fi
else
  # nginx-Site vorhanden: nur den Zielport nachziehen, falls PORT geändert wurde
  if ! grep -q "proxy_pass http://127.0.0.1:$CONF_PORT" /etc/nginx/sites-available/beamlog 2>/dev/null; then
    sed -i -E "s#proxy_pass http://127\.0\.0\.1:[0-9]+#proxy_pass http://127.0.0.1:$CONF_PORT#g" /etc/nginx/sites-available/beamlog
    if nginx -t >/dev/null 2>&1; then systemctl reload-or-restart nginx || NGINX_FAILED=1; else NGINX_FAILED=1; fi
  fi
fi

echo "== systemd-Dienst"
cp "$APP_DIR/deploy/beamlog.service" /etc/systemd/system/beamlog.service
systemctl daemon-reload
systemctl enable beamlog >/dev/null
systemctl restart beamlog || true
sleep 2
systemctl is-active --quiet beamlog || SERVICE_FAILED=1

# Tägliches Backup – bei jedem Lauf einrichten (fehlt sonst, falls ein früherer Lauf abgebrochen ist)
echo "== Tägliches Backup (03:15 Uhr) nach $DATA_DIR/backup"
cp "$APP_DIR/deploy/backup.sh" /usr/local/bin/beamlog-backup
chmod +x /usr/local/bin/beamlog-backup
echo "15 3 * * * root /usr/local/bin/beamlog-backup" > /etc/cron.d/beamlog-backup

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "Fertig. BeamLog: http://${IP:-<server-ip>}/   (Status: systemctl status beamlog)"
echo "Datenbank: $DATA_DIR/beamlog.db   Logs: journalctl -u beamlog -f"
echo "Einstellungen: $CONF   (danach: sudo systemctl restart beamlog)"
if [ "$MIGRATED" = 1 ]; then echo "Umgestellt von ContestLogger – die alten Daten liegen noch in /var/lib/contestlogger und können gelöscht werden."; fi
if [ "$SERVICE_FAILED" = 1 ]; then
  echo
  echo "!! Der Dienst beamlog läuft nicht. Ursache ansehen:  sudo journalctl -u beamlog -n 40 --no-pager"
  if [ "$DIRECT" = 1 ]; then echo "   Port 80 belegt?  sudo ss -ltnp 'sport = :80'"; fi
fi
if [ "$NGINX_FAILED" = 1 ]; then
  echo
  echo "!! nginx läuft nicht – BeamLog selbst läuft (127.0.0.1:$CONF_PORT), ist aber über Port 80 noch nicht erreichbar."
  echo "   Ursache ansehen:   sudo journalctl -u nginx -n 30 --no-pager"
  echo "   Port 80 belegt?    sudo ss -ltnp 'sport = :80'   (z. B. apache2: sudo systemctl disable --now apache2)"
  echo "   Danach:            sudo systemctl enable --now nginx"
  echo "   Ohne nginx:        in $CONF  PORT=80  eintragen und  sudo bash deploy/install.sh --update"
fi
