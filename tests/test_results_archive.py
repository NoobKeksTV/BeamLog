"""Ergebnislisten-Archiv: Auswertung der Formate (DARC UKW/KW, Archiv-Textlisten, OK2KKW) und Import-Ablauf ohne Netz."""
import time
import urllib.request

from fastapi.testclient import TestClient

from contestlogger import results_archive as ra
from contestlogger.app import create_app

KW_PAGE = """<select name="year"  onchange="submit()"><option selected="selected" value="2025">2025<option value="2024">2024</select>
<h3>Single operator, CW, low power</h3><table><thead><tr><th>Platz</th> <th>Rufzeichen</th> <th>DOK</th> <th>QSOs</th></tr></thead>
<tbody><tr><td>1&nbsp;</td> <td>DA9AAA</td> <td>F15</td> <td>1 272</td></tr></tbody>
<tbody><tr><td>2&nbsp;</td> <td>DA9BBB</td> <td>U08</td> <td>1 391</td></tr></tbody>
<tbody><tr><td>3&nbsp;</td> <td>OK9ZZZ</td> <td>-</td> <td>900</td></tr></tbody></table>"""
KW_EDITIONS = KW_PAGE.replace("</select>", """</select><select name="edition"  onchange="submit()"><option selected="selected" value="feb">feb<option value="mai">mai</select>""")
KW_MAI = """<table><tr><th>Platz</th><th>Rufzeichen</th><th>DOK</th></tr><tr><td>1</td><td>DK2OY</td><td>M15</td></tr></table>"""
UKW_ALT = """Wertungsgruppe 01: 145 MHz, Einmann
  Pl. Call         DOK     Loc.   QSOs  Points  ODX          Loc.-ODX  ODX-Pt.  Power
   1. DL6IAK       A36     JN48IX  597  194493  G3CKR/P      IO93AD     877       750
   2. DK0BN        40BN    JN39VV  815  277269  HA6W         KN08FB     884       600
"""
OK2_1990 = """  poo.  call     body     qso   loc      DX-km    m.ASL   TX-W  ANT
  1. OK1TDH/P   66794    267   JN98GU     724      901   200   4X 13el Y
  11. OK1AR      22003      25. OK2WDC     11154      39. OK1DAM      5515"""


def test_parse_kw_tables():
    rows = ra.parse_html_tables(KW_PAGE)
    assert rows == [("DA9AAA", "", "F15"), ("DA9BBB", "", "U08"), ("OK9ZZZ", "", "")]


def test_parse_text_pairs_with_odx_and_special_dok():
    rows = ra.parse_text_pairs(UKW_ALT)
    assert ("DL6IAK", "JN48IX", "A36") in rows and ("G3CKR/P", "IO93AD", "") in rows
    assert ("DK0BN", "JN39VV", "40BN") in rows and not any(r[0] == "40BN" for r in rows)  # Sonder-DOK ist kein Rufzeichen
    assert ra.parse_text_pairs(OK2_1990) == [("OK1TDH/P", "JN98GU", "")]  # Locator erst nach Punkten/QSOs; Zeilen ohne Locator zählen nicht


def test_kw_editions_and_listing():
    pages = {ra.kw_url("ft4log", 2025): KW_EDITIONS, ra.kw_url("ft4log", 2025, "mai"): KW_MAI,
             f"{ra.HUB}/~ft4log/arch_res.cgi?form=referat&lang=de": KW_PAGE}
    fetch = lambda u: pages[u].encode()  # noqa: E731
    entries = ra.list_darc_kw(fetch, ["ft4log"])
    assert [e.id for e in entries] == ["darc-kw:ft4log:2025", "darc-kw:ft4log:2024"]
    parsed = ra.parse_entry(fetch, entries[0])
    assert parsed.pages == 2 and ("DK2OY", "", "M15") in parsed.rows


