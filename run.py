#!/usr/bin/env python3
"""Startet den ContestLogger-Server.

    python run.py                 # Port 8000, erreichbar im ganzen LAN
    python run.py --port 8080
    python run.py --db /pfad/zur/datei.db
"""
from __future__ import annotations

import argparse
import socket

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


def main() -> None:
    p = argparse.ArgumentParser(description=f"{__app_name__} {__version__}")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--db", default="data/contestlogger.db")
    a = p.parse_args()
    app = create_app(a.db)
    print(f"\n  {__app_name__} {__version__}  {__copyright__}")
    print(f"  Lokal:    http://localhost:{a.port}")
    print(f"  Im LAN:   http://{lan_ip()}:{a.port}")
    print(f"  Daten:    {a.db}\n")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
