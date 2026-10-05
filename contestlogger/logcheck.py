"""Log-Prüfung vor der Abgabe: findet Fehler, die der Auswerter beanstanden würde.

Fehler verhindern den EDI-Export (außer der Admin erzwingt ihn), Hinweise nicht.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import geo, prefixes

RST_RE = re.compile(r"^[1-5][1-9][1-9]?$")
EDI_REQUIRED = [("resp_name", "Name des Verantwortlichen"), ("resp_call", "Rufzeichen des Verantwortlichen"),
                ("resp_address", "Straße"), ("resp_zip", "PLZ"), ("resp_city", "Ort"), ("resp_email", "E-Mail"),
                ("section", "Wertungsgruppe"), ("antenna", "Antenne"), ("power", "Leistung"), ("tx", "Sender")]


def _ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def check_station(contest: dict, station: dict, qsos: list[dict]) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []

    def err(msg: str, q: dict | None = None) -> None:
        errors.append({"qso_id": q["id"] if q else None, "serial": q["serial_sent"] if q else None, "call": q["call"] if q else None, "msg": msg})

    def warn(msg: str, q: dict | None = None) -> None:
        warnings.append({"qso_id": q["id"] if q else None, "serial": q["serial_sent"] if q else None, "call": q["call"] if q else None, "msg": msg})

    # --- Station / Kopfdaten
    if not geo.is_valid_locator(station["locator"]) or len(station["locator"]) < 6:
        err(f"Eigener Locator „{station['locator']}“ ist ungültig oder zu kurz (6 Stellen nötig)")
    if not prefixes.is_plausible_call(station["call"]):
        err(f"Eigenes Rufzeichen „{station['call']}“ ist unplausibel")
    info = station.get("info") or {}
    for key, label in EDI_REQUIRED:
        if not str(info.get(key) or "").strip():
            warn(f"EDI-Kopf: {label} fehlt (Verwaltung → Station bearbeiten)")
    if not qsos:
        err("Das Log enthält keine QSOs")
        return {"errors": errors, "warnings": warnings, "ok": False, "qsos": 0}

    now = datetime.now(timezone.utc) + timedelta(minutes=5)
    start = _ts(contest["start_utc"]) if contest.get("start_utc") else None
    end = _ts(contest["end_utc"]) if contest.get("end_utc") else None
    ordered = sorted(qsos, key=lambda q: (q["ts_utc"], q["id"]))
    exchange = contest.get("exchange") or "serial"
    if "dok" in exchange and not str(info.get("exchange") or "").strip():
        warn("Eigener DOK/OV fehlt (Verwaltung → Station bearbeiten → EDI-Angaben, Feld „Austausch“) – steht im EDI-Kopf als PExch")
    serials: dict[int, dict] = {}
    prev_ts = None
    for q in ordered:
        if not prefixes.is_plausible_call(q["call"]):
            err("Rufzeichen unplausibel", q)
        if "dok" in exchange and not (q.get("exch_rcvd") or "").strip():
            warn("DOK/OV fehlt (Austausch dieses Contests)", q)
        if not q["locator"]:
            err("Locator fehlt (0 Punkte, wird vom Auswerter gestrichen)", q)
        elif not geo.is_valid_locator(q["locator"]):
            err(f"Locator „{q['locator']}“ ungültig", q)
        elif len(q["locator"]) < 6:
            warn(f"Locator „{q['locator']}“ nur 4-stellig – Entfernung ist ungenau", q)
        if not RST_RE.match(str(q["rst_sent"])):
            err(f"RST gegeben „{q['rst_sent']}“ ungültig", q)
        if not RST_RE.match(str(q["rst_rcvd"])):
            err(f"RST erhalten „{q['rst_rcvd']}“ ungültig", q)
        if not str(q["serial_rcvd"]).strip():
            warn("Empfangene Nummer fehlt", q)
        elif not str(q["serial_rcvd"]).isdigit():
            err(f"Empfangene Nummer „{q['serial_rcvd']}“ ist keine Zahl", q)
        t = _ts(q["ts_utc"])
        if t > now:
            err("Zeit liegt in der Zukunft", q)
        if start and t < start:
            err(f"QSO liegt vor Contest-Beginn ({contest['start_utc'][:16].replace('T', ' ')} UTC)", q)
        if end and t > end:
            err(f"QSO liegt nach Contest-Ende ({contest['end_utc'][:16].replace('T', ' ')} UTC)", q)
        if q["serial_sent"] in serials:
            err(f"Gesendete Nummer {q['serial_sent']:03d} doppelt vergeben (auch bei {serials[q['serial_sent']]['call']})", q)
        serials[q["serial_sent"]] = q
        if prev_ts and q["serial_sent"] < prev_ts[1] and not q["dupe"]:
            warn(f"Nummer {q['serial_sent']:03d} kommt zeitlich nach Nummer {prev_ts[1]:03d} – Reihenfolge prüfen", q)
        prev_ts = (t, q["serial_sent"])
        if q["dupe"]:
            warn("Doppel-QSO (wird mit 0 Punkten als Dupe exportiert)", q)
        pl = prefixes.check_plausibility(q["call"], q["locator"]) if q["locator"] else {"ok": True}
        if not pl["ok"]:
            err(pl["msg"], q)
        if q["km"] > 1500:
            warn(f"{q['km']} km – ungewöhnlich weit, Locator prüfen", q)
    nums = sorted(serials)
    missing = [n for n in range(nums[0], nums[-1] + 1) if n not in serials]
    if missing:
        warn(f"Lücken in den gesendeten Nummern: {', '.join(f'{n:03d}' for n in missing[:20])}{' …' if len(missing) > 20 else ''}")
    if nums[0] != 1:
        warn(f"Erste gesendete Nummer ist {nums[0]:03d}, nicht 001")
    return {"errors": errors, "warnings": warnings, "ok": not errors, "qsos": len(qsos)}