def test_ok2kkw_listing_years():
    idx = """<a href="contests/90/1subr1990.htm">1. subregional</a> <a href="https://www.ok2kkw.com/00003016/vhf024/vhf_c-test_eu_fin.htm">IARU EU</a>
    <a href="contests/05/vhf05_iaru.htm">IARU 2005</a> <a href="winn.htm">Hall of fame</a> <a href="http://example.com/x.htm">fremd</a>"""
    entries = ra.list_ok2kkw(lambda u: idx.encode("cp1250"))
    assert sorted(e.year for e in entries) == [1990, 2005, 2024]
    assert all(e.url.startswith(ra.OK2KKW) for e in entries)


def test_archive_import_job(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAMLOG_MAINTAINER", "1")
    pages = {f"{ra.HUB}/~waglog/arch_res.cgi?form=referat&lang=de": KW_PAGE, ra.kw_url("waglog", 2025): KW_PAGE, ra.kw_url("waglog", 2024): KW_PAGE}

    class Resp:
        def __init__(self, data): self.data = data
        def read(self): return self.data
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: Resp(pages[req.full_url].encode()))
    monkeypatch.setattr(ra, "DARC_KW", {"waglog": "WAG"})
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        H = {"X-Admin-Token": c.post("/api/setup", json={"password": "admin1"}).json()["token"]}
        c.post("/api/callbook", json={"call": "DA9BBB", "locator": "JN58SE"}, headers=H)  # bekannt, ohne DOK
        lst = c.post("/api/results/list", json={"source": "darc-kw"}, headers=H).json()
        assert [e["id"] for e in lst["entries"]] == ["darc-kw:waglog:2025", "darc-kw:waglog:2024"]
        r = c.post("/api/results/import", json={"ids": ["darc-kw:waglog:2025"]}, headers=H)
        assert r.status_code == 200
        for _ in range(50):
            j = c.get("/api/results/job", headers=H).json()
            if not j["running"]:
                break
            time.sleep(0.1)
        assert j["done"] == 1 and j["dok"] == 1 and j["new"] == 0 and j["skipped"] == 2  # nur DOK bei der bekannten Station ergänzt
        assert c.get("/api/callbook?q=DA9BBB", headers=H).json()["rows"][0]["dok"] == "U08"
        assert not any(r["call"] == "DA9AAA" for r in c.get("/api/callbook?q=DA9AAA", headers=H).json()["rows"])
        assert c.get("/api/results/sources", headers=H).json()["done"]["darc-kw:waglog:2025"]["n"] == 1
        # mit „ohne Locator aufnehmen“ kommen die übrigen Stationen dazu
        c.post("/api/results/import", json={"ids": ["darc-kw:waglog:2024"], "without_locator": True}, headers=H)
        for _ in range(50):
            j = c.get("/api/results/job", headers=H).json()
            if not j["running"]:
                break
            time.sleep(0.1)
        assert j["new"] == 2


IARU_LIST = """<tr><td>2025 IARU Reg. 1 145 MHz Contest</td><td>2025-09-06 14:00</td><td>2025-09-07 14:00</td>
<td><a href="prg_xcsv.php?cont_id=75">CSV</a></td></tr>
<tr><td>2026 IARU Reg. 1 145 MHz Contest</td><td>2026-09-05 14:00</td><td>in Auswertung</td></tr>
<a href="/v_upld/prg_list.php?start=31">2</a>"""
IARU_CSV = '''"Section","Band","Rank","Rank for prize","Call","WWL","Claimed score",
"SO-LP","145 MHz","1","1","IO4R","JN63DT","137599",
"SO","145 MHz","2","2","OK1NPF","JO70UK","120178",
'''
IARU_PART = """<tr><td>SO 145 MHz</td><td>1</td><td>IO4R</td><td>JN63DT</td>
<td><a href="../v_qsos/prg_list.php?reset=1&start=1&master_v_qsos_part_id=111&master_v_qsos_vw=v_part">QSOs</a></td></tr>"""
IARU_QSOS = """<table><tr><th>Timestamp</th><th>RX Call</th><th>RX WWL</th><th>Cross checked score</th><th>Unique<br>Single Log</th></tr>
<tr><td>2025-09-06 14:01</td><td>OK5W</td><td>JO60OK</td><td>178</td><td>no/no</td></tr>
<tr><td>2025-09-06 14:02</td><td>DL9XYZ</td><td>JN58AA</td><td>90</td><td>no/yes</td></tr>
<tr><td>2025-09-06 14:03</td><td>OK1WQX</td><td>JN79HU</td><td>101</td><td>yes/yes</td></tr>
<tr><td>2025-09-06 14:04</td><td>OL2J</td><td>JN79TI</td><td>0</td><td>no/no</td></tr></table>"""
IARU_QSOS_MGM = """<table><tr><th>RX Call</th><th>RX WWL</th><th>Mode</th></tr><tr><td>OE4WHG</td><td>JN87MM</td><td>FT8</td></tr>
<tr><td>S52OR</td><td>JN76MM</td><td>CW</td></tr></table>"""


