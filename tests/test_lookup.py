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
