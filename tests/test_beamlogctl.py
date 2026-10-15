"""beamlogctl: Steuerskript für den Betrieb ohne systemd-Dienst (ServerController, SSH)."""
from __future__ import annotations

import http.server
import os
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("sh"), reason="nur Linux/macOS")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ctl(folder: Path, *args: str, port: int | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PORT"}
    if port:
        env["PORT"] = str(port)
    return subprocess.run(["sh", str(folder / "beamlogctl"), *args], capture_output=True, text=True, env=env, timeout=60)


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    shutil.copy(ROOT / "beamlogctl", tmp_path / "beamlogctl")
    return tmp_path


def test_syntax_posix_sh():
    assert subprocess.run(["sh", "-n", str(ROOT / "beamlogctl")]).returncode == 0
    assert os.access(ROOT / "beamlogctl", os.X_OK), "beamlogctl muss ausführbar sein (git: 100755)"


def test_status_stopped_and_usage(folder: Path):
    r = ctl(folder, "status", port=free_port())
    assert r.returncode == 1 and r.stdout.startswith("gestoppt")
    assert ctl(folder, "stop").returncode == 0
    assert ctl(folder, "unsinn").returncode == 2


def test_status_running_on_port_from_env_file(folder: Path):
    class Info(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"app":"BeamLog","version":"x"}' if self.path == "/api/info" else b""
            self.send_response(200 if body else 404)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Info)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        port = srv.server_address[1]
        (folder / ".env").write_text(f'HOST=0.0.0.0\nPORT="{port}"   # Kommentar\n')
        r = ctl(folder, "status")
        assert r.returncode == 0 and r.stdout.startswith("läuft"), r.stdout
        assert ctl(folder, "status", port=free_port()).returncode == 1  # $PORT (ServerController) geht vor
        r = ctl(folder, "start")  # läuft schon -> nichts doppelt starten
        assert r.returncode == 0 and not (folder / "data").exists()
    finally:
        srv.shutdown()


def test_start_reports_failure(folder: Path):
    (folder / "start.sh").write_text("#!/bin/sh\necho 'Port ist belegt'\nexit 1\n")
    os.chmod(folder / "start.sh", 0o755)
    r = ctl(folder, "start", port=free_port())
    assert r.returncode == 1 and "Port ist belegt" in r.stderr
    assert "Port ist belegt" in ctl(folder, "log", "5").stdout


def fake_installer(folder: Path) -> Path:
    """deploy/install.sh-Attrappe: schreibt nur ihre Argumente auf."""
    (folder / "deploy").mkdir()
    (folder / "deploy" / "install.sh").write_text(f'echo "$@" > "{folder}/args"\n')
    return folder / "args"


@pytest.mark.skipif(getattr(os, "geteuid", lambda: 1)() != 0 and not shutil.which("sudo"), reason="braucht root oder sudo")
def test_install_options_without_prompts(folder: Path):
    args = fake_installer(folder)
    r = ctl(folder, "install", "--no-nginx", "--no-backup", "-y")
    assert r.returncode == 0, r.stderr
    assert args.read_text().split() == ["--no-nginx", "--no-backup"]  # Dienst: wie zuletzt (install.sh merkt sich die Wahl)
    assert "nginx nein" in r.stdout and "Backup nein" in r.stdout
    r = ctl(folder, "install", "--deps-only", "--url", "http://contest.local/", "-y")
    assert args.read_text().split() == ["--no-service", "--no-nginx", "--no-backup", "--here", "--url", "http://contest.local/"]
    assert "Dienst nein" in r.stdout and "Ort: dieser Ordner" in r.stdout  # ohne Dienst wird nicht kopiert
    assert ctl(folder, "install", "--quatsch").returncode == 2


@pytest.mark.skipif(getattr(os, "geteuid", lambda: 1)() != 0 and not shutil.which("sudo"), reason="braucht root oder sudo")
def test_install_asks_interactively(folder: Path):
    import pty
    import select

    args = fake_installer(folder)
    master, slave = pty.openpty()
    env = {k: v for k, v in os.environ.items() if k != "PORT"}
    proc = subprocess.Popen(["sh", str(folder / "beamlogctl"), "install"], stdin=slave, stdout=slave, stderr=slave, env=env)
    os.close(slave)
    out = b""
    # Dienst: nein · nginx: Vorschlag (ja) · Backup: nein · Adresse · Weiter: ja · jetzt starten: nein
    answers = iter([b"n\n", b"\n", b"n\n", b"http://x.example/\n", b"\n", b"n\n"])
    prompts = 0
    while proc.poll() is None:
        r, _, _ = select.select([master], [], [], 10)
        if not r:
            break
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        out += chunk
        while out.count(b"?") + out.count(b"):") > prompts:  # neue Frage (endet auf „?“ bzw. „unverändert):“)
            prompts += 1
            os.write(master, next(answers, b"\n"))
    proc.wait(timeout=30)
    os.close(master)
    text = out.decode(errors="replace")
    assert proc.returncode == 0, text
    assert args.read_text().split() == ["--no-service", "--with-nginx", "--no-backup", "--url", "http://x.example/"]
    assert "Dienst nein · nginx ja · Backup nein" in text
