#!/usr/bin/env python3
"""Startet den BeamLog-Server.

Empfohlen: ./start.sh (Linux/macOS/Raspberry Pi) bzw. start.bat (Windows) – legt beim ersten Mal die virtuelle
Umgebung .venv an und hält die Pakete aktuell. Danach geht auch direkt:

    python run.py                 # Port 8000, erreichbar im ganzen LAN (nutzt automatisch .venv, falls vorhanden)
    python run.py --port 8080
    python run.py --db /pfad/zur/datei.db
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import socket
import sys
from pathlib import Path

# Pakete aus requirements.txt (Importname). Fehlen sie im aufrufenden Python (z. B. „python run.py“ mit dem System-Python),
# wird automatisch die virtuelle Umgebung .venv neben run.py genommen, die start.sh/start.bat bzw. install.sh anlegen.
CONFIG_NAME = ".env"  # Einstellungen neben dem Programm bzw. /etc/beamlog/.env
LEGACY_CONFIG_NAMES = ("beamlog.env", "contestlogger.env")  # werden beim Start bzw. von install.sh umbenannt

REQUIRED = ("fastapi", "uvicorn", "multipart", "qrcode", "pypdf", "construct", "tabulate", "httpx")


def ensure_packages() -> None:
    if getattr(sys, "frozen", False):
        return
    missing = [m for m in REQUIRED if importlib.util.find_spec(m) is None]
    if not missing:
        return
    venv = Path(__file__).resolve().parent / ".venv"
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if py.exists() and Path(sys.prefix).resolve() != venv.resolve() and not os.environ.get("BEAMLOG_VENV_REEXEC"):
        os.environ["BEAMLOG_VENV_REEXEC"] = "1"
        args = [str(py), str(Path(__file__).resolve()), *sys.argv[1:]]
        if os.name == "nt":  # execv ersetzt unter Windows den Prozess nicht sauber – als Kindprozess starten
            import subprocess
            sys.exit(subprocess.call(args))
        os.execv(str(py), args)
    starter = "start.bat" if os.name == "nt" else "./start.sh"
    where = "in .venv " if Path(sys.prefix).resolve() == venv.resolve() else ""
    sys.exit(f"BeamLog: Python-Pakete fehlen {where}({', '.join(missing)}).\n"
             f"  Am einfachsten mit {starter} starten – richtet .venv ein und installiert/aktualisiert alles.\n"
             f"  Oder von Hand: {sys.executable} -m pip install -r requirements.txt")


ensure_packages()

import uvicorn  # noqa: E402

from contestlogger import __app_name__, __copyright__, __version__, env  # noqa: E402
from contestlogger.app import create_app  # noqa: E402


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
        if (old / "contestlogger.env").exists() and not any((base / n).exists() for n in (CONFIG_NAME, *LEGACY_CONFIG_NAMES)):
            shutil.copy2(old / "contestlogger.env", base / CONFIG_NAME)
        print(f"  Daten aus der bisherigen Installation übernommen: {old / 'data'}  (Original bleibt unverändert)")
        return


def adopt_legacy_names(base: Path) -> None:
    """Alte Dateinamen umstellen: Einstellungen beamlog.env (bis 1.0.3) bzw. contestlogger.env (bis 0.9) -> .env,
    data/contestlogger.db -> data/beamlog.db (samt -wal/-shm). Nur wenn es die neue Datei noch nicht gibt; schlägt das
    Umbenennen fehl, bleibt alles wie es war."""
    for name in LEGACY_CONFIG_NAMES:
        if (base / name).is_file() and not (base / CONFIG_NAME).exists():
            os.replace(base / name, base / CONFIG_NAME)
            print(f"  Einstellungen umbenannt: {name} -> {CONFIG_NAME}")
        elif (base / name).is_file():
            print(f"  Hinweis: {name} wird nicht mehr gelesen, es gilt {CONFIG_NAME} – alte Datei bitte löschen.")
    old, new = base / "data" / "contestlogger.db", base / "data" / "beamlog.db"
    if old.exists() and not new.exists():
        for suffix in ("-wal", "-shm", ""):
            if Path(f"{old}{suffix}").exists():
                os.replace(f"{old}{suffix}", f"{new}{suffix}")
        print(f"  Datenbank umbenannt: {old.name} -> {new.name}")


LEGACY_DATA_DIRS = ("/var/lib/beamlog", "/var/lib/contestlogger")  # Server-Datenordner bis 1.0.3 bzw. 0.9


def prepare_data(db: str) -> str:
    """Datenordner (samt backup/ und lang/) anlegen, falls er fehlt, und prüfen, ob BeamLog dort schreiben darf –
    sonst eine verständliche Meldung mit der Lösung statt eines Absturzes. Zeigt die Einstellung noch auf den alten
    Server-Ordner (/var/lib/beamlog), die Daten liegen aber schon im Programmordner, wird der Programmordner genommen."""
    p = Path(db)
    local = portable_base() / "data" / "beamlog.db"
    if not p.exists() and str(p.parent) in LEGACY_DATA_DIRS and local.exists():
        print(f"  Hinweis: {p} gibt es nicht mehr, die Daten liegen jetzt in {local} – DB=… in der .env bitte anpassen.")
        p = local
    try:
        for d in (p.parent, p.parent / "backup", p.parent / "lang"):
            d.mkdir(parents=True, exist_ok=True)
        probe = p.parent / ".schreibtest"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        for f in (p, Path(f"{p}-wal"), Path(f"{p}-shm")):
            if f.exists() and not os.access(f, os.W_OK):
                raise PermissionError(13, "keine Schreibrechte", str(f))
    except OSError as e:
        import getpass
        user = getpass.getuser()
        where = e.filename or p.parent
        fix = (f"sudo chown -R {user}: {p.parent}" if os.name != "nt" else "Ordnerrechte prüfen oder einen anderen Ordner wählen (--db)")
        sys.exit(f"BeamLog kann nicht in {where} schreiben ({e.strerror or e}).\n"
                 f"  Läuft als Nutzer „{user}“. Lösung: {fix}\n"
                 f"  Als Server-Dienst: sudo bash deploy/install.sh --update (setzt die Rechte neu).")
    return str(p)


def check_port(host: str, port: int) -> None:
    """Port vorab prüfen und bei Problemen verständlich erklären, statt mit einer knappen uvicorn-Meldung zu enden."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if os.name != "nt":  # unter Windows würde SO_REUSEADDR einen belegten Port „teilen“
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host if host not in ("", "localhost") else "127.0.0.1", port))
    except PermissionError if os.name != "nt" and port < 1024 else ():  # Windows meldet belegte Ports ebenfalls als „Zugriff verweigert“
        sys.exit(f"  Port {port} darf von diesem Benutzer nicht geöffnet werden (Ports unter 1024 brauchen Sonderrechte).\n"
                 f"  Server-Dienst: sudo bash deploy/install.sh --update (die Unit erlaubt Port 80), sonst einen Port ab 1024 wählen.")
    except OSError as e:
        sys.exit(f"  Port {port} ist belegt oder nicht verfügbar ({e.strerror}).\n"
                 f"  Welches Programm ihn belegt:  sudo ss -ltnp 'sport = :{port}'  (z. B. nginx oder ein zweites BeamLog)")


