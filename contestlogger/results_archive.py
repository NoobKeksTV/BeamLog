"""Archiv der öffentlichen Contest-Ergebnislisten: alle verfügbaren Listen auflisten, laden und auswerten.

Quellen (jeweils so weit zurück, wie die Veranstalter sie online haben):
  darc-ukw      DARC UKW-Conteste, Contest-Hub dxhf2.darc.de (result.csv, ab 2017): Rufzeichen, Locator, DOK, ODX-Station
  darc-ukw-alt  DARC UKW-Conteste 2008–2016, Textlisten auf darc.de: Rufzeichen, DOK, Locator, ODX-Station
  darc-kw       DARC-KW-Conteste (WAG, WAE, 10 m, Fieldday, Oster-, Weihnachts-, Ausbildungs-, FT4-, RTTY-, Hell-Contest)
                vom Contest-Hub (ab 2014): Rufzeichen und DOK – Kurzwelle tauscht keinen Locator aus
  ok2kkw        Ergebnisse der IARU-Region-1-UKW-Conteste (September, Oktober UHF, Marconi, Subregionals, Mikrowelle) und der
                tschechischen UKW-Conteste, gesammelt von OK2KKW seit 1985: Rufzeichen und Locator
  (Der IARU-Contest-Robot iaru.oevsv.at sperrt automatische Abrufe per robots.txt – dessen CSV-Dateien lassen sich von Hand
   herunterladen und über „Ergebnisliste importieren“ einlesen.)

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
    "ok2kkw": {"name": "IARU-Region-1-UKW-Conteste und OK-Conteste (Archiv OK2KKW, ab 1985)", "group": "IARU", "locator": True},
}
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


def list_entries(fetch: Fetch, source: str, this_year: int) -> list[Entry]:
    if source == "darc-ukw":
        return list_darc_ukw(fetch, list(range(this_year, 2016, -1)))
    if source == "darc-ukw-alt":
        return list_darc_ukw_alt(fetch)
    if source == "darc-kw":
        return list_darc_kw(fetch)
    if source == "ok2kkw":
        return list_ok2kkw(fetch)
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


def parse_entry(fetch: Fetch, e: Entry) -> Parsed:
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
    raise ValueError(f"Unbekannte Quelle: {e.source}")
