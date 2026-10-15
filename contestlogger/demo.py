"""Demo-Modus (BEAMLOG_DEMO=1) für eine öffentliche Vorführ-Instanz, z. B. https://beamlogdemo.lhprinting.de/.

- Feste, auf der Seite angezeigte Zugangsdaten: Admin-Passwort und Stations-Passwort „demo“.
- Alles, was den Server, fremde Dienste oder echte Zugangsdaten betrifft, ist gesperrt (DemoGuard):
  Updates, Admin-Passwort, Server-Einstellungen, KST-Verbindungen, Kachel-Vorabladen, Rufzeichen-Abfrage-Test, Backups,
  Übersetzungen speichern, Betreuer-Importe. Die Beispiel-Stationen und der Beispiel-Contest lassen sich nicht löschen.
- Täglich (BEAMLOG_DEMO_RESET, Standard 03:00 Serverzeit) und bei jedem Start wird alles auf einen Beispiel-Contest
  mit drei Stationen und QSOs aus der Stationsdatenbank zurückgesetzt.
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import env, geo

ADMIN_PASSWORD = "demo"
STATION_PASSWORD = "demo"
CALL = "DN0DEMO/P"
LOCATOR = "JO51DT"  # Brocken (Harz) – klassischer Contest-Standort
STATIONS = [("144MHz", 60), ("432MHz", 26), ("1296MHz", 9)]  # Band, Anzahl Beispiel-QSOs
MAX_UPLOAD = 5 * 1024 * 1024  # Importe in der Demo höchstens 5 MB

_ON = ("1", "true", "yes", "ja", "on")


def enabled() -> bool:
    return env("DEMO").strip().lower() in _ON


def reset_time() -> tuple[int, int]:
    """Uhrzeit des täglichen Zurücksetzens (Serverzeit), BEAMLOG_DEMO_RESET=HH:MM."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", env("DEMO_RESET", "03:00"))
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
        return int(m.group(1)), int(m.group(2))
    return 3, 0


def next_reset(now: datetime | None = None) -> datetime:
    now = now or datetime.now().astimezone()
    h, mi = reset_time()
    at = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    return at if at > now else at + timedelta(days=1)


def info() -> dict:
    h, mi = reset_time()
    return {"admin_password": ADMIN_PASSWORD, "station_password": STATION_PASSWORD, "reset_at": f"{h:02d}:{mi:02d}",
            "next_reset_utc": next_reset().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


# ------------------------------------------------------------------ Sperren
REASON = "In der Demo-Instanz gesperrt"
BLOCKED: list[tuple[str, re.Pattern, str]] = [(m, re.compile(p), why) for m, p, why in [
    ("POST", r"/api/setup$", "Admin-Passwort ist fest „demo“"),
    ("POST", r"/api/admin/password$", "Admin-Passwort ist fest „demo“"),
    ("POST", r"/api/settings$", "Server-Einstellungen"),
    ("POST", r"/api/update/apply$", "Updates spielt der Betreiber ein"),
    ("POST", r"/api/tiles/prefetch$", "Karten-Kacheln vorab laden"),
    ("DELETE", r"/api/tiles$", "Kachelcache leeren"),
    ("POST", r"/api/lookup/test$", "Rufzeichen-Abfrage (HamQTH/QRZ)"),
    ("POST", r"/api/backups$", "Backups"),
    ("POST", r"/api/kst/(start|send|broadcast|refresh_users)$", "ON4KST-Chat (echte Verbindung mit Zugangsdaten)"),
    ("POST", r"/api/lang/[^/]+$", "Übersetzungen speichern"),
    ("POST", r"/api/(import/results|darc/import|results/.*|callbook/import_list)$", "Betreuer-Importe"),
]]
SECRET_FIELDS = ("kst_user", "kst_pass", "kst_autostart")


class DemoGuard:
    """ASGI-Middleware: blockt gesperrte Aufrufe mit 403 und prüft Stations-Änderungen auf Zugangsdaten bzw. Beispiel-Daten."""

    def __init__(self, app, protected: Callable[[], dict]):
        self.app, self.protected = app, protected

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/") or scope.get("method") not in ("POST", "PATCH", "DELETE", "PUT"):
            return await self.app(scope, receive, send)
        method, path = scope["method"], scope["path"]
        for m, pat, why in BLOCKED:
            if m == method and pat.match(path):
                return await _deny(send, f"{REASON}: {why}.")
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if method == "POST" and re.match(r"/api/import(/folder)?$", path) and int(headers.get("content-length") or 0) > MAX_UPLOAD:
            return await _deny(send, f"{REASON}: Dateien über {MAX_UPLOAD // 1024 // 1024} MB.", 413)
        prot = self.protected()
        mo = re.match(r"/api/(contests|stations|templates)/(\d+)$", path)
        if method == "DELETE" and mo and int(mo.group(2)) in prot.get(mo.group(1), []):
            return await _deny(send, f"{REASON}: Der Beispiel-Contest und seine Stationen bleiben stehen – lege für Tests einen eigenen an.")
        if not (method in ("POST", "PATCH") and re.match(r"/api/(stations/\d+|templates(/\d+)?|contests/\d+/stations)$", path)):
            return await self.app(scope, receive, send)
        # Body lesen, prüfen und unverändert weiterreichen
        body, more = b"", True
        while more:
            msg = await receive()
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = {}
        if isinstance(data, dict):
            if any(data.get(k) for k in SECRET_FIELDS):
                return await _deny(send, f"{REASON}: ON4KST-Zugangsdaten – bitte hier keine echten Zugangsdaten eintragen.")
            mo = re.match(r"/api/(stations|templates)/(\d+)$", path)
            if mo and int(mo.group(2)) in prot.get(mo.group(1), []) and (data.get("password") or "call" in data and data["call"] != CALL):
                return await _deny(send, f"{REASON}: Rufzeichen und Passwort der Beispiel-Stationen bleiben fest.")
        sent = {"done": False}

        async def replay():
            if not sent["done"]:
                sent["done"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()
        return await self.app(scope, replay, send)


async def _deny(send, detail: str, status: int = 403) -> None:
    raw = json.dumps({"detail": detail}, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode())]})
    await send({"type": "http.response.body", "body": raw})


