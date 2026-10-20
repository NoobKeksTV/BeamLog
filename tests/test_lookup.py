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


def qrz_xml(body: str) -> bytes:
    return f'<?xml version="1.0"?><QRZDatabase version="1.34" xmlns="http://xmldata.qrz.com">{body}<Session><Key>k1</Key><Count>42</Count></Session></QRZDatabase>'.encode()


def fake_services(hamqth: dict, qrz: dict, hamqth_error: str = ""):
    """HamQTH und QRZ.com zugleich nachbilden: je Call die Antwort, sonst „nicht gefunden“."""
    import threading
    lock, calls = threading.Lock(), []

    def get(url):
        with lock:
            calls.append(url)
        if "hamqth.com" in url:
            if "&p=" in url:
                return HAMQTH_LOGIN
            if hamqth_error:
                return f'<?xml version="1.0"?><HamQTH xmlns="https://www.hamqth.com"><session><error>{hamqth_error}</error></session></HamQTH>'.encode()
            return next((v for k, v in hamqth.items() if f"callsign={k}" in url), HAMQTH_MISS)
        if "password=" in url:
            return qrz_xml("")
        return next((qrz_xml(v) for k, v in qrz.items() if f"callsign={k}" in url), qrz_xml("").replace(b"<Key>", b"<Error>Not found: X</Error><Key>"))
    return get, calls


def fill_setup(c, H, tmp_path, rows):
    from contestlogger.db import Database
    c.post("/api/settings", json={"lookup_provider": "hamqth", "lookup_user_hamqth": "dn2lh", "lookup_pass_hamqth": "pw",
                                  "lookup_user_qrz": "dn2lh", "lookup_pass_qrz": "pw2"}, headers=H)
    db = Database(tmp_path / "t.db")
    with db.conn:
        db.conn.execute("DELETE FROM callbook")  # ohne die mitgelieferte Startdatenbank
    for call, loc, dok in rows:
        db.learn_call(call, loc, source="import", dok=dok)
    c.post("/api/callbook/fill/settings", json={"hamqth": {"par": 2, "pause": 0}, "qrz": {"par": 3, "pause": 0}}, headers=H)


def fill_wait(c, H):
    end = time.time() + 30
    while (j := c.get("/api/callbook/fill", headers=H).json()["job"])["running"] and time.time() < end:
        time.sleep(0.05)
    return j


def test_callbook_fill_both_services(monkeypatch, tmp_path):
    get, calls = fake_services({"DL1ABC": HAMQTH_DL, "DL3DOK": HAMQTH_DL.replace(b"G 01", b"B05")},
                               {"DL2QRZ": "<Callsign><call>DL2QRZ</call><grid>JO40AB</grid><fname>Udo</fname></Callsign>",
                                "OK1ZZZ": "<Callsign><call>OK1ZZZ</call><grid>JN79AA</grid></Callsign>"})
    monkeypatch.setattr(lookup, "_get", get)
    monkeypatch.setenv("BEAMLOG_MAINTAINER", "1")
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        H = {"X-Admin-Token": c.post("/api/setup", json={"password": "admin1"}).json()["token"]}
        assert c.post("/api/callbook/fill/start", headers=H).status_code == 400  # ohne Zugangsdaten
        fill_setup(c, H, tmp_path, [("DL1ABC", "", ""), ("DL2QRZ", "", ""), ("PA9NIX", "", ""), ("DL3DOK", "JO50AA", ""),
                                    ("OK1ZZZ", "", ""), ("PA3XYZ", "JO22EC", ""), ("DK5FUL", "JO50AA", "Z99")])
        st = c.get("/api/callbook/fill", headers=H).json()
        assert st["open"] == 5 and st["services"]["qrz"]["enabled"] and st["cfg"]["qrz"]["par"] == 3
        assert c.post("/api/callbook/fill/start", headers=H).status_code == 200
        j = fill_wait(c, H)
        assert (j["done"], j["found"], j["locator"], j["dok"], j["buffer"]) == (5, 4, 3, 2, 0)
        assert j["services"]["qrz"]["count"] == 42 and j["services"]["hamqth"]["done"] >= 2
        cb = {r["call"]: r for r in c.get("/api/callbook").json()["rows"]}
        assert (cb["DL1ABC"]["locator"], cb["DL1ABC"]["dok"]) == ("JO31AA", "G01")
        assert (cb["DL2QRZ"]["locator"], cb["DL2QRZ"]["name"]) == ("JO40AB", "Udo")       # HamQTH kannte ihn nicht -> QRZ.com
        assert (cb["DL3DOK"]["locator"], cb["DL3DOK"]["dok"]) == ("JO50AA", "B05")         # Locator bleibt, DOK nur von HamQTH
        assert not any("qrz.com" in u and "DL3DOK" in u for u in calls)                    # QRZ.com liefert keinen DOK
        assert sum("callsign=PA9NIX" in u for u in calls) == 2                             # bei beiden nachgefragt, dann gemerkt
        assert c.get("/api/callbook/fill", headers=H).json()["open"] == 0
        assert c.get("/api/callbook/fill", headers=H).json()["used_today"]["hamqth"] >= 2


def test_callbook_fill_service_stops(monkeypatch, tmp_path):
    get, _ = fake_services({}, {"DL2QRZ": "<Callsign><call>DL2QRZ</call><grid>JO40AB</grid></Callsign>"}, hamqth_error="Daily limit exceeded")
    monkeypatch.setattr(lookup, "_get", get)
    monkeypatch.setenv("BEAMLOG_MAINTAINER", "1")
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        H = {"X-Admin-Token": c.post("/api/setup", json={"password": "admin1"}).json()["token"]}
        fill_setup(c, H, tmp_path, [("DL2QRZ", "", ""), ("DL3DOK", "JO50AA", ""), ("DL4AAA", "", "")])
        c.post("/api/callbook/fill/start", headers=H)
        j = fill_wait(c, H)
        assert j["services"]["hamqth"]["stopped"].startswith("gestoppt") and not j["services"]["qrz"]["stopped"]
        assert j["done"] == 2 and j["locator"] == 1                    # QRZ.com macht ohne HamQTH weiter
        assert "HamQTH" in j["stopped"]
        assert c.get("/api/callbook/fill", headers=H).json()["open"] == 1   # DL3DOK (nur DOK fehlt) bleibt für HamQTH offen


def test_callbook_fill_maintainer_only(tmp_path, monkeypatch):
    """Auffüllen gibt es nur im Betreuer-Modus – normale Installationen holen die gepflegte Liste aus dem Repo."""
    monkeypatch.delenv("BEAMLOG_MAINTAINER", raising=False)
    monkeypatch.delenv("BEAMLOG_DEV", raising=False)
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        H = {"X-Admin-Token": c.post("/api/setup", json={"password": "admin1"}).json()["token"]}
        c.post("/api/settings", json={"lookup_user_hamqth": "dn2lh", "lookup_pass_hamqth": "pw"}, headers=H)
        assert c.get("/api/callbook/fill", headers=H).status_code == 403
        assert c.post("/api/callbook/fill/start", headers=H).status_code == 403
        assert c.post("/api/callbook/fill/settings", json={"auto": True}, headers=H).status_code == 403
        assert c.post("/api/callbook/fill/cancel", headers=H).status_code == 403
