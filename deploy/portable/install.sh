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
# Teile weglassen (beliebig kombinierbar, die Wahl wird in <ordner>/.install.options gemerkt und gilt auch für --update):
#   --no-nginx     nginx weder installieren noch einrichten (eigener Reverse-Proxy oder PORT=80 direkt);
#                  eine früher angelegte BeamLog-Site wird entfernt, nginx selbst und andere Sites bleiben unberührt
#   --no-service   keinen systemd-Dienst anlegen (BeamLog selbst starten, z. B. eigene Unit oder Container);
#                  ein früher angelegter Dienst „beamlog“ wird angehalten und entfernt. Ohne Dienst wird nichts nach
#                  /opt/beamlog kopiert – BeamLog bleibt automatisch in diesem Ordner (wie --here)
#   --no-backup    keinen täglichen Backup-Cron einrichten (ein vorhandener wird entfernt)
#   --with-nginx / --with-service / --with-backup   gemerkte Wahl wieder aufheben
#
# Mit Dienst wird BeamLog nach /opt/beamlog kopiert (fester Ort, eigener Systemnutzer, gehärtete Unit) – das Skript
# sagt das deutlich. Im aktuellen Ordner lassen statt zu kopieren:
#   --here         BeamLog bleibt, wo es liegt (dieser Ordner), läuft als der aufrufende Nutzer; Daten in ./data,
#                  Einstellungen in ./.env. Dienst, nginx und Backup-Cron zeigen dann auf diesen Ordner.
#   --deps-only    nur die Voraussetzungen installieren (Systempakete) –
#                  wie --here --no-nginx --no-service --no-backup; danach selbst starten
#   --system       gemerkte --here-Wahl aufheben und wieder nach /opt/beamlog installieren
#   Beispiel:  sudo bash deploy/install.sh --deps-only        bzw.   sudo bash deploy/install.sh --here --no-nginx
#   Beispiel:  sudo bash deploy/install.sh --no-nginx --no-backup
#
# Alles liegt in EINEM Ordner: /opt/beamlog (Programm), /opt/beamlog/data (Datenbank, Backups) und /opt/beamlog/.env
# (Einstellungen, wird beim ersten Lauf angelegt). Ältere Installationen (Daten in /var/lib/beamlog, Einstellungen in
# /etc/beamlog/.env bzw. beamlog.env) werden beim Update automatisch dorthin geholt.
# Ein Server aus Version 0.9 (Dienst „contestlogger“) wird dabei automatisch auf BeamLog umgestellt.
set -euo pipefail

APP_DIR=/opt/beamlog
DATA_DIR=/opt/beamlog/data          # alles in einem Ordner (bis 1.0.3: /var/lib/beamlog und /etc/beamlog)
CONF=/opt/beamlog/.env
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"       # der entpackte BeamLog-Ordner
MODE=install
PUBLIC_URL=""
CLI_NGINX=""; CLI_SERVICE=""; CLI_BACKUP=""; CLI_HERE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --update) MODE=update ;;
    --url) PUBLIC_URL="$2"; shift ;;
    --no-nginx) CLI_NGINX=0 ;;
    --with-nginx) CLI_NGINX=1 ;;
    --no-service) CLI_SERVICE=0 ;;
    --with-service) CLI_SERVICE=1 ;;
    --no-backup) CLI_BACKUP=0 ;;
    --with-backup) CLI_BACKUP=1 ;;
    --here|--in-place) CLI_HERE=1 ;;
    --system) CLI_HERE=0 ;;
    --deps-only) CLI_HERE=1; CLI_NGINX=0; CLI_SERVICE=0; CLI_BACKUP=0 ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unbekannte Option: $1  (Hilfe: --help)"; exit 1 ;;
  esac
  shift
done

