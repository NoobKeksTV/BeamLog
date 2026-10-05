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


CONFIG_KEYS = ("HOST", "PORT", "DB", "BACKUP_MIN", "PUBLIC_URL", "OPEN_BROWSER", "KST_HOST", "KST_PORT", "GITHUB_TOKEN")


def load_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE-Datei (wie .env) lesen; Kommentare mit #, Anführungszeichen erlaubt."""
    out: dict[str, str] = {}
    if not path or not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().upper().removeprefix("CONTESTLOGGER_")
        v = v.strip().strip('"').strip("'")
        if k in CONFIG_KEYS:
            out[k] = v
    return out


def find_config(explicit: str | None) -> Path | None:
    """Reihenfolge: --config, CONTESTLOGGER_CONFIG, contestlogger.env neben dem Programm, /etc/contestlogger/contestlogger.env."""
    cands = [explicit, os.environ.get("CONTESTLOGGER_CONFIG"), str(portable_base() / "contestlogger.env"), "/etc/contestlogger/contestlogger.env"]
    for c in cands:
        if c and Path(c).exists():
            return Path(c)
    return None


def main() -> None:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config")
    pre_a, _ = pre.parse_known_args()
    cfg_path = find_config(pre_a.config)
    cfg = load_env_file(cfg_path) if cfg_path else {}
    # Umgebungsvariablen (CONTESTLOGGER_HOST …) überstimmen die Datei, Kommandozeile überstimmt beides
    for k in CONFIG_KEYS:
        if os.environ.get(f"CONTESTLOGGER_{k}"):
            cfg[k] = os.environ[f"CONTESTLOGGER_{k}"]
    for k in ("KST_HOST", "KST_PORT", "GITHUB_TOKEN"):  # werden von den Modulen direkt aus der Umgebung gelesen
        if cfg.get(k):
            os.environ[f"CONTESTLOGGER_{k}"] = cfg[k]
    p = argparse.ArgumentParser(description=f"{__app_name__} {__version__}  –  Einstellungen auch über contestlogger.env (siehe contestlogger.env.example)")
    p.add_argument("--config", help="Pfad zur Konfigurationsdatei (KEY=VALUE)")
    p.add_argument("--host", default=cfg.get("HOST") or "0.0.0.0")
    p.add_argument("--port", type=int, default=int(cfg.get("PORT") or 8000))
    p.add_argument("--db", default=cfg.get("DB") or str(portable_base() / "data" / "contestlogger.db"))
    p.add_argument("--backup-min", type=float, default=float(cfg.get("BACKUP_MIN") or 15), help="automatische Sicherung alle N Minuten (0 = aus)")
    p.add_argument("--public-url", default=cfg.get("PUBLIC_URL") or "", help="Adresse für den QR-Code, z. B. http://contest.local/ (hinter nginx)")
    a = p.parse_args()
    if cfg.get("OPEN_BROWSER", "").lower() in ("0", "false", "no", "nein"):
        os.environ["CONTESTLOGGER_NO_BROWSER"] = "1"
    if cfg_path:
        print(f"  Konfiguration: {cfg_path}")
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
