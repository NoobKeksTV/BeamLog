"""Flugzeug-Scatter (wie AirScout): Flugzeugpositionen per ADS-B holen und auf den Funkpfad beziehen.

Quellen (Format wie dump1090/readsb aircraft.json: {"aircraft": [{hex, flight, t, lat, lon, alt_baro, gs, track, ...}]}):
  - adsb.fi (frei, 1 Anfrage/s, nicht-kommerziell, Quellenangabe nötig): https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}
  - eigener Empfänger (dump1090/readsb/tar1090): http://<host>:8080/data/aircraft.json

Geometrie (vereinfacht gegenüber AirScout, ohne Geländemodell):
  Ein Flugzeug in Höhe h (m) ist für eine Station bis zur Radio-Horizont-Entfernung d_h ≈ 4.12·√h km sichtbar
  (plus ein paar km für die eigene Antennenhöhe). Für Aircraft-Scatter muss das Flugzeug von BEIDEN Stationen
  sichtbar sein und nahe am Großkreis zwischen ihnen liegen (Korridor, Standard ±12 km).
"""
from __future__ import annotations

import json
import math
import time
import urllib.request
from typing import Any

from . import geo

ADSB_FI = "https://opendata.adsb.fi/api/v2/lat/{lat:.4f}/lon/{lon:.4f}/dist/{nm}"
R_EARTH = 6371.0
_cache: dict[str, tuple[float, list[dict]]] = {}
CACHE_SEC = 4.0


