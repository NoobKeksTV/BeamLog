import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from contestlogger.app import create_app


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as d:
        app = create_app(os.path.join(d, "t.db"))
        with TestClient(app) as c:
            yield c


def test_full_flow(client):
    info = client.get("/api/info").json()
    assert info["admin_configured"] is False and info["version"]

    admin = client.post("/api/setup", json={"password": "admin1"}).json()["token"]
    assert client.post("/api/setup", json={"password": "x"}).status_code == 409
    assert client.post("/api/admin/login", json={"password": "admin1"}).json()["token"] == admin
    H = {"X-Admin-Token": admin}

    assert client.post("/api/contests", json={"name": "Mai"}).status_code == 403
    cid = client.post("/api/contests", json={"name": "Mai"}, headers=H).json()["id"]
    st = client.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH/P", "locator": "JO31AA", "band": "432MHz", "password": "70cm"}, headers=H).json()
    sid = st["id"]
    assert client.post(f"/api/contests/{cid}/stations", json={"call": "X", "locator": "bad", "band": "432MHz"}, headers=H).status_code == 400

    # Station freischalten
    assert client.post(f"/api/stations/{sid}/unlock", json={"password": "nein"}).status_code == 403
    tok = client.post(f"/api/stations/{sid}/unlock", json={"password": "70cm"}).json()["token"]
    S = {"X-Station-Token": tok, "X-Nick": "Lars"}

    assert client.post(f"/api/stations/{sid}/qsos", json={"call": "DL8NAS", "locator": "JN59LE"}).status_code == 403
    q = client.post(f"/api/stations/{sid}/qsos", json={"call": "DL8NAS", "locator": "JN59LE", "serial_rcvd": "010"}, headers=S).json()
    assert q["points"] == 406 and q["serial_sent"] == 1 and q["logged_by"] == "Lars"
    q2 = client.post(f"/api/stations/{sid}/qsos", json={"call": "OL3Z", "locator": "JN79FX"}, headers=S).json()
    assert q2["serial_sent"] == 2

    sug = client.get("/api/suggest", params={"q": "DL8N", "station": sid}).json()
    assert sug[0]["call"] == "DL8NAS" and sug[0]["km"] == 406
    assert client.get("/api/call", params={"call": "DL8NAS/P"}).json()["locator"] == "JN59LE"
    assert client.get("/api/calc", params={"my": "JO31AA", "loc": "JN59LE"}).json()["km"] == 406

    # Bearbeiten / löschen
    assert client.patch(f"/api/qsos/{q2['id']}", json={"locator": "JN79XX"}, headers=S).json()["locator"] == "JN79XX"
    assert client.delete(f"/api/qsos/{q2['id']}", headers=S).json()["ok"]
    assert len(client.get(f"/api/stations/{sid}/qsos").json()) == 1

    # Seriennummer zurücksetzen
    assert client.post(f"/api/stations/{sid}/serial", json={"start": 1}, headers=S).json()["serial_next"] == 1

    sb = client.get(f"/api/contests/{cid}/scoreboard").json()
    assert sb[0]["points"] == 406
    stats = client.get(f"/api/stations/{sid}/stats").json()
    assert stats["summary"]["qsos"] == 1 and stats["top"][0]["call"] == "DL8NAS"

    # Export
    edi = client.get(f"/api/stations/{sid}/export.edi").text
    assert "PCall=DN2LH/P" in edi and "CQSOP=406" in edi
    assert "DL8NAS" in client.get(f"/api/stations/{sid}/export.adi").text
    assert "DL8NAS" in client.get(f"/api/stations/{sid}/export.csv").text

    # Import als neue Station
    txt = "Version:4.4.052\nN,05.10.24,17:13,DL0GM         ,59  001,59  078,JO31UB, 117,432 MHz,SQWb\n"
    r = client.post("/api/import", files={"file": ("Oktober 2024.txt", txt.encode())}, data={"target": "qsos", "station_id": str(sid)}, headers=H).json()
    assert r["qsos"] == 1
    r = client.post("/api/import", files={"file": ("Oktober 2024.txt", txt.encode())}, data={"target": "qsos", "station_id": str(sid)}, headers=H).json()
    assert r["qsos"] == 0  # Duplikate werden nicht doppelt importiert
    r = client.post("/api/import", files={"file": ("calls.csv", b"PA0ABC;JO22AA\n")}, data={"target": "callbook"}, headers=H).json()
    assert r["callbook"] == 1
    assert "PA0ABC" in client.get("/api/callbook/export.csv").text

    # Chat + WebSocket
    with client.websocket_connect("/ws?nick=Lars") as ws:
        first = ws.receive_json()
        assert first["type"] == "presence" and first["users"][0]["nick"] == "Lars"
        ws.send_json({"type": "chat", "text": "hallo"})
        msg = ws.receive_json()
        assert msg["type"] == "chat" and msg["msg"]["text"] == "hallo"
    assert client.get("/api/chat").json()[-1]["text"] == "hallo"

    assert client.get("/").status_code == 200


def test_summary_backup_rig(client):
    admin = client.post("/api/setup", json={"password": "admin1"}).json()["token"]
    H = {"X-Admin-Token": admin}
    cid = client.post("/api/contests", json={"name": "Multi"}, headers=H).json()["id"]
    s1 = client.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH", "locator": "JO31AA", "band": "144MHz"}, headers=H).json()["id"]
    s2 = client.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH", "locator": "JO31AA", "band": "432MHz"}, headers=H).json()["id"]
    client.post(f"/api/stations/{s1}/qsos", json={"call": "DL8NAS", "locator": "JN59LE"}, headers=H)
    client.post(f"/api/stations/{s2}/qsos", json={"call": "DL8NAS", "locator": "JN59LE", "freq": "432.200"}, headers=H)
    client.post(f"/api/stations/{s2}/qsos", json={"call": "OL3Z", "locator": "JN79FX"}, headers=H)
    sm = client.get(f"/api/contests/{cid}/summary").json()
    assert sm["total_qsos"] == 3 and sm["total_points"] == 406 * 2 + 607
    assert sm["unique_calls"] == 2 and [b["band"] for b in sm["bands"]] == ["144MHz", "432MHz"]
    assert "<FREQ:7>432.200" in client.get(f"/api/stations/{s2}/export.adi").text

    r = client.post(f"/api/stations/{s1}/rig", json={"freq": 144.3, "mode": "USB"}, headers=H).json()
    assert r["freq"] == "144.300"
    sb = {row["id"]: row for row in client.get(f"/api/contests/{cid}/scoreboard").json()}
    assert sb[s1]["rig"]["freq"] == "144.300" and sb[s2]["rig"] is None
    assert client.get(f"/api/stations/{s1}/rig").json()["mode"] == "USB"

    assert client.post("/api/backups").status_code == 403
    name = client.post("/api/backups", headers=H).json()["name"]
    lst = client.get("/api/backups", headers=H).json()
    assert lst["backups"][0]["name"] == name and name.endswith("-manual.db")
    import sqlite3, os
    con = sqlite3.connect(os.path.join(lst["dir"], name))
    assert con.execute("SELECT COUNT(*) FROM qsos").fetchone()[0] == 3
    con.close()