# Ort: /opt/beamlog (Standard) oder dieser Ordner (--here, wird im Ordner gemerkt)
HERE=0
if [ -f "$SRC_DIR/.install.options" ] && grep -qx 'HERE=1' "$SRC_DIR/.install.options"; then HERE=1; fi
[ -n "$CLI_HERE" ] && HERE=$CLI_HERE
# Ohne Dienst gibt es keinen Grund zu kopieren: dann bleibt BeamLog automatisch in diesem Ordner (außer mit --system)
AUTO_HERE=0
if [ -z "$CLI_HERE" ] && [ "$CLI_SERVICE" = 0 ] && [ "$HERE" = 0 ]; then HERE=1; AUTO_HERE=1; fi
RUN_USER=beamlog; RUN_GROUP=beamlog
OPTS="$APP_DIR/.install.options"
if [ "$HERE" = 1 ]; then
  case "$SRC_DIR" in *[[:space:]]*) echo "--here: Der Ordnerpfad enthält Leerzeichen ($SRC_DIR) – bitte in einen Ordner ohne Leerzeichen legen."; exit 1 ;; esac
  APP_DIR="$SRC_DIR"; DATA_DIR="$SRC_DIR/data"; CONF="$SRC_DIR/.env"; OPTS="$SRC_DIR/.install.options"
  RUN_USER="${SUDO_USER:-root}"; RUN_GROUP="$(id -gn "$RUN_USER")"
fi
# Welche Teile eingerichtet werden (1 = ja): gemerkte Wahl laden, Kommandozeile überstimmt sie
WANT_NGINX=1; WANT_SERVICE=1; WANT_BACKUP=1
OPTS_CANDS=("$OPTS"); [ "$HERE" = 0 ] && OPTS_CANDS+=(/etc/beamlog/install.options)   # gemerkte Wahl älterer Installationen
for f in "${OPTS_CANDS[@]}"; do
  if [ -f "$f" ]; then
    # shellcheck disable=SC1090
    . <(grep -E '^WANT_(NGINX|SERVICE|BACKUP)=[01]$' "$f" || true)
    break
  fi
done
[ -n "$CLI_NGINX" ] && WANT_NGINX=$CLI_NGINX
[ -n "$CLI_SERVICE" ] && WANT_SERVICE=$CLI_SERVICE
[ -n "$CLI_BACKUP" ] && WANT_BACKUP=$CLI_BACKUP
# Befehle im --here-Modus als der Besitzer des Ordners ausführen (nicht als root)
as_run() { if [ "$HERE" = 1 ] && [ "$RUN_USER" != root ]; then runuser -u "$RUN_USER" -- "$@"; else "$@"; fi; }

if [ "$(id -u)" -ne 0 ]; then echo "Bitte mit sudo ausführen."; exit 1; fi

# Die Einstellungsdatei heißt jetzt „.env“: eine vorhandene beamlog.env (bzw. contestlogger.env) daneben umbenennen,
# damit beim Update nichts verloren geht. Die Dienst-Unit wird weiter unten passend neu geschrieben.
for OLD_CONF in "$(dirname "$CONF")/beamlog.env" "$(dirname "$CONF")/contestlogger.env"; do
  if [ -f "$OLD_CONF" ] && [ ! -f "$CONF" ]; then
    mv "$OLD_CONF" "$CONF"
    echo "== Einstellungen umbenannt: $OLD_CONF -> $CONF"
  elif [ -f "$OLD_CONF" ]; then
    echo "== Hinweis: $OLD_CONF wird nicht mehr gelesen (es gilt $CONF) – bitte prüfen und löschen."
  fi
done
if [ ! -x "$SRC_DIR/BeamLog" ]; then echo "BeamLog-Binary nicht gefunden in $SRC_DIR – bitte aus dem entpackten ZIP-Ordner aufrufen."; exit 1; fi

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

