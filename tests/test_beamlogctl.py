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
