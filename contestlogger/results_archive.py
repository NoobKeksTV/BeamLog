"""Archiv der öffentlichen Contest-Ergebnislisten: alle verfügbaren Listen auflisten, laden und auswerten.

Quellen (jeweils so weit zurück, wie die Veranstalter sie online haben):
  darc-ukw      DARC UKW-Conteste, Contest-Hub dxhf2.darc.de (result.csv, ab 2017): Rufzeichen, Locator, DOK, ODX-Station
  darc-ukw-alt  DARC UKW-Conteste 2008–2016, Textlisten auf darc.de: Rufzeichen, DOK, Locator, ODX-Station
  darc-kw       DARC-KW-Conteste (WAG, WAE, 10 m, Fieldday, Oster-, Weihnachts-, Ausbildungs-, FT4-, RTTY-, Hell-Contest)
                vom Contest-Hub (ab 2014): Rufzeichen und DOK – Kurzwelle tauscht keinen Locator aus
  ok2kkw        Ergebnisse der IARU-Region-1-UKW-Conteste (September, Oktober UHF, Marconi, Subregionals, Mikrowelle) und der
                tschechischen UKW-Conteste, gesammelt von OK2KKW seit 1985: Rufzeichen und Locator
  iaru-robot    Offizielle Ergebnisse der IARU-Region-1-UKW-Conteste vom Contest-Robot iaru.oevsv.at (ab 2019, CSV-Export je Contest:
                Rufzeichen und Locator) sowie dessen Gesamtliste vhf.csv (Rufzeichen;Locator aller bisherigen Teilnehmer).
  darc-kw-logs  Einzel-Logs der DARC-KW-Conteste („Open Log“, ab 2017): je Teilnehmer das Cabrillo-Log – eigene Station mit
                Locator (GRID-LOCATOR) und DOK, dazu alle deutschen QSO-Partner mit empfangenem DOK
  iaru-robot-logs  dazu die Einzel-Logs aller Teilnehmer eines Contests (je Teilnehmer eine Seite mit allen QSOs: Partner-Rufzeichen
                und -Locator) – erfasst auch Stationen, die selbst kein Log eingereicht haben. Vom Robot als „unique“ (vermutlich
                verhört) oder ungültig markierte QSOs werden nicht übernommen. Abruf mit Erlaubnis des Betreibers.

Jeder Eintrag einer Quelle ist eine „Liste“ (ein Contest eines Jahres) mit eindeutiger id; geladen wird über fetch(url) -> bytes,
damit sich Netzwerk und Auswertung getrennt testen lassen. Ergebnis je Liste: [(Rufzeichen, Locator, DOK)], Datum der Liste.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from typing import Callable

from . import geo, importers, prefixes

Fetch = Callable[[str], bytes]

HUB = "https://dxhf2.darc.de"
DARC_WWW = "https://www.darc.de"
UKW_ALT_PAGE = DARC_WWW + "/der-club/referate/conteste/ukw/ukw-archiv/"
# KW-Conteste des Contest-Hubs: Kennung (Pfad ~<key>) -> Name
DARC_KW = {
    "waglog": "WAG – Worked All Germany", "d10mlog": "DARC 10m-Contest", "fdcwlog": "Fieldday CW", "fdssblog": "Fieldday SSB",
    "easterlog": "Ostercontest", "xmaslog": "Weihnachtswettbewerb", "waecwlog": "WAE DX CW", "waessblog": "WAE DX SSB",
    "waerttylog": "WAE DX RTTY", "aclog": "Ausbildungscontest", "accwlog": "Ausbildungscontest CW", "ft4log": "FT4-Contest",
    "shortrylog": "RTTY-Kurzcontest", "shorthelllog": "Hell-Kurzcontest",
}
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "mrz": 3, "apr": 4, "mai": 5, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10,
          "nov": 11, "dez": 12, "dec": 12}

SOURCES = {
    "darc-ukw": {"name": "DARC UKW-Conteste (Contest-Hub, ab 2017)", "group": "DARC", "locator": True},
    "darc-ukw-alt": {"name": "DARC UKW-Conteste 2008–2016 (Archiv darc.de)", "group": "DARC", "locator": True},
    "darc-kw": {"name": "DARC-KW-Conteste (Contest-Hub, ab 2014) – nur Rufzeichen + DOK", "group": "DARC", "locator": False},
    "darc-kw-logs": {"name": "DARC-KW-Conteste: Einzel-Logs aller Teilnehmer (eigener Locator + DOK, DOKs aller deutschen QSO-Partner, ab 2017) – "
                             "dauert 5–20 Minuten je Contest und Jahr", "group": "DARC", "locator": False},
    "ok2kkw": {"name": "IARU-Region-1-UKW-Conteste und OK-Conteste (Archiv OK2KKW, ab 1985)", "group": "IARU", "locator": True},
    "iaru-robot": {"name": "IARU-Region-1-UKW-Conteste (Contest-Robot iaru.oevsv.at, ab 2019)", "group": "IARU", "locator": True},
    "iaru-robot-logs": {"name": "IARU-Region-1-UKW-Conteste: Einzel-Logs aller Teilnehmer (QSO-Partner mit Locator, auch Stationen ohne eigenes Log) – "
                                "dauert 10–30 Minuten je Contest", "group": "IARU", "locator": True},
}


class Cancelled(Exception):
    """Import einer Liste abgebrochen (über den Fortschritts-Rückruf)."""


PAGE_WORKERS = 8  # gleichzeitige Abrufe von Einzelseiten innerhalb einer Liste (je Server begrenzt der Abrufer zusätzlich)
IARU_ROBOT = "https://iaru.oevsv.at"
OK2KKW = "https://www.ok2kkw.com/"
OK2KKW_INDEX = OK2KKW + "contesting_en.htm"
_OK2_SKIP = re.compile(r"contesting|winn\.htm|eme_contesting|log_cz|contests2_cz|statistika|main\.css", re.I)


@dataclass
class Entry:
    """Eine Ergebnisliste. url: was geladen wird; extra: weitere Teil-Seiten (z. B. Durchgänge eines Jahres)."""
    id: str
    source: str
    label: str
    year: int
    url: str
    when: str = ""  # Datum der Liste (JJJJ-MM-TT) – neuere Angaben gewinnen in der Stationsdatenbank
    group: str = ""  # Unterpunkt in der Oberfläche (z. B. Contest-Name)

    def as_dict(self) -> dict:
        return {"id": self.id, "source": self.source, "label": self.label, "year": self.year, "url": self.url, "when": self.when, "group": self.group}


@dataclass
class Parsed:
    rows: list[tuple[str, str, str]] = field(default_factory=list)  # (Rufzeichen, Locator oder "", DOK oder "")
    pages: int = 1


def _text(b: bytes) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1", "replace")


def _clean(cell: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", cell)).replace("\xa0", " ").strip()


# ---------------------------------------------------------------------------------------------- Aufzählen
def list_darc_ukw(fetch: Fetch, years: list[int]) -> list[Entry]:
    out: list[Entry] = []
    for y in years:
        for c in importers.parse_darc_index(_text(fetch(importers.DARC_INDEX.format(year=y))), y):
            month = c["id"][5:7] if re.fullmatch(r"\d{4}-\d{2}", c["id"]) else "06"
            out.append(Entry(f"darc-ukw:{c['id']}", "darc-ukw", f"{c['id']} {c['name']}", y, c["csv"], f"{y}-{month}-01", f"UKW {y}"))
    return out


def list_darc_ukw_alt(fetch: Fetch) -> list[Entry]:
    """Textlisten 2008–2016 (je Contest eine Kurz- und eine ausführliche Fassung „…a.txt“ – die ausführliche enthält die ODX-Station)."""
    page = _text(fetch(UKW_ALT_PAGE))
    links = sorted(set(re.findall(r'href="(/fileadmin/[^"]*?/Erg(\d{4})/([a-z]+|\d{2})-\d{4}(a?)\.txt)"', page)))  # „mai-2012.txt“ oder „05-2016.txt“
    by_key: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    for url, year, mon, full in links:
        key = (year, mon)
        if key not in by_key or full:  # die ausführliche Fassung bevorzugen
            by_key[key] = (url, year, mon, full)
    out = []
    for (year, mon), (url, _, _, _) in sorted(by_key.items()):
        m = int(mon) if mon.isdigit() else MONTHS.get(mon[:3], 6)
        out.append(Entry(f"darc-ukw-alt:{year}-{m:02d}", "darc-ukw-alt", f"{year}-{m:02d} UKW-Contest ({mon})", int(year), DARC_WWW + url,
                         f"{year}-{m:02d}-01", f"UKW {year}"))
    return out


def kw_url(key: str, year: int, edition: str = "") -> str:
    return f"{HUB}/~{key}/arch_res.cgi?form=referat&lang=de&year={year}" + (f"&edition={edition}" if edition else "")


def list_darc_kw(fetch: Fetch, keys: list[str] | None = None) -> list[Entry]:
    out: list[Entry] = []
    for key in keys or list(DARC_KW):
        page = _text(fetch(f"{HUB}/~{key}/arch_res.cgi?form=referat&lang=de"))
        sel = re.search(r'<select name="year".*?</select>', page, re.S)
        years = sorted({int(y) for y in re.findall(r'value="(\d{4})"', sel.group(0) if sel else "")}, reverse=True)
        for y in years:
            out.append(Entry(f"darc-kw:{key}:{y}", "darc-kw", f"{DARC_KW.get(key, key)} {y}", y, kw_url(key, y), f"{y}-01-01", DARC_KW.get(key, key)))
    return out


def _ok2_year(url: str, text: str) -> int:
    m = re.search(r"/contests/(\d\d)/", url) or re.search(r"/00003016/[a-z0-9]*?(\d\d)/", url)
    if m:
        yy = int(m.group(1)[:2])
        return 1900 + yy if yy >= 70 else 2000 + yy
    m = re.search(r"(19[89]\d|20[0-3]\d)", url + " " + text)
    return int(m.group(1)) if m else 0


def list_ok2kkw(fetch: Fetch) -> list[Entry]:
    page = fetch(OK2KKW_INDEX).decode("cp1250", "replace")
    out: list[Entry] = []
    seen: set[str] = set()
    for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S | re.I):
        href = href.strip()
        if href.startswith(("mailto:", "#")) or not re.search(r"\.(html?|pdf|txt)$", href, re.I) or _OK2_SKIP.search(href):
            continue
        if href.startswith("http"):
            if "ok2kkw.com" not in href:
                continue
            url = re.sub(r"^https?://(www\.)?ok2kkw\.com/", OK2KKW, href)
        else:
            url = OK2KKW + href.lstrip("./")
        if url in seen:
            continue
        seen.add(url)
        text = re.sub(r"<[^>]+>|&nbsp;|\s+", " ", label).strip()
        year = _ok2_year(url, text)
        name = url.rsplit("/", 1)[1]
        out.append(Entry(f"ok2kkw:{url.split('ok2kkw.com/', 1)[1]}", "ok2kkw", f"{year or '?'} {text or name} ({name})", year, url,
                         f"{year}-09-01" if year else "", f"IARU / OK {year}" if year else "IARU / OK"))
    return sorted(out, key=lambda e: (-e.year, e.label))


def list_iaru_robot(fetch: Fetch) -> list[Entry]:
    """Contest-Liste des Robots (seitenweise, start=1, 31, …): nur Conteste mit Ergebnis-CSV; dazu die Gesamtliste vhf.csv."""
    out: list[Entry] = []
    todo, seen_pages = [1], set()
    while todo:
        start = todo.pop(0)
        if start in seen_pages:
            continue
        seen_pages.add(start)
        page = _text(fetch(f"{IARU_ROBOT}/v_upld/prg_list.php?start={start}"))
        todo += [int(n) for n in re.findall(r"prg_list\.php\?start=(\d+)", page) if int(n) not in seen_pages]
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
            m = re.search(r"prg_xcsv\.php\?cont_id=(\d+)", row)
            if not m:
                continue  # Contest noch in der Auswertung
            cells = [re.sub(r"\s+", " ", _clean(c)) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            name = cells[0] if cells else f"Contest {m.group(1)}"
            date = next((c[:10] for c in cells[1:3] if re.match(r"\d{4}-\d{2}-\d{2}", c)), "")
            year = int(date[:4]) if date else int((re.search(r"(20\d\d)", name) or re.search(r"(\d{4})", "0000")).group(1))
            cid = m.group(1)
            if any(e.id == f"iaru-robot:{cid}" for e in out):
                continue
            out.append(Entry(f"iaru-robot:{cid}", "iaru-robot", f"{date} {name}".strip(), year, f"{IARU_ROBOT}/v_upld/prg_xcsv.php?cont_id={cid}",
                             date, f"IARU R1 {year}"))
    out.sort(key=lambda e: (-e.year, e.when, e.label))
    out.insert(0, Entry("iaru-robot:vhf.csv", "iaru-robot", "Gesamtliste vhf.csv (alle Teilnehmer, Rufzeichen;Locator)", 0,
                        f"{IARU_ROBOT}/cron/vhf.csv", "", "IARU R1 Gesamtliste"))
    return out


def list_iaru_robot_logs(fetch: Fetch) -> list[Entry]:
    return [Entry(e.id.replace("iaru-robot:", "iaru-robot-logs:"), "iaru-robot-logs", f"{e.label} – Einzel-Logs", e.year, e.url, e.when,
                  f"IARU R1 {e.year} – Einzel-Logs") for e in list_iaru_robot(fetch) if e.year]


def _table_rows(page: str) -> tuple[list[str], list[list[str]]]:
    heads = [re.sub(r"\s+", " ", _clean(h)) for h in re.findall(r"<th[^>]*>(.*?)</th>", page, re.S | re.I)]
    rows = [[re.sub(r"\s+", " ", _clean(c)) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S | re.I)]
            for r in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I)]
    return heads, rows


def parse_iaru_qsos(page: str) -> list[tuple[str, str, str]]:
    """QSO-Seite eines Teilnehmers: Partner-Rufzeichen und -Locator; ohne „unique“ (Rufzeichen nur in diesem Log – meist verhört)
    und ohne QSOs, die beim Gegencheck 0 Punkte bekamen."""
    heads, rows = _table_rows(page)
    idx = {h: i for i, h in enumerate(heads)}
    ci, li = idx.get("RX Call"), idx.get("RX WWL")
    if ci is None or li is None:
        return []
    ui = next((i for h, i in idx.items() if h.startswith("Unique")), None)
    xi = idx.get("Cross checked score")
    mi = idx.get("Mode")
    out = []
    for r in rows:
        if len(r) <= max(ci, li):
            continue
        if ui is not None and ui < len(r) and r[ui].lower().startswith("yes"):
            continue
        if xi is not None and xi < len(r) and r[xi].strip() == "0":
            continue
        call, loc = r[ci].upper().replace(" ", ""), r[li].upper()
        if mi is not None and mi < len(r) and re.search(r"FT\d|MGM|JT|MSK|Q65", r[mi].upper()) and loc.endswith("MM"):
            continue  # Digimodes tauschen nur das Großfeld aus – „MM“ ist aufgefüllt (Feldmitte), kein echter Locator
        if importers._CALL_TOKEN.fullmatch(call) and prefixes.is_plausible_call(call) and geo.is_valid_locator(loc) and len(loc) >= 6:  # noqa: SLF001
            out.append((call, loc, ""))
    return out


class FairSlots:
    """Wie ein Semaphor, aber der Reihe nach (FIFO): Laufen mehrere Listen gegen denselben Server, kommt jede gleichmäßig dran –
    ein normaler Semaphor lässt einzelne Seiten minutenlang warten, während andere Threads ständig wieder zugreifen."""

    def __init__(self, n: int):
        import collections
        import threading
        self.free, self.queue, self.cv = n, collections.deque(), threading.Condition()

    def __enter__(self):
        me = object()
        with self.cv:
            self.queue.append(me)
            while self.queue[0] is not me or not self.free:
                self.cv.wait()
            self.queue.popleft()
            self.free -= 1
            self.cv.notify_all()  # der Nächste in der Schlange darf prüfen, ob noch ein Platz frei ist

    def __exit__(self, *exc):
        with self.cv:
            self.free += 1
            self.cv.notify_all()


def fetch_many(fetch: Fetch, urls: list[str], progress=None, workers: int = 0) -> list[str]:
    """Viele Einzelseiten gleichzeitig laden (jede braucht auf den Servern rund eine Sekunde); Ergebnisse in der Reihenfolge der URLs.
    progress(n, gesamt) nach jeder Seite – gibt er False zurück, wird abgebrochen (Cancelled)."""
    from concurrent.futures import ThreadPoolExecutor
    import threading
    lock, state = threading.Lock(), {"n": 0, "stop": False}

    def one(url: str) -> str:
        if state["stop"]:
            return ""
        try:
            page = _text(fetch(url))
        except Exception:  # noqa: BLE001 – eine fehlende Einzelseite soll nicht die ganze Liste kippen
            page = ""
        with lock:
            state["n"] += 1
            n = state["n"]
        if progress and progress(n, len(urls)) is False:
            state["stop"] = True
        return page

    with ThreadPoolExecutor(max_workers=workers or PAGE_WORKERS) as pool:
        pages = list(pool.map(one, urls))
    if state["stop"]:
        raise Cancelled
    return pages


def parse_iaru_logs(fetch: Fetch, cid: str, progress=None) -> Parsed:
    """Alle Teilnehmer eines Contests (eigene Station + Locator) und deren QSO-Partner."""
    part = _text(fetch(f"{IARU_ROBOT}/v_part/prg_list.php?reset=1&start=1&master_v_part_cont_id={cid}&master_v_part_vw=v_upld"))
    rows: list[tuple[str, str, str]] = []
    pids: list[str] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", part, re.S):
        m = re.search(r"master_v_qsos_part_id=(\d+)", tr)
        if not m or m.group(1) in pids:
            continue
        pids.append(m.group(1))
        cells = [re.sub(r"\s+", " ", _clean(c)) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        call = next((c.upper() for c in cells if importers._CALL_TOKEN.fullmatch(c.upper() or "-")), "")  # noqa: SLF001
        loc = next((c.upper() for c in cells if importers._LOC_TOKEN.fullmatch(c.upper() or "-")), "")  # noqa: SLF001
        if call and loc:
            rows.append((call, loc, ""))
    urls = [f"{IARU_ROBOT}/v_qsos/prg_list.php?reset=1&start=1&master_v_qsos_part_id={pid}&master_v_qsos_vw=v_part" for pid in pids]
    for page in fetch_many(fetch, urls, progress):
        rows += parse_iaru_qsos(page)
    return Parsed(rows, 1 + len(pids))


def parse_iaru_csv(text: str) -> list[tuple[str, str, str]]:
    """Ergebnis-CSV des Robots (Spalten „Call“ und „WWL“) oder die Gesamtliste vhf.csv („CALL“;„LOCATOR“)."""
    import csv
    import io
    rows: list[tuple[str, str, str]] = []
    first = text.lstrip()[:400]
    if ";" in first.splitlines()[0] if first else False:
        for r in csv.reader(io.StringIO(text), delimiter=";"):
            if len(r) >= 2:
                rows.append((r[0].strip().upper(), r[1].strip().upper(), ""))
    else:
        for r in csv.DictReader(io.StringIO(text)):
            rows.append(((r.get("Call") or "").strip().upper(), (r.get("WWL") or "").strip().upper(), ""))
    return [(c, loc, d) for c, loc, d in rows if c and importers._CALL_TOKEN.fullmatch(c) and prefixes.is_plausible_call(c)  # noqa: SLF001
            and not c[0] == "0" and prefixes.country(c) != "?" and geo.is_valid_locator(loc) and len(loc) >= 6]


def _olog_form(fetch: Fetch, key: str) -> tuple[str, list[int], list[str]]:
    """Open-Log-Formular eines KW-Contests: interner Contest-Name, Jahre mit Logs, Durchgänge (FT4, AC-CW, RTTY-Kurz)."""
    page = _text(fetch(f"{HUB}/~{key}/user.cgi?fc=req_olog&form=referat&lang=de"))
    contest = (re.search(r'name="contest" value="([^"]+)"', page) or re.search(r"(x)", "x")).group(1)
    sel = re.search(r'<select name="jahr".*?</select>', page, re.S)
    years = sorted({int(y) for y in re.findall(r'value="(\d{4})"', sel.group(0) if sel else "")}, reverse=True)
    ed = re.search(r'<select name="edition".*?</select>', page, re.S)
    editions = re.findall(r'value="([^"]+)"', ed.group(0)) if ed else []
    return contest, years, editions


def list_darc_kw_logs(fetch: Fetch, keys: list[str] | None = None) -> list[Entry]:
    out: list[Entry] = []
    for key in keys or list(DARC_KW):
        contest, years, editions = _olog_form(fetch, key)
        if not contest or contest == "x":
            continue
        name = DARC_KW.get(key, key)
        for y in years:
            url = f"{HUB}/~{key}/user.cgi?fc=req_olog&contest={contest}&form=referat&lang=de&status=show&jahr={y}"
            out.append(Entry(f"darc-kw-logs:{key}:{y}", "darc-kw-logs", f"{name} {y} – Einzel-Logs", y, url, f"{y}-01-01",
                             f"{name} – Einzel-Logs"))
            if editions:
                out[-1].url += "&editions=" + ",".join(editions)
    return out


def parse_cabrillo(text: str) -> list[tuple[str, str, str]]:
    """Cabrillo-Log (Open Log): eigene Station (CALLSIGN, GRID-LOCATOR, DOK aus SPECIFIC/LOCATION) und die QSO-Partner mit
    empfangenem DOK – nur bei deutschen Partnern, ausländische Stationen senden eine Nummer."""
    rows: list[tuple[str, str, str]] = []
    head = {}
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^([A-Z-]+):\s*(.*)$", line)
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag != "QSO":
            head.setdefault(tag, val.upper())
            continue
        toks = val.upper().split()
        if len(toks) < 6:
            continue
        mycall = toks[4]
        # Partner = erstes Rufzeichen nach dem eigenen; danach RST und Austausch
        for i in range(5, len(toks)):
            t = toks[i]
            if t != mycall and importers._CALL_TOKEN.fullmatch(t) and prefixes.is_plausible_call(t) and not re.fullmatch(r"[A-Z]\d{2}", t):  # noqa: SLF001
                exch = toks[i + 1:i + 4]
                dok = next((x for x in exch if re.fullmatch(r"[A-Z]\d{2}|(?=.*[A-Z])(?=.*\d)[A-Z0-9]{3,8}", x)
                            and not re.fullmatch(r"[A-R]{2}\d{2}([A-X]{2})?", x) and not re.fullmatch(r"[+-]?\d+", x)), "")
                if prefixes.country(t) != "Deutschland":
                    dok = ""
                rows.append((t, "", dok))
                break
    call = head.get("CALLSIGN", "")
    loc = head.get("GRID-LOCATOR", "")
    own_dok = next((v for k, v in head.items() if k in ("SPECIFIC", "LOCATION") and re.fullmatch(r"[A-Z]\d{2}", v or "")), "")
    if call and importers._CALL_TOKEN.fullmatch(call):  # noqa: SLF001
        rows.insert(0, (call, loc if geo.is_valid_locator(loc) and len(loc) >= 6 else "", own_dok))
    return rows


def parse_darc_kw_logs(fetch: Fetch, e: Entry, progress=None) -> Parsed:
    """Teilnehmer aus der Ergebnisliste des Jahres (bei mehreren Durchgängen je Durchgang), dann je Teilnehmer das Open Log."""
    key = e.id.split(":")[1]
    base, _, eds = e.url.partition("&editions=")
    editions = [x for x in eds.split(",") if x] or [""]
    urls: list[str] = []
    for ed in editions:
        calls = list(dict.fromkeys(c for c, _, _ in parse_html_tables(_text(fetch(kw_url(key, e.year, ed))))))
        urls += [f"{base}&edition={ed or 2000}&call={c}&Show=1" for c in calls]
    rows: list[tuple[str, str, str]] = []
    for page in fetch_many(fetch, urls, progress):
        if "QSO:" in page:
            rows += parse_cabrillo(importers.html_to_text(page.encode("utf-8")))
    return Parsed(rows, len(urls) + len(editions))


def list_entries(fetch: Fetch, source: str, this_year: int) -> list[Entry]:
    if source == "darc-ukw":
        return list_darc_ukw(fetch, list(range(this_year, 2016, -1)))
    if source == "darc-ukw-alt":
        return list_darc_ukw_alt(fetch)
    if source == "darc-kw":
        return list_darc_kw(fetch)
    if source == "ok2kkw":
        return list_ok2kkw(fetch)
    if source == "iaru-robot":
        return list_iaru_robot(fetch)
    if source == "iaru-robot-logs":
        return list_iaru_robot_logs(fetch)
    if source == "darc-kw-logs":
        return list_darc_kw_logs(fetch)
    raise ValueError(f"Unbekannte Quelle: {source}")


# ---------------------------------------------------------------------------------------------- Auswerten
def parse_html_tables(page: str) -> list[tuple[str, str, str]]:
    """Ergebnistabellen (Kopfzeile mit „Rufzeichen“/„Call“, optional „DOK“ und „Locator/Loc/WWL“) -> Zeilen."""
    rows: list[tuple[str, str, str]] = []
    for table in re.findall(r"<table.*?</table>", page, re.S | re.I):
        heads = [_clean(h).lower() for h in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S | re.I)]
        ci = next((i for i, h in enumerate(heads) if h in ("rufzeichen", "call", "callsign", "rufz.")), None)
        if ci is None:
            continue
        di = next((i for i, h in enumerate(heads) if h in ("dok", "ov", "dok/ov")), None)
        li = next((i for i, h in enumerate(heads) if h in ("locator", "loc", "loc.", "wwl", "qth", "qth-locator")), None)
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I):
            cells = [_clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
            if len(cells) <= ci:
                continue
            call = cells[ci].upper().replace(" ", "")
            if not prefixes.is_plausible_call(call):
                continue
            loc = cells[li].upper() if li is not None and li < len(cells) else ""
            dok = importers._dok_value(cells[di]) if di is not None and di < len(cells) else ""  # noqa: SLF001
            rows.append((call, loc if geo.is_valid_locator(loc) and len(loc) >= 6 else "", dok if re.fullmatch(r"[A-Z0-9]{2,8}", dok or "") else ""))
    return rows


def parse_text_pairs(text: str) -> list[tuple[str, str, str]]:
    """Textlisten: in jeder Zeile alle Paare „Rufzeichen … Locator“ (eigene Station und ODX-Station), DOK direkt nach dem Rufzeichen."""
    rows: list[tuple[str, str, str]] = []
    for raw in text.splitlines():
        toks = raw.upper().split()
        skip: set[int] = set()  # Position eines DOK (Sonder-DOKs wie „40BN“ sähen sonst wie Rufzeichen aus)
        for i, tok in enumerate(toks):
            if i in skip or importers._LOC_TOKEN.fullmatch(tok) or not importers._CALL_TOKEN.fullmatch(tok) or tok in importers._NOT_CALLS:  # noqa: SLF001
                continue
            if not prefixes.is_plausible_call(tok):
                continue
            nxt = toks[i + 1:i + 3]
            loc = ""
            for k, t in enumerate(toks[i + 1:i + 6]):  # Locator bis zu 5 Spalten weiter (z. B. „Call Punkte QSOs Loc“), nie über das nächste Rufzeichen hinaus
                if importers._LOC_TOKEN.fullmatch(t):  # noqa: SLF001
                    loc = t
                    break
                if k > 0 and importers._CALL_TOKEN.fullmatch(t) and prefixes.is_plausible_call(t) and not re.fullmatch(r"[A-Z]\d{2}", t):  # noqa: SLF001
                    break
            if not loc:
                continue
            dok = nxt[0] if nxt and re.fullmatch(r"[A-Z]\d{2}|[A-Z0-9]{3,8}", nxt[0]) and nxt[0] != loc and not re.fullmatch(r"\d+", nxt[0]) else ""
            if dok:
                skip.add(i + 1)
            rows.append((tok, loc, dok if dok and not importers._LOC_TOKEN.fullmatch(dok) else ""))  # noqa: SLF001
    return rows


def parse_entry(fetch: Fetch, e: Entry, progress=None) -> Parsed:
    """progress(n, gesamt) bei Listen aus vielen Einzelseiten; gibt er False zurück, wird mit Cancelled abgebrochen."""
    if e.source == "darc-ukw":
        res = importers.parse_darc_csv(_text(fetch(e.url)))
        return Parsed([(c, loc, res.doks.get(prefixes.core_call(c), "")) for c, loc, _ in res.callbook])
    if e.source == "darc-ukw-alt":
        return Parsed(parse_text_pairs(_text(fetch(e.url))))
    if e.source == "darc-kw":
        page = _text(fetch(e.url))
        rows = parse_html_tables(page)
        # Mehrere Durchgänge im Jahr (FT4, RTTY-/Hell-Kurzcontest, Ausbildungscontest CW): alle weiteren Durchgänge mitnehmen
        sel = re.search(r'<select name="edition".*?</select>', page, re.S)
        pages = 1
        if sel:
            chosen = re.search(r'selected="selected" value="([^"]+)"', sel.group(0))
            key = e.id.split(":")[1]
            for ed in re.findall(r'value="([^"]+)"', sel.group(0)):
                if chosen and ed == chosen.group(1):
                    continue
                rows += parse_html_tables(_text(fetch(kw_url(key, e.year, ed))))
                pages += 1
        return Parsed(rows, pages)
    if e.source == "ok2kkw":
        data = fetch(e.url)
        if e.url.lower().endswith(".pdf"):
            text = importers.pdf_to_text(data)
        else:
            text = data.decode("cp1250", "replace") if b"charset=windows-1250" in data[:3000].lower() or b"charset=iso-8859-2" in data[:3000].lower() else _text(data)
            text = importers.html_to_text(text.encode("utf-8")) if "<" in text else text
        return Parsed(parse_text_pairs(text))
    if e.source == "iaru-robot":
        return Parsed(parse_iaru_csv(fetch(e.url).decode("iso-8859-1")))
    if e.source == "iaru-robot-logs":
        return parse_iaru_logs(fetch, e.id.split(":", 1)[1], progress)
    if e.source == "darc-kw-logs":
        return parse_darc_kw_logs(fetch, e, progress)
    raise ValueError(f"Unbekannte Quelle: {e.source}")
