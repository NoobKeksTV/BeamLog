import os
import tempfile

from fastapi.testclient import TestClient

from contestlogger.app import create_app
from contestlogger.db import Database
from contestlogger.logcheck import check_station


def test_check_finds_problems(tmp_path):
    if True:
        db = Database(tmp_path / "t.db")
        cid = db.create_contest("T", "2026-05-02T14:00:00Z", "2026-05-03T14:00:00Z")
        sid = db.create_station(cid, "DN2LH/P", "JO31AA", "432MHz", "SSB", "", {"resp_name": "Lars"})
        db.add_qso(sid, {"call": "DL8NAS", "locator": "JN59LE", "ts_utc": "2026-05-02T15:00:00Z", "serial_rcvd": "010"})
        db.add_qso(sid, {"call": "OL3Z", "locator": "JN79", "ts_utc": "2026-05-02T15:10:00Z", "serial_rcvd": "x1"})
        db.add_qso(sid, {"call": "G3M", "locator": "", "ts_utc": "2026-05-04T15:10:00Z", "serial_sent": 5})
        res = check_station(db.get_contest(cid), db.get_station(sid), db.list_qsos(sid))
        msgs = " | ".join(e["msg"] for e in res["errors"])
        assert not res["ok"]
        assert "Locator fehlt" in msgs and "nach Contest-Ende" in msgs and "keine Zahl" in msgs
        wmsgs = " | ".join(w["msg"] for w in res["warnings"])
        assert "4-stellig" in wmsgs and "Lücken" in wmsgs and "E-Mail fehlt" in wmsgs


def test_export_gate(tmp_path):
    if True:
        app = create_app(tmp_path / "t.db", backup_interval_min=0)
        with TestClient(app) as c:
            admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
            H = {"X-Admin-Token": admin}
            cid = c.post("/api/contests", json={"name": "T"}, headers=H).json()["id"]
            sid = c.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH", "locator": "JO31AA", "band": "432MHz"}, headers=H).json()["id"]
            c.post(f"/api/stations/{sid}/qsos", json={"call": "DL8NAS", "locator": ""}, headers=H)
            assert c.get(f"/api/stations/{sid}/check").json()["ok"] is False
            assert c.get(f"/api/stations/{sid}/export.edi").status_code == 409
            assert c.get(f"/api/stations/{sid}/export.edi?force=1", headers=H).status_code == 200
            z = c.get(f"/api/contests/{cid}/export.zip")
            assert z.status_code == 200 and b"NICHT_EXPORTIERT.txt" in z.content
            c.patch(f"/api/qsos/{c.get(f'/api/stations/{sid}/qsos').json()[0]['id']}", json={"locator": "JN59LE", "serial_rcvd": "001"}, headers=H)
            assert c.get(f"/api/stations/{sid}/check").json()["ok"] is True
            assert c.get(f"/api/stations/{sid}/export.edi").status_code == 200
            assert b"DN2LH_432MHz.edi" in c.get(f"/api/contests/{cid}/export.zip").content


def test_plausibility(tmp_path):
    from contestlogger.prefixes import check_plausibility
    assert check_plausibility("DL8NAS", "JN59LE")["ok"]
    assert not check_plausibility("DL8NAS", "JO22AA")["ok"]
    assert check_plausibility("OE/DL1ABC", "JN77AA")["ok"]
    assert check_plausibility("GB2RS", "IO91AA")["ok"]
    assert check_plausibility("XX9ZZ", "JO31AA")["ok"]  # unbekanntes Land: kein Fehlalarm
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
        H = {"X-Admin-Token": admin}
        cid = c.post("/api/contests", json={"name": "T"}, headers=H).json()["id"]
        sid = c.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH", "locator": "JO31AA", "band": "432MHz"}, headers=H).json()["id"]
        c.post(f"/api/stations/{sid}/qsos", json={"call": "PA3XYZ", "locator": "JN59LE", "serial_rcvd": "001"}, headers=H)
        res = c.get(f"/api/stations/{sid}/check").json()
        assert any("Niederlande" in e["msg"] for e in res["errors"])
        r = c.get("/api/calc", params={"my": "JO31AA", "loc": "JO22AA", "call": "DL8NAS"}).json()
        assert any("Deutschland" in w for w in r["warnings"]) and any("Stationsdatenbank" in w for w in r["warnings"])
