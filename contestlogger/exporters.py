"""Export: REG1TEST/EDI (für die Contest-Abgabe), ADIF und CSV."""
from __future__ import annotations

import csv
import io
from datetime import datetime

from . import __version__, scoring

CABRILLO_FREQ = {"50MHz": "50", "70MHz": "70", "144MHz": "144", "222MHz": "222", "432MHz": "432", "902MHz": "902", "1296MHz": "1.2G", "2320MHz": "2.3G",
                 "3400MHz": "3.4G", "5760MHz": "5.7G", "10368MHz": "10G", "24048MHz": "24G", "47088MHz": "47G", "76032MHz": "75G"}
CABRILLO_MODE = {"SSB": "PH", "CW": "CW", "FM": "FM", "AM": "PH", "MIXED": "PH"}

EDI_BAND = {
    "50MHz": "50 MHz", "70MHz": "70 MHz", "144MHz": "145 MHz", "432MHz": "435 MHz", "1296MHz": "1,3 GHz",
    "2320MHz": "2,3 GHz", "3400MHz": "3,4 GHz", "5760MHz": "5,7 GHz", "10368MHz": "10 GHz",
    "24048MHz": "24 GHz", "47088MHz": "47 GHz", "76032MHz": "76 GHz",
}
ADIF_BAND = {
    "50MHz": "6m", "70MHz": "4m", "144MHz": "2m", "432MHz": "70cm", "1296MHz": "23cm", "2320MHz": "13cm",
    "3400MHz": "9cm", "5760MHz": "6cm", "10368MHz": "3cm", "24048MHz": "1.25cm", "47088MHz": "6mm",
}
EDI_MODE = {"SSB": "1", "CW": "2", "FM": "6", "AM": "7"}


