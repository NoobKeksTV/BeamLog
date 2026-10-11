import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from contestlogger.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
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
    assert name.startswith("beamlog-")
    import sqlite3, os
    con = sqlite3.connect(os.path.join(lst["dir"], name))
    assert con.execute("SELECT COUNT(*) FROM qsos").fetchone()[0] == 3
    con.close()


def test_qr(client):
    r = client.get("/api/qr.svg", params={"text": "http://192.168.1.10:8000/"})
    assert r.status_code == 200 and b"<svg" in r.content


def test_contest_stats(client):
    admin = client.post("/api/setup", json={"password": "admin1"}).json()["token"]
    H = {"X-Admin-Token": admin}
    cid = client.post("/api/contests", json={"name": "G"}, headers=H).json()["id"]
    s1 = client.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH", "locator": "JO31AA", "band": "144MHz"}, headers=H).json()["id"]
    client.post(f"/api/stations/{s1}/qsos", json={"call": "DL8NAS", "locator": "JN59LE"}, headers={**H, "X-Nick": "Lars"})
    st = client.get(f"/api/contests/{cid}/stats").json()
    assert st["total_qsos"] == 1 and st["recent"][0]["own_call"] == "DN2LH" and st["odx"][0]["call"] == "DL8NAS"
    assert st["operators"][0]["nick"] == "Lars" and st["unique_countries"] == 1 and st["per_hour"][0]["band"] == "144MHz"


def test_languages(client, tmp_path):
    langs = client.get("/api/lang").json()
    assert {"code": "de", "name": "Deutsch"} in langs and any(l["code"] == "en" for l in langs)
    en = client.get("/api/lang/en").json()
    assert en["Loggen"] == "Logging" and "_name" not in en
    assert client.get("/api/lang/xx").status_code == 404
    tpl = client.get("/api/lang/template.json").json()
    assert tpl["Loggen"] == "" and "_name" in tpl
    # eigene Sprachdatei neben der Datenbank
    db_dir = client.app.state.db.path.parent
    (db_dir / "lang").mkdir()
    (db_dir / "lang" / "nl.json").write_text('{"_name": "Nederlands", "Loggen": "Loggen NL"}', encoding="utf-8")
    assert any(l["name"] == "Nederlands" for l in client.get("/api/lang").json())
    assert client.get("/api/lang/nl").json()["Loggen"] == "Loggen NL"


def test_seed_and_folder_import(client):
    # Startdatenbank wurde beim ersten Start geladen
    info = client.get("/api/info").json()
    assert info["callbook_count"] >= 100
    assert client.get("/api/callbook", params={"q": "DL8NAS"}).json()["rows"][0]["locator"] == "JN59LE"
    admin = client.post("/api/setup", json={"password": "admin1"}).json()["token"]
    H = {"X-Admin-Token": admin}
    txt = b"Version:4.4.052\nN,05.10.24,17:13,DL0GM         ,59  001,59  078,JO31UB, 117,432 MHz,SQWb\n"
    exp = b"*** Win-Contest V4 Exportdatei *** N\n4.4.053\nDN2LH\nJO31AA\n432MHz\n202410\n05.10.24,17:13,DL0GM,59  001,59  078,JO31UB,117,87,DL0GM,JO31,Deutschland,Null,SSB,x\n"
    r = client.post("/api/import/folder", files=[("files", ("Datenbank/Oktober 2024.txt", txt)), ("files", ("DD3KU/432MHz-05102024-DN2LH.EXP", exp)), ("files", ("Contest.dat", b"\x00\x01"))], headers=H).json()
    assert r["contests"] == 1 and r["qsos"] == 1 and len(r["files"]) == 2
    assert any(c["archived"] for c in client.get("/api/contests").json())
    assert client.delete("/api/callbook/DL0GM", headers=H).json()["ok"]


def test_results_import(client, monkeypatch):
    monkeypatch.setenv("BEAMLOG_MAINTAINER", "1")  # Quellen-Importe nur im Betreuer-Modus
    admin = client.post("/api/setup", json={"password": "admin1"}).json()["token"]
    H = {"X-Admin-Token": admin}
    html = b"<table><tr><td>1</td><td>DL0GM</td><td>JO31UB</td><td>312</td></tr><tr><td>2</td><td>OK9ZZZ</td><td>JN79FX</td><td>5</td></tr></table>"
    r = client.post("/api/import/results", files={"file": ("ergebnis.html", html)}, data={"commit": "0"}, headers=H).json()
    assert r["count"] == 2 and {p["call"] for p in r["pairs"]} == {"DL0GM", "OK9ZZZ"}
    assert next(p for p in r["pairs"] if p["call"] == "DL0GM")["status"] == "gleich"  # aus Startdatenbank bekannt
    r = client.post("/api/import/results", data={"text": "OK9ZZZ JN79FX 5", "commit": "1", "selected": "OK9ZZZ"}, headers=H).json()
    assert r["imported"] == 1
    assert client.get("/api/callbook", params={"q": "OK9ZZZ"}).json()["rows"][0]["locator"] == "JN79FX"
    assert client.post("/api/import/results", data={"commit": "0"}, headers=H).status_code == 400


