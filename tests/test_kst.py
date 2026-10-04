import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from contestlogger import importers, kst
from contestlogger.app import create_app
from tests.fake_kst import FakeKst

FIX = Path(__file__).parent / "fixtures"


def test_parsers():
    m = kst.parse_message("0846Z OZ5QF Jens 2m> (F6IFX/P)  Tnx qso Bert. Best 340/5 73")
    assert m == {"time": "08:46", "call": "OZ5QF", "name": "Jens 2m", "to": "F6IFX/P", "text": "Tnx qso Bert. Best 340/5 73"}
    assert kst.parse_message("1200Z DN2LH 144/432 MHz chat>") is None
    assert kst.parse_message("1200Z DL1ABC Hans &amp; Co> hi &amp; 73")["text"] == "hi & 73"
    assert kst.parse_user("VU2CPL           MK83TE Manoj") == {"call": "VU2CPL", "locator": "MK83TE", "name": "Manoj", "away": False}
    assert kst.parse_user("(DF7KF)          JO30XX Peter")["away"] is True
    assert kst.parse_user("Please wait 55 second(s) between two commands.") is None


def test_darc_parsers():
    r = importers.parse_darc_csv((FIX / "darc_result.csv").read_text(encoding="latin-1"))
    calls = {c for c, _, _ in r.callbook}
    assert "DR1H" in calls and "IK7FPU" in calls and ("DR1H", "JN59OP", "") in r.callbook  # Teilnehmer + ODX-Gegenstation
    assert all(len(loc) == 6 for _, loc, _ in r.callbook)
    idx = importers.parse_darc_index((FIX / "darc_index.html").read_text(), 2024)
    assert len(idx) == 10 and idx[0]["id"] == "2024-02" and idx[0]["name"] == "DARC UKW-Winter-Fieldday"
    assert idx[3]["csv"].endswith("/2024/2024-05/result/result.csv") and idx[3]["status"] == "Endergebnis"


def test_client_against_fake_server(monkeypatch):
    asyncio.run(_client_against_fake_server(monkeypatch))


async def _client_against_fake_server(monkeypatch):
    fake = FakeKst()
    await fake.start()
    monkeypatch.setattr(kst, "HOST", "127.0.0.1")
    monkeypatch.setattr(kst, "PORT", fake.port)
    events = []

    async def on_event(ev):
        events.append(ev)
    c = kst.KstClient("DN2LH", "secret", 2, on_event, my_calls=["DN2LH/P", "DL0ABC"])
    c._last_cmd = 0
    c.start()
    for _ in range(100):
        await asyncio.sleep(0.05)
        if c.users:
            break
    assert c.state == "verbunden" and "DL8NAS" in c.users and c.users["DF7KF"]["away"]
    await fake.push("1203Z DL8NAS Klaus> (DN2LH/P)  hi Lars, qrv 70cm?")
    await fake.push("1203Z OK1ABC Pepa> cq all")
    await fake.push("1203Z DF7KF Peter> dn2lh/p pse qsy 432.200")  # Call im Text, andere Schreibweise -> an mich
    await fake.push("1203Z DF7KF Peter> (DL0ABC-2)  hi")  # Zusatz-Call aus der Liste mit KST-Anhängsel -> an mich
    await c.send_text("/CQ DL8NAS yes, calling now")
    await asyncio.sleep(0.3)
    msgs = [e["msg"] for e in events if e["type"] == "kst"]
    assert msgs[0]["to_me"] and msgs[0]["locator"] == "JN59LE"
    assert not msgs[1]["to_me"]
    assert msgs[2]["to_me"] and msgs[3]["to_me"] and msgs[3]["to"] == "DL0ABC"
    assert msgs[4]["own"] and msgs[4]["to"] == "DL8NAS" and not msgs[4]["to_me"]
    assert "/CQ DL8NAS yes, calling now" in fake.received
    # Internetausfall: Verbindung bricht weg -> Client verbindet sich von selbst neu und holt die Nutzerliste erneut
    c.RECONNECT_WAIT = 0.2
    n_logins = fake.received.count("/SHOW USER")
    await fake.drop_all()
    for _ in range(100):
        await asyncio.sleep(0.05)
        if c.state == "verbunden" and fake.received.count("/SHOW USER") > n_logins:
            break
    assert c.state == "verbunden" and fake.received.count("/SHOW USER") > n_logins
    assert any(e["type"] == "kst_status" and e["state"] == "getrennt" for e in events)
    await c.stop()
    await fake.stop()