# Fehlt eine Vorlage aus deploy/ (z. B. unvollständig entpackt oder versehentlich gelöscht), wird eine Standardversion
# angelegt statt abzubrechen.
ensure_template() {
  local f=$1 kind=$2 host=127.0.0.1
  [ -f "$f" ] && return 0
  mkdir -p "$(dirname "$f")"
  echo "   Vorlage $f fehlt – lege eine Standardversion an"
  case "$kind" in
    env)
      [ "$WANT_NGINX" = 1 ] || host=0.0.0.0
      printf '%s\n' "# BeamLog – Einstellungen (KEY=VALUE), automatisch angelegt" "HOST=$host" "PORT=8000" "BACKUP_MIN=15" \
        "#PUBLIC_URL=http://contest.local/" > "$f" ;;
    service)
      printf '%s\n' "[Unit]" "Description=BeamLog – Amateurfunk-Contest-Logger" "After=network.target" "" "[Service]" "Type=simple" \
        "User=beamlog" "Group=beamlog" "WorkingDirectory=/opt/beamlog" "Environment=PYTHONUNBUFFERED=1" \
        "ExecStart=/opt/beamlog/BeamLog --config /opt/beamlog/.env" "Restart=always" "RestartSec=3" \
        "AmbientCapabilities=CAP_NET_BIND_SERVICE" "CapabilityBoundingSet=CAP_NET_BIND_SERVICE" "NoNewPrivileges=true" \
        "PrivateTmp=true" "ProtectSystem=strict" "ProtectHome=true" "ReadWritePaths=/opt/beamlog" "" "[Install]" \
        "WantedBy=multi-user.target" > "$f" ;;
    nginx)
      printf '%s\n' "server {" "    listen 80 default_server;" "    listen [::]:80 default_server;" "    server_name _;" \
        "    client_max_body_size 50m;" "    location /ws {" "        proxy_pass http://127.0.0.1:8000;" "        proxy_http_version 1.1;" \
        "        proxy_set_header Upgrade \$http_upgrade;" "        proxy_set_header Connection \"upgrade\";" \
        "        proxy_set_header Host \$host;" "        proxy_read_timeout 3600s;" "    }" "    location / {" \
        "        proxy_pass http://127.0.0.1:8000;" "        proxy_set_header Host \$host;" \
        "        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;" "        proxy_set_header X-Forwarded-Proto \$scheme;" \
        "    }" "}" > "$f" ;;
    backup)
      printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' 'DATA_DIR="${1:-/opt/beamlog/data}"' 'mkdir -p "$DATA_DIR/backup-daily"' \
        'STAMP=$(date -u +%Y%m%d-%H%M%S); OUT="$DATA_DIR/backup-daily/beamlog-$STAMP.db"' \
        'python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d)" "$DATA_DIR/beamlog.db" "$OUT"' \
        'gzip -f "$OUT"' 'find "$DATA_DIR/backup-daily" -name "beamlog-*.db.gz" -mtime +30 -delete' > "$f" ;;
  esac
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
    sed -e "s#/var/lib/contestlogger/contestlogger\.db#$DATA_DIR/beamlog.db#g" -e "s#/var/lib/contestlogger#$DATA_DIR#g" \
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
  PKGS="sqlite3 rsync"; [ "$WANT_NGINX" = 1 ] && PKGS="nginx $PKGS"
  echo "== Pakete installieren ($PKGS)"
  apt-get update -qq
  # shellcheck disable=SC2086
  apt-get install -y -qq $PKGS
