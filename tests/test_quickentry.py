"""Schnelleingabe (contestlogger/static/quickentry.js): eine Zeile in beliebiger Reihenfolge -> Felder."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "contestlogger" / "static" / "quickentry.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="Node.js nicht installiert")


def parse(line: str, **opts) -> dict:
    script = f"const Q = require({json.dumps(str(JS))}); process.stdout.write(JSON.stringify(Q.parse({json.dumps(line)}, {json.dumps(opts)})));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, timeout=30).stdout
    return json.loads(out)


def fields(r: dict) -> tuple:
    return r["call"], r["locator"], r["serial"], r["rst"], r["dok"], r["comment"]


@pytest.mark.parametrize("line", ["DL1ABC JO31AA 012 57 G01", "57 012 g01 jo31aa dl1abc", "jo31aa, dl1abc; 012 57 G01"])
def test_any_order(line):
    assert fields(parse(line, dok=True)) == ("DL1ABC", "JO31AA", "012", "57", "G01", "")


def test_rst_vs_serial():
    assert fields(parse("DL1ABC JO31AA 123")) == ("DL1ABC", "JO31AA", "123", "", "", "")         # einzelne Zahl = Nummer
    assert fields(parse("DL1ABC 59 12 JO31AA"))[2:4] == ("012", "59")                          # 59 ist der RST
    assert fields(parse("DL1ABC 12 59 JO31AA"))[2:4] == ("012", "59")
    assert fields(parse("DL1ABC 59 059 JO31AA"))[2:4] == ("059", "59")                         # führende Null = Nummer
    assert fields(parse("DL1ABC 49 12 JO31AA"))[2:4] == ("049", "")                            # 49 ist kein plausibler RST
    assert fields(parse("DL1ABC r44 12 JO31AA"))[2:4] == ("012", "44")                         # r… erzwingt RST
    assert fields(parse("DL1ABC #57 55 JO31AA"))[2:4] == ("057", "55")                         # #… erzwingt Nummer
    assert fields(parse("OK1KZ/P 599 045 JN79", mode="CW"))[:4] == ("OK1KZ/P", "JN79", "045", "599")
    assert fields(parse("OK1KZ 599 045 JN79", mode="SSB"))[2:4] == ("599", "")                 # 599 ist kein SSB-Rapport


def test_ambiguous_is_reported():
    r = parse("DL1ABC 57 55 JO31AA")
    assert (r["serial"], r["rst"]) == ("057", "55")
    assert r["notes"] == [{"kind": "ambiguous", "values": ["57", "55"]}]


def test_dok_only_and_comment():
    assert fields(parse("DK0XX 57 G01 JO30", serial=False, dok=True)) == ("DK0XX", "JO30", "", "57", "G01", "")
    assert fields(parse("dl1abc 59 12 jo31aa tnx Peter")) == ("DL1ABC", "JO31AA", "012", "59", "", "tnx Peter")
    assert parse("DL1ABC G01 JO31AA")["comment"] == "G01"                                       # ohne DOK-Austausch: Kommentar


def test_never_touches_own_data():
    r = parse("DL1ABC JO31AA 012 57")
    assert set(r) == {"call", "locator", "serial", "rst", "dok", "comment", "notes"}             # kein RST geg./Nr geg.
