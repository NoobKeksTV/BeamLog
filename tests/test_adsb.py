"""Flugzeug-Scatter: Geometrie und Endpunkt (Quelle: lokale aircraft.json-Datei)."""
import json

from fastapi.testclient import TestClient

from contestlogger import adsb
from contestlogger.app import create_app


A, B = (51.0208, 6.0417), (49.1875, 10.9583)  # JO31AA, JN59LE (Feldmitten)
ON_PATH = adsb.point_along(A, B, 0.6)


def test_scatter_geometry():
    planes = [
        {"hex": "1", "flight": "DLH123", "type": "A320", "desc": "", "lat": ON_PATH[0] + 0.03, "lon": ON_PATH[1], "alt_m": 11000, "fl": 361, "gs_kmh": 850, "track": 30, "ground": False},  # ~3 km neben dem Pfad
        {"hex": "2", "flight": "LOW", "type": "C172", "desc": "", "lat": 50.6, "lon": 9.0, "alt_m": 900, "fl": 30, "gs_kmh": 200, "track": 90, "ground": False},      # zu tief
        {"hex": "3", "flight": "FAR", "type": "B738", "desc": "", "lat": 53.5, "lon": 9.0, "alt_m": 11000, "fl": 361, "gs_kmh": 850, "track": 180, "ground": False},  # weit nördlich, fliegt auf den Pfad zu
    ]
    r = adsb.scatter("JO31AA", "JN59LE", planes)
    assert r["dist_km"] == 405 and r["zone"]["from_km"] == 0 and r["zone"]["to_km"] == 405  # 405 km Pfad: bei FL360 überall beidseitig sichtbar
    by = {p["flight"]: p for p in r["planes"]}
    assert "LOW" not in by
    assert by["DLH123"]["visible_both"] and abs(by["DLH123"]["xt_km"]) < 12 and by["DLH123"]["in_corridor"]
    assert not by["FAR"]["visible_both"] and by["FAR"]["eta_min"] and 20 < by["FAR"]["eta_min"] < 35
    assert r["planes"][0]["flight"] == "DLH123"  # Korridor-Flugzeuge zuerst
    # Querabstand/ETA-Vorzeichen: Flugzeug nördlich eines Ost-West-Pfads, Kurs Süd -> nähert sich
    xt, at = adsb.cross_along_track((50, 8), (50, 10), (50.5, 9))
    assert 50 < abs(xt) < 60 and 65 < at < 75
    assert adsb.radio_horizon_km(11000) > 430 and adsb.radio_horizon_km(0, 0) == 0


def test_aircraft_endpoint_local_source(tmp_path):
    src = tmp_path / "aircraft.json"
    src.write_text(json.dumps({"now": 1, "aircraft": [
        {"hex": "abc", "flight": "DLH123 ", "t": "A320", "lat": ON_PATH[0], "lon": ON_PATH[1], "alt_baro": 36000, "gs": 460, "track": 30},
        {"hex": "gnd", "flight": "TAXI", "t": "B738", "lat": 50.9, "lon": 7.1, "alt_baro": "ground", "gs": 5, "track": 0},
        {"hex": "nolat", "flight": "X"},
    ]}), encoding="utf-8")
    app = create_app(tmp_path / "t.db", backup_interval_min=0)
    with TestClient(app) as c:
        admin = c.post("/api/setup", json={"password": "admin1"}).json()["token"]
        H = {"X-Admin-Token": admin}
        c.post("/api/settings", json={"adsb_source": "local", "adsb_local_url": src.as_uri(), "adsb_corridor_km": 15}, headers=H)
        cfg = c.get("/api/settings", headers=H).json()
        assert cfg["adsb_source"] == "local" and cfg["adsb_corridor_km"] == 15
        r = c.get("/api/aircraft", params={"my": "JO31AA", "loc": "JN59LE"}).json()
        assert r["source"] == "local" and r["zone"] and [p["flight"] for p in r["planes"]] == ["DLH123"]
        assert r["planes"][0]["fl"] == 360 and r["planes"][0]["gs_kmh"] == 852 and r["planes"][0]["in_corridor"]
        r2 = c.get("/api/aircraft", params={"my": "JO31AA", "dist": 300}).json()  # ohne Partner: Umkreis 300 km
        assert r2["other"] == "" and {p["flight"] for p in r2["planes"]} == {"DLH123"}
        assert c.get("/api/aircraft", params={"my": "ZZ99"}).status_code == 400
        c.post("/api/settings", json={"adsb_local_url": "http://127.0.0.1:1/nix"}, headers=H)
        assert c.get("/api/aircraft", params={"my": "JO31AA"}).status_code == 502
