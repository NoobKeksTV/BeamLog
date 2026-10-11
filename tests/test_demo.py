"""Demo-Modus (BEAMLOG_DEMO=1): Beispieldaten, feste Zugangsdaten, Sperren und Zurücksetzen."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from contestlogger import demo
from contestlogger.app import create_app
from contestlogger.db import Database


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAMLOG_DEMO", "1")
    monkeypatch.setenv("BEAMLOG_MAINTAINER", "1")  # wird in der Demo ignoriert
    with TestClient(create_app(tmp_path / "demo.db", backup_interval_min=0)) as c:
        yield c


def admin(c):
    return {"X-Admin-Token": c.post("/api/admin/login", json={"password": demo.ADMIN_PASSWORD}).json()["token"]}


def test_demo_sample_data_and_info(client):
    info = client.get("/api/info").json()
    assert info["demo"]["admin_password"] == "demo" and info["admin_configured"] and not info["maintainer"]
    contests = client.get("/api/contests").json()
    assert len(contests) == 1 and len(contests[0]["stations"]) == len(demo.STATIONS)
    counts = sorted(len(client.get(f"/api/stations/{s['id']}/qsos").json()) for s in contests[0]["stations"])
    assert counts == sorted(n for _, n in demo.STATIONS)
    assert info["callbook_count"] > 1000  # Startdatei geladen – Vorschläge funktionieren


def test_demo_blocks_dangerous_actions(client):
    H = admin(client)
    c = client.get("/api/contests").json()[0]
    sid = c["stations"][0]["id"]
    for method, url, body in [("post", "/api/admin/password", {"password": "kaputt"}), ("post", "/api/settings", {"adsb_local_url": "http://intern/"}),
                              ("post", "/api/update/apply", {}), ("post", "/api/kst/start", {"station_id": sid}), ("post", "/api/backups", {}),
                              ("post", "/api/tiles/prefetch", {"locator": "JO51DT"}), ("post", "/api/results/list", {"source": "darc-kw"}),
                              ("patch", f"/api/stations/{sid}", {"kst_user": "DL1ABC", "kst_pass": "geheim"}),
                              ("patch", f"/api/stations/{sid}", {"password": "neu"}), ("delete", f"/api/contests/{c['id']}", None)]:
        r = client.request(method.upper(), url, json=body, headers=H)
        assert r.status_code == 403 and "Demo" in r.json()["detail"], (method, url, r.text)
    assert client.post("/api/admin/login", json={"password": "demo"}).status_code == 200  # Passwort unverändert
    # Erlaubt: Stationsdaten ändern, loggen, eigene Contests anlegen und löschen
    assert client.patch(f"/api/stations/{sid}", json={"info": {"power": "50"}}, headers=H).status_code == 200
    tok = client.post(f"/api/stations/{sid}/unlock", json={"password": demo.STATION_PASSWORD}).json()["token"]
    r = client.post(f"/api/stations/{sid}/qsos", json={"call": "DA9AAA", "locator": "JO62QM"}, headers={"X-Station-Token": tok})
    assert r.status_code == 200 and r.json()["km"] > 0
    own = client.post("/api/contests", json={"name": "Mein Test"}, headers=H).json()["id"]
    assert client.delete(f"/api/contests/{own}", headers=H).status_code == 200


def test_demo_reset_restores_everything(tmp_path):
    db = Database(tmp_path / "d.db")
    first = demo.reset(db, lambda: 0)
    db.set_admin_password("anders")
    db.create_contest("Fremd", None, None)
    second = demo.reset(db, lambda: 0)
    assert db.check_admin("demo") and len(db.list_contests()) == 1 and second["contests"] != first["contests"]
    db.close()


def test_demo_refuses_real_database(tmp_path):
    db = Database(tmp_path / "echt.db")
    db.create_contest("Echter Contest", None, None)
    with pytest.raises(RuntimeError, match="verweigert"):
        demo.reset(db, lambda: 0)
    assert len(db.list_contests()) == 1  # nichts gelöscht
    db.close()


def test_demo_next_reset(monkeypatch):
    monkeypatch.setenv("BEAMLOG_DEMO_RESET", "04:30")
    now = datetime(2026, 10, 11, 5, 0).astimezone()
    nxt = demo.next_reset(now)
    assert (nxt.day, nxt.hour, nxt.minute) == (12, 4, 30)
    assert demo.next_reset(now.replace(hour=1)).day == 11
