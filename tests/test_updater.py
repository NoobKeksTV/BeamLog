"""Updater: Versionsvergleich, Release-Prüfung (gemockt), Dateien einspielen, Änderungsprotokoll."""
import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from contestlogger import updater
from contestlogger.app import create_app


def test_version_compare_and_platform():
    assert updater.parse_version("v0.9.28") == (0, 9, 28)
    assert updater.is_newer("0.10.0", "0.9.28") and not updater.is_newer("0.9.28", "0.9.28") and not updater.is_newer("0.9.9", "0.9.28")
    assert updater.platform_tag().split("-")[0] in ("linux", "windows", "macos")


def test_check_latest_mocked(monkeypatch):
    rel = {"tag_name": "v9.9.9", "name": "ContestLogger 9.9.9", "body": "Notes", "published_at": "2026-10-05T10:00:00Z", "html_url": "https://x/",
           "assets": [{"name": f"ContestLogger-9.9.9-{updater.platform_tag()}.zip", "size": 10, "url": "https://api/asset/1", "browser_download_url": "https://x/a.zip"},
                      {"name": "ContestLogger-9.9.9-other-x.zip", "size": 10, "url": "https://api/asset/2", "browser_download_url": ""}]}

    class R(io.BytesIO):
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda req, timeout=0: R(json.dumps(rel).encode()))
    r = updater.check_latest("tok")
    assert r["version"] == "9.9.9" and r["available"] and r["asset"]["url"] == "https://api/asset/1" and r["can_self_update"] is False  # nicht frozen


def test_install_files_keeps_data(tmp_path):
    src = tmp_path / "src"; (src / "deploy").mkdir(parents=True); (src / "data").mkdir()  # kein Ordner "contestlogger": macOS ist case-insensitiv
    (src / "ContestLogger").write_bytes(b"new"); (src / "README.md").write_text("r"); (src / "data" / "x.db").write_text("NEW")
    dst = tmp_path / "dst"; (dst / "data").mkdir(parents=True)
    (dst / "ContestLogger").write_bytes(b"old"); (dst / "data" / "x.db").write_text("KEEP")
    copied = updater.install_files(src, dst)
    assert (dst / "ContestLogger").read_bytes() == b"new" and (dst / "ContestLogger.old").read_bytes() == b"old"
    assert (dst / "data" / "x.db").read_text() == "KEEP" and "README.md" in copied and not any(c.startswith("data") for c in copied)
    updater.cleanup_old(dst)
    assert not (dst / "ContestLogger.old").exists()


def test_extract_zip_layout(tmp_path):
    z = tmp_path / "p.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("ContestLogger/ContestLogger", "bin"); zf.writestr("ContestLogger/start.sh", "sh"); zf.writestr("ContestLogger/README.md", "r")
    root = updater.extract(z, tmp_path / "x")
    assert root.name == "ContestLogger" and (root / "README.md").exists()


def test_changelog_and_update_api(tmp_path, monkeypatch):
    cl = tmp_path / "CHANGELOG.md"
    from contestlogger import __version__ as cur
    nxt = cur.rsplit(".", 1)[0] + "." + str(int(cur.rsplit(".", 1)[1]) + 1)  # unveröffentlichte Version (darf nicht erscheinen)
    cl.write_text(f"# Änderungsprotokoll\n\n## v{nxt} (2026-10-06)\n- Zukunft\n\n## v{cur} (2026-10-05)\n- Neu A\n  - Detail\n\n## v0.0.2 (2026-10-04)\n- Neu B\n\n## v0.0.1 (2026-10-04)\n- Alt\n", encoding="utf-8")
    monkeypatch.setattr(updater, "CHANGELOG_FILE", cl)
    assert [e["version"] for e in updater.load_changelog()] == [nxt, cur, "0.0.2", "0.0.1"]
    assert [e["version"] for e in updater.changelog_since("0.0.2")] == [nxt, cur]
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
        H = {"X-Admin-Token": admin}
        r = c.get("/api/changelog", params={"since": "0.0.2"}).json()
        assert [e["version"] for e in r["entries"]] == [cur] and r["entries"][0]["lines"][0] == "- Neu A"  # Unveröffentlichtes wird ausgeblendet
        st = c.get("/api/update/status").json()
        assert st["current"] and st["available"] is False and st["frozen"] is False
        assert c.post("/api/update/check").status_code == 403  # nur Admin
        monkeypatch.setattr(updater, "check_latest", lambda token="", timeout=15: {"version": "9.9.9", "tag": "v9.9.9", "name": "x", "body": "b", "published_at": "", "html_url": "", "assets": [], "asset": None, "platform": "linux-x86_64", "current": "0.0.1", "available": True, "can_self_update": False})
        r = c.post("/api/update/check", headers=H).json()
        assert r["available"] and r["frozen"] is False
        assert c.get("/api/update/status").json()["available"] is True
        assert c.post("/api/update/apply", headers=H).status_code == 400  # Quellcode-Installation
