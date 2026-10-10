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


# Größenklasse (wie AirScout: große Flugzeuge reflektieren deutlich besser). ADS-B-Kategorie A1 leicht … A5 schwer;
# fehlt sie, entscheidet der Typ.
HEAVY_TYPES = {"A388", "A380", "B744", "B748", "B747", "B77W", "B77L", "B772", "B773", "B777", "A359", "A35K", "A350", "A346", "A345", "A343", "A342", "A340",
               "B788", "B789", "B78X", "B787", "A332", "A333", "A338", "A339", "A330", "B763", "B764", "B767", "MD11", "A124", "C5M", "C17", "B752", "B753"}
LIGHT_TYPES = {"C172", "C152", "C182", "PA28", "DA40", "DA42", "SR22", "P28A", "C72R", "GLID", "ULAC", "PC12", "TBM9"}


def size_class(category: str, typ: str) -> str:
    """'heavy' | 'large' | 'medium' | 'light' | '' – aus ADS-B-Kategorie (A1–A5) oder dem Flugzeugtyp."""
    cat = (category or "").upper().strip()
    typ = (typ or "").upper().strip()
    if cat in ("A5",) or typ in HEAVY_TYPES:
        return "heavy"
    if cat in ("A4", "A3"):
        return "large"
    if cat in ("A2",):
        return "medium"
    if cat in ("A1", "A7", "B1", "B2", "B4") or typ in LIGHT_TYPES:
        return "light"
    if typ:
        return "medium"  # Linienflugzeuge (A320, B738 …) ohne Kategorie
    return ""


def required_alt_m(d_km: float, antenna_m: float = 15.0) -> float:
    """Mindesthöhe (m), ab der ein Objekt in d_km Entfernung über dem Funkhorizont einer Station mit Antennenhöhe antenna_m steht."""
    x = d_km / 4.12 - math.sqrt(max(antenna_m, 0.0))
    return x * x if x > 0 else 0.0


def elevation_deg(d_km: float, alt_m: float, antenna_m: float = 15.0) -> float:
    """Elevationswinkel von der Station zum Objekt (4/3-Erde, Erdkrümmung berücksichtigt)."""
    if d_km <= 0:
        return 90.0
    drop_m = (d_km * 1000) ** 2 / (2 * (4 / 3) * R_EARTH * 1000)
    return math.degrees(math.atan2(alt_m - antenna_m - drop_m, d_km * 1000))


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
            "category": str(a.get("category") or ""), "size": size_class(str(a.get("category") or ""), str(a.get("t") or "")),
            "vr_ms": round(float(a.get("baro_rate") or a.get("geom_rate") or 0) * 0.00508, 1),  # ft/min -> m/s
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
    req = urllib.request.Request(url, headers={"User-Agent": "BeamLog (Amateurfunk, aircraft scatter; non-commercial)", "Accept": "application/json"})
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
    # Mindesthöhe entlang des Pfads (Profil für die Seitenansicht wie in AirScout): max. der beiden Stationen
    def req_at(s_km: float) -> float:
        return max(required_alt_m(s_km, antenna_m), required_alt_m(dist - s_km, antenna_m))

    steps = 40
    profile = [{"km": round(dist * i / steps), "req_m": round(req_at(dist * i / steps))} for i in range(steps + 1)] if dist else []
    min_req = min((x["req_m"] for x in profile), default=0.0)
    now = time.time()
    out = []
    for p in planes:
        if p["ground"] or p["alt_m"] < 1500:
            continue
        xt, at = cross_along_track(a, b, (p["lat"], p["lon"]))
        if at < -corridor_km or at > dist + corridor_km:
            continue
        d1 = dist_ll(a, (p["lat"], p["lon"]))
        d2 = dist_ll(b, (p["lat"], p["lon"]))
        # Mindesthöhe an der aktuellen Position (beide Stationen) und Höhenreserve = Flughöhe minus Mindesthöhe
        req_m = max(required_alt_m(d1, antenna_m), required_alt_m(d2, antenna_m))
        margin_m = p["alt_m"] - req_m
        visible_both = margin_m > 0
        # Zeit bis zum Kreuzen des Pfads: Geschwindigkeitsanteil quer zum Pfad; Kreuzungspunkt aus dem Anteil längs des Pfads
        path_brg = bearing_rad(a, b)
        v_cross = -p["gs_kmh"] * math.sin(_rad(p["track"]) - path_brg) * (1 if xt > 0 else -1) if p["gs_kmh"] else 0  # km/h Richtung Pfad
        v_along = p["gs_kmh"] * math.cos(_rad(p["track"]) - path_brg)
        eta_min = (abs(xt) / v_cross * 60) if v_cross > 5 else None
        cross = None
        if eta_min is not None and eta_min < 90:
            s_cross = at + v_along * eta_min / 60
            alt_cross = p["alt_m"] + p.get("vr_ms", 0) * eta_min * 60
            req_cross = req_at(s_cross) if 0 <= s_cross <= dist else None
            cross = {"km": round(s_cross), "utc": time.strftime("%H:%M:%S", time.gmtime(now + eta_min * 60)), "on_path": 0 <= s_cross <= dist,
                     "in_zone": bool(zone and zone["from_km"] <= s_cross <= zone["to_km"]), "req_m": round(req_cross) if req_cross is not None else None,
                     "margin_m": round(alt_cross - req_cross) if req_cross is not None else None}
        in_corridor = abs(xt) <= corridor_km
        if in_corridor and visible_both:
            status = "hot"
        elif cross and cross["on_path"] and (cross["margin_m"] or 0) > 0 and eta_min <= 20:
            status = "soon"
        elif visible_both:
            status = "visible"
        elif (cross and cross["on_path"] and (cross["margin_m"] or 0) <= 0) or (not cross and p["alt_m"] < min_req):
            status = "low"  # zu tief: auch am Kreuzungspunkt bzw. überall auf dem Pfad unter dem Funkhorizont
        else:
            status = "far"
        out.append({**p, "xt_km": round(xt, 1), "at_km": round(at), "d1_km": round(d1), "d2_km": round(d2), "visible_both": visible_both,
                    "in_corridor": in_corridor, "eta_min": round(eta_min, 1) if eta_min is not None and eta_min < 60 else None,
                    "req_m": round(req_m), "margin_m": round(margin_m), "elev1": round(elevation_deg(d1, p["alt_m"], antenna_m), 1),
                    "elev2": round(elevation_deg(d2, p["alt_m"], antenna_m), 1), "cross": cross, "status": status})
    order = {"hot": 0, "soon": 1, "visible": 2, "far": 3, "low": 4}
    out.sort(key=lambda p: (order[p["status"]], p["eta_min"] if p["status"] == "soon" and p["eta_min"] is not None else abs(p["xt_km"])))
    return {"my": my_loc, "other": other_loc, "dist_km": round(dist), "corridor_km": corridor_km, "zone": zone, "horizon_km": round(h),
            "antenna_m": antenna_m, "profile": profile, "path_from": a, "path_to": b, "planes": out[:60]}
