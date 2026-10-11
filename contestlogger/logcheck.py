"""Log-Prüfung vor der Abgabe: findet Fehler, die der Auswerter beanstanden würde.

Fehler verhindern den EDI-Export (außer der Admin erzwingt ihn), Hinweise nicht.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import geo, prefixes

RST_RE = re.compile(r"^[1-5][1-9][1-9]?$")


def norm_rst(value) -> str:
    """RST mit führenden Nullen („059“, „0599“) still auf die übliche Form bringen; alles andere bleibt wie es ist."""
    s = str(value if value is not None else "").strip()
    t = s.lstrip("0")
    return t if RST_RE.match(t) else s
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
NUM_RE = re.compile(r"^\d+([.,]\d+)?$")
# Wertungsgruppen, die die IARU-Region-1-/DARC-Auswerter kennen (REG1TEST PSect); frei eingetragene Texte geben nur einen Hinweis
KNOWN_SECTIONS = {"SINGLE", "MULTI", "SINGLE-OP", "MULTI-OP", "SO", "MO", "6H", "LOW POWER", "LP", "QRP", "SOLP", "SOHP", "MOLP", "MOHP",
                  "SINGLE OPERATOR", "MULTI OPERATOR", "NEWCOMER", "YL", "OPEN", "LOW", "HIGH"}
EDI_REQUIRED = [("resp_name", "Name des Verantwortlichen"), ("resp_call", "Rufzeichen des Verantwortlichen"),
                ("resp_address", "Straße"), ("resp_zip", "PLZ"), ("resp_city", "Ort"), ("resp_email", "E-Mail"),
                ("section", "Wertungsgruppe"), ("antenna", "Antenne"), ("power", "Leistung"), ("tx", "Sender")]


def _ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def check_station(contest: dict, station: dict, qsos: list[dict]) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []

    # Jeder Befund trägt für die Vergleichsansicht: Feld, geloggter Wert, erwarteter Wert/Grund (kurz)
    def _item(msg: str, q: dict | None, field: str, logged: str, expected: str) -> dict:
        return {"qso_id": q["id"] if q else None, "serial": q["serial_sent"] if q else None, "call": q["call"] if q else None,
                "ts": q["ts_utc"] if q else None, "msg": msg, "field": field, "logged": logged, "expected": expected}

    def err(msg: str, q: dict | None = None, field: str = "", logged: str = "", expected: str = "") -> None:
        errors.append(_item(msg, q, field, logged, expected))

    def warn(msg: str, q: dict | None = None, field: str = "", logged: str = "", expected: str = "") -> None:
        warnings.append(_item(msg, q, field, logged, expected))

    # --- Station / Kopfdaten
    if not geo.is_valid_locator(station["locator"]) or len(station["locator"]) < 6:
        err(f"Eigener Locator „{station['locator']}“ ist ungültig oder zu kurz (6 Stellen nötig)")
    if not prefixes.is_plausible_call(station["call"]):
        err(f"Eigenes Rufzeichen „{station['call']}“ ist unplausibel")
    info = station.get("info") or {}
    for key, label in EDI_REQUIRED:
        if not str(info.get(key) or "").strip():
            warn(f"EDI-Kopf: {label} fehlt (Verwaltung → Station bearbeiten)")
    sect = str(info.get("section") or "").strip()
    if sect and sect.upper() not in KNOWN_SECTIONS and not sect.isdigit():
        warn(f"EDI-Kopf: Wertungsgruppe „{sect}“ ist keine übliche Bezeichnung (Single, Multi, 6H, Low Power, QRP oder die Nummer laut Ausschreibung)")
    if "MULTI" in sect.upper() and not str(info.get("operators") or "").strip():
        warn("EDI-Kopf: Multi-Operator ohne Operatorenliste (MOpe1)")
    email = str(info.get("resp_email") or "").strip()
    if email and not EMAIL_RE.match(email):
        warn(f"EDI-Kopf: E-Mail „{email}“ sieht ungültig aus")
    for key, label in (("power", "Leistung"), ("antenna_height", "Antennenhöhe"), ("asl", "Höhe über NN")):
        v = str(info.get(key) or "").strip().replace(" W", "").replace("W", "").replace(" m", "").replace("m", "")
        if v and not NUM_RE.match(v):
            warn(f"EDI-Kopf: {label} „{info.get(key)}“ ist keine Zahl – Auswerter erwarten nur die Zahl")
    for key, label, mx in (("resp_name", "Name", 40), ("resp_address", "Straße", 40), ("resp_city", "Ort", 40), ("club", "Club", 40), ("operators", "Operatoren", 80)):
        if len(str(info.get(key) or "")) > mx:
            warn(f"EDI-Kopf: {label} länger als {mx} Zeichen – wird vom Auswerter evtl. abgeschnitten")
    if len(str(contest.get("name") or "")) > 60:
        warn("Contest-Name länger als 60 Zeichen (TName)")
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
            err("Rufzeichen unplausibel", q, "Rufzeichen", q["call"], "gültiges Rufzeichen")
        if "dok" in exchange and not (q.get("exch_rcvd") or "").strip():
            warn("DOK/OV fehlt (Austausch dieses Contests)", q, "DOK", "–", "DOK/OV")
        if not q["locator"]:
            err("Locator fehlt (0 Punkte, wird vom Auswerter gestrichen)", q, "Locator", "–", "6-stelliger Locator")
        elif not geo.is_valid_locator(q["locator"]):
            err(f"Locator „{q['locator']}“ ungültig", q, "Locator", q["locator"], "z. B. JO31AA")
        elif len(q["locator"]) < 6:
            warn(f"Locator „{q['locator']}“ nur 4-stellig – Entfernung ist ungenau", q, "Locator", q["locator"], "6 Stellen")
        if not RST_RE.match(norm_rst(q["rst_sent"])):
            err(f"RST gegeben „{q['rst_sent']}“ ungültig", q, "RST geg.", str(q["rst_sent"]), "z. B. 59 / 599")
        if not RST_RE.match(norm_rst(q["rst_rcvd"])):
            err(f"RST erhalten „{q['rst_rcvd']}“ ungültig", q, "RST erh.", str(q["rst_rcvd"]), "z. B. 59 / 599")
        if not str(q["serial_rcvd"]).strip():
            warn("Empfangene Nummer fehlt", q, "Nr erh.", "–", "Nummer")
        elif not str(q["serial_rcvd"]).isdigit():
            err(f"Empfangene Nummer „{q['serial_rcvd']}“ ist keine Zahl", q, "Nr erh.", str(q["serial_rcvd"]), "nur Ziffern")
        t = _ts(q["ts_utc"])
        if t > now:
            err("Zeit liegt in der Zukunft", q, "Zeit", q["ts_utc"][11:16], "nicht in der Zukunft")
        if start and t < start:
            err(f"QSO liegt vor Contest-Beginn ({contest['start_utc'][:16].replace('T', ' ')} UTC)", q, "Zeit", q["ts_utc"][5:16].replace("T", " "), f"ab {contest['start_utc'][5:16].replace('T', ' ')}")
        if end and t > end:
            err(f"QSO liegt nach Contest-Ende ({contest['end_utc'][:16].replace('T', ' ')} UTC)", q, "Zeit", q["ts_utc"][5:16].replace("T", " "), f"bis {contest['end_utc'][5:16].replace('T', ' ')}")
        if q["serial_sent"] in serials:
            err(f"Gesendete Nummer {q['serial_sent']:03d} doppelt vergeben (auch bei {serials[q['serial_sent']]['call']})", q, "Nr geg.", f"{q['serial_sent']:03d}", f"schon bei {serials[q['serial_sent']]['call']}")
        serials[q["serial_sent"]] = q
        if prev_ts and q["serial_sent"] < prev_ts[1] and not q["dupe"]:
            warn(f"Nummer {q['serial_sent']:03d} kommt zeitlich nach Nummer {prev_ts[1]:03d} – Reihenfolge prüfen", q, "Nr geg.", f"{q['serial_sent']:03d}", f"> {prev_ts[1]:03d} (Reihenfolge)")
        prev_ts = (t, q["serial_sent"])
        if q["dupe"]:
            warn("Doppel-QSO (wird mit 0 Punkten als Dupe exportiert)", q, "Dupe", q["call"], "0 Punkte, als Dupe markiert")
        pl = prefixes.check_plausibility(q["call"], q["locator"]) if q["locator"] else {"ok": True}
        if not pl["ok"]:
            err(pl["msg"], q, "Land", f"{q['call']} ({pl.get('country') or '?'})", f"{q['locator']} liegt in {', '.join((pl.get('locator_countries') or ['?'])[:2])}{' …' if len(pl.get('locator_countries') or []) > 2 else ''}")
        if q["km"] > 1500:
            warn(f"{q['km']} km – ungewöhnlich weit, Locator prüfen", q, "Entfernung", f"{q['km']} km", "Locator prüfen")
    own_core = prefixes.core_call(station["call"])
    for q in ordered:
        if prefixes.core_call(q["call"]) == own_core:
            err("QSO mit dem eigenen Rufzeichen", q, "Rufzeichen", q["call"], "nicht das eigene")
        if q["locator"] and station["locator"] and q["locator"].upper() == station["locator"].upper() and q["km"] == 0:
            warn("Partner im eigenen Locator-Feld (0 km) – stimmt der Locator?", q, "Locator", q["locator"], "≠ eigener Locator")
    nums = sorted(serials)
    missing = [n for n in range(nums[0], nums[-1] + 1) if n not in serials]
    if missing:
        warn(f"Lücken in den gesendeten Nummern: {', '.join(f'{n:03d}' for n in missing[:20])}{' …' if len(missing) > 20 else ''}")
    if nums[0] != 1:
        warn(f"Erste gesendete Nummer ist {nums[0]:03d}, nicht 001")
    return {"errors": errors, "warnings": warnings, "ok": not errors, "qsos": len(qsos)}
