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


# ---------------------------------------------------------------------------
# Plausibilität: Liegt der Locator im Land des Rufzeichens?
# Grobe Umrisse (lat_min, lat_max, lon_min, lon_max); mehrere Kästen je Land möglich.
COUNTRY_BOXES: dict[str, list[tuple[float, float, float, float]]] = {
    "Deutschland": [(47.2, 55.1, 5.8, 15.1)],
    "Österreich": [(46.3, 49.1, 9.5, 17.2)],
    "Schweiz": [(45.8, 47.9, 5.9, 10.6)], "Liechtenstein": [(47.0, 47.3, 9.4, 9.7)],
    "Niederlande": [(50.7, 53.6, 3.3, 7.3)], "Belgien": [(49.4, 51.6, 2.5, 6.5)], "Luxemburg": [(49.4, 50.2, 5.7, 6.6)],
    "Frankreich": [(42.3, 51.2, -5.2, 8.3)], "Korsika": [(41.3, 43.1, 8.5, 9.6)], "Monaco": [(43.7, 43.8, 7.3, 7.5)],
    "England": [(49.8, 55.9, -6.5, 1.9)], "Wales": [(51.3, 53.5, -5.4, -2.6)], "Schottland": [(54.5, 61.0, -8.7, 0.0)],
    "Nordirland": [(53.9, 55.4, -8.2, -5.3)], "Irland": [(51.3, 55.5, -10.7, -5.9)], "Isle of Man": [(54.0, 54.5, -4.9, -4.2)],
    "Guernsey": [(49.4, 49.8, -2.7, -2.1)], "Jersey": [(49.1, 49.3, -2.3, -1.9)], "Großbritannien": [(49.8, 61.0, -8.7, 1.9)],
    "Tschechien": [(48.5, 51.1, 12.0, 18.9)], "Slowakei": [(47.7, 49.7, 16.8, 22.6)], "Polen": [(49.0, 54.9, 14.1, 24.2)],
    "Ungarn": [(45.7, 48.6, 16.1, 22.9)], "Slowenien": [(45.4, 46.9, 13.3, 16.6)], "Kroatien": [(42.3, 46.6, 13.4, 19.5)],
    "Bosnien-Herz.": [(42.5, 45.3, 15.7, 19.7)], "Serbien": [(42.2, 46.2, 18.8, 23.1)], "Montenegro": [(41.8, 43.6, 18.4, 20.4)],
    "Nordmazedonien": [(40.8, 42.4, 20.4, 23.1)], "Albanien": [(39.6, 42.7, 19.2, 21.1)], "Kosovo": [(41.8, 43.3, 20.0, 21.8)],
    "Italien": [(36.6, 47.1, 6.6, 18.6)], "Sardinien": [(38.8, 41.3, 8.1, 9.9)], "Sizilien": [(36.6, 38.4, 12.3, 15.7)],
    "San Marino": [(43.8, 44.0, 12.3, 12.6)], "Vatikan": [(41.8, 42.0, 12.4, 12.5)], "Malta": [(35.7, 36.1, 14.1, 14.6)],
    "Dänemark": [(54.5, 57.8, 8.0, 15.2)], "Schweden": [(55.3, 69.1, 10.9, 24.2)], "Norwegen": [(57.9, 71.3, 4.5, 31.2)],
    "Finnland": [(59.7, 70.1, 19.5, 31.6)], "Aland": [(59.7, 60.5, 19.3, 21.3)], "Island": [(63.3, 66.6, -24.6, -13.4)],
    "Färöer": [(61.3, 62.4, -7.8, -6.2)], "Svalbard": [(74.0, 81.0, 10.0, 35.0)], "Grönland": [(59.7, 83.7, -73.1, -11.3)],
    "Estland": [(57.5, 59.7, 21.7, 28.3)], "Lettland": [(55.6, 58.1, 20.9, 28.3)], "Litauen": [(53.9, 56.5, 20.9, 26.9)],
    "Spanien": [(35.9, 43.8, -9.4, 3.4)], "Balearen": [(38.6, 40.1, 1.1, 4.4)], "Kanaren": [(27.6, 29.5, -18.2, -13.3)],
    "Portugal": [(36.9, 42.2, -9.6, -6.1)], "Madeira": [(32.3, 33.2, -17.4, -16.2)], "Azoren": [(36.9, 39.8, -31.4, -24.9)],
    "Andorra": [(42.4, 42.7, 1.4, 1.8)], "Gibraltar": [(36.1, 36.2, -5.4, -5.3)], "Ceuta/Melilla": [(35.1, 35.9, -5.4, -2.9)],
    "Rumänien": [(43.6, 48.3, 20.2, 29.8)], "Bulgarien": [(41.2, 44.3, 22.3, 28.7)], "Griechenland": [(34.8, 41.8, 19.3, 29.7)],
    "Türkei": [(35.8, 42.2, 25.6, 44.9)], "Türkei (europ.)": [(40.0, 42.2, 25.6, 29.9)], "Zypern": [(34.5, 35.8, 32.2, 34.7)],
    "Zypern UK": [(34.5, 35.8, 32.2, 34.7)], "Nordzypern": [(35.0, 35.8, 32.5, 34.7)],
    "Ukraine": [(44.3, 52.4, 22.1, 40.3)], "Belarus": [(51.2, 56.2, 23.1, 32.8)], "Moldawien": [(45.4, 48.5, 26.6, 30.2)],
    "Russland": [(41.1, 82.0, 27.3, 180.0)], "Russland (asiat.)": [(41.1, 82.0, 59.0, 180.0)], "Kaliningrad": [(54.3, 55.3, 19.6, 22.9)],
    "Georgien": [(41.0, 43.6, 40.0, 46.7)], "Armenien": [(38.8, 41.3, 43.4, 46.6)], "Aserbaidschan": [(38.4, 41.9, 44.8, 50.4)],
    "Israel": [(29.4, 33.4, 34.2, 35.9)], "Palästina": [(31.2, 32.6, 34.2, 35.6)], "Jordanien": [(29.1, 33.4, 34.9, 39.3)],
    "Libanon": [(33.0, 34.7, 35.1, 36.6)], "Syrien": [(32.3, 37.3, 35.7, 42.4)], "Irak": [(29.0, 37.4, 38.8, 48.6)],
    "Iran": [(25.0, 39.8, 44.0, 63.4)], "Saudi-Arabien": [(16.3, 32.2, 34.5, 55.7)], "Kuwait": [(28.5, 30.1, 46.5, 48.5)],
    "Bahrain": [(25.7, 26.4, 50.3, 50.8)], "Katar": [(24.4, 26.2, 50.7, 51.7)], "VAE": [(22.6, 26.1, 51.5, 56.4)], "Oman": [(16.6, 26.4, 52.0, 59.9)],
    "Ägypten": [(21.9, 31.7, 24.6, 36.9)], "Libyen": [(19.5, 33.2, 9.3, 25.2)], "Tunesien": [(30.2, 37.4, 7.5, 11.6)],
    "Algerien": [(18.9, 37.1, -8.7, 12.0)], "Marokko": [(27.6, 35.9, -13.2, -0.9)],
    "USA": [(24.4, 49.4, -125.0, -66.9)], "Alaska": [(51.2, 71.4, -179.2, -129.9)], "Hawaii": [(18.9, 22.3, -160.3, -154.8)],
    "Kanada": [(41.6, 83.2, -141.0, -52.6)], "Mexiko": [(14.5, 32.8, -118.5, -86.7)],
    "Japan": [(24.0, 45.6, 122.9, 146.0)], "Südkorea": [(33.1, 38.7, 124.6, 131.0)], "China": [(18.1, 53.6, 73.5, 135.1)],
    "Taiwan": [(21.8, 25.4, 119.3, 122.1)], "Hongkong": [(22.1, 22.6, 113.8, 114.5)], "Indien": [(6.7, 35.5, 68.1, 97.4)],
    "Australien": [(-43.7, -10.4, 112.9, 153.7)], "Neuseeland": [(-47.4, -34.3, 166.3, 178.6)], "Südafrika": [(-34.9, -22.1, 16.4, 32.9)],
    "Brasilien": [(-33.8, 5.3, -73.9, -34.7)], "Argentinien": [(-55.1, -21.8, -73.6, -53.6)], "Chile": [(-56.0, -17.5, -75.7, -66.4)],
}

