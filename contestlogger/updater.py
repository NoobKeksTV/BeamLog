"""Update-Prüfung und Selbst-Aktualisierung der portablen Version über die GitHub-Releases.

Ablauf: Releases-API abfragen (mit Token auch bei privatem Repo) -> passendes ZIP für die eigene Plattform laden ->
in ein Staging-Verzeichnis entpacken -> Dateien über die Installation kopieren (data/ bleibt unangetastet) -> neu starten.
Linux/macOS: die laufende Binärdatei wird umbenannt (.old) und ersetzt, danach exec der neuen Datei (unter systemd bleibt
die PID erhalten). Windows: eine laufende .exe lässt sich nicht überschreiben – ein kleines update.bat wartet auf das
Programmende, kopiert die Dateien und startet neu.
Quellcode-Installationen (nicht „frozen“) werden nicht automatisch aktualisiert (git pull).
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from . import __version__

REPO = "NoobKeksTV/BeamLog"
API = f"https://api.github.com/repos/{REPO}"
CHANGELOG_FILE = Path(__file__).parent / "CHANGELOG.md"


def parse_version(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", s or "")[:4]) or (0,)


def is_newer(latest: str, current: str = __version__) -> bool:
    return parse_version(latest) > parse_version(current)


def platform_tag() -> str:
    osname = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), platform.system().lower())
    arch = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    return f"{osname}-{arch}"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    return Path(sys.executable).resolve().parent if is_frozen() else Path.cwd()


def _headers(token: str = "", accept: str = "application/vnd.github+json") -> dict[str, str]:
    h = {"User-Agent": f"BeamLog/{__version__}", "Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def check_latest(token: str = "", timeout: float = 15) -> dict[str, Any]:
    """Neuestes Release: Version, Notizen, Assets. Wirft bei Netz-/API-Fehlern."""
    req = urllib.request.Request(f"{API}/releases/latest", headers=_headers(token))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rel = json.loads(r.read().decode("utf-8", "replace"))
    tag = rel.get("tag_name") or ""
    version = tag.lstrip("v")
    assets = [{"name": a["name"], "size": a.get("size", 0), "url": a["url"], "browser_url": a.get("browser_download_url", "")} for a in rel.get("assets", [])]
    mine = platform_tag()
    asset = next((a for a in assets if mine in a["name"] and a["name"].endswith(".zip")), None)
    return {"version": version, "tag": tag, "name": rel.get("name") or tag, "body": rel.get("body") or "", "published_at": rel.get("published_at") or "",
            "html_url": rel.get("html_url") or "", "assets": assets, "asset": asset, "platform": mine,
            "current": __version__, "available": is_newer(version), "can_self_update": is_frozen() and asset is not None}


def download(asset: dict, token: str = "", dest_dir: Path | None = None, progress=None, timeout: float = 60) -> Path:
    """ZIP-Asset laden (über die API-URL, damit es auch bei privatem Repo klappt)."""
    dest_dir = dest_dir or Path(tempfile.mkdtemp(prefix="contestlogger-update-"))
    dest = dest_dir / asset["name"]
    req = urllib.request.Request(asset["url"], headers=_headers(token, accept="application/octet-stream"))
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as fh:
        total = int(r.headers.get("Content-Length") or asset.get("size") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return dest


PKG_DIRS = ("BeamLog", "ContestLogger")  # Ordner/Programmnamen im ZIP (ContestLogger = Name bis 0.9)


def extract(zip_path: Path, staging: Path) -> Path:
    """ZIP entpacken; liefert den Ordner mit den Programmdateien (BeamLog/ im ZIP, bis 0.9 ContestLogger/)."""
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(staging)
        names = z.namelist()
    root = next((staging / d for d in PKG_DIRS if any(n.startswith(d + "/") for n in names)), staging)
    for f in root.rglob("*"):
        if f.is_file() and (f.name.startswith(PKG_DIRS) or f.suffix == ".sh"):
            try:
                f.chmod(0o755)
            except OSError:
                pass
    return root


SKIP_DIRS = {"data", "backup", "lang"}


def install_files(src: Path, dst: Path) -> list[str]:
    """Alle Dateien aus src nach dst kopieren – außer Datenordnern. Laufende Binärdateien werden vorher umbenannt."""
    copied: list[str] = []
    for f in src.rglob("*"):
        rel = f.relative_to(src)
        if rel.parts and rel.parts[0] in SKIP_DIRS:
            continue
        target = dst / rel
        if f.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and (target.name.startswith(PKG_DIRS) and target.suffix in ("", ".exe")):
            old = target.with_name(target.name + ".old")
            try:
                if old.exists():
                    old.unlink()
                target.rename(old)  # laufende Datei darf umbenannt, aber nicht überschrieben werden
            except OSError:
                pass
        shutil.copy2(f, target)
        copied.append(str(rel))
    return copied


def cleanup_old(dst: Path) -> None:
    for f in dst.glob("*.old"):
        try:
            f.unlink()
        except OSError:
            pass


def apply_update(asset: dict, token: str = "", progress=None) -> dict[str, Any]:
    """Komplettes Update einspielen. Liefert {"restart": "exec"|"batch", "copied": n, ...}."""
    if not is_frozen():
        raise RuntimeError("Quellcode-Installation: bitte mit „git pull“ und „pip install -r requirements.txt“ aktualisieren.")
    staging = Path(tempfile.mkdtemp(prefix="contestlogger-staging-"))
    zip_path = download(asset, token, staging, progress)
    root = extract(zip_path, staging / "x")
    base = base_dir()
    if os.name == "nt":
        # Windows: Dateien kopieren erledigt ein Batch nach dem Programmende
        bat = base / "update.bat"
        exe = Path(sys.executable).name
        args = " ".join(f'"{a}"' for a in sys.argv[1:])
        bat.write_text(
            "@echo off\r\n"
            f"cd /d \"{base}\"\r\n"
            ":wait\r\n"
            f"tasklist /FI \"PID eq {os.getpid()}\" 2>NUL | find \"{os.getpid()}\" >NUL && (timeout /t 1 /nobreak >NUL & goto wait)\r\n"
            f"xcopy /E /Y /I /Q \"{root}\\*\" \"{base}\" /EXCLUDE:\"{base}\\update-exclude.txt\" >NUL\r\n"
            f"rmdir /S /Q \"{staging}\" 2>NUL\r\n"
            f"start \"\" \"{base}\\{exe}\" {args}\r\n"
            "del \"%~f0\"\r\n", encoding="utf-8")
        (base / "update-exclude.txt").write_text("\\data\\\r\n", encoding="utf-8")
        return {"restart": "batch", "staging": str(staging), "bat": str(bat), "version_file": str(root)}
    copied = install_files(root, base)
    shutil.rmtree(staging, ignore_errors=True)
    return {"restart": "exec", "copied": len(copied)}


def restart_now(mode: str, bat: str = "") -> None:
    """Neustart auslösen – wird vom Server nach der Antwort an den Browser aufgerufen."""
    time.sleep(0.5)
    if mode == "batch" and bat:
        subprocess.Popen(["cmd", "/c", "start", "/min", "", bat], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0) | getattr(subprocess, "DETACHED_PROCESS", 0), close_fds=True)
        os._exit(0)
    exe = Path(sys.executable)
    try:
        os.execv(str(exe), [str(exe), *sys.argv[1:]])
    except OSError:
        os._exit(0)  # unter systemd (Restart=always) reicht das Beenden


# ------------------------------------------------------------------ Änderungsprotokoll (mitgeliefert, offline)
def load_changelog() -> list[dict[str, Any]]:
    """CHANGELOG.md -> [{version, date, title, lines:[...]}, …] (neueste zuerst)."""
    if not CHANGELOG_FILE.exists():
        return []
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for line in CHANGELOG_FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## v?(\d+(?:\.\d+)+)(?:\s*\((\d{4}-\d{2}-\d{2})\))?", line)
        if m:
            cur = {"version": m.group(1), "date": m.group(2) or "", "lines": []}
            out.append(cur)
        elif cur is not None and line.strip():
            cur["lines"].append(line.rstrip())
    return out


def changelog_since(version: str) -> list[dict[str, Any]]:
    """Alle Einträge, die neuer sind als version (für „Was ist neu“)."""
    return [e for e in load_changelog() if parse_version(e["version"]) > parse_version(version)]
