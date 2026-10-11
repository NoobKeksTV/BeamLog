#!/usr/bin/env bash
# BeamLog starten (Linux/macOS/Raspberry Pi). Legt beim ersten Mal die virtuelle Umgebung .venv an und
# installiert die Pakete neu, sobald sich requirements.txt geändert hat (z. B. nach git pull).
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Erster Start: richte .venv ein …"
  python3 -m venv .venv || { echo "python3-venv fehlt – Debian/Ubuntu: sudo apt install python3-venv  (oder: sudo bash deploy/install.sh --deps-only)"; exit 1; }
fi
if ! cmp -s requirements.txt .venv/.requirements.installed; then
  echo "Installiere Python-Pakete (requirements.txt) …"
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt
  cp requirements.txt .venv/.requirements.installed
fi
exec .venv/bin/python run.py "$@"
