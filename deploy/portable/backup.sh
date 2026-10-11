#!/usr/bin/env bash
# Tägliche konsistente Sicherung der SQLite-Datenbank (portable Version, nutzt sqlite3; behält 30 Tage).
# Zusätzlich zu den automatischen Sicherungen des Servers in /var/lib/beamlog/backup/.
set -euo pipefail
DATA_DIR="${1:-/var/lib/beamlog}"   # Datenordner (install.sh --here übergibt <ordner>/data)
mkdir -p "$DATA_DIR/backup-daily"
STAMP=$(date -u +%Y%m%d-%H%M%S)
sqlite3 "$DATA_DIR/beamlog.db" ".backup '$DATA_DIR/backup-daily/beamlog-$STAMP.db'"
gzip -f "$DATA_DIR/backup-daily/beamlog-$STAMP.db"
find "$DATA_DIR/backup-daily" -name "beamlog-*.db.gz" -mtime +30 -delete
