"""Offline-Kachelcache: Karten-Kacheln über den Server laden, auf Platte speichern und daraus ausliefern.

Damit funktioniert die Karte auch ohne Internet am Standort: vor dem Contest einmal die Region vorab laden
(oder einfach die Karte ansehen – alles, was einmal geladen wurde, bleibt im Cache). Der Kachelserver von
OpenStreetMap erlaubt keine Massen-Downloads; Vorab-Laden ist deshalb auf kleine Zoomstufen (≤ 10) und eine
überschaubare Kachelzahl begrenzt. Für große Regionen/hohe Zoomstufen einen eigenen Kachelserver eintragen.
"""
from __future__ import annotations

import math
import threading
import time
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
MAX_PREFETCH_TILES = 4000
MAX_PREFETCH_ZOOM = 10
UA = "ContestLogger (Amateurfunk-Contest-Logger; offline map cache; contact via github.com/NoobKeksTV/ContestLogger)"


def latlon_to_tile(lat: float, lon: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(max(-85.05, min(85.05, lat)))
    y = int((1.0 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def region_tiles(lat: float, lon: float, radius_km: float, zmin: int, zmax: int) -> list[tuple[int, int, int]]:
    """Alle Kacheln (z, x, y), die ein Quadrat von ±radius_km um den Punkt abdecken."""
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    out: list[tuple[int, int, int]] = []
    for z in range(zmin, zmax + 1):
        x0, y0 = latlon_to_tile(lat + dlat, lon - dlon, z)
        x1, y1 = latlon_to_tile(lat - dlat, lon + dlon, z)
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                out.append((z, x, y))
    return out


class TileCache:
    def __init__(self, directory: Path, url_template: str = DEFAULT_URL):
        self.dir = Path(directory)
        self.url = url_template or DEFAULT_URL
        self.job: dict = {"running": False, "done": 0, "total": 0, "errors": 0, "skipped": 0, "started": 0.0, "finished": 0.0, "message": ""}
        self._stop = threading.Event()

    def path(self, z: int, x: int, y: int) -> Path:
        return self.dir / str(z) / str(x) / f"{y}.png"

    def get(self, z: int, x: int, y: int, fetch: bool = True, timeout: float = 15) -> bytes | None:
        """Kachel aus dem Cache; fehlt sie, vom Kachelserver holen und speichern (fetch=True)."""
        p = self.path(z, x, y)
        if p.exists():
            return p.read_bytes()
        if not fetch:
            return None
        url = self.url.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y)).replace("{s}", "a")
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/png,image/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        if data:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return data

    def stats(self) -> dict:
        n = size = 0
        if self.dir.exists():
            for f in self.dir.rglob("*.png"):
                n += 1
                size += f.stat().st_size
        return {"tiles": n, "size_mb": round(size / 1048576, 1), "dir": str(self.dir), "url": self.url, "job": dict(self.job)}

    def clear(self) -> int:
        n = 0
        if self.dir.exists():
            for f in self.dir.rglob("*.png"):
                f.unlink(missing_ok=True)
                n += 1
        return n

    def plan(self, lat: float, lon: float, radius_km: float, zmin: int, zmax: int) -> list[tuple[int, int, int]]:
        zmax = min(int(zmax), MAX_PREFETCH_ZOOM)
        zmin = max(2, min(int(zmin), zmax))
        tiles = region_tiles(lat, lon, radius_km, zmin, zmax)
        if len(tiles) > MAX_PREFETCH_TILES:
            raise ValueError(f"{len(tiles)} Kacheln – zu viele für den öffentlichen Kachelserver (max. {MAX_PREFETCH_TILES}). Radius oder Zoom verkleinern oder eigenen Kachelserver eintragen.")
        return tiles

    def prefetch(self, tiles: list[tuple[int, int, int]], delay: float = 0.15) -> None:
        """Hintergrund-Download (gedrosselt, höflich zum Kachelserver); Fortschritt in self.job."""
        if self.job["running"]:
            raise RuntimeError("Es läuft bereits ein Download")
        self._stop.clear()
        self.job.update({"running": True, "done": 0, "total": len(tiles), "errors": 0, "skipped": 0, "started": time.time(), "finished": 0.0, "message": ""})

        def work() -> None:
            for z, x, y in tiles:
                if self._stop.is_set():
                    self.job["message"] = "abgebrochen"
                    break
                try:
                    if self.path(z, x, y).exists():
                        self.job["skipped"] += 1
                    else:
                        self.get(z, x, y)
                        time.sleep(delay)
                except Exception as e:  # noqa: BLE001
                    self.job["errors"] += 1
                    self.job["message"] = str(e)[:120]
                    if self.job["errors"] > 20:
                        self.job["message"] = f"abgebrochen nach {self.job['errors']} Fehlern: {str(e)[:80]}"
                        break
                self.job["done"] += 1
            self.job["running"] = False
            self.job["finished"] = time.time()

        threading.Thread(target=work, daemon=True, name="tile-prefetch").start()

    def stop(self) -> None:
        self._stop.set()
