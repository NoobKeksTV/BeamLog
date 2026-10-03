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
    # --- Rest der Welt (die wichtigsten Präfixe, für Sporadic-E/EME/HF-Nutzung) ---
    "K": "USA", "W": "USA", "N": "USA", "AA": "USA", "AB": "USA", "AC": "USA", "AD": "USA", "AE": "USA", "AF": "USA", "AG": "USA", "AI": "USA", "AJ": "USA", "AK": "USA",
    "KL": "Alaska", "KH6": "Hawaii", "KP4": "Puerto Rico",
    "VE": "Kanada", "VA": "Kanada", "VO": "Kanada", "VY": "Kanada", "XE": "Mexiko",
    "PY": "Brasilien", "PP": "Brasilien", "PU": "Brasilien", "LU": "Argentinien", "CE": "Chile", "CX": "Uruguay", "HK": "Kolumbien", "YV": "Venezuela", "OA": "Peru", "HC": "Ecuador", "CP": "Bolivien", "ZP": "Paraguay",
    "JA": "Japan", "JE": "Japan", "JF": "Japan", "JG": "Japan", "JH": "Japan", "JI": "Japan", "JJ": "Japan", "JK": "Japan", "JL": "Japan", "JM": "Japan", "JN": "Japan", "JO": "Japan", "JP": "Japan", "JQ": "Japan", "JR": "Japan", "JS": "Japan", "7J": "Japan", "7K": "Japan", "7L": "Japan", "7M": "Japan", "7N": "Japan", "8J": "Japan",
    "BY": "China", "BA": "China", "BD": "China", "BG": "China", "BH": "China", "BV": "Taiwan", "HL": "Südkorea", "DS": "Südkorea", "VR": "Hongkong", "XX9": "Macao",
    "VU": "Indien", "AP": "Pakistan", "4S": "Sri Lanka", "9N": "Nepal", "S2": "Bangladesch",
    "HS": "Thailand", "E2": "Thailand", "9M": "Malaysia", "9V": "Singapur", "YB": "Indonesien", "YC": "Indonesien", "DU": "Philippinen", "XV": "Vietnam", "3W": "Vietnam",
    "VK": "Australien", "ZL": "Neuseeland", "P2": "Papua-Neuguinea", "3D2": "Fidschi",
    "ZS": "Südafrika", "ZR": "Südafrika", "ZU": "Südafrika", "5Z": "Kenia", "5H": "Tansania", "ET": "Äthiopien", "SU": "Ägypten", "CN": "Marokko", "7X": "Algerien", "3V": "Tunesien", "5A": "Libyen",
    "EA9": "Ceuta/Melilla", "IG9": "Lampedusa", "IH9": "Pantelleria", "CT3": "Madeira", "CU": "Azoren", "D4": "Kap Verde", "9G": "Ghana", "5N": "Nigeria", "6W": "Senegal", "TU": "Elfenbeinküste",
    "4X": "Israel", "4Z": "Israel", "JY": "Jordanien", "OD": "Libanon", "YK": "Syrien", "YI": "Irak", "EP": "Iran", "A4": "Oman", "A6": "VAE", "A7": "Katar", "A9": "Bahrain", "9K": "Kuwait", "HZ": "Saudi-Arabien", "7Z": "Saudi-Arabien",
    "UN": "Kasachstan", "UP": "Kasachstan", "EX": "Kirgisistan", "EY": "Tadschikistan", "EZ": "Turkmenistan", "UK": "Usbekistan", "4L": "Georgien", "EK": "Armenien", "4J": "Aserbaidschan", "4K": "Aserbaidschan",
    "UA9": "Russland (asiat.)", "UA0": "Russland (asiat.)", "R9": "Russland (asiat.)", "R0": "Russland (asiat.)", "JT": "Mongolei",
    "TA1": "Türkei (europ.)", "1B": "Nordzypern", "GB": "Großbritannien", "ZD8": "Ascension", "VP8": "Falkland", "VP9": "Bermuda", "VP2E": "Anguilla", "8P": "Barbados", "J6": "St. Lucia", "9Y": "Trinidad", "HI": "Dominikan. Rep.", "HH": "Haiti", "CO": "Kuba", "CM": "Kuba", "6Y": "Jamaika", "TI": "Costa Rica", "HP": "Panama", "TG": "Guatemala", "YS": "El Salvador", "HR": "Honduras", "YN": "Nicaragua",
    "FM": "Martinique", "FG": "Guadeloupe", "FY": "Franz.-Guayana", "FR": "Réunion", "FH": "Mayotte", "FK": "Neukaledonien", "FO": "Franz.-Polynesien", "FP": "St. Pierre & Miquelon",
    "PJ2": "Curaçao", "PJ4": "Bonaire", "P4": "Aruba", "V3": "Belize", "KP2": "US Virgin Isl.",
    "T9": "Bosnien-Herz.", "4N": "Serbien", "YZ": "Serbien", "Z6": "Kosovo", "E4": "Palästina", "T4": "Kuba",
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
