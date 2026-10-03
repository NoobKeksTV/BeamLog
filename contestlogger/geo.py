"""Maidenhead-Locator-Berechnungen: Koordinaten, Entfernung (km) und Richtung (Grad).

Entfernung nach der im VHF/UHF-Contest üblichen Methode (Großkreis, Mittelpunkt
des Locator-Feldes, Erdradius 6371 km), so wie es auch WinContest / EDI erwarten.
"""
from __future__ import annotations

import math
import re

LOCATOR_RE = re.compile(r"^[A-R]{2}[0-9]{2}([A-X]{2}([0-9]{2})?)?$")
EARTH_RADIUS_KM = 6371.0


def normalize_locator(loc: str | None) -> str:
    return (loc or "").strip().upper()


def is_valid_locator(loc: str | None) -> bool:
    return bool(LOCATOR_RE.match(normalize_locator(loc)))


def locator_to_latlon(loc: str) -> tuple[float, float]:
    """Mittelpunkt des Locator-Feldes als (lat, lon) in Grad."""
    loc = normalize_locator(loc)
    if not is_valid_locator(loc):
        raise ValueError(f"Ungültiger Locator: {loc!r}")
    lon = (ord(loc[0]) - ord("A")) * 20.0 - 180.0
    lat = (ord(loc[1]) - ord("A")) * 10.0 - 90.0
    lon += int(loc[2]) * 2.0
    lat += int(loc[3]) * 1.0
    if len(loc) >= 6:
        lon += (ord(loc[4]) - ord("A")) * (2.0 / 24)
        lat += (ord(loc[5]) - ord("A")) * (1.0 / 24)
        if len(loc) >= 8:
            lon += int(loc[6]) * (2.0 / 240)
            lat += int(loc[7]) * (1.0 / 240)
            lon += 2.0 / 240 / 2
            lat += 1.0 / 240 / 2
        else:
            lon += 2.0 / 24 / 2
            lat += 1.0 / 24 / 2
    else:
        lon += 1.0
        lat += 0.5
    return lat, lon


def distance_km(loc_a: str, loc_b: str) -> float:
    lat1, lon1 = map(math.radians, locator_to_latlon(loc_a))
    lat2, lon2 = map(math.radians, locator_to_latlon(loc_b))
    d = math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon1 - lon2)
    d = max(-1.0, min(1.0, d))
    return math.acos(d) * EARTH_RADIUS_KM


def bearing_deg(loc_a: str, loc_b: str) -> float:
    """Kurzweg-Richtung von A nach B in Grad (0..360)."""
    lat1, lon1 = map(math.radians, locator_to_latlon(loc_a))
    lat2, lon2 = map(math.radians, locator_to_latlon(loc_b))
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def distance_km_int(loc_a: str, loc_b: str) -> int:
    """Entfernung in angefangenen km (aufgerundet) – so rechnet WinContest/REG1TEST."""
    return max(1, math.ceil(distance_km(loc_a, loc_b) - 1e-9))


def qso_points(loc_a: str, loc_b: str, min_points: int = 1) -> int:
    """DARC/IARU-Region-1 VHF-Wertung: 1 Punkt pro angefangenem km, mindestens 1."""
    if not (is_valid_locator(loc_a) and is_valid_locator(loc_b)):
        return 0
    return max(min_points, distance_km_int(loc_a, loc_b))


def square(loc: str) -> str:
    """Großfeld (4 Zeichen, z. B. JO31) für die Multiplikator-Zählung."""
    loc = normalize_locator(loc)
    return loc[:4] if len(loc) >= 4 else ""
