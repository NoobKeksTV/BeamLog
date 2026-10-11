#!/usr/bin/env bash
# Tägliche konsistente Sicherung der SQLite-Datenbank (behält 30 Tage).
set -euo pipefail
DATA_DIR=/var/lib/beamlog
mkdir -p "$DATA_DIR/backup"
STAMP=$(date -u +%Y%m%d-%H%M%S)
/opt/beamlog/.venv/bin/python - <<PY
import sqlite3
src = sqlite3.connect("$DATA_DIR/beamlog.db")
dst = sqlite3.connect("$DATA_DIR/backup/beamlog-$STAMP.db")
src.backup(dst); dst.close(); src.close()
PY
gzip -f "$DATA_DIR/backup/beamlog-$STAMP.db"
find "$DATA_DIR/backup" -name "beamlog-*.db.gz" -mtime +30 -delete
