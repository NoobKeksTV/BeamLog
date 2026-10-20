import time
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from contestlogger import lookup
from contestlogger.app import create_app

HAMQTH_LOGIN = b'<?xml version="1.0"?><HamQTH version="2.8" xmlns="https://www.hamqth.com"><session><session_id>abc123</session_id></session></HamQTH>'
HAMQTH_CALL = b'<?xml version="1.0"?><HamQTH version="2.8" xmlns="https://www.hamqth.com"><search><callsign>pa3xyz</callsign><nick>Jan</nick><qth>Amsterdam</qth><country>Netherlands</country><grid>JO22EC</grid></search></HamQTH>'
HAMQTH_MISS = b'<?xml version="1.0"?><HamQTH version="2.8" xmlns="https://www.hamqth.com"><session><error>Callsign not found</error></session></HamQTH>'


def test_hamqth_lookup(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        if "&p=" in url:
            return HAMQTH_LOGIN
        if "callsign=PA3XYZ" in url:
            return HAMQTH_CALL
        return HAMQTH_MISS
    monkeypatch.setattr(lookup, "_get", fake_get)
    lk = lookup.Lookup("hamqth", "dn2lh", "pw")
    assert lk.enabled
    r = lk.lookup("PA3XYZ/P")
    assert r["locator"] == "JO22EC" and r["name"] == "Jan" and r["source"] == "hamqth"
    assert lk.lookup("XX1XX") == {}
    assert len([c for c in calls if "&p=" in c]) == 1  # Session wird wiederverwendet
    assert "OK" in lk.test()


def test_lookup_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(lookup, "_get", lambda url: HAMQTH_LOGIN if "&p=" in url else (HAMQTH_CALL if "PA3XYZ" in url else HAMQTH_MISS))
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
        H = {"X-Admin-Token": admin}
        assert c.get("/api/lookup", params={"call": "PA3XYZ"}).json()["source"] == "none"  # aus
        c.post("/api/settings", json={"lookup_provider": "hamqth", "lookup_user": "dn2lh", "lookup_pass": "pw"}, headers=H)
        cfg = c.get("/api/settings", headers=H).json()
        assert cfg["lookup_provider"] == "hamqth" and cfg["lookup_pass_set"] and "lookup_pass" not in cfg
        r = c.get("/api/lookup", params={"call": "PA3XYZ"}).json()
        assert r["locator"] == "JO22EC" and r["source"] == "hamqth"
        # jetzt lokal gecacht
        assert c.get("/api/lookup", params={"call": "PA3XYZ"}).json()["source"] == "local"
        assert c.get("/api/callbook", params={"q": "PA3XYZ"}).json()["rows"][0]["name"] == "Jan"
        assert c.get("/api/lookup", params={"call": "XX1XX"}).json()["source"] == "none"
        assert c.post("/api/lookup/test", headers=H).json()["ok"]


HAMQTH_DL = b'<?xml version="1.0"?><HamQTH version="2.8" xmlns="https://www.hamqth.com"><search><callsign>dl1abc</callsign><nick>Peter</nick><grid>JO31AA</grid><dok>G 01</dok></search></HamQTH>'
HAMQTH_LIMIT = b'<?xml version="1.0"?><HamQTH version="2.8" xmlns="https://www.hamqth.com"><session><error>Daily limit exceeded</error></session></HamQTH>'


def test_hamqth_dok_and_errors(monkeypatch):
    answers = {"DL1ABC": HAMQTH_DL, "DL2LIM": HAMQTH_LIMIT}
    monkeypatch.setattr(lookup, "_get", lambda url: HAMQTH_LOGIN if "&p=" in url else next((v for k, v in answers.items() if k in url), HAMQTH_MISS))
    lk = lookup.Lookup("hamqth", "dn2lh", "pw")
    r = lk.lookup("DL1ABC")
    assert (r["locator"], r["dok"], r["name"]) == ("JO31AA", "G01", "Peter")
    assert lk.lookup("DL9NIX") == {}                    # nicht gefunden: kein Fehler
    with pytest.raises(lookup.LookupError_, match="limit"):
        lk.lookup("DL2LIM")                             # Limit: Fehler, das Auffüllen hört dann auf


def test_callbook_stats_and_name_limit(tmp_path):
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        H = {"X-Admin-Token": c.post("/api/setup", json={"password": "admin1"}).json()["token"]}
        from contestlogger.db import Database
        db = Database(tmp_path / "t.db")
        with db.conn:
            db.conn.execute("DELETE FROM callbook")  # ohne die mitgelieferte Startdatenbank
        for call, loc, dok in (("DL1AAA", "JO31AA", "G01"), ("DL2BBB", "JO40AA", ""), ("DK3CCC", "", "B01"), ("PA3XYZ", "JO22EC", "")):
            c.post("/api/callbook", json={"call": call, "locator": loc or "JO31AA", "dok": dok, "name": "X" * 40}, headers=H)
        with db.conn:
            db.conn.execute("UPDATE callbook SET locator='' WHERE call='DK3CCC'")
        s = c.get("/api/callbook/stats").json()
        assert (s["total"], s["locator"], s["dok"], s["both"], s["none"]) == (4, 3, 2, 1, 0)
        de = s["countries"][0]
        assert de["country"] == "Deutschland" and (de["total"], de["locator"], de["dok"]) == (3, 2, 2)
        rows = c.get("/api/callbook").json()["rows"]
        assert all(len(r["name"]) <= 32 for r in rows) and "qso_count" not in rows[0]


def test_callbook_fill_job(monkeypatch, tmp_path):
    answers = {"DL1ABC": HAMQTH_DL, "PA3XYZ": HAMQTH_CALL}
    monkeypatch.setattr(lookup, "_get", lambda url: HAMQTH_LOGIN if "&p=" in url else next((v for k, v in answers.items() if k in url), HAMQTH_MISS))
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        H = {"X-Admin-Token": c.post("/api/setup", json={"password": "admin1"}).json()["token"]}
        assert c.post("/api/callbook/fill/start", headers=H).status_code == 400  # ohne Zugangsdaten
        c.post("/api/settings", json={"lookup_provider": "hamqth", "lookup_user": "dn2lh", "lookup_pass": "pw"}, headers=H)
        from contestlogger.db import Database
        db = Database(tmp_path / "t.db")
        with db.conn:
            db.conn.execute("DELETE FROM callbook")
        db.learn_call("DL1ABC", "", source="import")          # ohne Locator und DOK
        db.learn_call("DL9NIX", "", source="import")          # unbekannt bei HamQTH
        db.learn_call("PA3XYZ", "JO22EC", source="import")    # hat Locator, Ausland: braucht keinen DOK -> nicht abfragen
        db.learn_call("DK5FUL", "JO50AA", source="import", dok="Z99")  # vollständig
        st = c.get("/api/callbook/fill", headers=H).json()
        assert st["open"] == 2 and st["enabled"] and st["cfg"]["pause"] >= 1
        c.post("/api/callbook/fill/settings", json={"pause": 1, "daily": 5}, headers=H)
        assert c.post("/api/callbook/fill/start", headers=H).status_code == 200
        end = time.time() + 20
        while (j := c.get("/api/callbook/fill", headers=H).json()["job"])["running"] and time.time() < end:
            time.sleep(0.1)
        assert (j["done"], j["found"], j["locator"], j["dok"]) == (2, 1, 1, 1)
        row = c.get("/api/callbook", params={"q": "DL1ABC"}).json()["rows"][0]
        assert (row["locator"], row["dok"], row["name"]) == ("JO31AA", "G01", "Peter")
        st = c.get("/api/callbook/fill", headers=H).json()
        assert st["open"] == 0 and st["used_today"] == 2     # abgefragt (auch ohne Treffer) -> erst nach redo_days wieder
