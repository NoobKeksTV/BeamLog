#!/usr/bin/env bash
# BeamLog starten (Linux/macOS/Raspberry Pi). Legt beim ersten Mal eine virtuelle Umgebung an.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt
fi
exec .venv/bin/python run.py "$@"