def test_kst_endpoints(tmp_path, monkeypatch):
    loop = asyncio.new_event_loop()
    fake = FakeKst()
    loop.run_until_complete(fake.start())
    import threading
    th = threading.Thread(target=loop.run_forever, daemon=True)
    th.start()
    monkeypatch.setattr(kst, "HOST", "127.0.0.1")
    monkeypatch.setattr(kst, "PORT", fake.port)
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
        H = {"X-Admin-Token": admin}
        cid = c.post("/api/contests", json={"name": "T"}, headers=H).json()["id"]
        sid = c.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH/P", "locator": "JO31AA", "band": "432MHz"}, headers=H).json()["id"]
        sid2 = c.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH", "locator": "JO31AA", "band": "144MHz"}, headers=H).json()["id"]
        assert c.post("/api/kst/start", json={"station_id": sid}, headers=H).status_code == 400  # nicht konfiguriert
        st = c.patch(f"/api/stations/{sid}", json={"kst_user": "DN2LH", "kst_pass": "secret", "kst_room": 2, "kst_my_calls": "DN2LH, DN2LH/P"}, headers=H).json()
        assert st["kst_user"] == "DN2LH" and st["kst_pass_set"] and "kst_pass" not in st
        assert "kst_pass" not in c.get("/api/contests").json()[0]["stations"][0]
        st = c.post("/api/kst/start", json={"station_id": sid}, headers=H).json()
        import time
        for _ in range(60):
            time.sleep(0.05)
            st = c.get("/api/kst/status", params={"station_id": sid}).json()
            if st["state"] == "verbunden" and st["users"]:
                break
        assert st["state"] == "verbunden" and st["users"] == 5 and st["macros"]  # DN2LH-2 wird als DN2LH geführt
        assert c.get("/api/kst/status", params={"station_id": sid2}).json()["state"] == "aus"  # andere Station: eigene Verbindung
        assert c.get("/api/callbook", params={"q": "VU2CPL"}).json()["rows"][0]["locator"] == "MK83TE"  # aus Nutzerliste gelernt
        users = c.get("/api/kst/users", params={"station_id": sid, "my": "JO31AA"}).json()
        assert next(u for u in users if u["call"] == "DL8NAS")["km"] == 406 and users[0]["km"] <= users[-1]["km"]
        assert c.post("/api/kst/send", json={"text": "/CQ DL8NAS hallo", "station_id": sid}).json()["ok"]
        assert c.post("/api/kst/send", json={"text": "hallo", "station_id": sid2}).status_code == 409
        time.sleep(0.3)
        msgs = c.get("/api/kst/messages", params={"station_id": sid}).json()
        assert msgs and msgs[-1]["own"] and msgs[-1]["to"] == "DL8NAS"
        assert c.get("/api/kst/messages", params={"station_id": sid2}).json() == []
        c.post("/api/settings", json={"kst_macros": [{"label": "X", "text": "hi all"}]}, headers=H)
        assert c.get("/api/kst/status", params={"station_id": sid}).json()["macros"][0]["label"] == "X"
        assert c.post("/api/kst/stop", json={"station_id": sid}, headers=H).json()["state"] == "aus"
        assert c.get("/api/kst/status", params={"station_id": sid}).json()["state"] == "aus"
    loop.call_soon_threadsafe(loop.stop)


