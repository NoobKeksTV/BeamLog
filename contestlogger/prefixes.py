"""Rufzeichen-Analyse: Kern-Call (ohne /P, /M, Präfix-Zusätze) und DXCC-Land.

Die Präfixtabelle deckt die in VHF/UHF-Contesten in Mitteleuropa relevanten
Länder ab; Unbekanntes wird als "?" gemeldet und schadet nicht.
"""
from __future__ import annotations

import re

# Längster passender Präfix gewinnt.
PREFIXES: dict[str, str] = {
    "DA": "Deutschland", "DB": "Deutschland", "DC": "Deutschland", "DD": "Deutschland",
    "DE": "Deutschland", "DF": "Deutschland", "DG": "Deutschland", "DH": "Deutschland",
    "DJ": "Deutschland", "DK": "Deutschland", "DL": "Deutschland", "DM": "Deutschland",
    "DN": "Deutschland", "DO": "Deutschland", "DP": "Deutschland", "DQ": "Deutschland",
    "DR": "Deutschland", "Y2": "Deutschland",
    "OK": "Tschechien", "OL": "Tschechien", "OM": "Slowakei",
    "ON": "Belgien", "OO": "Belgien", "OP": "Belgien", "OQ": "Belgien", "OR": "Belgien", "OS": "Belgien", "OT": "Belgien",
    "PA": "Niederlande", "PB": "Niederlande", "PC": "Niederlande", "PD": "Niederlande",
    "PE": "Niederlande", "PF": "Niederlande", "PG": "Niederlande", "PH": "Niederlande", "PI": "Niederlande",
    "LX": "Luxemburg",
    "F": "Frankreich", "TM": "Frankreich", "TK": "Korsika",
    "G": "England", "M": "England", "2E": "England",
    "GW": "Wales", "MW": "Wales", "2W": "Wales",
    "GM": "Schottland", "MM": "Schottland", "2M": "Schottland",
    "GI": "Nordirland", "MI": "Nordirland", "2I": "Nordirland",
    "GD": "Isle of Man", "MD": "Isle of Man", "GU": "Guernsey", "MU": "Guernsey", "GJ": "Jersey", "MJ": "Jersey",
    "EI": "Irland", "EJ": "Irland",
    "OE": "Österreich",
    "HB": "Schweiz", "HB0": "Liechtenstein",
    "I": "Italien", "IS": "Sardinien", "IT9": "Sizilien",
    "SP": "Polen", "SN": "Polen", "SO": "Polen", "SQ": "Polen", "SR": "Polen", "HF": "Polen", "3Z": "Polen",
    "HA": "Ungarn", "HG": "Ungarn",
    "S5": "Slowenien", "9A": "Kroatien", "E7": "Bosnien-Herz.", "YU": "Serbien", "YT": "Serbien",
    "OZ": "Dänemark", "OU": "Dänemark", "OV": "Dänemark", "5P": "Dänemark", "5Q": "Dänemark",
    "SM": "Schweden", "SA": "Schweden", "SB": "Schweden", "SC": "Schweden", "SD": "Schweden",
    "SE": "Schweden", "SF": "Schweden", "SG": "Schweden", "SH": "Schweden", "SI": "Schweden",
    "SJ": "Schweden", "SK": "Schweden", "SL": "Schweden", "7S": "Schweden", "8S": "Schweden",
    "LA": "Norwegen", "LB": "Norwegen", "LC": "Norwegen", "LN": "Norwegen",
    "OH": "Finnland", "OF": "Finnland", "OG": "Finnland", "OI": "Finnland", "OJ": "Finnland", "OH0": "Aland",
    "ES": "Estland", "YL": "Lettland", "LY": "Litauen",
    "EA": "Spanien", "EB": "Spanien", "EC": "Spanien", "ED": "Spanien", "EE": "Spanien", "EF": "Spanien", "EG": "Spanien", "EH": "Spanien",
    "EA6": "Balearen", "EA8": "Kanaren", "CT": "Portugal",
    "YO": "Rumänien", "YP": "Rumänien", "YQ": "Rumänien", "YR": "Rumänien",
    "LZ": "Bulgarien", "SV": "Griechenland", "TA": "Türkei",
    "UR": "Ukraine", "US": "Ukraine", "UT": "Ukraine", "UW": "Ukraine", "UX": "Ukraine", "UY": "Ukraine", "UZ": "Ukraine", "EM": "Ukraine", "EN": "Ukraine", "EO": "Ukraine",
    "EU": "Belarus", "EV": "Belarus", "EW": "Belarus",
    "R": "Russland", "UA": "Russland", "UB": "Russland", "UC": "Russland", "UD": "Russland", "UE": "Russland", "UF": "Russland", "UG": "Russland", "UH": "Russland", "UI": "Russland",
    "UA2": "Kaliningrad", "R2": "Kaliningrad",
    "ER": "Moldawien", "4O": "Montenegro", "Z3": "Nordmazedonien", "ZA": "Albanien",
    "9H": "Malta", "T7": "San Marino", "3A": "Monaco", "HV": "Vatikan", "1A": "SMOM", "C3": "Andorra", "ZB": "Gibraltar",
    "OY": "Färöer", "TF": "Island", "JW": "Svalbard", "OX": "Grönland",
    "4U1": "UN Wien/Genf", "ZC4": "Zypern UK", "5B": "Zypern",
}

# Portabel-/Zusatzkennungen, die kein Länderpräfix sind.
IGNORED_SUFFIXES = {"P", "M", "MM", "AM", "QRP", "A", "LH", "J", "B", "R", "T"}

CALL_RE = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z0-9]*[A-Z]$")


def split_call(call: str) -> tuple[str, str]:
    """Liefert (Kern-Rufzeichen, Präfix-relevanter Teil).

    DL1ABC/P -> (DL1ABC, DL1ABC); OE/DL1ABC -> (DL1ABC, OE); DL1ABC/HB9 -> (DL1ABC, HB9)
    """
    call = (call or "").strip().upper()
    parts = [p for p in call.split("/") if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], parts[0]
    # Suffix wie /P /M /QRP ignorieren
    tail = parts[-1]
    if tail in IGNORED_SUFFIXES or tail.isdigit():
        core = max(parts[:-1], key=len)
        prefix_part = [p for p in parts[:-1] if p != core]
        return core, (prefix_part[0] if prefix_part else core)
    # Präfix voran (OE/DL1ABC) oder hinten (DL1ABC/HB9): der Teil ohne Ziffer-Buchstabe-Muster ist der Präfix
    core = max(parts, key=lambda p: (bool(CALL_RE.match(p)), len(p)))
    others = [p for p in parts if p != core]
    return core, (others[0] if others else core)


def core_call(call: str) -> str:
    return split_call(call)[0]


def country(call: str) -> str:
    _, pfx = split_call(call)
    pfx = pfx.upper()
    for n in range(min(4, len(pfx)), 0, -1):
        if pfx[:n] in PREFIXES:
            return PREFIXES[pfx[:n]]
    return "?"


def is_plausible_call(call: str) -> bool:
    core = core_call(call)
    return bool(core) and len(core) >= 3 and any(c.isdigit() for c in core) and any(c.isalpha() for c in core)