# ------------------------------------------------------------------ Zurücksetzen
KEEP_SETTINGS = ("secret", "templates_migrated")


def reset(db, seed_callbook: Callable[[], int], now: datetime | None = None) -> dict:
    """Alles löschen und den Beispiel-Contest neu anlegen. Gibt die geschützten IDs zurück (auch in settings 'demo_ids')."""
    now = (now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    if db.get_setting("demo_ids") is None and db.row("SELECT 1 AS x FROM contests LIMIT 1"):
        raise RuntimeError(f"Demo-Modus verweigert: Die Datenbank {db.path} enthält bereits Contests, die nicht aus der Demo stammen. "
                           "Der Demo-Modus löscht täglich alles – für eine Demo eine eigene, leere Datenbank (DB=…) verwenden.")
    with db.conn:
        for table in ("qsos", "stations", "contests", "station_templates", "chat", "kst_messages", "kst_seen", "audit", "callbook"):
            db.conn.execute(f"DELETE FROM {table}")  # noqa: S608 – feste Tabellennamen
        db.conn.execute(f"DELETE FROM settings WHERE key NOT IN ({','.join('?' * len(KEEP_SETTINGS))})", KEEP_SETTINGS)
    db.set_admin_password(ADMIN_PASSWORD)
    seed_callbook()

    start = (now - timedelta(hours=5)).replace(minute=0)
    cid = db.create_contest("Demo-Contest UKW (zum Ausprobieren)", start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            (start + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"), "km",
                            "Öffentliche Demo – alle Daten werden täglich zurückgesetzt.", "serial")
    info = {"section": "MULTI", "operators": "DEMO", "tx": "IC-9700", "rx": "IC-9700", "power": "100",
            "antenna": "2× 10-Element-Yagi", "antenna_height": "12", "asl": "1141", "site_city": "Brocken (Harz)"}
    tid = db.create_template(CALL, LOCATOR, "144MHz", "SSB", STATION_PASSWORD, info)
    rnd = random.Random(now.strftime("%Y%m%d"))
    pool = [r for r in db.rows("SELECT call, locator FROM callbook WHERE length(locator)=6")
            if geo.is_valid_locator(r["locator"]) and 25 <= geo.distance_km_int(LOCATOR, r["locator"]) <= 750]
    sids: list[int] = []
    for band, n in STATIONS:
        sid = db.create_station(cid, CALL, LOCATOR, band, "SSB", STATION_PASSWORD, info)
        sids.append(sid)
        picks = rnd.sample(pool, min(n, len(pool)))
        span = (now - start).total_seconds()
        times = sorted(start + timedelta(seconds=rnd.uniform(60, span - 120)) for _ in picks)
        for (r, ts) in zip(picks, times):
            db.add_qso(sid, {"call": r["call"], "locator": r["locator"], "ts_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "rst_sent": "59", "rst_rcvd": rnd.choice(["59", "59", "57", "55"]),
                             "serial_rcvd": str(rnd.randint(1, 180)).zfill(3)}, logged_by="Demo")
    for nick, text in [("BeamLog", "Willkommen in der BeamLog-Demo! Admin- und Stations-Passwort: demo. Probiert alles aus – "
                                    "die Daten werden täglich zurückgesetzt."),
                       ("BeamLog", "Tipp: Rufzeichen eintippen, Vorschläge kommen aus der Stationsdatenbank. F1 zeigt alle Tastenkürzel.")]:
        db.add_chat(nick, text, cid)
    ids = {"contests": [cid], "stations": sids, "templates": [tid]}
    db.set_setting("demo_ids", json.dumps(ids))
    db.set_setting("demo_reset_at", now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return ids


def protected_ids(db) -> dict:
    try:
        return json.loads(db.get_setting("demo_ids", "") or "{}")
    except ValueError:
        return {}
