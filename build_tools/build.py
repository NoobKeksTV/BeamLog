#!/usr/bin/env python3
"""Builder: erzeugt portable Programme (ohne Python-Installation) mit PyInstaller.

    python build_tools/build.py            # baut für das aktuelle Betriebssystem
    python build_tools/build.py --onedir   # Ordner statt Einzeldatei (startet schneller)
    python build_tools/build.py --no-zip   # ohne ZIP-Paket

Ergebnis in dist/:
    ContestLogger[.exe]          Server + Weboberfläche (Daten in ./data neben der Datei)
    ContestLogger-CAT[.exe]      CAT-Bridge (Frequenz/CW vom Funkgerät an den Server)
    ContestLogger-Import[.exe]   Import eines kompletten WinContest-Ordners
    ContestLogger-<version>-<os>-<arch>.zip   alles zusammen, portabel
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from contestlogger import __version__  # noqa: E402

SEP = ";" if os.name == "nt" else ":"
HIDDEN = ["uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio", "uvicorn.protocols",
          "uvicorn.protocols.http", "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl", "uvicorn.protocols.http.httptools_impl",
          "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto", "uvicorn.protocols.websockets.websockets_impl",
          "uvicorn.protocols.websockets.wsproto_impl", "uvicorn.lifespan", "uvicorn.lifespan.on", "uvicorn.lifespan.off",
          "websockets", "websockets.legacy", "websockets.legacy.server", "wsproto", "h11", "anyio._backends._asyncio",
          "multipart", "python_multipart", "qrcode", "qrcode.image.svg", "construct", "tabulate", "pypdf"]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def build(name: str, script: str, onefile: bool, extra: list[str]) -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", name,
           "--onefile" if onefile else "--onedir", "--console", "--distpath", str(ROOT / "dist"),
           "--workpath", str(ROOT / "build" / "pyinstaller"), "--specpath", str(ROOT / "build" / "spec"), *extra, script]
    run(cmd)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--onedir", action="store_true")
    ap.add_argument("--no-zip", action="store_true")
    a = ap.parse_args()
    onefile = not a.onedir
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    dist = ROOT / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    static = ROOT / "contestlogger" / "static"
    seed = ROOT / "contestlogger" / "seed"
    changelog = ROOT / "contestlogger" / "CHANGELOG.md"
    try:  # Änderungsprotokoll aus der Git-Historie (für „Was ist neu“ im Programm, offline)
        txt = subprocess.run([sys.executable, str(ROOT / "build_tools" / "release_notes.py"), "--changelog", __version__], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        if txt.strip():
            changelog.write_text(txt, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"CHANGELOG nicht erzeugt: {e}")
    server_extra = [f"--add-data={static}{SEP}contestlogger/static", f"--add-data={seed}{SEP}contestlogger/seed"] + [f"--hidden-import={h}" for h in HIDDEN]
    if changelog.exists():
        server_extra.append(f"--add-data={changelog}{SEP}contestlogger")
    icon = ROOT / "build_tools" / "icon.ico"
    if icon.exists() and os.name == "nt":
        server_extra.append(f"--icon={icon}")
    build("ContestLogger", "run.py", onefile, server_extra)
    build("ContestLogger-CAT", "tools/cat_bridge.py", onefile, [])
    build("ContestLogger-Import", "tools/import_dd3ku.py", onefile, [])

    # Portables Paket
    pkg = dist / "portable"
    pkg.mkdir()
    for item in dist.iterdir():
        if item == pkg:
            continue
        shutil.move(str(item), pkg / item.name)
    (pkg / "data").mkdir()
    (pkg / "data" / "lang").mkdir()
    shutil.copy(ROOT / "README.md", pkg / "README.md")
    shutil.copy(ROOT / "LICENSE", pkg / "LICENSE") if (ROOT / "LICENSE").exists() else None
    exe = ".exe" if os.name == "nt" else ""
    (pkg / "START.txt").write_text(
        f"ContestLogger {__version__} – portable Version\n\n"
        f"1. ContestLogger{exe} starten (Doppelklick). Der Server läuft, die Oberfläche öffnet sich im Browser.\n"
        f"   Andere Rechner im LAN: die beim Start angezeigte Adresse eingeben (oder QR-Code in der Oberfläche).\n"
        f"2. Alle Daten liegen im Ordner data/ neben dem Programm (Datenbank, Backups, eigene Sprachen).\n"
        f"   Zum Umziehen auf einen anderen Rechner einfach den ganzen Ordner kopieren.\n"
        f"3. Optionen: ContestLogger{exe} --port 8080   --backup-min 5   --public-url http://contest.local/\n\n"
        f"ContestLogger-CAT{exe}: Frequenz/CW vom Funkgerät (Hamlib rigctld) an den Server melden, z. B.\n"
        f"   ContestLogger-CAT{exe} --server http://192.168.1.10:8000 --station 1 --password 70cm --cw\n"
        f"ContestLogger-Import{exe}: alten WinContest-Ordner übernehmen, z. B.\n"
        f"   ContestLogger-Import{exe} \"D:\\Contest\" --db data\\contestlogger.db\n\n"
        f"Beenden: Fenster schließen oder Strg+C. Vorher wird automatisch ein Backup geschrieben.\n",
        encoding="utf-8")
    if os.name == "nt":
        (pkg / "ContestLogger-Port8080.bat").write_text('@echo off\r\ncd /d "%~dp0"\r\nContestLogger.exe --port 8080\r\npause\r\n')
    else:
        (pkg / "start.sh").write_text('#!/usr/bin/env bash\ncd "$(dirname "$0")"\n./ContestLogger "$@"\n')
        os.chmod(pkg / "start.sh", 0o755)
    if platform.system() == "Linux":
        # Deploy-Paket für Debian-Server (nginx + systemd) liegt im Linux-ZIP immer bei
        shutil.copytree(ROOT / "deploy" / "portable", pkg / "deploy")
        for f in (pkg / "deploy").glob("*.sh"):
            os.chmod(f, 0o755)
        with open(pkg / "START.txt", "a", encoding="utf-8") as fh:
            fh.write("\nServer-Installation (Debian/Ubuntu/Raspberry Pi, nginx + systemd):  sudo bash deploy/install.sh\n"
                     "   Einzelheiten in deploy/README.md\n")

    if not a.no_zip:
        osname = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), platform.system().lower())
        arch = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
        zname = dist / f"ContestLogger-{__version__}-{osname}-{arch}.zip"
        with zipfile.ZipFile(zname, "w", zipfile.ZIP_DEFLATED) as z:
            for f in pkg.rglob("*"):
                info = zipfile.ZipInfo.from_file(f, f"ContestLogger/{f.relative_to(pkg)}")
                if f.is_dir():
                    z.writestr(info, "")
                else:
                    info.external_attr = (0o755 if os.access(f, os.X_OK) else 0o644) << 16
                    z.writestr(info, f.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
        print(f"\nPaket: {zname}  ({zname.stat().st_size // 1024 // 1024} MB)")
    print(f"Portable Dateien in: {pkg}")


if __name__ == "__main__":
    main()
