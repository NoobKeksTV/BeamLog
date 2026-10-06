import os
import tempfile

from contestlogger import exporters, importers
from contestlogger.db import Database

TXT = """Version:4.4.053
N,03.05.25,14:12,DL8NAS        ,59  001,59  010,JN59LE, 406,432 MHz,vr2S
N,03.05.25,14:15,OL3Z          ,59  002,59  021,JN79FX, 607,432 MHz,2UvB
"""

EXP = """*** Win-Contest V4 Exportdatei *** N
4.4.053
DN2LH
JO31AA
432MHz
202505
03.05.25,14:12,DL8NAS,59  001,59  010,JN59LE,406,118,DL8NAS,JN59,Deutschland,Null,SSB,NQSN
"""

EDI = """[REG1TEST;1]
TName=Test
PCall=DN2LH/P
PWWLo=JO31AA
PBand=435 MHz
[QSORecords;1]
250503;1412;DL8NAS;1;59;001;59;010;;JN59LE;406;;;;
"""

ADI = """hdr
<eoh>
<call:6>DL8NAS<qso_date:8:d>20250503<time_on:4>1412<mode:3>SSB<RST_RCVD:2>59<RST_SENT:2>59<GRIDSQUARE:6>JN59LE<STX:3>001<SRX:3>010<FREQ:3>432<BAND:4>70cm<eor>
"""


def test_parsers_detect_and_parse():
    for name, content in (("a.txt", TXT), ("a.EXP", EXP), ("a.edi", EDI), ("a.adi", ADI)):
        r = importers.parse_file(name, content.encode("latin-1"))
        assert r.qsos, name
        q = r.qsos[0]
        assert q.call == "DL8NAS" and q.locator == "JN59LE" and q.serial_sent == 1 and q.serial_rcvd == "010"
        assert q.ts_utc == "2025-05-03T14:12:00Z"
        assert q.band == "432MHz", (name, q.band)
    r = importers.parse_file("a.EXP", EXP.encode())
    assert r.header["call"] == "DN2LH" and r.header["locator"] == "JO31AA"


def test_callbook_csv():
    r = importers.parse_file("calls.csv", b"DL8NAS;JN59LE;Klaus\nOL3Z JN79FX\nfoo;bar\n")
    assert [c[0] for c in r.callbook] == ["DL8NAS", "OL3Z"]
    assert r.warnings


def test_export_roundtrip(tmp_path):
    if True:
        db = Database(tmp_path / "t.db")
        cid = db.create_contest("DARC 70cm", None, None)
        sid = db.create_station(cid, "DN2LH/P", "JO31AA", "432MHz", "SSB", "", {"section": "Single"})
        for q in importers.parse_dd3ku_txt(TXT).qsos:
            db.add_qso(sid, q.__dict__, "import")
        contest, station, qsos = db.get_contest(cid), db.get_station(sid), db.list_qsos(sid)
        edi = exporters.export_edi(contest, station, qsos)
        assert "CQSOs=2;1" in edi and "CQSOP=1013" in edi and "CODXC=OL3Z;JN79FX;607" in edi
        assert "250503;1412;DL8NAS;1;59;001;59;010;;JN59LE;406;;;;" in edi
        back = importers.parse_edi(edi)
        assert len(back.qsos) == 2 and back.header["call"] == "DN2LH/P"
        adif = exporters.export_adif(contest, station, qsos)
        assert len(importers.parse_adif(adif).qsos) == 2
        csv_ = exporters.export_csv(contest, station, qsos)
        assert "DL8NAS" in csv_


def test_mdb_pure_python():
    from pathlib import Path
    data = (Path(__file__).parent / "fixtures" / "wincontest.mdb").read_bytes()
    r = importers.parse_file("Oktober 2024.mdb", data)
    assert r.kind == "mdb" and len(r.qsos) == 11 and not r.warnings
    assert r.header == {"call": "DN2LH", "locator": "JO31AA", "band": "432MHz"}
    q = r.qsos[0]
    assert (q.call, q.locator, q.serial_sent, q.serial_rcvd, q.ts_utc) == ("DL0GM", "JO31UB", 1, "078", "2024-10-05T17:13:00Z")


