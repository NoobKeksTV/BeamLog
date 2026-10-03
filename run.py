#!/usr/bin/env python3
"""Startet den ContestLogger-Server.

    python run.py                 # Port 8000, erreichbar im ganzen LAN
    python run.py --port 8080
    python run.py --db /pfad/zur/datei.db
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

import uvicorn

from contestlogger import __app_name__, __copyright__, __version__
from contestlogger.app import create_app


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def portable_base() -> Path:
    """Im portablen Build (PyInstaller) liegen die Daten neben der ausführbaren Datei."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def main() -> None:
    p = argparse.ArgumentParser(description=f"{__app_name__} {__version__}")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--db", default=str(portable_base() / "data" / "contestlogger.db"))
    p.add_argument("--backup-min", type=float, default=15, help="automatische Sicherung alle N Minuten (0 = aus)")
    p.add_argument("--public-url", default="", help="Adresse für den QR-Code, z. B. http://contest.local/ (hinter nginx)")
    a = p.parse_args()
    url = a.public_url or (f"http://{lan_ip()}/" if a.host in ("127.0.0.1", "localhost") else f"http://{lan_ip()}:{a.port}/")
    app = create_app(a.db, backup_interval_min=a.backup_min, public_url=url)
    print(f"\n  {__app_name__} {__version__}  {__copyright__}")
    print(f"  Lokal:    http://localhost:{a.port}")
    print(f"  Im LAN:   {url}")
    print(f"  Daten:    {a.db}  (Backups alle {a.backup_min:g} min in backup/)\n")
    if getattr(sys, "frozen", False) and os.name == "nt" and os.environ.get("CONTESTLOGGER_NO_BROWSER") != "1":
        import threading
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{a.port}")).start()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