fi
# Bis 1.0.3 lagen Daten in /var/lib/beamlog und Einstellungen in /etc/beamlog – jetzt alles in $APP_DIR.
# Einstellungen und gemerkte Wahl werden verschoben, die Daten kopiert (das Original bleibt als Sicherung liegen).
LEGACY_DATA=/var/lib/beamlog
LEGACY_ETC=/etc/beamlog
MOVED_DATA=0
migrate_to_app_dir() {
  local f
  mkdir -p "$APP_DIR" "$DATA_DIR"
  for f in "$LEGACY_ETC/.env" "$LEGACY_ETC/beamlog.env"; do
    if [ -f "$f" ] && [ ! -f "$CONF" ]; then
      mv "$f" "$CONF"
      echo "== Umzug: Einstellungen $f -> $CONF"
    fi
  done
  if [ -f "$LEGACY_ETC/install.options" ]; then
    [ -f "$OPTS" ] || mv "$LEGACY_ETC/install.options" "$OPTS"
    rm -f "$LEGACY_ETC/install.options"
  fi
  rmdir "$LEGACY_ETC" 2>/dev/null || true
  if [ -f "$LEGACY_DATA/beamlog.db" ] && [ ! -f "$DATA_DIR/beamlog.db" ]; then
    systemctl stop beamlog >/dev/null 2>&1 || true   # konsistente Kopie: Dienst kurz anhalten (startet unten neu)
    cp -a "$LEGACY_DATA/." "$DATA_DIR/"
    MOVED_DATA=1
    echo "== Umzug: Daten $LEGACY_DATA -> $DATA_DIR (das Original bleibt als Sicherung liegen)"
  fi
  # Pfade in der Einstellungsdatei nachziehen (z. B. DB=/var/lib/beamlog/beamlog.db)
  if [ -f "$CONF" ] && grep -q "$LEGACY_DATA/" "$CONF"; then
    sed -i "s#$LEGACY_DATA/#$DATA_DIR/#g" "$CONF"
    echo "   Pfade in $CONF auf $DATA_DIR umgestellt"
  fi
}

if [ "$HERE" = 0 ]; then
  migrate_from_contestlogger
  id beamlog >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin beamlog
  migrate_to_app_dir
fi

if [ "$HERE" = 1 ]; then
  echo "== BeamLog bleibt in $APP_DIR (kein Kopieren$( [ "$AUTO_HERE" = 1 ] && echo ", weil ohne Dienst")), läuft als Nutzer $RUN_USER; Daten in $DATA_DIR"
  mkdir -p "$DATA_DIR/lang"
  chown "$RUN_USER:$RUN_GROUP" "$DATA_DIR" "$DATA_DIR/lang"
  chmod +x "$APP_DIR"/BeamLog* 2>/dev/null || true