CONFIG_KEYS = ("HOST", "PORT", "DB", "BACKUP_MIN", "PUBLIC_URL", "OPEN_BROWSER", "KST_HOST", "KST_PORT", "GITHUB_TOKEN", "MAINTAINER", "DEV", "DEMO", "DEMO_RESET")


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
    """Reihenfolge: --config, BEAMLOG_CONFIG, .env neben dem Programm, /etc/beamlog/.env – dazu die alten Namen
    beamlog.env (bis 1.0.3) und contestlogger.env (bis 0.9). Zeigt --config auf eine alte, inzwischen umbenannte Datei
    (z. B. eine eigene Dienst-Unit mit …/beamlog.env), wird die .env daneben genommen."""
    base = portable_base()
    given = [c for c in (explicit, env("CONFIG")) if c]
    for c in given:
        if Path(c).exists():
            return Path(c)
        if Path(c).name in LEGACY_CONFIG_NAMES and (Path(c).parent / CONFIG_NAME).exists():
            return Path(c).parent / CONFIG_NAME
    cands = [base / n for n in (CONFIG_NAME, *LEGACY_CONFIG_NAMES)]
    cands += [Path("/etc/beamlog") / CONFIG_NAME, Path("/etc/beamlog/beamlog.env"), Path("/etc/contestlogger/contestlogger.env")]
    for c in cands:
        if c.is_file():
            return c
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
    for k in ("KST_HOST", "KST_PORT", "GITHUB_TOKEN", "MAINTAINER", "DEV", "DEMO", "DEMO_RESET"):  # werden von den Modulen direkt aus der Umgebung gelesen
        if cfg.get(k):
            os.environ[f"BEAMLOG_{k}"] = cfg[k]
    p = argparse.ArgumentParser(description=f"{__app_name__} {__version__}  –  Einstellungen auch über .env (siehe .env.example)")
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
    if pre_a.config and not Path(pre_a.config).exists() and cfg_path is None:
        print(f"  Hinweis: Konfiguration {pre_a.config} nicht gefunden – es gelten die Standardwerte.")
    a.db = prepare_data(a.db)
    app = create_app(a.db, backup_interval_min=a.backup_min, public_url=url)
    print(f"\n  {__app_name__} {__version__}  {__copyright__}")
    print(f"  Lokal:    http://localhost:{a.port}")
    print(f"  Im LAN:   {url}")
    demo_on = cfg.get("DEMO", "").strip().lower() in ("1", "true", "yes", "ja", "on")
    print(f"  Daten:    {a.db}  " + ("(DEMO-MODUS: keine Backups, täglich zurückgesetzt)\n" if demo_on else f"(Backups alle {a.backup_min:g} min in backup/)\n"))
    if getattr(sys, "frozen", False) and os.name == "nt" and env("NO_BROWSER") != "1":
        import threading
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{a.port}")).start()
    check_port(a.host, a.port)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