def test_candidates_and_broadcast(tmp_path, monkeypatch):
    loop = asyncio.new_event_loop()
    fake = FakeKst()
    loop.run_until_complete(fake.start())
    import threading, time
    threading.Thread(target=loop.run_forever, daemon=True).start()
    monkeypatch.setattr(kst, "HOST", "127.0.0.1")
    monkeypatch.setattr(kst, "PORT", fake.port)
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
        H = {"X-Admin-Token": admin}
        cid = c.post("/api/contests", json={"name": "T"}, headers=H).json()["id"]
        sid = c.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH", "locator": "JO31AA", "band": "432MHz"}, headers=H).json()["id"]
        c.post(f"/api/stations/{sid}/qsos", json={"call": "DL8NAS", "locator": "JN59LE"}, headers=H)  # schon gearbeitet
        c.patch(f"/api/stations/{sid}", json={"kst_user": "DN2LH", "kst_pass": "secret", "kst_room": 2}, headers=H)
        c.post("/api/kst/start", json={"station_id": sid}, headers=H)
        for _ in range(60):
            time.sleep(0.05)
            if c.get("/api/kst/status", params={"station_id": sid}).json().get("users"):
                break
        cand = c.get("/api/kst/candidates", params={"station_id": sid, "max_km": 500}).json()
        assert [u["call"] for u in cand] == []  # DF7KF ist abwesend, DL8NAS gearbeitet, VU2CPL zu weit, DN2LH(-2) bin ich selbst
        cand = c.get("/api/kst/candidates", params={"station_id": sid, "max_km": 500, "include_away": 1}).json()
        assert [u["call"] for u in cand] == ["DF7KF"] and cand[0]["km"] == 135  # ON4KST (Server) nie dabei
        assert c.post("/api/kst/rundruf_texts", json={"texts": ["GA {name}, QRV?", " "]}).json() == ["GA {name}, QRV?"]
        assert c.get("/api/kst/rundruf_texts").json() == ["GA {name}, QRV?"]
        r = c.post("/api/kst/broadcast", json={"calls": ["DF7KF", "VU2CPL"], "text": "GA {name}, QRV {band}? loc {myloc}", "station_id": sid}).json()
        assert r["queued"] == 2
        time.sleep(0.5)
        assert any(x == "/CQ DF7KF GA Peter, QRV 432 MHz? loc JO31AA" for x in fake.received)
        c.post("/api/kst/stop", headers=H)
    loop.call_soon_threadsafe(loop.stop)


def test_kst_history_not_duplicated(tmp_path, monkeypatch):
    """Der KST-Server schickt nach dem Neuverbinden den Verlauf erneut – Nachrichten dürfen nicht doppelt gespeichert werden."""
    loop = asyncio.new_event_loop()
    fake = FakeKst()
    loop.run_until_complete(fake.start())
    import threading, time
    threading.Thread(target=loop.run_forever, daemon=True).start()
    monkeypatch.setattr(kst, "HOST", "127.0.0.1")
    monkeypatch.setattr(kst, "PORT", fake.port)
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
        H = {"X-Admin-Token": admin}
        cid = c.post("/api/contests", json={"name": "T"}, headers=H).json()["id"]
        sid = c.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH", "locator": "JO31AA", "band": "432MHz", "kst_user": "DN2LH", "kst_pass": "secret"}, headers=H).json()["id"]
        c.post("/api/kst/start", json={"station_id": sid}, headers=H)
        for _ in range(60):
            time.sleep(0.05)
            if c.get("/api/kst/status", params={"station_id": sid}).json().get("state") == "verbunden":
                break
        for _ in range(3):  # dieselbe Nachricht dreimal (wie ein wiederholter Verlauf)
            asyncio.run_coroutine_threadsafe(fake.push("1203Z DL8NAS Klaus> (DN2LH)  hi Lars"), loop).result()
        time.sleep(0.5)
        msgs = c.get("/api/kst/messages", params={"station_id": sid}).json()
        assert len([m for m in msgs if m["text"] == "hi Lars"]) == 1
        c.post("/api/kst/stop", json={"station_id": sid}, headers=H)
    loop.call_soon_threadsafe(loop.stop)
