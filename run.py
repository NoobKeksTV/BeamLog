#!/usr/bin/env python3
"""Startet den BeamLog-Server.

    python run.py                 # Port 8000, erreichbar im ganzen LAN
    python run.py --port 8080
    python run.py --db /pfad/zur/datei.db
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import sys
from pathlib import Path

import uvicorn

from contestlogger import __app_name__, __copyright__, __version__, env
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


def migrate_from_contestlogger(base: Path) -> None:
    """Umstieg von 0.9.x (hieß „ContestLogger“): liegt der neue BeamLog-Ordner neben dem alten Ordner ContestLogger
    (oder darin) und hat noch keine eigenen Daten, werden data/ und die Einstellungsdatei einmalig hinüberkopiert."""
    if any((base / "data" / n).exists() for n in ("beamlog.db", "contestlogger.db")):
        return
    for old in (base.parent / "ContestLogger", base.parent):
        if old == base or not (old / "data" / "contestlogger.db").exists():
            continue
        if not any((old / n).is_file() for n in ("ContestLogger.exe", "ContestLogger")):
            continue
        shutil.copytree(old / "data", base / "data", dirs_exist_ok=True)
        if (old / "contestlogger.env").exists() and not (base / "beamlog.env").exists():
            shutil.copy2(old / "contestlogger.env", base / "beamlog.env")
        print(f"  Daten aus der bisherigen Installation übernommen: {old / 'data'}  (Original bleibt unverändert)")
        return


def adopt_legacy_names(base: Path) -> None:
    """Dateinamen bis 0.9 auf BeamLog umstellen: contestlogger.env -> beamlog.env, data/contestlogger.db -> data/beamlog.db
    (samt -wal/-shm). Nur wenn es die neue Datei noch nicht gibt; schlägt das Umbenennen fehl, bleibt alles wie es war."""
    if (base / "contestlogger.env").exists() and not (base / "beamlog.env").exists():
        os.replace(base / "contestlogger.env", base / "beamlog.env")
    old, new = base / "data" / "contestlogger.db", base / "data" / "beamlog.db"
    if old.exists() and not new.exists():
        for suffix in ("-wal", "-shm", ""):
            if Path(f"{old}{suffix}").exists():
                os.replace(f"{old}{suffix}", f"{new}{suffix}")
        print(f"  Datenbank umbenannt: {old.name} -> {new.name}")


def check_port(host: str, port: int) -> None:
    """Port vorab prüfen und bei Problemen verständlich erklären, statt mit einer knappen uvicorn-Meldung zu enden."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host if host not in ("", "localhost") else "127.0.0.1", port))
    except PermissionError:
        sys.exit(f"  Port {port} darf von diesem Benutzer nicht geöffnet werden (Ports unter 1024 brauchen Sonderrechte).\n"
                 f"  Server-Dienst: sudo bash deploy/install.sh --update (die Unit erlaubt Port 80), sonst einen Port ab 1024 wählen.")
    except OSError as e:
        sys.exit(f"  Port {port} ist belegt oder nicht verfügbar ({e.strerror}).\n"
                 f"  Welches Programm ihn belegt:  sudo ss -ltnp 'sport = :{port}'  (z. B. nginx oder ein zweites BeamLog)")


CONFIG_KEYS = ("HOST", "PORT", "DB", "BACKUP_MIN", "PUBLIC_URL", "OPEN_BROWSER", "KST_HOST", "KST_PORT", "GITHUB_TOKEN", "MAINTAINER", "DEV")


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
        k = k.strip().upper().removeprefix("BEAMLOG_").removeprefix("CONTESTLOGGER_")
        v = re.sub(r"\s+#.*$", "", v).strip().strip('"').strip("'")  # Kommentar hinter dem Wert („PORT=80   # direkt“)
        if k in CONFIG_KEYS:
            out[k] = v
    return out


def find_config(explicit: str | None) -> Path | None:
    """Reihenfolge: --config, BEAMLOG_CONFIG, beamlog.env neben dem Programm, /etc/beamlog/beamlog.env
    (dazu die alten Namen contestlogger.env und /etc/contestlogger/contestlogger.env aus 0.9)."""
    base = portable_base()
    cands = [explicit, env("CONFIG"), str(base / "beamlog.env"), str(base / "contestlogger.env"),
             "/etc/beamlog/beamlog.env", "/etc/contestlogger/contestlogger.env"]
    for c in cands:
        if c and Path(c).exists():
            return Path(c)
    return None


def main() -> None:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config")
    pre_a, _ = pre.parse_known_args()
    try:
        if getattr(sys, "frozen", False):
            migrate_from_contestlogger(portable_base())
        adopt_legacy_names(portable_base())
    except OSError as e:
        print(f"  Übernahme der alten Daten fehlgeschlagen: {e}")
    cfg_path = find_config(pre_a.config)
    cfg = load_env_file(cfg_path) if cfg_path else {}
    # Umgebungsvariablen (BEAMLOG_HOST …, alt: CONTESTLOGGER_HOST …) überstimmen die Datei, Kommandozeile überstimmt beides
    for k in CONFIG_KEYS:
        if env(k):
            cfg[k] = env(k)
    for k in ("KST_HOST", "KST_PORT", "GITHUB_TOKEN", "MAINTAINER", "DEV"):  # werden von den Modulen direkt aus der Umgebung gelesen
        if cfg.get(k):
            os.environ[f"BEAMLOG_{k}"] = cfg[k]
    p = argparse.ArgumentParser(description=f"{__app_name__} {__version__}  –  Einstellungen auch über beamlog.env (siehe beamlog.env.example)")
    p.add_argument("--config", help="Pfad zur Konfigurationsdatei (KEY=VALUE)")
    p.add_argument("--host", default=cfg.get("HOST") or "0.0.0.0")
    p.add_argument("--port", type=int, default=int(cfg.get("PORT") or 8000))
    p.add_argument("--db", default=cfg.get("DB") or str(portable_base() / "data" / "beamlog.db"))
    p.add_argument("--backup-min", type=float, default=float(cfg.get("BACKUP_MIN") or 15), help="automatische Sicherung alle N Minuten (0 = aus)")
    p.add_argument("--public-url", default=cfg.get("PUBLIC_URL") or "", help="Adresse für den QR-Code, z. B. http://contest.local/ (hinter nginx)")
    a = p.parse_args()
    if cfg.get("OPEN_BROWSER", "").lower() in ("0", "false", "no", "nein"):
        os.environ["BEAMLOG_NO_BROWSER"] = "1"
    if cfg_path:
        print(f"  Konfiguration: {cfg_path}")
    url = a.public_url or (f"http://{lan_ip()}/" if a.host in ("127.0.0.1", "localhost") else f"http://{lan_ip()}:{a.port}/")
    app = create_app(a.db, backup_interval_min=a.backup_min, public_url=url)
    print(f"\n  {__app_name__} {__version__}  {__copyright__}")
    print(f"  Lokal:    http://localhost:{a.port}")
    print(f"  Im LAN:   {url}")
    print(f"  Daten:    {a.db}  (Backups alle {a.backup_min:g} min in backup/)\n")
    if getattr(sys, "frozen", False) and os.name == "nt" and env("NO_BROWSER") != "1":
        import threading
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{a.port}")).start()
    check_port(a.host, a.port)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