else
  echo
  echo "######################################################################################"
  echo "#  ACHTUNG: BeamLog wird nach $APP_DIR KOPIERT – wegen des systemd-Dienstes."
  echo "#  Der Dienst läuft dort als eigener Nutzer „beamlog“, Daten in $DATA_DIR,"
  echo "#  Einstellungen in $CONF. Dieser Ordner ($SRC_DIR) wird danach nicht mehr benutzt."
  echo "#  Im Ordner bleiben stattdessen:  --here (mit Dienst)  oder  --no-service / --deps-only"
  echo "######################################################################################"
  echo
  echo "== Programm nach $APP_DIR kopieren (Daten bleiben in $DATA_DIR)"
  mkdir -p "$APP_DIR" "$DATA_DIR/lang"
  rsync -a --delete --exclude /data --exclude /.env --exclude /beamlog.env --exclude /.install.options "$SRC_DIR/" "$APP_DIR/"
  chmod +x "$APP_DIR"/BeamLog* "$APP_DIR"/*.sh 2>/dev/null || true
  chown -R beamlog:beamlog "$APP_DIR" "$DATA_DIR"
fi

echo "== Konfiguration $CONF"
mkdir -p "$(dirname "$CONF")"
if [ ! -f "$CONF" ]; then
  TEMPLATE="$APP_DIR/deploy/server.env"; [ "$HERE" = 1 ] && TEMPLATE="$APP_DIR/.env.example"
  ensure_template "$TEMPLATE" env
  cp "$TEMPLATE" "$CONF"
  echo "   neu angelegt (Vorlage ${TEMPLATE#"$APP_DIR"/})"
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
chmod 640 "$CONF"; chown "$RUN_USER:$RUN_GROUP" "$CONF"
printf '# Von install.sh gemerkte Wahl (1 = einrichten, 0 = weglassen) – ändern mit --no-… / --with-… / --here / --system\nHERE=%s\nWANT_NGINX=%s\nWANT_SERVICE=%s\nWANT_BACKUP=%s\n' \
  "$HERE" "$WANT_NGINX" "$WANT_SERVICE" "$WANT_BACKUP" > "$OPTS"
chown "$RUN_USER:$RUN_GROUP" "$OPTS"
echo "   Ort: $APP_DIR$( [ "$HERE" = 1 ] && echo " (--here)")   Teile: nginx=$( [ "$WANT_NGINX" = 1 ] && echo ja || echo nein ), Dienst=$( [ "$WANT_SERVICE" = 1 ] && echo ja || echo nein ), Backup-Cron=$( [ "$WANT_BACKUP" = 1 ] && echo ja || echo nein )  (gemerkt in $OPTS)"

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

if [ "$WANT_NGINX" = 0 ]; then
  echo "== nginx: übersprungen (--no-nginx)"
  if [ -e /etc/nginx/sites-enabled/beamlog ]; then
    rm -f /etc/nginx/sites-enabled/beamlog
    echo "   frühere BeamLog-Site entfernt (nginx selbst und andere Sites bleiben unberührt)"
    if systemctl is-active --quiet nginx 2>/dev/null && nginx -t >/dev/null 2>&1; then systemctl reload nginx || true; fi
  fi
  if [ "$DIRECT" = 1 ] && systemctl is-active --quiet nginx 2>/dev/null; then
    echo "   Achtung: PORT=80, aber nginx läuft und belegt Port 80 vermutlich selbst – mit --no-nginx bleibt nginx unangetastet."
    echo "   nginx abschalten:  sudo systemctl disable --now nginx   (oder mit --with-nginx, dann erledigt das das Skript)"
  fi
elif [ "$DIRECT" = 1 ]; then
  echo "== nginx: nicht nötig, BeamLog läuft direkt auf Port 80"
  rm -f /etc/nginx/sites-enabled/beamlog
  if systemctl is-active --quiet nginx 2>/dev/null; then
    echo "   nginx belegt Port 80 und wird angehalten (wieder einschalten: sudo systemctl enable --now nginx)"
    systemctl disable --now nginx >/dev/null 2>&1 || true
  fi
elif [ "$MODE" = install ] || [ "$MIGRATED" = 1 ] || [ ! -e /etc/nginx/sites-enabled/beamlog ]; then
  echo "== nginx (Port 80 -> Dienst auf 127.0.0.1:$CONF_PORT)"
  if [ "$MODE" = install ] || [ ! -f /etc/nginx/sites-available/beamlog ]; then
    ensure_template "$APP_DIR/deploy/nginx-beamlog.conf" nginx
    cp "$APP_DIR/deploy/nginx-beamlog.conf" /etc/nginx/sites-available/beamlog
  fi
  sed -i -E "s#proxy_pass http://127\.0\.0\.1:[0-9]+#proxy_pass http://127.0.0.1:$CONF_PORT#g" /etc/nginx/sites-available/beamlog
  if [ "$HERE" = 1 ]; then sed -i '/location \/static\/ {/,/}/d' /etc/nginx/sites-available/beamlog; fi   # nginx darf in /home meist nicht lesen
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

if [ "$WANT_SERVICE" = 1 ]; then
  echo "== systemd-Dienst"
  ensure_template "$APP_DIR/deploy/beamlog.service" service
  if [ "$HERE" = 1 ]; then
    sed -e "s#/opt/beamlog#$APP_DIR#g" -e "s#^User=.*#User=$RUN_USER#" -e "s#^Group=.*#Group=$RUN_GROUP#" \
        -e "s#^ReadWritePaths=.*#ReadWritePaths=$APP_DIR#" -e "s#^ProtectHome=.*#ProtectHome=false#" \
        "$APP_DIR/deploy/beamlog.service" > /etc/systemd/system/beamlog.service
  else
    cp "$APP_DIR/deploy/beamlog.service" /etc/systemd/system/beamlog.service
  fi
  systemctl daemon-reload
  systemctl enable beamlog >/dev/null
  systemctl restart beamlog || true
  sleep 2
  systemctl is-active --quiet beamlog || SERVICE_FAILED=1
else
  echo "== systemd-Dienst: übersprungen (--no-service)"
  if [ -e /etc/systemd/system/beamlog.service ]; then
    systemctl disable --now beamlog >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/beamlog.service
    systemctl daemon-reload
    echo "   früheren Dienst „beamlog“ angehalten und entfernt"
  fi
fi

# Tägliches Backup – bei jedem Lauf einrichten (fehlt sonst, falls ein früherer Lauf abgebrochen ist)
if [ "$WANT_BACKUP" = 1 ]; then
  echo "== Tägliches Backup (03:15 Uhr) nach $DATA_DIR/backup-daily (30 Tage)"
  ensure_template "$APP_DIR/deploy/backup.sh" backup
  cp "$APP_DIR/deploy/backup.sh" /usr/local/bin/beamlog-backup
  chmod +x /usr/local/bin/beamlog-backup
  echo "15 3 * * * root /usr/local/bin/beamlog-backup $DATA_DIR" > /etc/cron.d/beamlog-backup
else
  echo "== Tägliches Backup: übersprungen (--no-backup)"
  rm -f /etc/cron.d/beamlog-backup /usr/local/bin/beamlog-backup
fi

sleep 1
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
START_CMD="sudo -u beamlog $APP_DIR/BeamLog --config $CONF"
[ "$HERE" = 1 ] && START_CMD="cd $APP_DIR && ./BeamLog"
echo
if [ "$HERE" = 0 ]; then
  echo ">>> Installiert nach $APP_DIR (kopiert wegen des systemd-Dienstes) – Daten: $DATA_DIR, Einstellungen: $CONF"
  echo ">>> Der Ordner $SRC_DIR wird nicht benutzt. Im Ordner bleiben: --here oder --no-service"
else
  echo ">>> BeamLog läuft aus diesem Ordner: $APP_DIR (Daten: $DATA_DIR, Einstellungen: $CONF)"
fi
if [ "$DIRECT" = 1 ] || [ "$WANT_NGINX" = 1 ]; then URL="http://${IP:-<server-ip>}/"
elif [ "$CONF_HOST" = 127.0.0.1 ] || [ "$CONF_HOST" = localhost ]; then URL="http://127.0.0.1:$CONF_PORT/ (nur am Server – für den eigenen Reverse-Proxy)"
else URL="http://${IP:-<server-ip>}:$CONF_PORT/"; fi
if [ "$WANT_SERVICE" = 1 ]; then
  echo "Fertig. BeamLog: $URL   (Status: systemctl status beamlog)"
else
  echo "Fertig. BeamLog ist installiert, aber ohne Dienst (--no-service) – selbst starten (als Nutzer $RUN_USER):"
  echo "   $START_CMD"
  echo "   Adresse danach: $URL"
fi
echo "Datenbank: $DATA_DIR/beamlog.db$( [ "$WANT_SERVICE" = 1 ] && echo "   Logs: journalctl -u beamlog -f")"
echo "Einstellungen: $CONF   (danach: sudo systemctl restart beamlog bzw. eigenen Prozess neu starten)"
if [ "$HERE" = 1 ]; then echo "Update später: neue Version in $APP_DIR entpacken (data/ und .env bleiben) und  sudo bash deploy/install.sh --update"
else echo "Update später: neues ZIP entpacken und dort  sudo bash deploy/install.sh --update"; fi
if [ "$MOVED_DATA" = 1 ]; then echo "Umgezogen: Die bisherigen Daten liegen zusätzlich noch in $LEGACY_DATA – nach Prüfung löschbar (sudo rm -r $LEGACY_DATA)."; fi
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
