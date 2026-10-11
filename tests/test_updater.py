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
    rel = {"tag_name": "v9.9.9", "name": "BeamLog 9.9.9", "body": "Notes", "published_at": "2026-10-05T10:00:00Z", "html_url": "https://x/",
           "assets": [{"name": f"BeamLog-9.9.9-{updater.platform_tag()}.zip", "size": 10, "url": "https://api/asset/1", "browser_download_url": "https://x/a.zip"},
                      {"name": "BeamLog-9.9.9-other-x.zip", "size": 10, "url": "https://api/asset/2", "browser_download_url": ""}]}

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
    z2 = tmp_path / "b.zip"  # ab 1.0 heißen Ordner und Programm BeamLog
    with zipfile.ZipFile(z2, "w") as zf:
        zf.writestr("BeamLog/BeamLog", "bin"); zf.writestr("BeamLog/README.md", "r")
    root = updater.extract(z2, tmp_path / "y")
    assert root.name == "BeamLog" and (root / "BeamLog").exists()


def test_install_files_renames_running_beamlog(tmp_path):
    src = tmp_path / "src"; src.mkdir(); (src / "BeamLog").write_bytes(b"new")
    dst = tmp_path / "dst"; dst.mkdir(); (dst / "BeamLog").write_bytes(b"old")
    updater.install_files(src, dst)
    assert (dst / "BeamLog").read_bytes() == b"new" and (dst / "BeamLog.old").read_bytes() == b"old"


def test_migrate_from_contestlogger(tmp_path):
    import run
    old = tmp_path / "ContestLogger"; (old / "data" / "backup").mkdir(parents=True)
    (old / "ContestLogger.exe").write_bytes(b"x"); (old / "data" / "contestlogger.db").write_text("DB"); (old / "contestlogger.env").write_text("PORT=8080")
    new = tmp_path / "BeamLog"; (new / "data" / "lang").mkdir(parents=True)
    run.migrate_from_contestlogger(new)
    assert (new / "data" / "contestlogger.db").read_text() == "DB" and (new / "data" / "backup").is_dir() and (new / ".env").read_text() == "PORT=8080"
    assert (old / "data" / "contestlogger.db").exists()  # Original bleibt
    run.adopt_legacy_names(new)  # danach heißt die Datenbank beamlog.db
    assert (new / "data" / "beamlog.db").read_text() == "DB" and not (new / "data" / "contestlogger.db").exists()
    (new / "data" / "beamlog.db").write_text("NEU")
    run.migrate_from_contestlogger(new)  # vorhandene Daten werden nie überschrieben
    assert (new / "data" / "beamlog.db").read_text() == "NEU"
    inner = old / "BeamLog"; (inner / "data").mkdir(parents=True)  # neuer Ordner im alten entpackt
    run.migrate_from_contestlogger(inner)
    assert (inner / "data" / "contestlogger.db").read_text() == "DB"


def test_adopt_legacy_names(tmp_path):
    import run
    (tmp_path / "data").mkdir(); (tmp_path / "contestlogger.env").write_text("A=1")
    for suf, txt in (("", "DB"), ("-wal", "WAL"), ("-shm", "SHM")):
        (tmp_path / "data" / f"contestlogger.db{suf}").write_text(txt)
    run.adopt_legacy_names(tmp_path)
    assert (tmp_path / ".env").read_text() == "A=1" and not (tmp_path / "contestlogger.env").exists()
    assert [(tmp_path / "data" / f"beamlog.db{s}").read_text() for s in ("", "-wal", "-shm")] == ["DB", "WAL", "SHM"]
    (tmp_path / "data" / "contestlogger.db").write_text("ALT")  # gibt es beamlog.db schon, bleibt alles unangetastet
    run.adopt_legacy_names(tmp_path)
    assert (tmp_path / "data" / "beamlog.db").read_text() == "DB" and (tmp_path / "data" / "contestlogger.db").exists()


def test_beamlog_env_renamed_to_dotenv(tmp_path, monkeypatch):
    """Ab jetzt heißt die Einstellungsdatei .env – eine vorhandene beamlog.env wird beim Start umbenannt, eine Unit mit
    --config …/beamlog.env findet danach die .env daneben."""
    import run
    (tmp_path / "beamlog.env").write_text("PORT=8123")
    run.adopt_legacy_names(tmp_path)
    assert (tmp_path / ".env").read_text() == "PORT=8123" and not (tmp_path / "beamlog.env").exists()
    (tmp_path / "beamlog.env").write_text("ALT")  # gibt es .env schon, bleibt die alte Datei liegen (nur Hinweis)
    run.adopt_legacy_names(tmp_path)
    assert (tmp_path / ".env").read_text() == "PORT=8123" and (tmp_path / "beamlog.env").exists()
    (tmp_path / "beamlog.env").unlink()
    monkeypatch.chdir(tmp_path); monkeypatch.delenv("BEAMLOG_CONFIG", raising=False); monkeypatch.delenv("CONTESTLOGGER_CONFIG", raising=False)
    assert run.find_config(str(tmp_path / "beamlog.env")) == tmp_path / ".env"
    assert run.find_config(None) == tmp_path / ".env"


def test_env_and_config_names(tmp_path, monkeypatch):
    import run
    from contestlogger import env
    monkeypatch.delenv("BEAMLOG_X", raising=False); monkeypatch.setenv("CONTESTLOGGER_X", "alt")
    assert env("X") == "alt"  # alter Name gilt weiter
    monkeypatch.setenv("BEAMLOG_X", "neu")
    assert env("X") == "neu"  # neuer Name hat Vorrang
    f = tmp_path / "beamlog.env"; f.write_text("BEAMLOG_PORT=9000\nCONTESTLOGGER_HOST=127.0.0.1\nDB=/x/beamlog.db\n")
    assert run.load_env_file(f) == {"PORT": "9000", "HOST": "127.0.0.1", "DB": "/x/beamlog.db"}


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


def test_env_file_inline_comments_and_port_check(tmp_path):
    import socket

    import pytest

    import run
    f = tmp_path / "beamlog.env"
    f.write_text('PORT=80   # direkt ohne nginx\nHOST="0.0.0.0" # alle\nPUBLIC_URL=http://contest.local/#x\n')
    assert run.load_env_file(f) == {"PORT": "80", "HOST": "0.0.0.0", "PUBLIC_URL": "http://contest.local/#x"}
    with socket.socket() as busy:  # belegter Port -> verständliche Meldung statt Absturz
        busy.bind(("127.0.0.1", 0)); busy.listen()
        with pytest.raises(SystemExit) as e:
            run.check_port("127.0.0.1", busy.getsockname()[1])
    assert "belegt" in str(e.value)