def _dt(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def export_edi(contest: dict, station: dict, qsos: list[dict]) -> str:
    """REG1TEST-Datei nach IARU-Region-1-Vorgabe; Stationsangaben aus station['info']."""
    info = station.get("info") or {}
    qsos = sorted(qsos, key=lambda q: (q["ts_utc"], q["id"]))
    valid = [q for q in qsos if not q["dupe"]]
    dates = sorted({_dt(q["ts_utc"]).strftime("%Y%m%d") for q in qsos}) or [datetime.utcnow().strftime("%Y%m%d")]
    squares = {q["square"] for q in valid if q["square"]}
    countries = {q["country"] for q in valid if q["country"] and q["country"] != "?"}
    exchanges = {q.get("exch_rcvd") for q in valid if q.get("exch_rcvd")}
    points = sum(q["points"] for q in valid)
    tot = scoring.total(contest.get("scoring"), points, len(squares), len(exchanges))
    odx = max(valid, key=lambda q: q["km"], default=None)

    def g(key: str, default: str = "") -> str:
        return str(info.get(key, default) or "")

    lines = [
        "[REG1TEST;1]",
        f"TName={contest['name']}",
        f"TDate={dates[0]};{dates[-1]}",
        f"PCall={station['call']}",
        f"PWWLo={station['locator']}",
        f"PExch={g('exchange') or g('dok')}",
        f"PAdr1={g('site_address')}",
        f"PAdr2={g('site_city')}",
        f"PSect={g('section', 'Single')}",
        f"PBand={EDI_BAND.get(station['band'], station['band'])}",
        f"PClub={g('club')}",
        f"RName={g('resp_name')}",
        f"RCall={g('resp_call')}",
        f"RAdr1={g('resp_address')}",
        "RAdr2=",
        f"RPoCo={g('resp_zip')}",
        f"RCity={g('resp_city')}",
        f"RCoun={g('resp_country', 'Deutschland')}",
        f"RPhon={g('resp_phone')}",
        f"RHBBS={g('resp_email')}",
        f"MOpe1={g('operators')}",
        "MOpe2=",
        f"STXEq={g('tx')}",
        f"SPowe={g('power')}",
        f"SRXEq={g('rx')}",
        f"SAnte={g('antenna')}",
        f"SAntH={g('antenna_height')};{g('asl')}",
        f"CQSOs={len(valid)};1",
        f"CQSOP={points}",
        f"CWWLs={len(squares)};0;1",
        "CWWLB=0",
        f"CExcs={len(exchanges)};0;1",
        "CExcB=",
        f"CDXCs={len(countries)};0;1",
        "CDXCB=0",
        f"CToSc={tot['score']}",
        f"CODXC={odx['call']};{odx['locator']};{odx['km']}" if odx else "CODXC=",
        "[Remarks]",
        f"Erstellt mit ContestLogger {__version__} - Wertung: {scoring.label(contest.get('scoring')).replace('×', 'x')}" + (f", Multiplikator {tot['multiplier']}" if tot["multiplier"] else ""),
        f"[QSORecords;{len(qsos)}]",
    ]
    for q in qsos:
        d = _dt(q["ts_utc"])
        lines.append(";".join([
            d.strftime("%y%m%d"), d.strftime("%H%M"), q["call"], EDI_MODE.get(q["mode"], "1"),
            q["rst_sent"], f"{int(q['serial_sent']):03d}", q["rst_rcvd"], str(q["serial_rcvd"]).zfill(3) if str(q["serial_rcvd"]).isdigit() else str(q["serial_rcvd"]),
            q.get("exch_rcvd") or "", q["locator"], str(q["points"]), "", "", "", "D" if q["dupe"] else "",
        ]))
    return "\r\n".join(lines) + "\r\n"


def export_cabrillo(contest: dict, station: dict, qsos: list[dict]) -> str:
    """Cabrillo 3.0 (viele Auswerter nehmen es neben EDI an); Austausch: RST, Nummer, Locator und ggf. DOK."""
    info = station.get("info") or {}
    qsos = sorted(qsos, key=lambda q: (q["ts_utc"], q["id"]))
    valid = [q for q in qsos if not q["dupe"]]
    squares = {q["square"] for q in valid if q["square"]}
    exchanges = {q.get("exch_rcvd") for q in valid if q.get("exch_rcvd")}
    tot = scoring.total(contest.get("scoring"), sum(q["points"] for q in valid), len(squares), len(exchanges))
    g = lambda k, d="": str(info.get(k, d) or "")  # noqa: E731
    sect = g("section", "SINGLE-OP").upper()
    lines = [
        "START-OF-LOG: 3.0",
        f"CALLSIGN: {station['call']}",
        f"CONTEST: {contest.get('name', '')}",
        f"CATEGORY-OPERATOR: {'MULTI-OP' if 'MULTI' in sect else 'SINGLE-OP'}",
        f"CATEGORY-BAND: {CABRILLO_FREQ.get(station['band'], station['band'])}",
        f"CATEGORY-POWER: {'LOW' if g('power') and g('power').replace('.', '').isdigit() and float(g('power')) <= 100 else 'HIGH'}",
        f"CATEGORY-STATION: {'PORTABLE' if station['call'].endswith('/P') else 'FIXED'}",
        f"GRID-LOCATOR: {station['locator']}",
        f"CLAIMED-SCORE: {tot['score']}",
        f"OPERATORS: {g('operators')}",
        f"CLUB: {g('club')}",
        f"NAME: {g('resp_name')}",
        f"ADDRESS: {g('resp_address')}",
        f"ADDRESS-CITY: {g('resp_city')}",
        f"ADDRESS-POSTALCODE: {g('resp_zip')}",
        f"ADDRESS-COUNTRY: {g('resp_country', 'Germany')}",
        f"EMAIL: {g('resp_email')}",
        f"CREATED-BY: ContestLogger {__version__}",
        f"SOAPBOX: {g('tx')} {g('power')} W, {g('antenna')} ({g('antenna_height')} m agl, {g('asl')} m asl)".rstrip(),
    ]
    own_exch = g("exchange")
    freq = CABRILLO_FREQ.get(station["band"], station["band"].replace("MHz", ""))
    for q in qsos:
        d = _dt(q["ts_utc"])
        sent = f"{q['rst_sent']} {int(q['serial_sent']):03d} {station['locator']}" + (f" {own_exch}" if own_exch else "")
        rcvd = f"{q['rst_rcvd']} {str(q['serial_rcvd']).zfill(3) if str(q['serial_rcvd']).isdigit() else (q['serial_rcvd'] or '---')} {q['locator'] or '------'}" + (f" {q['exch_rcvd']}" if q.get("exch_rcvd") else "")
        lines.append(f"QSO: {freq:>5} {CABRILLO_MODE.get(q['mode'], 'PH')} {d.strftime('%Y-%m-%d %H%M')} {station['call']:<13} {sent} {q['call']:<13} {rcvd}" + ("  X-QSO" if q["dupe"] else ""))
    lines.append("END-OF-LOG:")
    return "\r\n".join(lines) + "\r\n"


def _adif_field(name: str, value) -> str:
    v = str(value if value is not None else "")
    return f"<{name}:{len(v)}>{v}" if v else ""


def export_adif(contest: dict, station: dict, qsos: list[dict]) -> str:
    out = [
        f"ContestLogger {__version__} ADIF Export",
        f"Call={station['call']}", f"Locator={station['locator']}", f"Band={station['band']}",
        f"Contest={contest['name']}",
        _adif_field("ADIF_VER", "3.1.4"), _adif_field("PROGRAMID", "ContestLogger"), _adif_field("PROGRAMVERSION", __version__),
        "<eoh>",
    ]
    for q in sorted(qsos, key=lambda q: (q["ts_utc"], q["id"])):
        d = _dt(q["ts_utc"])
        out.append("".join([
            _adif_field("CALL", q["call"]), _adif_field("QSO_DATE", d.strftime("%Y%m%d")),
            _adif_field("TIME_ON", d.strftime("%H%M")), _adif_field("MODE", q["mode"]),
            _adif_field("RST_SENT", q["rst_sent"]), _adif_field("RST_RCVD", q["rst_rcvd"]),
            _adif_field("GRIDSQUARE", q["locator"]), _adif_field("STX", f"{int(q['serial_sent']):03d}"),
            _adif_field("SRX", q["serial_rcvd"]), _adif_field("BAND", ADIF_BAND.get(q["band"], q["band"])),
            _adif_field("SRX_STRING", q.get("exch_rcvd") or ""), _adif_field("DARC_DOK", q.get("exch_rcvd") or ""),
            _adif_field("STX_STRING", (station.get("info") or {}).get("exchange") or ""),
            _adif_field("FREQ", q.get("freq") or ""),
            _adif_field("STATION_CALLSIGN", station["call"]), _adif_field("MY_GRIDSQUARE", station["locator"]),
            _adif_field("CONTEST_ID", contest["name"]), _adif_field("DISTANCE", q["km"]),
            _adif_field("COMMENT", q["comment"]), "<eor>",
        ]))
    return "\r\n".join(out) + "\r\n"


def export_csv(contest: dict, station: dict, qsos: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Datum", "Zeit UTC", "Rufzeichen", "RST geg", "Nr geg", "RST erh", "Nr erh", "DOK erh", "Locator", "km", "Grad", "Punkte", "Land", "Modus", "Band", "Dupe", "Kommentar", "Operator"])
    for q in sorted(qsos, key=lambda q: (q["ts_utc"], q["id"])):
        d = _dt(q["ts_utc"])
        w.writerow([d.strftime("%d.%m.%Y"), d.strftime("%H:%M"), q["call"], q["rst_sent"], f"{int(q['serial_sent']):03d}",
                    q["rst_rcvd"], q["serial_rcvd"], q.get("exch_rcvd") or "", q["locator"], q["km"], q["bearing"], q["points"], q["country"],
                    q["mode"], q["band"], "D" if q["dupe"] else "", q["comment"], q["logged_by"]])
    return buf.getvalue()


def export_callbook_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Call", "Locator", "Name", "DOK", "QSOs", "Zuletzt", "Weitere Locator"])
    for r in rows:
        w.writerow([r["call"], r["locator"], r["name"], r.get("dok") or "", r["qso_count"], r["last_seen"], r["alt_locators"]])
    return buf.getvalue()
