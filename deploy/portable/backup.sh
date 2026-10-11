#!/usr/bin/env bash
# Tägliche konsistente Sicherung der SQLite-Datenbank (portable Version, nutzt sqlite3; behält 30 Tage).
# Zusätzlich zu den automatischen Sicherungen des Servers in data/backup/.
set -euo pipefail
DATA_DIR="${1:-/opt/beamlog/data}"   # Datenordner (install.sh übergibt ihn)
mkdir -p "$DATA_DIR/backup-daily"
STAMP=$(date -u +%Y%m%d-%H%M%S)
sqlite3 "$DATA_DIR/beamlog.db" ".backup '$DATA_DIR/backup-daily/beamlog-$STAMP.db'"
gzip -f "$DATA_DIR/backup-daily/beamlog-$STAMP.db"
find "$DATA_DIR/backup-daily" -name "beamlog-*.db.gz" -mtime +30 -delete