def test_iaru_robot_list_csv_and_logs():
    pages = {f"{ra.IARU_ROBOT}/v_upld/prg_list.php?start=1": IARU_LIST, f"{ra.IARU_ROBOT}/v_upld/prg_list.php?start=31": IARU_LIST,
             f"{ra.IARU_ROBOT}/v_upld/prg_xcsv.php?cont_id=75": IARU_CSV,
             f"{ra.IARU_ROBOT}/v_part/prg_list.php?reset=1&start=1&master_v_part_cont_id=75&master_v_part_vw=v_upld": IARU_PART,
             f"{ra.IARU_ROBOT}/v_qsos/prg_list.php?reset=1&start=1&master_v_qsos_part_id=111&master_v_qsos_vw=v_part": IARU_QSOS}
    fetch = lambda u: pages[u].encode("iso-8859-1")  # noqa: E731
    es = ra.list_iaru_robot(fetch)
    assert [e.id for e in es] == ["iaru-robot:vhf.csv", "iaru-robot:75"]  # Contest in Auswertung (ohne CSV) fehlt
    assert ra.parse_entry(fetch, es[1]).rows == [("IO4R", "JN63DT", ""), ("OK1NPF", "JO70UK", "")]
    logs = ra.list_iaru_robot_logs(fetch)
    assert [e.id for e in logs] == ["iaru-robot-logs:75"]
    seen = []
    parsed = ra.parse_entry(fetch, logs[0], lambda n, t: seen.append((n, t)) or True)
    # eigene Station + QSO-Partner; „unique“ (verhört) und beim Gegencheck gestrichene QSOs fehlen, Stationen ohne Log sind dabei
    assert parsed.rows == [("IO4R", "JN63DT", ""), ("OK5W", "JO60OK", ""), ("DL9XYZ", "JN58AA", "")] and seen == [(1, 1)]
    try:
        ra.parse_entry(fetch, logs[0], lambda n, t: False)
        assert False, "Abbruch erwartet"
    except ra.Cancelled:
        pass
    assert ra.parse_iaru_qsos(IARU_QSOS_MGM) == [("S52OR", "JN76MM", "")]  # FT8: nur Großfeld, mit „MM“ aufgefüllt -> weglassen
    assert ra.parse_iaru_csv('"DF0MU";"JO31PC"\n"";"JN19BQ"\n"0DF5TV";"JN48OL"\n') == [("DF0MU", "JO31PC", "")]


CAB = """<pre>START-OF-LOG: 3.0
CONTEST: WAG
SPECIFIC: X36
CALLSIGN: DA9AAA
GRID-LOCATOR: JO50BU
QSO: 28000 CW 2025-10-18 1502 DA9AAA        599 X36    EA9ACD        599 0
QSO: 28000 CW 2025-10-18 1503 DA9AAA        599 X36    DL6KVA        599 V01
QSO: 28000 CW 2025-10-18 1506 DA9AAA        599 X36    DR1D          599 G20
QSO: 7049 DG 2025-05-13 1901 DA9AAA        -12  JO44 DL2LBK       -11  JO54
END-OF-LOG:</pre>"""