def test_audit_log(tmp_path):
    from contestlogger.app import create_app
    from fastapi.testclient import TestClient
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
        H = {"X-Admin-Token": admin, "X-Nick": "Lars"}
        cid = c.post("/api/contests", json={"name": "T"}, headers=H).json()["id"]
        sid = c.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH", "locator": "JO31AA", "band": "432MHz", "kst_pass": "geheim"}, headers=H).json()["id"]
        c.post(f"/api/stations/{sid}/qsos", json={"call": "DL8NAS", "locator": "JN59LE"}, headers=H)
        assert c.post("/api/admin/login", json={"password": "falsch"}).status_code == 403
        assert c.get("/api/audit").status_code == 403  # nur Admin
        rows = c.get("/api/audit", headers=H).json()
        actions = [r["action"] for r in rows]
        assert "Server gestartet" in actions and "Admin-Passwort festgelegt (Ersteinrichtung)" in actions
        st = next(r for r in rows if r["action"].startswith("Station in Contest"))
        assert st["nick"] == "Lars" and st["admin"] == 1 and "***" in st["details"] and "geheim" not in st["details"]
        qso = next(r for r in rows if r["action"].startswith("QSO geloggt"))
        assert "DL8NAS" in qso["details"]
        fail = next(r for r in rows if r["action"] == "Admin-Anmeldung")
        assert fail["status"] == 403 and fail["admin"] == 0
        assert c.get("/api/audit", headers=H, params={"q": "DL8NAS"}).json()[0]["action"].startswith("QSO geloggt")
        assert "QSO geloggt" in c.get("/api/audit.txt", headers=H).text


def test_templates_and_callbook_repo(tmp_path):
    from contestlogger.app import create_app
    from fastapi.testclient import TestClient
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
        H = {"X-Admin-Token": admin}
        # globale Stationen anlegen, Contest mit Auswahl erzeugen
        t1 = c.post("/api/templates", json={"call": "DN2LH/P", "locator": "JO31AA", "band": "432MHz", "password": "70cm", "kst_user": "DN2LH", "kst_pass": "x", "info": {"club": "G13"}}, headers=H).json()
        t2 = c.post("/api/templates", json={"call": "DN2LH", "locator": "JO31AA", "band": "144MHz"}, headers=H).json()
        assert t1["has_password"] and t1["kst_user"] == "DN2LH" and "kst_pass" not in t1 and "password_hash" not in t1
        assert c.post("/api/templates", json={"call": "X", "locator": "ZZ99", "band": "144MHz"}, headers=H).status_code == 400
        assert len(c.get("/api/templates", headers=H).json()) == 2
        contest = c.post("/api/contests", json={"name": "Mai", "template_ids": [t1["id"], t2["id"]]}, headers=H).json()
        cl = c.get("/api/contests").json()[0]
        assert {(s["call"], s["band"]) for s in cl["stations"]} == {("DN2LH/P", "432MHz"), ("DN2LH", "144MHz")}
        s432 = next(s for s in cl["stations"] if s["band"] == "432MHz")
        assert s432["has_password"] and s432["kst_user"] == "DN2LH" and s432["info"]["club"] == "G13"
        assert c.post(f"/api/stations/{s432['id']}/unlock", json={"password": "70cm"}).status_code == 200  # Passwort übernommen
        # Station nachträglich aufnehmen, Vorlage ändern/löschen ohne Auswirkung auf Contest-Station
        c.patch(f"/api/templates/{t2['id']}", json={"locator": "JO31AB"}, headers=H)
        s2 = c.post(f"/api/contests/{contest['id']}/stations/from_template", json={"template_id": t2["id"]}, headers=H).json()
        assert s2["locator"] == "JO31AB"
        c.delete(f"/api/templates/{t2['id']}", headers=H)
        assert len(c.get("/api/contests").json()[0]["stations"]) == 3
        # Stationsdatenbank: Repo-Format exportieren und aus einer (lokalen) Repo-Datei abgleichen
        seed = c.get("/api/callbook/export_seed.csv").text
        assert seed.startswith("Call;Locator;Zuletzt;DOK\n") and "DA2C;JO30XF" in seed
        repo = tmp_path / "repo.csv"
        repo.write_text("Call;Locator;Zuletzt\nDA2C;JO30XF;2025-05-04\nOK9NEW;JN79XX;2026-01-01\n", encoding="utf-8")
        r = c.post("/api/callbook/sync_repo", json={"url": repo.as_uri()}, headers=H).json()
        assert r["total"] == 2 and r["new"] == 1 and r["known"] == 1
        assert c.get("/api/callbook", params={"q": "OK9NEW"}).json()["rows"][0]["locator"] == "JN79XX"
        assert c.post("/api/callbook/sync_repo", json={"url": "http://127.0.0.1:1/nix"}, headers=H).status_code == 502


