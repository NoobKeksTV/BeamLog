#!/usr/bin/env bash
# Tägliche konsistente Sicherung der SQLite-Datenbank (portable Version, nutzt sqlite3; behält 30 Tage).
# Zusätzlich zu den automatischen Sicherungen des Servers in /var/lib/contestlogger/backup/.
set -euo pipefail
DATA_DIR=/var/lib/contestlogger
mkdir -p "$DATA_DIR/backup-daily"
STAMP=$(date -u +%Y%m%d-%H%M%S)
sqlite3 "$DATA_DIR/contestlogger.db" ".backup '$DATA_DIR/backup-daily/contestlogger-$STAMP.db'"
gzip -f "$DATA_DIR/backup-daily/contestlogger-$STAMP.db"
find "$DATA_DIR/backup-daily" -name "contestlogger-*.db.gz" -mtime +30 -delete