# Länder, die als Teil eines anderen gelten dürfen (z. B. GB-Call in England)
COUNTRY_ALIASES = {"Großbritannien": ["England", "Wales", "Schottland", "Nordirland"], "Russland": ["Russland (asiat.)", "Kaliningrad"], "Türkei": ["Türkei (europ.)"]}


def locator_countries(locator: str, margin: float = 0.35) -> list[str]:
    """Alle Länder, in deren (grobem) Umriss der Locator liegt."""
    from . import geo
    if not geo.is_valid_locator(locator):
        return []
    lat, lon = geo.locator_to_latlon(locator)
    out = []
    for name, boxes in COUNTRY_BOXES.items():
        for lat0, lat1, lon0, lon1 in boxes:
            if lat0 - margin <= lat <= lat1 + margin and lon0 - margin <= lon <= lon1 + margin:
                out.append(name)
                break
    return out


def check_plausibility(call: str, locator: str) -> dict:
    """Prüft, ob der Locator zum Land des Rufzeichens passt.

    Liefert {"ok": bool, "country": Land des Calls, "locator_countries": [...], "msg": Hinweis oder ""}.
    Unbekannte Länder oder Länder ohne Umriss gelten als plausibel.
    """
    ctry = country(call)
    locs = locator_countries(locator)
    if ctry == "?" or ctry not in COUNTRY_BOXES or not locs:
        return {"ok": True, "country": ctry, "locator_countries": locs, "msg": ""}
    allowed = {ctry, *COUNTRY_ALIASES.get(ctry, [])}
    for parent, parts in COUNTRY_ALIASES.items():
        if ctry in parts:
            allowed.add(parent)
    if allowed & set(locs):
        return {"ok": True, "country": ctry, "locator_countries": locs, "msg": ""}
    where = "/".join(l for l in locs if l not in ("Russland",) or len(locs) == 1)[:60]
    return {"ok": False, "country": ctry, "locator_countries": locs,
            "msg": f"Rufzeichen aus {ctry}, Locator {normalize(locator)} liegt aber in {where} – Locator oder Rufzeichen prüfen (bei Portabelbetrieb im Ausland gehört der Landespräfix vor das Rufzeichen, z. B. PA/DL1ABC)"}


def normalize(locator: str) -> str:
    return (locator or "").strip().upper()