def test_migration_creates_templates_from_stations(tmp_path):
    """Bestehende Datenbank: vorhandene Contest-Stationen werden beim Start als globale Stationen übernommen."""
    from contestlogger.db import Database
    db = Database(tmp_path / "t.db")
    cid = db.create_contest("Alt", None, None)
    db.create_station(cid, "DN2LH/P", "JO31AA", "432MHz", "SSB", "pw")
    db.create_station(cid, "DN2LH/P", "JO31AA", "144MHz", "SSB", "")
    with db.conn:
        db.conn.execute("DELETE FROM settings WHERE key='templates_migrated'")  # wie eine Datenbank aus einer Version ohne globale Stationen
    db.close()
    db2 = Database(tmp_path / "t.db")
    tpl = db2.list_templates()
    assert {(x["call"], x["band"]) for x in tpl} == {("DN2LH/P", "432MHz"), ("DN2LH/P", "144MHz")}
    db2.close()


def test_contest_exchange_api(client):
    admin = client.post("/api/setup", json={"password": "admin1"}).json()["token"]
    H = {"X-Admin-Token": admin}
    cid = client.post("/api/contests", json={"name": "KAC", "exchange": "dok"}, headers=H).json()["id"]
    assert client.get("/api/contests").json()[0]["exchange"] == "dok"
    client.patch(f"/api/contests/{cid}", json={"exchange": "serial_dok"}, headers=H)
    assert client.get("/api/contests").json()[0]["exchange"] == "serial_dok"
    client.patch(f"/api/contests/{cid}", json={"exchange": "nonsense"}, headers=H)
    assert client.get("/api/contests").json()[0]["exchange"] == "serial"
    sid = client.post(f"/api/contests/{cid}/stations", json={"call": "DN2LH", "locator": "JO31AA", "band": "432MHz"}, headers=H).json()["id"]
    q = client.post(f"/api/stations/{sid}/qsos", json={"call": "DL8NAS", "locator": "JN59LE", "serial_rcvd": "010", "exch_rcvd": "b21"}, headers=H).json()
    assert q["exch_rcvd"] == "B21"
    assert client.get(f"/api/stations/{sid}/qsos?q=B21").json()[0]["call"] == "DL8NAS"
    # Callbuch: DOK anzeigen, bearbeiten, exportieren, Repo-Format
    assert client.get("/api/callbook?q=B21").json()["rows"][0]["call"] == "DL8NAS"
    client.post("/api/callbook", json={"call": "DL8NAS", "locator": "JN59LE", "dok": "b22"}, headers=H)
    assert client.get("/api/callbook?q=DL8NAS").json()["rows"][0]["dok"] == "B22"
    assert "DL8NAS;JN59LE;2" in client.get("/api/callbook/export_seed.csv").text.replace("\r", "") and ";B22\n" in client.get("/api/callbook/export_seed.csv").text
    assert ";B22;" in client.get("/api/callbook/export.csv").text
    # Log-Prüfung warnt bei fehlendem DOK
    client.patch(f"/api/contests/{cid}", json={"exchange": "dok"}, headers=H)
    client.post(f"/api/stations/{sid}/qsos", json={"call": "OL3Z", "locator": "JN79FX"}, headers=H)
    chk = client.get(f"/api/stations/{sid}/check", headers=H).json()
    assert any("DOK" in w["msg"] for w in chk["warnings"])