def test_dok_exchange_roundtrip(tmp_path):
    """Contest mit DOK-Austausch (z. B. Köln-Aachen): DOK wird geloggt, exportiert, importiert und ins Callbuch übernommen."""
    db = Database(tmp_path / "t.db")
    cid = db.create_contest("Köln-Aachen", None, None, exchange="dok")
    assert db.get_contest(cid)["exchange"] == "dok"
    sid = db.create_station(cid, "DN2LH", "JO31AA", "432MHz", "SSB", "", {"exchange": "G01"})
    q = db.add_qso(sid, {"call": "DL8NAS", "locator": "JN59LE", "exch_rcvd": " b 21 ", "ts_utc": "2025-05-03T14:12:00Z"})
    assert q["exch_rcvd"] == "B21"
    assert db.lookup_call("DL8NAS")["dok"] == "B21"
    q = db.update_qso(q["id"], {"exch_rcvd": "b22"})
    assert q["exch_rcvd"] == "B22" and db.lookup_call("DL8NAS")["dok"] == "B22"
    assert db.station_summary(sid)["exchanges"] == 1
    contest, station, qsos = db.get_contest(cid), db.get_station(sid), db.list_qsos(sid)
    edi = exporters.export_edi(contest, station, qsos)
    assert "PExch=G01" in edi and "CExcs=1;0;1" in edi and ";59;001;59;;B22;JN59LE;" in edi
    assert importers.parse_edi(edi).qsos[0].exch_rcvd == "B22"
    adif = exporters.export_adif(contest, station, qsos)
    assert "<DARC_DOK:3>B22" in adif and "<STX_STRING:3>G01" in adif
    assert importers.parse_adif(adif).qsos[0].exch_rcvd == "B22"
    assert ";B22;" in exporters.export_csv(contest, station, qsos)
    # Callbook-Listen mit DOK: Kopfzeile oder strenges Muster, Repo-Format
    r = importers.parse_callbook_csv("Call;Locator;Zuletzt;DOK\nDL8NAS;JN59LE;2025-05-03;B21\nOL3Z;JN79FX;2025-05-03;\n")
    assert r.doks == {"DL8NAS": "B21"} and r.callbook[0][2] == "2025-05-03"
    r = importers.parse_callbook_csv("DK0FY JN49KT G01\nDG1E;JO31LE;Peter\n")
    assert r.doks == {"DK0FY": "G01"} and r.callbook[1][2] == "Peter"
    r = importers.parse_darc_csv("Rufzeichen (Basis);Locator;DOK;ODX Call;ODX Locator\nDL1ABC;JO31AA;G20;OK1KKW;JN79XX\n")
    assert r.doks == {"DL1ABC": "G20"} and len(r.callbook) == 2
    r = importers.parse_results_list("1. DL1ABC  G20  JO31AA  120 QSO\n")
    assert r.doks == {"DL1ABC": "G20"}
    db.learn_call("DK0FY", "JN49KT", source="import", dok="G01")
    assert db.lookup_call("DK0FY")["dok"] == "G01"
    assert db.suggest("DK0F")[0]["dok"] == "G01"


def test_scoring_and_cabrillo(tmp_path):
    """Wertung mit Multiplikator (Punkte × DOKs), Neuberechnung bei Wertungswechsel, Cabrillo-Export."""
    from contestlogger import scoring
    assert scoring.parse("km*squares")["mult"] == "squares" and scoring.normalize("Unsinn") == "km" and scoring.parse("fix2*doks")["fixed"] == 2
    assert scoring.qso_points("fix3", 500, "JN59LE") == 3 and scoring.qso_points("km", 0, "JN59") == 1 and scoring.qso_points("km", 406, "JN59LE", dupe=True) == 0
    assert scoring.total("km", 1000, 5, 2) == {"score": 1000, "multiplier": None} and scoring.total("fix1*squares_doks", 10, 5, 2)["score"] == 70
    db = Database(tmp_path / "t.db")
    cid = db.create_contest("KAC", None, None, scoring="fix1*doks", exchange="dok")
    sid = db.create_station(cid, "DN2LH", "JO31AA", "432MHz", "SSB", "", {"exchange": "G01", "section": "Single", "power": "100"})
    db.add_qso(sid, {"call": "DL8NAS", "locator": "JN59LE", "exch_rcvd": "B21", "ts_utc": "2025-05-03T14:12:00Z"})
    db.add_qso(sid, {"call": "OL3Z", "locator": "JN79FX", "exch_rcvd": "G20", "ts_utc": "2025-05-03T14:15:00Z"})
    db.add_qso(sid, {"call": "DG1E", "locator": "JO31LE", "exch_rcvd": "G20", "ts_utc": "2025-05-03T14:20:00Z"})
    s = db.station_summary(sid)
    assert s["points"] == 3 and s["multiplier"] == 2 and s["score"] == 6 and "DOKs" in s["scoring_label"]
    db.update_contest(cid, scoring="km*squares"); db.rescore_contest(cid)
    s = db.station_summary(sid)
    assert s["points"] == 406 + 607 + 67 and s["multiplier"] == 3 and s["score"] == s["points"] * 3
    assert db.contest_summary(cid)["total_score"] == s["score"] and db.scoreboard(cid)[0]["score"] == s["score"]
    contest, station, qsos = db.get_contest(cid), db.get_station(sid), db.list_qsos(sid)
    edi = exporters.export_edi(contest, station, qsos)
    assert f"CToSc={s['score']}" in edi and f"CQSOP={s['points']}" in edi and "Multiplikator 3" in edi
    cbr = exporters.export_cabrillo(contest, station, qsos)
    assert cbr.startswith("START-OF-LOG: 3.0") and f"CLAIMED-SCORE: {s['score']}" in cbr and "CATEGORY-BAND: 432" in cbr and "GRID-LOCATOR: JO31AA" in cbr
    assert "QSO:   432 PH 2025-05-03 1412 DN2LH         59 001 JO31AA G01 DL8NAS        59 --- JN59LE B21" in cbr and cbr.rstrip().endswith("END-OF-LOG:")
    # strengere Log-Prüfung
    from contestlogger import logcheck
    db.update_station(sid, info={"exchange": "G01", "section": "Supergruppe", "resp_email": "kaputt", "power": "100 Watt", "operators": ""})
    chk = logcheck.check_station(contest, db.get_station(sid), qsos)
    msgs = " | ".join(w["msg"] for w in chk["warnings"])
    assert "Wertungsgruppe" in msgs and "E-Mail" in msgs and "Leistung" in msgs
    db.add_qso(sid, {"call": "DN2LH/P", "locator": "JO31AA", "ts_utc": "2025-05-03T14:30:00Z"})
    chk = logcheck.check_station(contest, db.get_station(sid), db.list_qsos(sid))
    assert any("eigenen Rufzeichen" in e["msg"] for e in chk["errors"])
