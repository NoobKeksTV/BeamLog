#!/usr/bin/env bash
# Portable Linux/macOS-Version bauen (Ergebnis in dist/)
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
.venv/bin/pip install -q pyinstaller
exec .venv/bin/python build_tools/build.py "$@"