def test_maintainer_gate_and_list_import(tmp_path, monkeypatch):
    monkeypatch.delenv("BEAMLOG_MAINTAINER", raising=False)
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
        H = {"X-Admin-Token": admin}
        assert c.get("/api/info").json()["maintainer"] is False
        assert c.get("/api/darc/contests?year=2025", headers=H).status_code == 403
        assert c.post("/api/import/results", data={"text": "DL1ABC JO31AA"}, headers=H).status_code == 403
        csv_ = "Call;Locator;Name;DOK;QSOs;Zuletzt;Weitere Locator\nDL9XYZ;JO31XX;Peter;G20;3;2026-05-03;\nOE5XX;JN68AA;;;1;;\n"
        assert c.post("/api/callbook/import_list", files={"file": ("liste.csv", csv_)}, headers=H).status_code == 403
        monkeypatch.setenv("BEAMLOG_MAINTAINER", "1")
        assert c.get("/api/info").json()["maintainer"] is True
        r = c.post("/api/callbook/import_list", files={"file": ("liste.csv", csv_)}, headers=H).json()
        assert r["total"] == 2 and r["new"] == 2
        row = c.get("/api/callbook?q=DL9XYZ").json()["rows"][0]
        assert row["dok"] == "G20" and row["name"] == "Peter" and row["last_seen"].startswith("2026-05-03")
        # Stationsdatenbank-Export lässt sich wieder einlesen (Rundlauf)
        exp = c.get("/api/callbook/export.csv").text
        r = c.post("/api/callbook/import_list", files={"file": ("liste.csv", exp)}, headers=H).json()
        assert r["new"] == 0 and r["known"] >= 2


def test_tile_cache(client, tmp_path, monkeypatch):
    from contestlogger import tiles
    admin = client.post("/api/setup", json={"password": "admin1"}).json()["token"]
    H = {"X-Admin-Token": admin}
    png = b"\x89PNG fake"
    monkeypatch.setattr(tiles.urllib.request, "urlopen", lambda req, timeout=0: type("R", (), {"read": lambda self: png, "__enter__": lambda self: self, "__exit__": lambda self, *a: None})())
    assert client.get("/api/info").json()["tile_cache"] is False
    r = client.get("/tiles/5/16/10.png")
    assert r.status_code == 200 and r.content == png
    st = client.get("/api/tiles/status", headers=H).json()
    assert st["tiles"] == 1 and st["job"]["running"] is False
    assert client.post("/api/tiles/prefetch", json={"locator": "JO31AA", "radius_km": 5000, "zmin": 4, "zmax": 10}, headers=H).status_code == 400  # zu viele
    r = client.post("/api/tiles/prefetch", json={"locator": "JO31AA", "radius_km": 100, "zmin": 4, "zmax": 6}, headers=H).json()
    assert r["total"] >= 3
    import time
    for _ in range(50):
        st = client.get("/api/tiles/status", headers=H).json()
        if not st["job"]["running"]:
            break
        time.sleep(0.1)
    assert st["job"]["done"] == r["total"] and st["tiles"] >= r["total"]
    client.post("/api/settings", json={"tile_cache": "1"}, headers=H)
    assert client.get("/api/info").json()["tile_cache"] is True
    assert client.delete("/api/tiles", headers=H).json()["deleted"] >= r["total"]
    assert len(tiles.region_tiles(51, 7, 100, 5, 5)) >= 1 and tiles.latlon_to_tile(0, 0, 1) == (1, 1)
    # gesperrte Kachel (OSM: HTTP 200 + x-blocked) wird nicht gespeichert
    blocked = type("R", (), {"read": lambda self: png, "headers": {"x-blocked": "1", "Content-Type": "image/png"}, "__enter__": lambda self: self, "__exit__": lambda self, *a: None})
    monkeypatch.setattr(tiles.urllib.request, "urlopen", lambda req, timeout=0: blocked())
    assert client.get("/tiles/6/33/21.png").status_code == 502
    assert client.get("/api/tiles/status", headers=H).json()["tiles"] == 0
    assert tiles.UA.startswith("BeamLog/")


def test_calc_accepts_alternative_locators(client):
    admin = client.post("/api/setup", json={"password": "admin1"}).json()["token"]
    H = {"X-Admin-Token": admin}
    client.post("/api/callbook", json={"call": "9A1CRS", "locator": "JN95AE"}, headers=H)
    client.post("/api/callbook", json={"call": "9A1CRS", "locator": "JN85OD"}, headers=H)  # zweiter Standort
    cb = client.get("/api/callbook?q=9A1CRS").json()["rows"][0]
    locs = {cb["locator"], *[x for x in cb["alt_locators"].split(",") if x]}
    assert locs == {"JN95AE", "JN85OD"}
    for loc in ("JN95AE", "JN85OD", "JN95"):
        w = client.get("/api/calc", params={"my": "JO31AA", "loc": loc, "call": "9A1CRS"}).json()["warnings"]
        assert not any("Stationsdatenbank" in x for x in w), (loc, w)
    w = client.get("/api/calc", params={"my": "JO31AA", "loc": "JN75AA", "call": "9A1CRS"}).json()["warnings"]
    assert any("Stationsdatenbank kennt 9A1CRS mit" in x and "JN95AE" in x and "JN85OD" in x and "–" not in x for x in w), w
