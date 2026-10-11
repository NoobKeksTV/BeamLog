import os
import tempfile

import pytest

from contestlogger import geo, prefixes
from contestlogger.db import Database


def test_locator_distance_matches_wincontest():
    # Werte aus dem DD3KU-Log DN2LH (JO31AA)
    assert geo.distance_km_int("JO31AA", "JN59LE") == 406
    assert geo.distance_km_int("JO31AA", "JN79FX") == 607
    assert geo.distance_km_int("JO31AA", "JO01QD") == 327
    assert geo.distance_km_int("JO31AA", "JO31LE") == 67


def test_bearing():
    b = geo.bearing_deg("JO31AA", "JN59LE")
    assert 110 <= b <= 125  # WinContest: 118


def test_invalid_locator():
    assert not geo.is_valid_locator("JO3")
    assert not geo.is_valid_locator("ZZ99")
    assert geo.is_valid_locator("jo31aa")


def test_prefixes():
    assert prefixes.core_call("DL1ABC/P") == "DL1ABC"
    assert prefixes.core_call("DN2LH-2") == "DN2LH" and prefixes.core_call("DN2LH/P-3") == "DN2LH" and prefixes.core_call("OJ7F-23CM") == "OJ7F"
    assert prefixes.core_call("OE/DL1ABC") == "DL1ABC"
    assert prefixes.country("OE/DL1ABC") == "Österreich"
    assert prefixes.country("M1CRO/P") == "England"
    assert prefixes.country("OL3Z") == "Tschechien"
    assert prefixes.country("DN2LH") == "Deutschland"
    assert prefixes.country("HB0ABC") == "Liechtenstein"


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "t.db")
    yield database
    database.close()


def test_log_flow(db):
    cid = db.create_contest("Test", "2026-05-02T14:00:00Z", "2026-05-03T14:00:00Z")
    sid = db.create_station(cid, "DN2LH/P", "JO31AA", "432MHz", "SSB", "geheim")
    assert db.check_station_password(sid, "geheim")
    assert not db.check_station_password(sid, "falsch")

    q1 = db.add_qso(sid, {"call": "DL8NAS", "locator": "JN59LE", "serial_rcvd": "010"}, "lars")
    assert q1["serial_sent"] == 1 and q1["points"] == 406 and q1["dupe"] == 0
    q2 = db.add_qso(sid, {"call": "DL8NAS/P", "locator": "JN59LE"}, "lars")
    assert q2["serial_sent"] == 2 and q2["dupe"] == 1 and q2["points"] == 0
    assert db.get_station(sid)["serial_next"] == 3

    # Bearbeiten: Dupe wird neu bewertet
    db.update_qso(q2["id"], {"call": "OL3Z", "locator": "JN79FX"})
    q2 = db.get_qso(q2["id"])
    assert q2["dupe"] == 0 and q2["points"] == 607

    s = db.station_summary(sid)
    assert s["qsos"] == 2 and s["points"] == 1013 and s["squares"] == 2

    # Vorschläge aus Call-Buch
    sug = db.suggest("DL8", station_id=sid)
    assert sug and sug[0]["call"] == "DL8NAS" and sug[0]["locator"] == "JN59LE"
    assert sug[0]["worked_here"] is not None

    db.delete_qso(q1["id"])
    assert db.station_summary(sid)["qsos"] == 1

    db.reset_serial(sid, 1)
    assert db.get_station(sid)["serial_next"] == 1


def test_bad_call(db):
    cid = db.create_contest("Test", None, None)
    sid = db.create_station(cid, "DN2LH", "JO31AA", "432MHz", "SSB", "")
    with pytest.raises(ValueError):
        db.add_qso(sid, {"call": "ABC"})


def test_backups_old_and_new_names(tmp_path):
    db = Database(tmp_path / "beamlog.db")
    b = db.backup_dir; b.mkdir()
    (b / "contestlogger-20261001-120000-manual.db").write_text("alt")  # Sicherung aus 0.9
    new = db.create_backup("manual")
    names = [x["name"] for x in db.list_backups()]
    assert names[0] == new.name and new.name.startswith("beamlog-") and "contestlogger-20261001-120000-manual.db" in names
    for i in range(55):  # Aufräumen erfasst alte und neue Namen gemeinsam
        (b / f"beamlog-20261002-{i:06d}-manual.db").write_text("x")
    db.prune_backups()
    assert len(db.list_backups()) == 50 and not (b / "contestlogger-20261001-120000-manual.db").exists()