def test_parse_cabrillo_open_log():
    from contestlogger import importers
    rows = ra.parse_cabrillo(importers.html_to_text(CAB.encode()))
    assert rows[0] == ("DA9AAA", "JO50BU", "X36")  # eigene Station mit Locator und DOK
    assert ("DL6KVA", "", "V01") in rows and ("DR1D", "", "G20") in rows
    assert ("EA9ACD", "", "") in rows  # Ausland sendet eine Nummer, keinen DOK
    assert ("DL2LBK", "", "") in rows  # FT4: Großfeld ist kein DOK


def test_darc_kw_logs_listing_and_parse():
    form = """<select name="jahr" ><option value="2025">2025<option value="2024">2024</select>
    <input type="hidden" name="contest" value="wag"  /><input type="hidden" name="edition" value="2000"  />"""
    res = """<table><tr><th>Platz</th><th>Rufzeichen</th><th>DOK</th></tr><tr><td>1</td><td>DA9AAA</td><td>X36</td></tr></table>"""
    base = f"{ra.HUB}/~waglog/user.cgi?fc=req_olog&contest=wag&form=referat&lang=de&status=show&jahr=2025"
    pages = {f"{ra.HUB}/~waglog/user.cgi?fc=req_olog&form=referat&lang=de": form, ra.kw_url("waglog", 2025): res,
             f"{base}&edition=2000&call=DA9AAA&Show=1": CAB}
    fetch = lambda u: pages[u].encode()  # noqa: E731
    es = ra.list_darc_kw_logs(fetch, ["waglog"])
    assert [e.id for e in es] == ["darc-kw-logs:waglog:2025", "darc-kw-logs:waglog:2024"]
    rows = ra.parse_entry(fetch, es[0], lambda n, t: True).rows
    assert rows[0] == ("DA9AAA", "JO50BU", "X36") and ("DL6KVA", "", "V01") in rows


def test_archive_job_runs_lists_in_parallel(tmp_path, monkeypatch):
    """Mehrere Listen gleichzeitig: alle werden fertig, done_ids nennt jede genau einmal."""
    import threading
    monkeypatch.setenv("BEAMLOG_MAINTAINER", "1")
    keys = {f"k{i}": f"Contest {i}" for i in range(5)}
    pages = {f"{ra.HUB}/~{k}/arch_res.cgi?form=referat&lang=de": KW_PAGE for k in keys}
    pages.update({ra.kw_url(k, y): KW_PAGE for k in keys for y in (2025, 2024)})
    state = {"now": 0, "max": 0}
    lock = threading.Lock()

    class Resp:
        def __init__(self, data): self.data = data
        def read(self):
            with lock:
                state["now"] += 1; state["max"] = max(state["max"], state["now"])
            time.sleep(0.05)
            with lock:
                state["now"] -= 1
            return self.data
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: Resp(pages[req.full_url].encode()))
    monkeypatch.setattr(ra, "DARC_KW", keys)
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        H = {"X-Admin-Token": c.post("/api/setup", json={"password": "admin1"}).json()["token"]}
        ids = [e["id"] for e in c.post("/api/results/list", json={"source": "darc-kw"}, headers=H).json()["entries"]]
        assert len(ids) == 10
        c.post("/api/results/import", json={"ids": ids, "without_locator": True}, headers=H)
        for _ in range(100):
            j = c.get("/api/results/job", headers=H).json()
            if not j["running"]:
                break
            time.sleep(0.1)
        assert j["done"] == 10 and sorted(j["done_ids"]) == sorted(ids) and not j["errors"]
        assert state["max"] > 1  # tatsächlich gleichzeitig geladen
