"""Import von Logs und Call-Listen.

Unterstützt die Dateien von DD3KU WinContest (Datenbank/*.txt, DD3KU/*.EXP,
Access *.mdb über mdbtools), REG1TEST/EDI, ADIF sowie einfache CSV-Listen
(Call;Locator[;Name]) als Call-Buch.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import geo, prefixes


@dataclass
class ImportedQso:
    ts_utc: str
    call: str
    locator: str = ""
    rst_sent: str = "59"
    rst_rcvd: str = "59"
    serial_sent: int | None = None
    serial_rcvd: str = ""
    mode: str = "SSB"
    band: str = ""
    comment: str = ""


@dataclass
class ImportResult:
    kind: str
    qsos: list[ImportedQso] = field(default_factory=list)
    header: dict = field(default_factory=dict)  # call, locator, band, name ...
    callbook: list[tuple[str, str, str]] = field(default_factory=list)  # (call, locator, name)
    warnings: list[str] = field(default_factory=list)


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _split_rst(field_: str) -> tuple[str, str]:
    """'59  001' -> ('59', '001'); '599 012' -> ('599','012')."""
    parts = field_.strip().split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        s = parts[0]
        if len(s) > 3 and s[:2].isdigit():
            return s[:2], s[2:]
        return s, ""
    return "59", ""


def _ts(date_ddmmyy: str, time_hhmm: str) -> str:
    d = date_ddmmyy.strip()
    t = time_hhmm.strip()
    for fmt in ("%d.%m.%y", "%d.%m.%Y", "%y%m%d", "%Y%m%d"):
        try:
            day = datetime.strptime(d, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Datum nicht lesbar: {d!r}")
    t = t.replace(":", "")
    hh, mm = int(t[:2]), int(t[2:4])
    return day.replace(hour=hh, minute=mm).strftime("%Y-%m-%dT%H:%M:00Z")


BAND_ALIASES = {
    "50": "50MHz", "6M": "50MHz", "70": "70MHz", "4M": "70MHz",
    "144": "144MHz", "145": "144MHz", "2M": "144MHz",
    "432": "432MHz", "433": "432MHz", "435": "432MHz", "70CM": "432MHz",
    "1296": "1296MHz", "1,3G": "1296MHz", "1.3G": "1296MHz", "1296M": "1296MHz", "23CM": "1296MHz",
    "2320": "2320MHz", "2,3G": "2320MHz", "2.3G": "2320MHz", "13CM": "2320MHz",
    "3400": "3400MHz", "3,4G": "3400MHz", "3.4G": "3400MHz", "9CM": "3400MHz",
    "5760": "5760MHz", "5,7G": "5760MHz", "5.7G": "5760MHz", "6CM": "5760MHz",
    "10368": "10368MHz", "10G": "10368MHz", "3CM": "10368MHz",
    "24048": "24048MHz", "24G": "24048MHz", "1.25CM": "24048MHz",
    "47088": "47088MHz", "47G": "47088MHz", "76032": "76032MHz", "76G": "76032MHz",
}


def _band_label(raw: str) -> str:
    """'435 MHz', '70cm', '1,3 GHz', '432' -> einheitlich '432MHz' usw."""
    s = (raw or "").replace(" ", "").upper()
    if not s:
        return ""
    if s in BAND_ALIASES:
        return BAND_ALIASES[s]
    s2 = re.sub(r"HZ$", "", s)  # 435MHZ -> 435M, 1,3GHZ -> 1,3G
    if s2 in BAND_ALIASES:
        return BAND_ALIASES[s2]
    if s2.endswith("M") and s2[:-1] in BAND_ALIASES:
        return BAND_ALIASES[s2[:-1]]
    if s2.endswith("G"):
        try:
            mhz = int(round(float(s2[:-1].replace(",", ".")) * 1000))
            return BAND_ALIASES.get(str(mhz), f"{mhz}MHz")
        except ValueError:
            pass
    m = re.match(r"(\d+)", s)
    return f"{m.group(1)}MHz" if m else raw.strip()


# ---------------------------------------------------------------- DD3KU TXT
def parse_dd3ku_txt(text: str) -> ImportResult:
    """Datenbank/<Name>.txt: 'N,03.05.25,14:12,DL8NAS ,59  001,59  010,JN59LE, 406,432 MHz,hash'."""
    res = ImportResult("dd3ku_txt")
    for line in text.splitlines():
        if not line or line.startswith("Version") or not line.startswith("N,"):
            continue
        parts = line.split(",")
        if len(parts) < 9:
            res.warnings.append(f"Zeile übersprungen: {line[:60]}")
            continue
        try:
            rs, ss = _split_rst(parts[4])
            rr, sr = _split_rst(parts[5])
            res.qsos.append(ImportedQso(
                ts_utc=_ts(parts[1], parts[2]), call=parts[3].strip().upper(), locator=parts[6].strip().upper(),
                rst_sent=rs, rst_rcvd=rr, serial_sent=int(ss) if ss.isdigit() else None, serial_rcvd=sr,
                band=_band_label(parts[8]),
            ))
        except Exception as e:  # noqa: BLE001
            res.warnings.append(f"{line[:60]}: {e}")
    if res.qsos:
        res.header["band"] = res.qsos[0].band
    return res


# ---------------------------------------------------------------- DD3KU EXP
def parse_dd3ku_exp(text: str) -> ImportResult:
    res = ImportResult("dd3ku_exp")
    lines = text.splitlines()
    if not lines or "Win-Contest" not in lines[0]:
        raise ValueError("Keine WinContest-Exportdatei")
    # Kopf: Version, Call, Locator, Band, YYYYMM
    res.header = {"call": lines[2].strip(), "locator": lines[3].strip(), "band": _band_label(lines[4].strip())}
    for line in lines[6:]:
        parts = line.split(",")
        if len(parts) < 7:
            continue
        try:
            rs, ss = _split_rst(parts[3])
            rr, sr = _split_rst(parts[4])
            res.qsos.append(ImportedQso(
                ts_utc=_ts(parts[0], parts[1]), call=parts[2].strip().upper(), locator=parts[5].strip().upper(),
                rst_sent=rs, rst_rcvd=rr, serial_sent=int(ss) if ss.isdigit() else None, serial_rcvd=sr,
                mode=parts[12].strip() if len(parts) > 12 else "SSB", band=res.header["band"],
            ))
        except Exception as e:  # noqa: BLE001
            res.warnings.append(f"{line[:60]}: {e}")
    return res


# ---------------------------------------------------------------- EDI / REG1TEST
def parse_edi(text: str) -> ImportResult:
    res = ImportResult("edi")
    section = ""
    band = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[]").split(";")[0].upper()
            continue
        if section == "REG1TEST" and "=" in line:
            k, _, v = line.partition("=")
            k = k.strip()
            if k == "PCall":
                res.header["call"] = v.strip()
            elif k == "PWWLo":
                res.header["locator"] = v.strip()
            elif k == "PBand":
                band = _band_label(v)
                res.header["band"] = band
            elif k == "TName":
                res.header["name"] = v.strip()
            elif k == "TDate":
                res.header["date"] = v.strip()
        elif section == "QSORECORDS":
            parts = line.split(";")
            if len(parts) < 10:
                continue
            try:
                res.qsos.append(ImportedQso(
                    ts_utc=_ts(parts[0], parts[1]), call=parts[2].upper(), locator=parts[9].upper(),
                    mode={"1": "SSB", "2": "CW", "6": "FM", "7": "AM"}.get(parts[3], "SSB"),
                    rst_sent=parts[4], serial_sent=int(parts[5]) if parts[5].isdigit() else None,
                    rst_rcvd=parts[6], serial_rcvd=parts[7], band=band,
                ))
            except Exception as e:  # noqa: BLE001
                res.warnings.append(f"{line[:60]}: {e}")
    return res


# ---------------------------------------------------------------- ADIF
_ADIF_FIELD = re.compile(r"<([A-Za-z_0-9]+):(\d+)(?::[A-Za-z])?>", re.I)


def parse_adif(text: str) -> ImportResult:
    res = ImportResult("adif")
    body = text
    if "<eoh>" in text.lower():
        idx = text.lower().index("<eoh>")
        header = text[:idx]
        for key in ("Call", "Locator", "Band"):
            m = re.search(rf"{key}=(\S+)", header)
            if m:
                res.header[key.lower()] = m.group(1)
        body = text[idx + 5:]
    for record in re.split(r"<eor>", body, flags=re.I):
        fields: dict[str, str] = {}
        pos = 0
        while True:
            m = _ADIF_FIELD.search(record, pos)
            if not m:
                break
            name, length = m.group(1).upper(), int(m.group(2))
            start = m.end()
            fields[name] = record[start:start + length]
            pos = start + length
        if "CALL" not in fields:
            continue
        try:
            t = (fields.get("TIME_ON") or "0000")[:4]
            band = fields.get("FREQ") or fields.get("BAND") or res.header.get("band", "")
            res.qsos.append(ImportedQso(
                ts_utc=_ts(fields.get("QSO_DATE", ""), t), call=fields["CALL"].upper(),
                locator=fields.get("GRIDSQUARE", "").upper(), rst_sent=fields.get("RST_SENT", "59"),
                rst_rcvd=fields.get("RST_RCVD", "59"),
                serial_sent=int(fields["STX"]) if fields.get("STX", "").isdigit() else None,
                serial_rcvd=fields.get("SRX", ""), mode=fields.get("MODE", "SSB"),
                band=_band_label(band) if band else "", comment=fields.get("COMMENT", ""),
            ))
        except Exception as e:  # noqa: BLE001
            res.warnings.append(f"ADIF-Record: {e}")
    return res


# ---------------------------------------------------------------- Access MDB
def parse_mdb(data: bytes) -> ImportResult:
    """Liest die WinContest-Access-Datenbank – rein in Python (auch verschlüsselte Jet4-Dateien),
    mdbtools nur noch als Reserve, falls der Python-Leser scheitert."""
    try:
        from . import mdb
        tables = mdb.read_tables(data)
    except Exception as e:  # noqa: BLE001
        if shutil.which("mdb-tables"):
            return _parse_mdb_mdbtools(data)
        raise ValueError(f"Access-Datei nicht lesbar: {e}") from e
    res = ImportResult("mdb")
    param = tables.get("PARAM") or {}
    if param.get("Call"):
        res.header["call"] = str(param["Call"][0] or "")
        res.header["locator"] = str((param.get("Locator") or [""])[0] or "")
    for t, cols in tables.items():
        if not re.match(r"^\d+(MHz|GHz|MHZ|GHZ)?$", t) and t != "LASER":
            continue
        n = len(cols.get("Rufzeichen") or [])
        for i in range(n):
            r = {k: (v[i] if i < len(v) else None) for k, v in cols.items()}
            if not r.get("Rufzeichen"):
                continue
            try:
                rs, ss = _split_rst(str(r.get("RST_geg") or ""))
                rr, sr = _split_rst(str(r.get("RST_erh") or ""))
                res.qsos.append(ImportedQso(
                    ts_utc=_ts(str(r["Datum"]), str(r["Zeit"])), call=str(r["Rufzeichen"]).strip().upper(),
                    locator=str(r.get("Locator") or "").strip().upper(), rst_sent=rs, rst_rcvd=rr,
                    serial_sent=int(ss) if ss.isdigit() else None, serial_rcvd=sr,
                    mode=str(r.get("Modus") or "SSB").strip() or "SSB", band=_band_label(t),
                    comment=str(r.get("Kommentar") or "").strip(),
                ))
            except Exception as e:  # noqa: BLE001
                res.warnings.append(f"{t} #{i + 1}: {e}")
        if res.qsos and "band" not in res.header:
            res.header["band"] = _band_label(t)
    res.qsos.sort(key=lambda q: q.ts_utc)
    return res


def _parse_mdb_mdbtools(data: bytes) -> ImportResult:
    """Reserve über das Systemprogramm mdb-export (Paket mdbtools)."""
    res = ImportResult("mdb")
    with tempfile.NamedTemporaryFile(suffix=".mdb", delete=False) as fh:
        fh.write(data)
        path = fh.name
    try:
        tables = subprocess.run(["mdb-tables", "-1", path], capture_output=True, text=True, check=True).stdout.split()
        param = subprocess.run(["mdb-export", path, "PARAM"], capture_output=True, text=True).stdout if "PARAM" in tables else ""
        if param:
            rows = list(csv.DictReader(io.StringIO(param)))
            if rows:
                res.header["call"] = rows[0].get("Call", "")
                res.header["locator"] = rows[0].get("Locator", "")
        for t in tables:
            if not re.match(r"^\d+(MHz|GHz|MHZ|GHZ)?$", t) and t != "LASER":
                continue
            out = subprocess.run(["mdb-export", path, t], capture_output=True, text=True, check=True).stdout
            for r in csv.DictReader(io.StringIO(out)):
                try:
                    rs, ss = _split_rst(r.get("RST_geg", ""))
                    rr, sr = _split_rst(r.get("RST_erh", ""))
                    res.qsos.append(ImportedQso(
                        ts_utc=_ts(r["Datum"], r["Zeit"]), call=r["Rufzeichen"].strip().upper(),
                        locator=(r.get("Locator") or "").strip().upper(), rst_sent=rs, rst_rcvd=rr,
                        serial_sent=int(ss) if ss.isdigit() else None, serial_rcvd=sr,
                        mode=(r.get("Modus") or "SSB").strip(), band=_band_label(t),
                        comment=(r.get("Kommentar") or "").strip(),
                    ))
                except Exception as e:  # noqa: BLE001
                    res.warnings.append(f"{t}: {e}")
            if res.qsos and "band" not in res.header:
                res.header["band"] = _band_label(t)
    finally:
        Path(path).unlink(missing_ok=True)
    return res


# ---------------------------------------------------------------- Call-Listen
def parse_callbook_csv(text: str) -> ImportResult:
    """Call;Locator[;Name] – Trennzeichen ; , Tab oder Leerzeichen."""
    res = ImportResult("callbook")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r"[;,\t]| {2,}| ", line) if p.strip()]
        if len(parts) < 2:
            continue
        call, loc = parts[0].upper(), parts[1].upper()
        if not prefixes.is_plausible_call(call) or not geo.is_valid_locator(loc):
            if call.upper() not in ("CALL", "RUFZEICHEN"):
                res.warnings.append(f"übersprungen: {line[:40]}")
            continue
        res.callbook.append((call, loc, " ".join(parts[2:])))
    return res


# ---------------------------------------------------------------- Dispatcher
def parse_file(filename: str, data: bytes) -> ImportResult:
    ext = Path(filename).suffix.lower()
    if ext == ".mdb":
        return parse_mdb(data)
    text = _decode(data)
    head = text[:300]
    if ext in (".edi", ".reg") or "[REG1TEST" in text[:2000]:
        return parse_edi(text)
    if ext in (".adi", ".adif") or "<eoh>" in text.lower()[:5000] or "<eor>" in text.lower():
        return parse_adif(text)
    if ext == ".exp" or "Win-Contest" in head:
        return parse_dd3ku_exp(text)
    if head.startswith("Version") or re.match(r"^N,\d\d\.\d\d\.\d\d,", text.lstrip()):
        return parse_dd3ku_txt(text)
    return parse_callbook_csv(text)


# ---------------------------------------------------------------- Ergebnislisten (DARC/IARU/UKW-CC)
_CALL_TOKEN = re.compile(r"(?<![A-Z0-9/])((?:[A-Z0-9]{1,3}/)?[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,4}[A-Z](?:/[A-Z0-9]{1,3})?)(?![A-Z0-9/])")
_LOC_TOKEN = re.compile(r"(?<![A-Z0-9])([A-R]{2}[0-9]{2}[A-X]{2})(?![A-Z0-9])")
_NOT_CALLS = {"MHZ", "GHZ", "KHZ", "QSO", "QSOS", "ODX", "PKT", "KM", "NR", "DOK", "UKW", "SSB", "CW", "FM", "PLATZ", "RANG", "NAME", "CALL"}


def html_to_text(data: bytes) -> str:
    text = _decode(data)
    if "<" in text and (">" in text):
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"(?i)</(tr|p|div|li|h\d|table)>|<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</t[dh]>", " \t ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        import html as _html
        text = _html.unescape(text)
    return text


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise ValueError("PDF-Import braucht das Paket pypdf") from e
    import io as _io
    reader = PdfReader(_io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_results_list(text: str) -> ImportResult:
    """Erkennt in Ergebnislisten (DARC, IARU, UKW-Contest-Club …) zeilenweise Rufzeichen + Locator.

    Zeilen ohne 6-stelligen Locator werden ignoriert; pro Zeile zählt das erste plausible Rufzeichen.
    """
    res = ImportResult("results")
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.upper()
        locs = _LOC_TOKEN.findall(line)
        if not locs:
            continue
        call = ""
        for m in _CALL_TOKEN.finditer(line):
            tok = m.group(1)
            if tok in _NOT_CALLS or _LOC_TOKEN.fullmatch(tok) or not prefixes.is_plausible_call(tok):
                continue
            if prefixes.country(tok) == "?" and len(tok) < 4:
                continue
            call = tok
            break
        if not call:
            continue
        core = prefixes.core_call(call)
        if core in seen:
            continue
        seen.add(core)
        pl = prefixes.check_plausibility(call, locs[0])
        res.callbook.append((call, locs[0], ""))
        if not pl["ok"]:
            res.warnings.append(f"{call} {locs[0]}: {pl['msg'].split(' – ')[0]}")
    return res


# ---------------------------------------------------------------- DARC-Contest-Hub (dxhf2.darc.de)
DARC_BASE = "https://dxhf2.darc.de/~ukwlog/"
DARC_INDEX = DARC_BASE + "user.cgi?fc=arch_rukw&form=referat&lang=de&year={year}"


def parse_darc_csv(text: str) -> ImportResult:
    """result.csv des DARC-Contest-Hubs: Rufzeichen (Basis) + Locator sowie ODX Call + ODX Locator."""
    res = ImportResult("darc")
    rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    seen: set[str] = set()
    for r in rows:
        for ck, lk in (("Rufzeichen (Basis)", "Locator"), ("Rufzeichen", "Locator"), ("ODX Call", "ODX Locator")):
            call = (r.get(ck) or "").strip().upper()
            loc = (r.get(lk) or "").strip().upper()
            if not call or not geo.is_valid_locator(loc) or len(loc) < 6 or not prefixes.is_plausible_call(call):
                continue
            core = prefixes.core_call(call)
            if core in seen:
                continue
            seen.add(core)
            res.callbook.append((core, loc, ""))
    return res


def parse_darc_index(html_text: str, year: int) -> list[dict]:
    """Archivseite -> [{id, year, name, status, date, csv}] aus den Tabellenzeilen
    <td>2024-05</td><td>Name</td><td>Status</td><td><a href=…html>Datum</a></td><td><a href=…csv>Datum</a></td>."""
    out: list[dict] = []
    row_re = re.compile(r"<td>\s*(\d{4}-[\w]+)\s*</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>.*?href=\"([^\"]*?/result/result\.csv)\"[^>]*>([^<]*)<", re.S)
    for m in row_re.finditer(html_text):
        cid, name, status, csv_url, date = m.groups()
        if any(o["id"] == cid for o in out):
            continue
        out.append({"id": cid, "year": year, "name": _html_unescape(re.sub(r"<[^>]+>", "", name)).strip(),
                    "status": _html_unescape(re.sub(r"<[^>]+>", "", status)).strip(), "date": date.strip(), "csv": csv_url.strip()})
    return out


def _html_unescape(s: str) -> str:
    import html as _h
    return _h.unescape(s)