def dist_ll(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Großkreisentfernung in km zwischen zwei (lat, lon)-Punkten."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(min(1.0, h)))


def radio_horizon_km(alt_m: float, antenna_m: float = 15.0) -> float:
    """Entfernung bis zum Funkhorizont (4/3-Erde) für Höhe alt_m plus Antennenhöhe antenna_m."""
    return 4.12 * (math.sqrt(max(alt_m, 0.0)) + math.sqrt(max(antenna_m, 0.0)))


def _normalize(raw: dict | list) -> list[dict]:
    items = raw.get("aircraft") or raw.get("ac") or [] if isinstance(raw, dict) else raw
    out = []
    for a in items:
        try:
            lat, lon = float(a.get("lat")), float(a.get("lon"))
        except (TypeError, ValueError):
            continue
        alt = a.get("alt_geom", a.get("alt_baro"))
        if alt in (None, "ground"):
            alt_m = 0.0
        else:
            try:
                alt_m = float(alt) * 0.3048
            except (TypeError, ValueError):
                alt_m = 0.0
        out.append({
            "hex": str(a.get("hex") or ""), "flight": str(a.get("flight") or "").strip(), "type": str(a.get("t") or ""), "desc": str(a.get("desc") or ""),
            "lat": lat, "lon": lon, "alt_m": round(alt_m), "fl": round(alt_m / 30.48) if alt_m else 0,
            "gs_kmh": round(float(a.get("gs") or 0) * 1.852), "track": float(a.get("track") or a.get("true_heading") or 0), "ground": alt in ("ground",),
        })
    return out


def fetch(source: str, lat: float, lon: float, dist_km: float, local_url: str = "", timeout: float = 10) -> list[dict]:
    """Flugzeuge um einen Punkt (max. 250 nm bei adsb.fi), 4 s gecacht."""
    nm = min(250, max(10, int(dist_km / 1.852)))
    url = local_url if source == "local" and local_url else ADSB_FI.format(lat=lat, lon=lon, nm=nm)
    key = f"{url}|{lat:.2f}|{lon:.2f}|{nm}"
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_SEC:
        return hit[1]
    req = urllib.request.Request(url, headers={"User-Agent": "ContestLogger (Amateurfunk, aircraft scatter; non-commercial)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    planes = _normalize(data)
    if source == "local":  # lokaler Empfänger liefert alles – auf den Umkreis einschränken
        planes = [p for p in planes if dist_ll((lat, lon), (p["lat"], p["lon"])) <= dist_km]
    _cache[key] = (now, planes)
    return planes


# ------------------------------------------------------------------ Geometrie
def _rad(x: float) -> float:
    return x * math.pi / 180


def bearing_rad(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(_rad, (a[0], a[1], b[0], b[1]))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return math.atan2(y, x)


def cross_along_track(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> tuple[float, float]:
    """Abstand von P zum Großkreis A→B (km, vorzeichenbehaftet) und Position entlang des Pfads ab A (km)."""
    d_ap = dist_ll(a, p) / R_EARTH
    if d_ap == 0:
        return 0.0, 0.0
    th_ap = bearing_rad(a, p)
    th_ab = bearing_rad(a, b)
    xt = math.asin(math.sin(d_ap) * math.sin(th_ap - th_ab))
    at = math.acos(max(-1.0, min(1.0, math.cos(d_ap) / max(1e-12, math.cos(xt)))))
    # Richtung entlang des Pfads: vor A (negativ) oder dahinter
    if abs(th_ap - th_ab) > math.pi / 2 and abs(th_ap - th_ab) < 3 * math.pi / 2:
        at = -at
    return xt * R_EARTH, at * R_EARTH


def point_along(a: tuple[float, float], b: tuple[float, float], frac: float) -> tuple[float, float]:
    lat1, lon1, lat2, lon2 = map(_rad, (a[0], a[1], b[0], b[1]))
    d = dist_ll(a, b) / R_EARTH
    if d < 1e-9:
        return a
    A = math.sin((1 - frac) * d) / math.sin(d)
    B = math.sin(frac * d) / math.sin(d)
    x = A * math.cos(lat1) * math.cos(lon1) + B * math.cos(lat2) * math.cos(lon2)
    y = A * math.cos(lat1) * math.sin(lon1) + B * math.cos(lat2) * math.sin(lon2)
    z = A * math.sin(lat1) + B * math.sin(lat2)
    return math.degrees(math.atan2(z, math.sqrt(x * x + y * y))), math.degrees(math.atan2(y, x))


def scatter(my_loc: str, other_loc: str, planes: list[dict], corridor_km: float = 12.0, antenna_m: float = 15.0, typical_alt_m: float = 11000.0) -> dict[str, Any]:
    """Pfad, Zone gemeinsamer Sichtbarkeit und Flugzeuge im Korridor (nach AirScout-Prinzip, ohne Gelände)."""
    a = geo.locator_to_latlon(my_loc)
    b = geo.locator_to_latlon(other_loc)
    dist = dist_ll(a, b)
    h = radio_horizon_km(typical_alt_m, antenna_m)
    # beide Stationen sehen einen Punkt des Pfads in Höhe typical_alt, wenn s < h und dist - s < h
    zone = None
    if dist and dist < 2 * h:
        s0, s1 = max(0.0, dist - h), min(dist, h)
        zone = {"from_km": round(s0), "to_km": round(s1), "from": point_along(a, b, s0 / dist if dist else 0), "to": point_along(a, b, s1 / dist if dist else 1)}
    out = []
    for p in planes:
        if p["ground"] or p["alt_m"] < 1500:
            continue
        xt, at = cross_along_track(a, b, (p["lat"], p["lon"]))
        if at < -corridor_km or at > dist + corridor_km:
            continue
        d1 = dist_ll(a, (p["lat"], p["lon"]))
        d2 = dist_ll(b, (p["lat"], p["lon"]))
        horizon = radio_horizon_km(p["alt_m"], antenna_m)
        visible_both = d1 < horizon and d2 < horizon
        # Zeit bis zum Kreuzen des Pfads: Geschwindigkeitsanteil quer zum Pfad
        path_brg = bearing_rad(a, b)
        v_cross = -p["gs_kmh"] * math.sin(_rad(p["track"]) - path_brg) * (1 if xt > 0 else -1) if p["gs_kmh"] else 0  # km/h Richtung Pfad
        eta_min = (abs(xt) / v_cross * 60) if v_cross > 5 else None
        out.append({**p, "xt_km": round(xt, 1), "at_km": round(at), "d1_km": round(d1), "d2_km": round(d2), "visible_both": visible_both,
                    "in_corridor": abs(xt) <= corridor_km, "eta_min": round(eta_min, 1) if eta_min is not None and eta_min < 60 else None})
    out.sort(key=lambda p: (not (p["in_corridor"] and p["visible_both"]), abs(p["xt_km"])))
    return {"my": my_loc, "other": other_loc, "dist_km": round(dist), "corridor_km": corridor_km, "zone": zone, "horizon_km": round(h), "planes": out[:60]}
