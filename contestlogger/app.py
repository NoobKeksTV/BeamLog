"""HTTP-/WebSocket-Server (FastAPI). Zentraler Speicher, Live-Updates und Chat
für alle im LAN angemeldeten Browser.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __app_name__, __copyright__, __license__, __source_url__, __version__, env, adsb, audit, exporters, geo, importers, kst, logcheck, lookup, prefixes, tiles, updater
from .db import Database, normalize_dok

STATIC = Path(__file__).parent / "static"
SEED = Path(__file__).parent / "seed" / "stationsdatenbank.csv"


def create_app(db_path: str | os.PathLike | None = None, backup_interval_min: float | None = None, public_url: str = "") -> FastAPI:
    db = Database(db_path or env("DB", "data/beamlog.db"))
    interval = backup_interval_min if backup_interval_min is not None else float(env("BACKUP_MIN", "15"))

    async def backup_loop():
        while True:
            await asyncio.sleep(interval * 60)
            try:
                # Nur sichern, wenn sich seit der letzten Sicherung etwas geändert hat
                changed = db.row("SELECT MAX(updated_at) AS t FROM qsos")
                last = db.get_setting("last_backup_change", "")
                if (changed or {}).get("t") != last:
                    await asyncio.to_thread(db.create_backup, "auto")
                    db.set_setting("last_backup_change", (changed or {}).get("t") or "")
            except Exception as e:  # noqa: BLE001
                print(f"Backup fehlgeschlagen: {e}")

    def seed_callbook() -> int:
        """Beim ersten Start: mitgelieferte Stationsdatenbank (aus den eigenen WinContest-Logs) laden."""
        if db.callbook_count() or db.get_setting("seeded") or not SEED.exists():
            return 0
        res = importers.parse_callbook_csv(SEED.read_text(encoding="utf-8"))
        import re as _re
        for call, loc, name in res.callbook:
            when = f"{name}T00:00:00Z" if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", name) else ""
            db.learn_call(call, loc, source="seed", name="" if when else name, when=when, dok=res.doks.get(call, ""))
        db.set_setting("seeded", "1")
        return len(res.callbook)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        n = seed_callbook()
        if n:
            print(f"Stationsdatenbank: {n} Rufzeichen aus der mitgelieferten Startdatei geladen.")
        db.add_audit("Server gestartet", details=f"Version {__version__}", nick="Server")
        db.prune_audit()
        task = asyncio.create_task(backup_loop()) if interval > 0 else None
        update_task = asyncio.create_task(update_loop())
        for st in db.rows("SELECT id FROM stations WHERE kst_autostart=1 AND kst_user<>'' AND kst_pass<>''"):
            try:
                await kst_start(st["id"])
            except HTTPException:
                pass
        yield
        db.add_audit("Server wird beendet", nick="Server")
        for c in list(kst_state.values()):
            await c.stop()
        if task:
            task.cancel()
        update_task.cancel()
        try:
            db.create_backup("shutdown")
        except Exception:  # noqa: BLE001
            pass
        db.close()

    app = FastAPI(title=__app_name__, version=__version__, lifespan=lifespan)
    app.state.db = db
    hub = Hub()
    app.state.hub = hub
    rig: dict[int, dict] = {}  # station_id -> {"freq": "432.200", "mode": "USB", "ts": ...}
    cw_queue: dict[int, list[str]] = {}  # station_id -> Texte, die die CAT-Bridge als CW senden soll
    # ------------------------------------------------------------ Updates (GitHub-Releases)
    update_state: dict[str, Any] = {"latest": None, "checked_at": 0.0, "error": "", "busy": False, "progress": ""}

    async def do_update_check(force: bool = False) -> dict:
        if db.get_setting("update_check", "1") == "0" and not force:
            return {"current": __version__, "available": False, "disabled": True}
        if not force and update_state["latest"] and time.time() - update_state["checked_at"] < 3600:
            return update_state["latest"]
        try:
            latest = await asyncio.to_thread(updater.check_latest, github_token())
            was = (update_state["latest"] or {}).get("version")
            update_state.update(latest=latest, checked_at=time.time(), error="")
            if latest["available"] and latest["version"] != was:
                await hub.broadcast({"type": "update_available", "version": latest["version"], "current": __version__})
            return latest
        except Exception as e:  # noqa: BLE001
            update_state.update(checked_at=time.time(), error=str(e))
            raise

    async def update_loop() -> None:
        await asyncio.sleep(20)
        while True:
            try:
                await do_update_check()
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(3600)

    kst_state: dict[int, kst.KstClient] = {}  # station_id -> Verbindung (eine je Station)
    app.state.kst_clients = kst_state

    def kst_event_for(station_id: int):
        async def kst_event(ev: dict) -> None:
            if ev.get("type") == "kst_users":
                for u in ev["users"]:
                    if u.get("locator"):
                        db.learn_call(u["call"], u["locator"], source="kst", name=u.get("name", ""))
            if ev.get("type") == "kst":
                m = ev["msg"]
                # Nach einem Neuverbinden schickt der KST-Server den letzten Verlauf erneut – schon bekannte
                # Nachrichten (gleiche Uhrzeit, Absender, Ziel, Text) nicht doppelt speichern und nicht erneut melden
                dup = db.row("SELECT 1 FROM kst_messages WHERE station_id=? AND time=? AND call=? AND to_call=? AND text=? AND id > (SELECT COALESCE(MAX(id),0) FROM kst_messages) - 400",
                             (station_id, m["time"], m["call"], m["to"], m["text"]))
                if not dup and m.get("replay"):
                    # wiederholter Verlauf nach (Neu-)Anmeldung: toleranter vergleichen (Uhrzeit + Absender + Text, Leerzeichen egal)
                    dup = db.row("SELECT 1 FROM kst_messages WHERE station_id=? AND time=? AND call=? AND REPLACE(text,' ','')=? AND id > (SELECT COALESCE(MAX(id),0) FROM kst_messages) - 1000",
                                 (station_id, m["time"], m["call"], m["text"].replace(" ", "")))
                if dup:
                    return
                m.pop("replay", None)
                with db.conn:
                    db.conn.execute("INSERT INTO kst_messages(ts_utc,time,call,name,to_call,text,own,to_me,station_id) VALUES(?,?,?,?,?,?,?,?,?)",
                                    (m["ts"], m["time"], m["call"], m["name"], m["to"], m["text"], int(m["own"]), int(m["to_me"]), station_id))
            if ev.get("type") != "kst_raw":
                await hub.broadcast({**ev, "station_id": station_id})
        return kst_event

    def kst_client(station_id: int | None) -> kst.KstClient | None:
        return kst_state.get(int(station_id or 0))

    def kst_my_calls(st: dict) -> list[str]:
        """Rufzeichen, bei denen eine KST-Nachricht als 'an mich' gilt: KST-Login, Stations-Call und die 'An mich'-Liste."""
        extra = [c for c in re.split(r"[\s,;]+", (st.get("kst_my_calls") or "").upper()) if c]
        return [c for c in [st.get("kst_user") or "", st.get("call") or "", *extra] if c]

    async def kst_start(station_id: int) -> dict:
        st = db.get_station(station_id, secrets=True)
        if not st:
            raise HTTPException(404, "Station nicht gefunden")
        user, pw = st.get("kst_user") or "", st.get("kst_pass") or ""
        if not (user and pw):
            raise HTTPException(400, "KST: Rufzeichen und Passwort bei der Station eintragen (Verwaltung → Station ✎)")
        c = kst_state.get(station_id)
        if c:
            await c.stop()
        c = kst.KstClient(user, pw, int(st.get("kst_room") or 2), kst_event_for(station_id), my_calls=kst_my_calls(st))
        kst_state[station_id] = c
        c.start()
        return c.status()

    async def kst_stop(station_id: int) -> None:
        c = kst_state.pop(station_id, None)
        if c:
            await c.stop()

    REPO_CALLBOOK_URL = "https://api.github.com/repos/NoobKeksTV/BeamLog/contents/contestlogger/seed/stationsdatenbank.csv?ref=main"

    def github_token() -> str:
        """Optionales GitHub-Token nur aus Umgebung/Config (BEAMLOG_GITHUB_TOKEN) – das Repo ist öffentlich, normalerweise leer."""
        return env("GITHUB_TOKEN")
    lookup_state = {"client": None}
    lookup_cache: dict[str, float] = {}  # Call -> Zeitpunkt der letzten erfolglosen Abfrage

    def lookup_client() -> lookup.Lookup:
        if lookup_state["client"] is None:
            lookup_state["client"] = lookup.Lookup(db.get_setting("lookup_provider", "none") or "none",
                                                   db.get_setting("lookup_user", "") or "", db.get_setting("lookup_pass", "") or "")
        return lookup_state["client"]

    # ------------------------------------------------------------ Auth-Helfer
    def is_admin(token: str | None) -> bool:
        return bool(token) and token == db.sign("admin")

    def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
        if not is_admin(x_admin_token):
            raise HTTPException(403, "Admin-Anmeldung erforderlich")

    def is_maintainer() -> bool:
        """Betreuer-Modus (MAINTAINER=1 in beamlog.env): Quellen-Importe für die zentrale Stationsdatenbank."""
        on = ("1", "true", "yes", "ja", "on")
        return env("MAINTAINER").strip().lower() in on or env("DEV").strip().lower() in on

    def require_maintainer(x_admin_token: str | None = Header(default=None)) -> None:
        if not is_admin(x_admin_token):
            raise HTTPException(403, "Admin-Anmeldung erforderlich")
        if not is_maintainer():
            raise HTTPException(403, "Nur im Betreuer-Modus (MAINTAINER=1 in beamlog.env). Normale Installationen holen die Liste über „Nach neuen suchen (Repo)“.")

    def require_station(sid: int, token: str | None, admin: str | None) -> dict:
        station = db.get_station(sid)
        if not station:
            raise HTTPException(404, "Station nicht gefunden")
        if is_admin(admin) or db.check_station_token(sid, token or ""):
            return station
        raise HTTPException(403, "Station ist nicht freigeschaltet")

    def nick_of(x_nick: str | None) -> str:
        return (x_nick or "").strip()[:24]

    app.add_middleware(audit.AuditMiddleware, record=db.add_audit, is_admin=is_admin)

    @app.get("/api/audit", dependencies=[Depends(require_admin)])
    def audit_list(limit: int = 200, q: str = ""):
        return db.list_audit(min(int(limit), 2000), q.strip())

    @app.get("/api/audit.txt", dependencies=[Depends(require_admin)])
    def audit_txt(limit: int = 5000):
        lines = [f"{r['ts_utc']}  {r['nick'] or '?'}{' [Admin]' if r['admin'] else ''}  {r['action']}  {r['details']}  {'(' + str(r['status']) + ')' if r['status'] >= 400 else ''}".rstrip()
                 for r in reversed(db.list_audit(min(int(limit), 20000)))]
        return PlainTextResponse("\n".join(lines), headers={"Content-Disposition": "attachment; filename=beamlog-protokoll.txt"})

    # ------------------------------------------------------------ Allgemein
    @app.get("/api/info")
    def info():
        return {
            "app": __app_name__, "version": __version__, "copyright": __copyright__, "license": __license__, "source_url": __source_url__,
            "admin_configured": db.admin_configured(), "callbook_count": db.callbook_count(),
            "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "public_url": public_url or env("URL"),
            "tile_url": db.get_setting("tile_url", "") or "",
            "tile_cache": db.get_setting("tile_cache", "0") == "1",  # Kacheln über den Server (Offline-Cache) statt direkt vom Kachelserver
            "lookup_provider": db.get_setting("lookup_provider", "none") or "none",
            "mdbtools": True,  # MDB-Import rein in Python eingebaut
            "maintainer": is_maintainer(),
        }

    @app.get("/api/qr.svg")
    def qr_svg(text: str = Query(..., max_length=500)):
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
        return Response(img.to_string(), media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

    @app.post("/api/settings", dependencies=[Depends(require_admin)])
    def set_settings(body: dict):
        for k in ("tile_url", "tile_cache", "lookup_provider", "lookup_user", "lookup_pass", "kst_macros", "repo_url", "adsb_source", "adsb_local_url", "adsb_corridor_km", "adsb_antenna_m", "update_check"):
            if k in body:
                db.set_setting(k, json.dumps(body[k]) if k == "kst_macros" else str(body[k] or ""))
        lookup_state["client"] = None
        lookup_cache.clear()
        return {"ok": True}

    @app.get("/api/settings", dependencies=[Depends(require_admin)])
    def get_settings():
        return {"tile_url": db.get_setting("tile_url", ""), "lookup_provider": db.get_setting("lookup_provider", "none") or "none",
                "lookup_user": db.get_setting("lookup_user", ""), "lookup_pass_set": bool(db.get_setting("lookup_pass", "")),
                "providers": lookup.PROVIDERS,
                "kst_rooms": kst.ROOMS, "repo_url": db.get_setting("repo_url", "") or REPO_CALLBOOK_URL,
                "adsb_source": db.get_setting("adsb_source", "adsb.fi") or "adsb.fi", "adsb_local_url": db.get_setting("adsb_local_url", "") or "",
                "adsb_corridor_km": float(db.get_setting("adsb_corridor_km", "12") or 12), "adsb_antenna_m": float(db.get_setting("adsb_antenna_m", "15") or 15),
                "update_check": db.get_setting("update_check", "1") != "0", "tile_cache": db.get_setting("tile_cache", "0") == "1"}

    # ------------------------------------------------------------ Karten-Kacheln (Offline-Cache)
    tile_cache = tiles.TileCache(db.path.parent / "tiles", db.get_setting("tile_url", "") or tiles.DEFAULT_URL)

    @app.get("/tiles/{z}/{x}/{y}.png")
    async def tile(z: int, x: int, y: int):
        """Kachel aus dem Server-Cache; fehlt sie, wird sie (bei Internet) nachgeladen und gespeichert."""
        tile_cache.url = db.get_setting("tile_url", "") or tiles.DEFAULT_URL
        try:
            data = await asyncio.to_thread(tile_cache.get, z, x, y)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Kachel nicht verfügbar: {e}")
        if not data:
            raise HTTPException(404)
        return Response(data, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})

    @app.get("/api/tiles/status", dependencies=[Depends(require_admin)])
    def tiles_status():
        return tile_cache.stats()

    @app.post("/api/tiles/prefetch", dependencies=[Depends(require_admin)])
    def tiles_prefetch(body: dict):
        """Region vorab laden: Locator (Mitte), Radius km, Zoom von/bis – läuft im Hintergrund, Status über /api/tiles/status."""
        loc = str(body.get("locator") or "").upper()
        if not geo.is_valid_locator(loc):
            raise HTTPException(400, "Locator ungültig")
        lat, lon = geo.locator_to_latlon(loc)
        tile_cache.url = db.get_setting("tile_url", "") or tiles.DEFAULT_URL
        try:
            plan = tile_cache.plan(lat, lon, float(body.get("radius_km") or 300), int(body.get("zmin") or 4), int(body.get("zmax") or 9))
            tile_cache.prefetch(plan)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(400, str(e))
        db.add_audit("Karten-Kacheln vorab geladen", details=f"{loc} ±{body.get('radius_km', 300)} km, Zoom {body.get('zmin', 4)}–{body.get('zmax', 9)}: {len(plan)} Kacheln", nick="Admin", admin=True)
        return {"total": len(plan)}

    @app.post("/api/tiles/stop", dependencies=[Depends(require_admin)])
    def tiles_stop():
        tile_cache.stop()
        return {"ok": True}

    @app.delete("/api/tiles", dependencies=[Depends(require_admin)])
    def tiles_clear():
        n = tile_cache.clear()
        db.add_audit("Kachelcache geleert", details=f"{n} Kacheln", nick="Admin", admin=True)
        return {"deleted": n}

    @app.post("/api/lookup/test", dependencies=[Depends(require_admin)])
    async def lookup_test():
        try:
            return {"ok": True, "msg": await asyncio.to_thread(lookup_client().test)}
        except lookup.LookupError_ as e:
            return {"ok": False, "msg": str(e)}

    @app.get("/api/lookup")
    async def lookup_call(call: str):
        """Rufzeichen nachschlagen: erst Stationsdatenbank, dann (wenn eingerichtet) HamQTH/QRZ."""
        core = prefixes.core_call(call)
        known = db.lookup_call(core)
        if known and known.get("locator"):
            alts = [a for a in (known.get("alt_locators") or "").split(",") if a and a != known["locator"]]
            return {"source": "local", **{k: known[k] for k in ("call", "locator", "name")}, "alt_locators": alts}
        client = lookup_client()
        if not client.enabled or not prefixes.is_plausible_call(core):
            return {"source": "none"}
        import time as _t
        if _t.time() - lookup_cache.get(core, 0) < 600:
            return {"source": "none"}
        try:
            res = await asyncio.to_thread(client.lookup, core)
        except lookup.LookupError_ as e:
            return {"source": "error", "error": str(e)}
        if not res:
            lookup_cache[core] = _t.time()
            return {"source": "none"}
        db.learn_call(core, res.get("locator", ""), source=res["source"], name=res.get("name", ""))
        return {"call": core, **res}

    @app.post("/api/setup")
    def setup(body: dict):
        if db.admin_configured():
            raise HTTPException(409, "Admin-Passwort ist bereits gesetzt")
        pw = (body.get("password") or "").strip()
        if len(pw) < 4:
            raise HTTPException(400, "Passwort zu kurz (mind. 4 Zeichen)")
        db.set_admin_password(pw)
        return {"token": db.sign("admin")}

    @app.post("/api/admin/login")
    def admin_login(body: dict):
        if not db.check_admin(body.get("password") or ""):
            raise HTTPException(403, "Falsches Admin-Passwort")
        return {"token": db.sign("admin")}

    @app.post("/api/admin/password", dependencies=[Depends(require_admin)])
    def admin_password(body: dict):
        pw = (body.get("password") or "").strip()
        if len(pw) < 4:
            raise HTTPException(400, "Passwort zu kurz")
        db.set_admin_password(pw)
        return {"ok": True}

    # ------------------------------------------------------------ Contests
    @app.get("/api/contests")
    def contests():
        out = db.list_contests()
        for c in out:
            c["stations"] = db.list_stations(c["id"])
        return out

    @app.post("/api/contests", dependencies=[Depends(require_admin)])
    async def create_contest(body: dict):
        if not (body.get("name") or "").strip():
            raise HTTPException(400, "Name fehlt")
        cid = db.create_contest(body["name"], body.get("start_utc"), body.get("end_utc"), body.get("scoring", "km"), body.get("notes", ""), body.get("exchange") or "serial")
        for tid in body.get("template_ids") or []:  # teilnehmende globale Stationen
            try:
                sid = db.create_station_from_template(cid, int(tid))
            except ValueError:
                continue
            st = db.get_station(sid, secrets=True) or {}
            if st.get("kst_autostart") and st.get("kst_user") and st.get("kst_pass"):
                try:
                    await kst_start(sid)
                except HTTPException:
                    pass
        await hub.broadcast({"type": "update", "scope": "contests"})
        return db.get_contest(cid)

    # ------------------------------------------------------------ globale Stationen (Vorlagen)
    @app.get("/api/templates", dependencies=[Depends(require_admin)])
    def templates_list():
        return db.list_templates()

    @app.post("/api/templates", dependencies=[Depends(require_admin)])
    def template_create(body: dict):
        try:
            tid = db.create_template(body.get("call", ""), body.get("locator", ""), body.get("band", "144MHz"), body.get("mode", "SSB"), body.get("password", ""), body.get("info") or {},
                                     **{k: v for k, v in body.items() if k.startswith("kst_")})
        except ValueError as e:
            raise HTTPException(400, str(e))
        return db.get_template(tid)

    @app.patch("/api/templates/{tid}", dependencies=[Depends(require_admin)])
    def template_update(tid: int, body: dict):
        if not db.get_template(tid):
            raise HTTPException(404, "Globale Station nicht gefunden")
        try:
            db.update_template(tid, **body)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return db.get_template(tid)

    @app.delete("/api/templates/{tid}", dependencies=[Depends(require_admin)])
    def template_delete(tid: int):
        db.delete_template(tid)
        return {"ok": True}

    @app.post("/api/contests/{cid}/stations/from_template", dependencies=[Depends(require_admin)])
    async def station_from_template(cid: int, body: dict):
        if not db.get_contest(cid):
            raise HTTPException(404, "Contest nicht gefunden")
        try:
            sid = db.create_station_from_template(cid, int(body.get("template_id") or 0))
        except ValueError as e:
            raise HTTPException(400, str(e))
        await hub.broadcast({"type": "update", "scope": "contests"})
        return db.get_station(sid)

    @app.patch("/api/contests/{cid}", dependencies=[Depends(require_admin)])
    async def update_contest(cid: int, body: dict):
        old = db.get_contest(cid)
        if not old:
            raise HTTPException(404)
        db.update_contest(cid, **body)
        new = db.get_contest(cid)
        if new and new.get("scoring") != old.get("scoring"):
            await asyncio.to_thread(db.rescore_contest, cid)  # Punkte aller QSOs nach der neuen Wertung
            for s in db.list_stations(cid):
                await hub.broadcast({"type": "update", "scope": "qsos", "station_id": s["id"]})
        await hub.broadcast({"type": "update", "scope": "contests"})
        return new

    @app.delete("/api/contests/{cid}", dependencies=[Depends(require_admin)])
    async def delete_contest(cid: int):
        db.delete_contest(cid)
        await hub.broadcast({"type": "update", "scope": "contests"})
        return {"ok": True}

    @app.get("/api/contests/{cid}/scoreboard")
    def scoreboard(cid: int):
        rows = db.scoreboard(cid)
        for r in rows:
            r["rig"] = rig.get(r["id"])
        return rows

    @app.get("/api/contests/{cid}/stats")
    def contest_stats(cid: int):
        if not db.get_contest(cid):
            raise HTTPException(404)
        return db.contest_stats(cid)

    @app.get("/api/contests/{cid}/summary")
    def contest_summary(cid: int):
        if not db.get_contest(cid):
            raise HTTPException(404)
        return db.contest_summary(cid)

    @app.get("/api/backups", dependencies=[Depends(require_admin)])
    def backups():
        return {"dir": str(db.backup_dir), "interval_min": interval, "backups": db.list_backups()[:60]}

    @app.post("/api/backups", dependencies=[Depends(require_admin)])
    async def backup_now():
        path = await asyncio.to_thread(db.create_backup, "manual")
        return {"name": path.name}

    @app.post("/api/stations/{sid}/rig")
    async def rig_update(sid: int, body: dict, x_station_token: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        """Von der CAT-Bridge (tools/cat_bridge.py) gemeldete Frequenz/Betriebsart."""
        require_station(sid, x_station_token, x_admin_token)
        freq = body.get("freq")
        entry = {"freq": f"{float(freq):.3f}" if freq not in (None, "") else "", "mode": str(body.get("mode") or ""),
                 "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        rig[sid] = entry
        await hub.broadcast({"type": "rig", "station_id": sid, **entry})
        return entry

    @app.get("/api/stations/{sid}/rig")
    def rig_get(sid: int):
        return rig.get(sid) or {}

    @app.post("/api/stations/{sid}/cw")
    async def cw_send(sid: int, body: dict, x_station_token: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        """Makro-Text in die CW-Warteschlange stellen; die CAT-Bridge (--cw) holt ihn ab und gibt ihn über rigctld."""
        require_station(sid, x_station_token, x_admin_token)
        text = (body.get("text") or "").strip()[:200]
        if body.get("stop"):
            cw_queue[sid] = ["\x00STOP"]
        elif text:
            cw_queue.setdefault(sid, []).append(text)
        return {"queued": len(cw_queue.get(sid, []))}

    @app.get("/api/stations/{sid}/cw/next")
    def cw_next(sid: int, x_station_token: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        require_station(sid, x_station_token, x_admin_token)
        q = cw_queue.get(sid) or []
        if not q:
            return {}
        text = q.pop(0)
        if text == "\x00STOP":
            cw_queue[sid] = []
            return {"stop": True}
        rig.setdefault(sid, {})["cw"] = True
        return {"text": text}

    # ------------------------------------------------------------ Stationen
    @app.post("/api/contests/{cid}/stations", dependencies=[Depends(require_admin)])
    async def create_station(cid: int, body: dict):
        if not db.get_contest(cid):
            raise HTTPException(404, "Contest nicht gefunden")
        try:
            sid = db.create_station(cid, body.get("call", ""), body.get("locator", ""), body.get("band", "144MHz"),
                                    body.get("mode", "SSB"), body.get("password", ""), body.get("info") or {})
        except ValueError as e:
            raise HTTPException(400, str(e))
        kst_fields = {k: v for k, v in body.items() if k.startswith("kst_")}
        if kst_fields:
            db.update_station(sid, **kst_fields)
        await hub.broadcast({"type": "update", "scope": "contests"})
        return db.get_station(sid)

    @app.patch("/api/stations/{sid}")
    async def update_station(sid: int, body: dict, x_station_token: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        require_station(sid, x_station_token, x_admin_token)
        if not is_admin(x_admin_token):
            # Operator darf nur Stationsdaten (Antenne usw.) und Seriennummer ändern, nicht Call/Passwort
            body = {k: v for k, v in body.items() if k in ("info", "serial_next", "mode")}
        try:
            db.update_station(sid, **body)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if any(k.startswith("kst_") for k in body) and kst_client(sid):
            await kst_stop(sid)
            try:
                await kst_start(sid)
            except HTTPException:
                pass
        await hub.broadcast({"type": "update", "scope": "contests"})
        await hub.broadcast({"type": "update", "scope": "qsos", "station_id": sid})
        return db.get_station(sid)

    @app.delete("/api/stations/{sid}", dependencies=[Depends(require_admin)])
    async def delete_station(sid: int):
        await kst_stop(sid)
        db.delete_station(sid)
        await hub.broadcast({"type": "update", "scope": "contests"})
        return {"ok": True}

    @app.post("/api/stations/{sid}/unlock")
    def unlock(sid: int, body: dict, x_admin_token: str | None = Header(default=None)):
        if not db.get_station(sid):
            raise HTTPException(404)
        if is_admin(x_admin_token) or db.check_station_password(sid, body.get("password") or ""):
            return {"token": db.station_token(sid)}
        raise HTTPException(403, "Falsches Stations-Passwort")

    @app.post("/api/stations/{sid}/serial")
    async def reset_serial(sid: int, body: dict, x_station_token: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        require_station(sid, x_station_token, x_admin_token)
        db.reset_serial(sid, int(body.get("start", 1)))
        await hub.broadcast({"type": "update", "scope": "contests"})
        return db.get_station(sid)

    @app.get("/api/stations/{sid}/stats")
    def stats(sid: int):
        if not db.get_station(sid):
            raise HTTPException(404)
        return db.station_stats(sid)

    # ------------------------------------------------------------ QSOs
    @app.get("/api/stations/{sid}/qsos")
    def qsos(sid: int, limit: int | None = Query(default=None), q: str = Query(default="")):
        if not db.get_station(sid):
            raise HTTPException(404)
        return db.list_qsos(sid, limit=limit, search=q)

    @app.post("/api/stations/{sid}/qsos")
    async def add_qso(sid: int, body: dict, x_station_token: str | None = Header(default=None),
                      x_admin_token: str | None = Header(default=None), x_nick: str | None = Header(default=None)):
        require_station(sid, x_station_token, x_admin_token)
        try:
            qso = db.add_qso(sid, body, logged_by=nick_of(x_nick))
        except ValueError as e:
            raise HTTPException(400, str(e))
        await hub.broadcast({"type": "update", "scope": "qsos", "station_id": sid, "qso": qso, "by": nick_of(x_nick)})
        return qso

    @app.patch("/api/qsos/{qid}")
    async def update_qso(qid: int, body: dict, x_station_token: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        old = db.get_qso(qid)
        if not old:
            raise HTTPException(404)
        require_station(old["station_id"], x_station_token, x_admin_token)
        try:
            qso = db.update_qso(qid, body)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await hub.broadcast({"type": "update", "scope": "qsos", "station_id": old["station_id"]})
        return qso

    @app.delete("/api/qsos/{qid}")
    async def delete_qso(qid: int, x_station_token: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        old = db.get_qso(qid)
        if not old:
            raise HTTPException(404)
        require_station(old["station_id"], x_station_token, x_admin_token)
        db.delete_qso(qid)
        await hub.broadcast({"type": "update", "scope": "qsos", "station_id": old["station_id"]})
        return {"ok": True}

    # ------------------------------------------------------------ Call-Buch
    @app.get("/api/suggest")
    def suggest(q: str = "", station: int | None = None):
        return db.suggest(q, station_id=station)

    @app.get("/api/call")
    def call_lookup(call: str = ""):
        return db.lookup_call(call) or {}

    def fmt_day(ts: str) -> str:
        """2025-05-03… -> 03.05.2025"""
        d = (ts or "")[:10]
        return f"{d[8:10]}.{d[5:7]}.{d[0:4]}" if len(d) == 10 else d

    @app.get("/api/calc")
    def calc(my: str, loc: str, call: str = ""):
        from . import geo  # noqa: F401
        if not (geo.is_valid_locator(my) and geo.is_valid_locator(loc)):
            return {"valid": False}
        out = {"valid": True, "km": geo.distance_km_int(my, loc), "bearing": round(geo.bearing_deg(my, loc)) % 360, "warnings": []}
        if call:
            pl = prefixes.check_plausibility(call, loc)
            if not pl["ok"]:
                out["warnings"].append(pl["msg"])
            known = db.lookup_call(call)
            if known and known["locator"]:
                # Hauptlocator und alle bekannten weiteren Standorte zählen; ein 4-stelliger Eintrag passt zu jedem Feld darin
                locs = [known["locator"]] + [x for x in (known.get("alt_locators") or "").split(",") if x and x != known["locator"]]
                mine = geo.normalize_locator(loc)
                if not any(mine == k or mine.startswith(k) or k.startswith(mine) for k in locs if k):
                    when = f", zuletzt {fmt_day(known['last_seen'])}" if known.get("last_seen") else ""
                    out["warnings"].append(f"Stationsdatenbank kennt {prefixes.core_call(call)} mit {', '.join(locs)}{when}")
        return out

    @app.get("/api/callbook")
    def callbook_list(q: str = "", limit: int = 200):
        q = q.strip().upper()
        sql = "SELECT call, locator, name, qso_count, last_seen, alt_locators, source, dok FROM callbook"
        params: list = []
        if q:
            sql += " WHERE call LIKE ? OR locator LIKE ? OR name LIKE ? OR dok=?"
            params = [f"%{q}%", f"{q}%", f"%{q}%", q]
        rows = db.rows(sql + " ORDER BY call LIMIT ?", params + [min(int(limit), 2000)])
        return {"total": db.callbook_count(), "rows": rows}

    @app.delete("/api/callbook/{call}", dependencies=[Depends(require_admin)])
    def callbook_delete(call: str):
        with db.conn:
            db.conn.execute("DELETE FROM callbook WHERE call=?", (call.upper(),))
        return {"ok": True}

    @app.post("/api/import/folder", dependencies=[Depends(require_admin)])
    async def import_folder(files: list[UploadFile] = File(...), x_nick: str | None = Header(default=None)):
        """Ganzer WinContest-Ordner (mehrere Dateien): jedes Log wird ein archivierter Contest, alle Calls ins Call-Buch."""
        report: dict[str, Any] = {"files": [], "contests": 0, "qsos": 0, "callbook": 0, "calls_new": 0, "calls_known": 0, "skipped": []}
        seen_logs: set[tuple[str, str]] = set()
        for up in sorted(files, key=lambda f: (0 if (f.filename or "").lower().endswith(".mdb") else 1, f.filename or "")):
            name = Path(up.filename or "datei").name
            if name.lower().rsplit(".", 1)[-1] not in ("mdb", "txt", "exp", "edi", "adi", "adif", "csv"):
                continue
            data = await up.read()
            try:
                res = importers.parse_file(name, data)
            except ValueError as e:
                report["skipped"].append(f"{name}: {e}")
                continue
            if not res.qsos and not res.callbook:
                continue
            entry = {"file": name, "kind": res.kind, "qsos": len(res.qsos), "imported": 0, "calls_new": 0, "calls_known": 0}
            for call, loc, nm in res.callbook:
                r = db.learn_call(call, loc, source="import", name=nm, dok=res.doks.get(prefixes.core_call(call), ""))
                entry["calls_new" if r == "new" else "calls_known"] += 1 if r else 0
            for q in res.qsos:
                r = db.learn_call(q.call, q.locator, source="import", when=q.ts_utc)
                entry["calls_new" if r == "new" else "calls_known"] += 1 if r else 0
            report["callbook"] += entry["calls_new"] + entry["calls_known"]
            report["calls_new"] += entry["calls_new"]
            report["calls_known"] += entry["calls_known"]
            report["files"].append(entry)
            if not res.qsos or not res.header.get("locator"):
                continue
            band = res.header.get("band") or res.qsos[0].band or "144MHz"
            first = min(q.ts_utc for q in res.qsos)
            key = (f"{prefixes.core_call(res.header.get('call', ''))}/{band}", first)
            if key in seen_logs:
                entry["note"] = "gleiches Log bereits aus anderer Datei übernommen"
                continue
            seen_logs.add(key)
            cname = res.header.get("name") or f"{Path(name).stem} ({band})"
            existing = next((c for c in db.list_contests() if c["name"] == cname), None)
            cid = existing["id"] if existing else db.create_contest(cname, first, max(q.ts_utc for q in res.qsos))
            if not existing:
                db.update_contest(cid, archived=1)
                report["contests"] += 1
            st = next((x for x in db.list_stations(cid) if x["band"] == band), None)
            sid = st["id"] if st else db.create_station(cid, res.header.get("call") or "IMPORT", res.header["locator"], band, "SSB", "")
            have = {(q["core_call"], q["ts_utc"]) for q in db.list_qsos(sid)}
            for q in sorted(res.qsos, key=lambda x: x.ts_utc):
                if (prefixes.core_call(q.call), q.ts_utc) in have:
                    continue
                d = q.__dict__.copy()
                d["band"] = d["band"] or band
                try:
                    db.add_qso(sid, d, logged_by=nick_of(x_nick) or "import")
                    entry["imported"] += 1
                    report["qsos"] += 1
                except ValueError as e:
                    report["skipped"].append(f"{name} {q.call}: {e}")
        await hub.broadcast({"type": "update", "scope": "contests"})
        return report

    @app.post("/api/import/results", dependencies=[Depends(require_maintainer)])
    async def import_results(file: UploadFile | None = File(None), text: str = Form(""), url: str = Form(""),
                             commit: int = Form(0), selected: str = Form("")):
        """Ergebnisliste (DARC/IARU/…) als Datei, Text oder URL: Vorschau (commit=0) oder Übernahme (commit=1)."""
        raw = b""
        name = ""
        if file is not None and file.filename:
            raw = await file.read()
            name = file.filename
        elif url.strip():
            import urllib.request
            try:
                req = urllib.request.Request(url.strip(), headers={"User-Agent": "Mozilla/5.0 BeamLog"})
                with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
                    raw = r.read(20_000_000)
                    name = url
                    ctype = r.headers.get("Content-Type", "")
                    if "pdf" in ctype.lower():
                        name = url + ".pdf"
            except Exception as e:  # noqa: BLE001
                raise HTTPException(400, f"Abruf fehlgeschlagen: {e}")
        elif text.strip():
            raw = text.encode("utf-8")
        else:
            raise HTTPException(400, "Datei, Text oder URL angeben")
        try:
            content = importers.pdf_to_text(raw) if (name.lower().endswith(".pdf") or raw[:5] == b"%PDF-") else importers.html_to_text(raw)
            res = importers.parse_results_list(content)
        except ValueError as e:
            raise HTTPException(400, str(e))
        pairs = [{"call": c, "locator": loc, "dok": res.doks.get(prefixes.core_call(c), "")} for c, loc, _ in res.callbook]
        if not commit:
            known = {r["call"]: r["locator"] for r in db.rows("SELECT call, locator FROM callbook")}
            for pr in pairs:
                core = prefixes.core_call(pr["call"])
                pr["known"] = known.get(core, "")
                pr["status"] = "neu" if core not in known else ("gleich" if known[core] == pr["locator"] else "anders")
            return {"pairs": pairs, "warnings": res.warnings[:100], "count": len(pairs)}
        wanted = set(x.strip().upper() for x in selected.split(",") if x.strip()) if selected else None
        n = 0
        for pr in pairs:
            if wanted is not None and pr["call"] not in wanted:
                continue
            db.learn_call(pr["call"], pr["locator"], source="results", dok=pr.get("dok", ""))
            n += 1
        return {"imported": n}

    # ------------------------------------------------------------ ON4KST-Chat
    @app.get("/api/kst/status")
    def kst_status(station_id: int = 0):
        c = kst_client(station_id)
        st = db.get_station(station_id, secrets=True) or {}
        base = {"configured": bool(st.get("kst_user") and st.get("kst_pass")), "station_id": station_id,
                "macros": json.loads(db.get_setting("kst_macros", "") or "null") or kst_default_macros()}
        return {**base, **(c.status() if c else {"state": "aus", "error": "", "users": 0, "messages": 0, "user": st.get("kst_user", ""), "room": int(st.get("kst_room") or 2)})}

    def kst_default_macros() -> list[dict]:
        # Im KST-Reiter gehen die Texte an alle (ohne Adressierung); im DM-Reiter werden sie automatisch an den Kontakt gerichtet.
        return [{"label": "CQ", "text": "CQ {band} from {myloc} – who is QRV? pse call"},
                {"label": "QRV", "text": "QRV {band} SSB, loc {myloc}, listening"},
                {"label": "TNX", "text": "TNX QSO, 73!"},
                {"label": "NIL", "text": "sri, nil heard – try again later?"},
                {"label": "SKED", "text": "sked {band} in 5 min?"}]

    def body_station(body: dict) -> int:
        return int(body.get("station_id") or 0)

    @app.post("/api/kst/start", dependencies=[Depends(require_admin)])
    async def kst_start_ep(body: dict | None = None):
        return await kst_start(body_station(body or {}))

    @app.post("/api/kst/stop", dependencies=[Depends(require_admin)])
    async def kst_stop_ep(body: dict | None = None):
        await kst_stop(body_station(body or {}))
        return {"state": "aus"}

    @app.post("/api/kst/send")
    async def kst_send(body: dict, x_nick: str | None = Header(default=None)):
        c = kst_client(body_station(body))
        if not c or c.state != "verbunden":
            raise HTTPException(409, "Nicht mit dem KST-Chat verbunden")
        text = (body.get("text") or "").strip()[:300]
        if not text:
            raise HTTPException(400, "Leere Nachricht")
        if text.startswith("/") and not text.upper().startswith("/CQ "):
            await c.send_command(text)
        else:
            await c.send_text(text)
        return {"ok": True}

    @app.get("/api/kst/candidates")
    def kst_candidates(station_id: int, max_km: int = 300, include_away: int = 0):
        """KST-Nutzer im Umkreis, die mit dieser Station (Band) noch nicht gearbeitet wurden."""
        st = db.get_station(station_id)
        c = kst_client(station_id)
        if not st or not c:
            return []
        worked = {q["core_call"] for q in db.list_qsos(station_id)}
        # wer von dieser Station schon eine gerichtete Nachricht bekommen hat (Rundruf, DM, anderer Client), fällt raus
        messaged = {prefixes.core_call(r["to_call"]) for r in db.rows("SELECT DISTINCT to_call FROM kst_messages WHERE station_id=? AND own=1 AND to_call<>''", (station_id,))}
        st_full = db.get_station(station_id, secrets=True) or {}
        mine = {prefixes.core_call(st["call"]), prefixes.core_call(st_full.get("kst_user") or "")} | {prefixes.core_call(x) for x in kst_my_calls(st_full)}
        out = []
        for u in c.users.values():
            if not u.get("locator") or not geo.is_valid_locator(u["locator"]):
                continue
            if u.get("away") and not include_away:
                continue
            core = prefixes.core_call(u["call"])
            if core in worked or core in mine or core in messaged or core in kst.SYSTEM_SENDERS:
                continue
            km = geo.distance_km_int(st["locator"], u["locator"])
            if km > max_km:
                continue
            out.append({**u, "km": km, "bearing": round(geo.bearing_deg(st["locator"], u["locator"])) % 360})
        out.sort(key=lambda u: u["km"])
        return out

    @app.get("/api/kst/raw", dependencies=[Depends(require_admin)])
    def kst_raw(station_id: int = 0):
        """Rohzeilen der KST-Verbindung (letzte 500) – zur Fehlersuche."""
        c = kst_client(station_id)
        return {"lines": list(c.raw) if c else [], "state": c.state if c else "aus"}

    @app.get("/api/kst/rundruf_texts")
    def rundruf_texts_get():
        return json.loads(db.get_setting("rundruf_texts", "") or "[]")

    @app.post("/api/kst/rundruf_texts")
    def rundruf_texts_set(body: dict):
        """Eigene Rundruf-Texte, gemeinsam für alle Operatoren (kein Admin nötig)."""
        texts = [str(x).strip() for x in (body.get("texts") or []) if str(x).strip()][:30]
        db.set_setting("rundruf_texts", json.dumps(texts))
        return texts

    @app.post("/api/kst/broadcast")
    async def kst_broadcast(body: dict, x_nick: str | None = Header(default=None)):
        """Mehrere Nutzer nacheinander per /CQ anschreiben (Platzhalter je Empfänger, 2 s Abstand)."""
        c = kst_client(body_station(body))
        if not c or c.state != "verbunden":
            raise HTTPException(409, "Nicht mit dem KST-Chat verbunden")
        calls = [str(x).strip().upper() for x in (body.get("calls") or []) if str(x).strip()][:60]
        text = (body.get("text") or "").strip()
        if not calls or not text:
            raise HTTPException(400, "Empfänger und Text angeben")
        st = db.get_station(int(body.get("station_id") or 0)) or {}

        async def run():
            for i, call in enumerate(calls):
                u = c.users.get(call) or {}
                msg = text
                for k, v in {"call": call, "name": (u.get("name") or "").split(" ")[0], "loc": u.get("locator", ""), "mycall": st.get("call", ""),
                             "myloc": st.get("locator", ""), "band": (st.get("band") or "").replace("MHz", " MHz")}.items():
                    msg = msg.replace("{" + k + "}", v)
                if not msg.upper().startswith("/CQ "):
                    msg = f"/CQ {call} {msg}"
                try:
                    await c.send_text(msg)
                except RuntimeError:
                    break
                await hub.broadcast({"type": "kst_broadcast", "done": i + 1, "total": len(calls), "call": call, "station_id": body_station(body)})
                if i < len(calls) - 1:
                    await asyncio.sleep(2)
        asyncio.create_task(run())
        return {"queued": len(calls)}

    @app.post("/api/kst/refresh_users")
    async def kst_refresh_users(body: dict | None = None):
        c = kst_client(body_station(body or {}))
        if not c or c.state != "verbunden":
            raise HTTPException(409, "Nicht verbunden")
        await c.send_command("/SHOW USER")
        return {"ok": True}

    @app.get("/api/kst/messages")
    def kst_messages(station_id: int = 0, limit: int = 300):
        # letzte N Nachrichten plus alle DM-relevanten (eigene gerichtete und 'an mich'), damit Gespräche vollständig bleiben
        rows = db.rows("""SELECT * FROM kst_messages WHERE id IN (
                             SELECT id FROM (SELECT id FROM kst_messages WHERE station_id=? ORDER BY id DESC LIMIT ?)
                             UNION SELECT id FROM (SELECT id FROM kst_messages WHERE station_id=? AND ((own=1 AND to_call<>'') OR to_me=1) ORDER BY id DESC LIMIT 2000))
                          ORDER BY id DESC""", (station_id, min(int(limit), 2000), station_id))
        c = kst_client(station_id)
        users = c.users if c else {}
        out = []
        for r in reversed(rows):
            out.append({"ts": r["ts_utc"], "time": r["time"], "call": r["call"], "name": r["name"], "to": r["to_call"], "text": r["text"],
                        "own": bool(r["own"]), "to_me": bool(r["to_me"]), "locator": (users.get(r["call"]) or {}).get("locator", "")})
        return out

    @app.get("/api/kst/users")
    def kst_users(station_id: int = 0, my: str = ""):
        c = kst_client(station_id)
        out = []
        for u in (c.users.values() if c else []):
            d = dict(u)
            if my and geo.is_valid_locator(my) and u.get("locator"):
                d["km"] = geo.distance_km_int(my, u["locator"])
                d["bearing"] = round(geo.bearing_deg(my, u["locator"])) % 360
            out.append(d)
        out.sort(key=lambda u: u.get("km", 99999))
        return out

    # ------------------------------------------------------------ DARC-Contest-Hub
    @app.get("/api/darc/contests", dependencies=[Depends(require_maintainer)])
    async def darc_contests(year: int):
        import urllib.request
        url = importers.DARC_INDEX.format(year=year)
        try:
            def fetch():
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 BeamLog"})
                with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
                    return r.read().decode("utf-8", "replace")
            text = await asyncio.to_thread(fetch)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"DARC-Contest-Hub nicht erreichbar: {e}")
        return importers.parse_darc_index(text, year)

    @app.post("/api/darc/import", dependencies=[Depends(require_maintainer)])
    async def darc_import(body: dict):
        """{'years': [2024, 2025]} oder {'csv_urls': [...]} – lädt die result.csv-Dateien und übernimmt Call+Locator."""
        import urllib.request
        urls: list[str] = list(body.get("csv_urls") or [])
        years = body.get("years") or []
        report: list[dict] = []

        def fetch(url: str) -> str:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 BeamLog"})
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
                return r.read().decode("utf-8", "replace")

        for y in years:
            try:
                idx = importers.parse_darc_index(await asyncio.to_thread(fetch, importers.DARC_INDEX.format(year=int(y))), int(y))
                urls += [c["csv"] for c in idx]
            except Exception as e:  # noqa: BLE001
                report.append({"url": str(y), "error": str(e)})
        total = 0
        for url in urls:
            if not url.startswith(importers.DARC_BASE):
                report.append({"url": url, "error": "nur DARC-Contest-Hub-Adressen"})
                continue
            try:
                res = importers.parse_darc_csv(await asyncio.to_thread(fetch, url))
            except Exception as e:  # noqa: BLE001
                report.append({"url": url, "error": str(e)})
                continue
            for call, loc, _ in res.callbook:
                db.learn_call(call, loc, source="darc", dok=res.doks.get(call, ""))
            total += len(res.callbook)
            report.append({"url": url, "calls": len(res.callbook)})
        return {"total": total, "callbook_count": db.callbook_count(), "files": report}

    @app.get("/api/callbook/export.csv")
    def callbook_export():
        rows = db.rows("SELECT * FROM callbook ORDER BY call")
        return PlainTextResponse(exporters.export_callbook_csv(rows), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=callbook.csv"})

    @app.post("/api/callbook", dependencies=[Depends(require_admin)])
    def callbook_edit(body: dict):
        db.learn_call(body.get("call", ""), body.get("locator", ""), source="manual", name=body.get("name", ""), dok=body.get("dok", ""))
        if "dok" in body:  # leeres Feld löscht den DOK bewusst
            with db.conn:
                db.conn.execute("UPDATE callbook SET dok=? WHERE call=?", (normalize_dok(body.get("dok")), prefixes.core_call(body.get("call", ""))))
        return db.lookup_call(body.get("call", "")) or {}

    # ------------------------------------------------------------ Import
    @app.post("/api/import", dependencies=[Depends(require_admin)])
    async def do_import(file: UploadFile = File(...), target: str = Form("auto"),
                        station_id: int | None = Form(None), contest_id: int | None = Form(None),
                        contest_name: str = Form(""), x_nick: str | None = Header(default=None)):
        data = await file.read()
        try:
            res = importers.parse_file(file.filename or "import", data)
        except ValueError as e:
            raise HTTPException(400, str(e))
        report: dict[str, Any] = {"kind": res.kind, "warnings": res.warnings[:50], "qsos": 0, "callbook": 0}
        # Call-Listen und – immer – die Rufzeichen/Locator aus den QSOs ins Call-Buch
        for call, loc, name in res.callbook:
            db.learn_call(call, loc, source="import", name=name, dok=res.doks.get(prefixes.core_call(call), ""))
            report["callbook"] += 1
        if target == "callbook" or (target == "auto" and not res.qsos):
            for q in res.qsos:
                db.learn_call(q.call, q.locator, source="import", when=q.ts_utc)
                report["callbook"] += 1
            return report
        if not res.qsos:
            return report
        # QSOs in eine Station übernehmen
        sid = station_id
        if not sid:
            cid = contest_id
            if not cid:
                name = contest_name.strip() or res.header.get("name") or f"Import {Path(file.filename or '').stem}"
                dates = sorted(q.ts_utc for q in res.qsos)
                cid = db.create_contest(name, dates[0], dates[-1])
                report["contest_id"] = cid
            band = res.header.get("band") or res.qsos[0].band or "144MHz"
            if not res.header.get("locator"):
                raise HTTPException(400, "Datei enthält keinen eigenen Locator – bitte Zielstation auswählen")
            sid = db.create_station(cid, res.header.get("call") or "IMPORT", res.header["locator"], band, "SSB", "")
            report["station_id"] = sid
        station = db.get_station(sid)
        if not station:
            raise HTTPException(404, "Station nicht gefunden")
        existing = {(q["core_call"], q["ts_utc"]) for q in db.list_qsos(sid)}
        for q in sorted(res.qsos, key=lambda x: x.ts_utc):
            if (prefixes.core_call(q.call), q.ts_utc) in existing:
                continue
            try:
                d = q.__dict__.copy()
                d["band"] = d["band"] or station["band"]
                db.add_qso(sid, d, logged_by=nick_of(x_nick) or "import")
                report["qsos"] += 1
                report["callbook"] += 1
            except ValueError as e:
                report["warnings"].append(f"{q.call}: {e}")
        await hub.broadcast({"type": "update", "scope": "contests"})
        await hub.broadcast({"type": "update", "scope": "qsos", "station_id": sid})
        return report

    # ------------------------------------------------------------ Export
    @app.get("/api/stations/{sid}/check")
    async def check(sid: int, lookup_max: int = 150):
        station = db.get_station(sid)
        if not station:
            raise HTTPException(404)
        contest = db.get_contest(station["contest_id"]) or {"name": ""}
        qsos = db.list_qsos(sid)
        res = logcheck.check_station(contest, station, qsos)
        # Abgleich mit HamQTH/QRZ (falls eingerichtet): jedes Rufzeichen nur einmal nachschlagen, Ergebnis im Call-Buch merken
        client = lookup_client()
        checked = 0
        if client.enabled:
            seen: set[str] = set()
            for q in qsos:
                core = prefixes.core_call(q["call"])
                if not core or core in seen or q.get("dupe"):
                    continue
                seen.add(core)
                row = db.lookup_call(core) or {}
                if not row.get("ext_checked"):
                    if checked >= lookup_max:
                        res["warnings"].append({"qso_id": None, "serial": None, "call": None, "msg": f"Online-Abgleich: nur {lookup_max} Rufzeichen je Durchlauf – Prüfung nochmal starten für den Rest"})
                        break
                    try:
                        r = await asyncio.to_thread(client.lookup, core)
                    except Exception as e:  # noqa: BLE001
                        res["warnings"].append({"qso_id": None, "serial": None, "call": None, "msg": f"Online-Abgleich nicht möglich: {e}"})
                        break
                    db.set_ext_lookup(core, r.get("locator", ""), r.get("source", client.provider) if r else client.provider)
                    row = db.lookup_call(core) or {}
                    checked += 1
                ext = (row.get("ext_locator") or "").upper()
                if ext and q["locator"] and ext[:4] != q["locator"].upper()[:4]:
                    res["warnings"].append({"qso_id": q["id"], "serial": q["serial_sent"], "call": q["call"], "field": "Locator", "logged": q["locator"].upper(), "expected": f"{lookup.PROVIDERS.get(row.get('ext_source'), 'Online-DB')}: {ext}", "ts": q["ts_utc"], "fix": {"locator": ext}, "msg": f"{lookup.PROVIDERS.get(row.get('ext_source'), 'Online-DB')} kennt {core} mit {ext} (Log: {q['locator']}) – Locator prüfen"})
                elif ext and q["locator"] and ext != q["locator"].upper() and len(q["locator"]) >= 6 and len(ext) >= 6:
                    res["warnings"].append({"qso_id": q["id"], "serial": q["serial_sent"], "call": q["call"], "field": "Locator (fein)", "logged": q["locator"].upper(), "expected": f"{lookup.PROVIDERS.get(row.get('ext_source'), 'Online-DB')}: {ext}", "ts": q["ts_utc"], "fix": {"locator": ext}, "msg": f"{lookup.PROVIDERS.get(row.get('ext_source'), 'Online-DB')}: {core} mit {ext} eingetragen (Log: {q['locator']}) – Portabelbetrieb?"})
            res["lookup"] = {"provider": client.provider, "checked_now": checked}
        else:
            res["lookup"] = {"provider": "none", "checked_now": 0}
        add_fixes(res, qsos)
        return res

    def add_fixes(res: dict, qsos: list[dict]) -> None:
        """Korrekturvorschläge aus der Stationsdatenbank (Locator, DOK), wo ein Befund keinen eigenen hat.
        Die Oberfläche trägt den Vorschlag beim Öffnen des QSOs schon ein und hebt ihn hervor."""
        by_id = {q["id"]: q for q in qsos}
        for item in res["errors"] + res["warnings"]:
            q = by_id.get(item.get("qso_id"))
            if not q or item.get("fix"):
                continue
            field = item.get("field") or ""
            row = db.lookup_call(q["call"]) or {}
            if field in ("Locator", "Land"):
                cand = [c for c in [row.get("ext_locator"), row.get("locator"), *(row.get("alt_locators") or "").split(",")] if c]
                logged = (q.get("locator") or "").upper()
                if len(logged) == 4:  # nur 4-stellig geloggt: Vorschlag muss im selben Großfeld liegen
                    cand = [c for c in cand if c.strip().upper().startswith(logged)]
                for c in cand:
                    c = c.strip().upper()
                    if c and c != logged and geo.is_valid_locator(c) and len(c) >= 6 and prefixes.check_plausibility(q["call"], c).get("ok", True):
                        item["fix"] = {"locator": c}
                        break
            elif field == "DOK" and row.get("dok"):
                item["fix"] = {"exch_rcvd": row["dok"]}

    # ------------------------------------------------------------ Update-API
    @app.get("/api/update/status")
    def update_status():
        """Für alle Nutzer: läuft eine neue Version? (aus dem stündlichen Check, ohne Netzzugriff)"""
        latest = update_state["latest"] or {}
        return {"current": __version__, "latest": latest.get("version", ""), "available": bool(latest.get("available")), "html_url": latest.get("html_url", ""),
                "can_self_update": bool(latest.get("can_self_update")), "frozen": updater.is_frozen(), "platform": updater.platform_tag(),
                "busy": update_state["busy"], "progress": update_state["progress"], "error": update_state["error"], "checked_at": update_state["checked_at"]}

    @app.post("/api/update/check", dependencies=[Depends(require_admin)])
    async def update_check():
        try:
            latest = await do_update_check(force=True)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Update-Prüfung fehlgeschlagen: {e}")
        return {**latest, "frozen": updater.is_frozen()}

    @app.post("/api/update/apply", dependencies=[Depends(require_admin)])
    async def update_apply(body: dict | None = None):
        """Neueste Version laden, einspielen und neu starten (nur portable Version)."""
        if update_state["busy"]:
            raise HTTPException(409, "Update läuft bereits")
        latest = update_state["latest"] or await do_update_check(force=True)
        if not latest.get("available") and not (body or {}).get("force"):
            raise HTTPException(400, "Keine neuere Version verfügbar")
        if not updater.is_frozen():
            raise HTTPException(400, "Quellcode-Installation: bitte mit „git pull“ und „pip install -r requirements.txt“ aktualisieren und den Dienst neu starten.")
        if not latest.get("asset"):
            raise HTTPException(400, f"Kein Paket für diese Plattform ({updater.platform_tag()}) im Release")
        update_state.update(busy=True, progress="lade …")

        def prog(done, total):
            update_state["progress"] = f"lade … {done // 1048576} / {total // 1048576} MB" if total else f"lade … {done // 1048576} MB"
        try:
            res = await asyncio.to_thread(updater.apply_update, latest["asset"], github_token(), prog)
        except Exception as e:  # noqa: BLE001
            update_state.update(busy=False, progress="", error=str(e))
            raise HTTPException(500, f"Update fehlgeschlagen: {e}")
        update_state["progress"] = "neu starten …"
        db.add_audit(f"Update auf {latest['version']} eingespielt", details=f"von {__version__}, Neustart ({res['restart']})", nick="Admin", admin=True)
        try:
            db.create_backup("update")
        except Exception:  # noqa: BLE001
            pass
        await hub.broadcast({"type": "restarting", "version": latest["version"]})
        asyncio.get_event_loop().call_later(1.0, lambda: asyncio.get_event_loop().run_in_executor(None, updater.restart_now, res["restart"], res.get("bat", "")))
        return {"ok": True, "version": latest["version"], "restart": res["restart"]}

    @app.get("/api/changelog")
    def changelog(since: str = ""):
        """Mitgeliefertes Änderungsprotokoll (für „Was ist neu“ und „News anzeigen“)."""
        entries = updater.changelog_since(since) if since else updater.load_changelog()
        entries = [e for e in entries if updater.parse_version(e["version"]) <= updater.parse_version(__version__)]  # nichts Unveröffentlichtes zeigen
        return {"current": __version__, "entries": entries[:30]}

    # ------------------------------------------------------------ Flugzeug-Scatter (ADS-B, wie AirScout)
    @app.get("/api/aircraft")
    async def aircraft(my: str, loc: str = "", dist: float = 0):
        """Flugzeuge um die eigene Station bzw. entlang des Pfads zum Partner-Locator, mit Scatter-Bewertung."""
        if not geo.is_valid_locator(my):
            raise HTTPException(400, "Eigener Locator ungültig")
        source = db.get_setting("adsb_source", "adsb.fi") or "adsb.fi"
        local_url = db.get_setting("adsb_local_url", "") or ""
        corridor = float(db.get_setting("adsb_corridor_km", "12") or 12)
        antenna = float(db.get_setting("adsb_antenna_m", "15") or 15)
        a = geo.locator_to_latlon(my)
        if loc and geo.is_valid_locator(loc):
            b = geo.locator_to_latlon(loc)
            center = adsb.point_along(a, b, 0.5)
            radius = max(dist or 0, adsb.dist_ll(a, b) / 2 + 60)
        else:
            center, radius = a, (dist or 150)
        try:
            planes = await asyncio.to_thread(adsb.fetch, source, center[0], center[1], min(radius, 460), local_url)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"ADS-B-Quelle nicht erreichbar ({'eigener Empfänger' if source == 'local' else 'adsb.fi'}): {e}")
        if loc and geo.is_valid_locator(loc):
            res = adsb.scatter(my, loc, planes, corridor_km=corridor, antenna_m=antenna)
        else:
            res = {"my": my, "other": "", "dist_km": 0, "corridor_km": corridor, "zone": None, "horizon_km": 0,
                   "planes": [{**p, "xt_km": None, "at_km": None, "d1_km": round(adsb.dist_ll(a, (p["lat"], p["lon"]))), "d2_km": None, "visible_both": False, "in_corridor": False, "eta_min": None} for p in planes if not p["ground"]][:120]}
        res["source"] = "adsb.fi" if source != "local" else "local"
        res["attribution"] = "Flugzeugdaten: adsb.fi (https://adsb.fi)" if source != "local" else "Flugzeugdaten: eigener ADS-B-Empfänger"
        return res

    # ------------------------------------------------------------ Stationsdatenbank aus dem Repo abgleichen
    @app.post("/api/callbook/sync_repo", dependencies=[Depends(require_admin)])
    async def callbook_sync_repo(body: dict | None = None):
        """Stationsdatenbank aus dem Repo (seed/stationsdatenbank.csv) holen und neue/geänderte Einträge übernehmen.
        Standard: GitHub-API (liefert mit Token auch aus privaten Repos); eine andere URL ist in den Einstellungen möglich."""
        import urllib.request
        url = (body or {}).get("url") or db.get_setting("repo_url", "") or REPO_CALLBOOK_URL
        token = github_token()
        headers = {"User-Agent": f"BeamLog/{__version__}", "Accept": "application/vnd.github.raw"}
        if token and "github" in url:
            headers["Authorization"] = f"Bearer {token}"
        try:
            text = await asyncio.to_thread(lambda: urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30).read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            hint = " – privates Repo? Dann in der Verwaltung ein GitHub-Token (Lesezugriff auf das Repo) eintragen." if "404" in str(e) or "401" in str(e) else ""
            raise HTTPException(502, f"Repo nicht erreichbar: {e}{hint}")
        res = importers.parse_callbook_csv(text)
        new = known = changed = 0
        import re as _re
        for call, loc, name in res.callbook:
            when = f"{name}T00:00:00Z" if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", name) else ""
            before = db.lookup_call(call)
            r = db.learn_call(call, loc, source="repo", name="" if when else name, when=when, dok=res.doks.get(call, ""))
            if r == "new":
                new += 1
            elif r == "known":
                known += 1
                if before and loc and before.get("locator") != loc:
                    changed += 1
        db.add_audit("Stationsdatenbank aus dem Repo abgeglichen", details=f"{len(res.callbook)} Einträge, {new} neu, {changed} Locator geändert", nick="Admin", admin=True)
        return {"total": len(res.callbook), "new": new, "known": known, "changed": changed, "callbook_count": db.callbook_count(), "url": url}

    @app.post("/api/callbook/import_list", dependencies=[Depends(require_maintainer)])
    async def callbook_import_list(file: UploadFile = File(...)):
        """Betreuer: Stationsliste eines anderen Nutzers (CSV-Export der Stationsdatenbank oder Repo-Format) in die zentrale Liste einpflegen."""
        text = (await file.read()).decode("utf-8-sig", "replace")
        res = importers.parse_callbook_csv(text)
        new = known = 0
        for call, loc, name in res.callbook:
            core = prefixes.core_call(call)
            when = res.seen.get(core, "")
            r = db.learn_call(call, loc, source="list", name=name, when=f"{when}T00:00:00Z" if when else "", dok=res.doks.get(core, ""))
            if r == "new":
                new += 1
            elif r == "known":
                known += 1
        db.add_audit("Stationsliste eingepflegt", details=f"{file.filename}: {len(res.callbook)} Einträge, {new} neu", nick="Admin", admin=True)
        return {"total": len(res.callbook), "new": new, "known": known, "warnings": res.warnings[:20], "callbook_count": db.callbook_count()}

    @app.get("/api/callbook/export_seed.csv")
    def callbook_export_seed():
        """Stationsdatenbank im Repo-Format (Call;Locator;Zuletzt;DOK) – zum Einchecken als contestlogger/seed/stationsdatenbank.csv."""
        rows = db.rows("SELECT call, locator, last_seen, dok FROM callbook WHERE locator<>'' ORDER BY call")
        lines = ["Call;Locator;Zuletzt;DOK"] + [f"{r['call']};{r['locator']};{(r['last_seen'] or '')[:10]};{r['dok'] or ''}" for r in rows]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/csv", headers={"Content-Disposition": "attachment; filename=stationsdatenbank.csv"})

    @app.get("/api/contests/{cid}/check")
    async def check_contest(cid: int):
        """Log-Prüfung aller Stationen eines Contests – Grundlage für den EDI-ZIP-Dialog."""
        contest = db.get_contest(cid)
        if not contest:
            raise HTTPException(404)
        out = []
        for st in db.list_stations(cid):
            station = db.get_station(st["id"])
            res = await asyncio.to_thread(logcheck.check_station, contest, station, db.list_qsos(st["id"]))
            out.append({"station_id": st["id"], "call": station["call"], "band": station["band"], "qsos": res["qsos"], "ok": res["ok"],
                        "errors": res["errors"][:20], "n_errors": len(res["errors"]), "n_warnings": len(res["warnings"])})
        return {"stations": out, "ok": sum(1 for s in out if s["ok"]), "total": len(out)}

    @app.get("/api/contests/{cid}/export.zip")
    def export_contest_zip(cid: int, force: int = 0, nick: str = "", x_admin_token: str | None = Header(default=None)):
        """Alle Stationen/Bänder eines Contests als EDI-Dateien in einem ZIP – nur geprüfte Logs."""
        import io
        import zipfile
        contest = db.get_contest(cid)
        if not contest:
            raise HTTPException(404)
        buf = io.BytesIO()
        skipped = []
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for st in db.list_stations(cid):
                station = db.get_station(st["id"])
                qsos = db.list_qsos(st["id"])
                res = logcheck.check_station(contest, station, qsos)
                if res["errors"] and not (force and is_admin(x_admin_token)):
                    lines = [f"  - #{e['serial']:03d} {e['call']}: {e['msg']}" if e.get("serial") else f"  - {e['msg']}" for e in res["errors"][:30]]
                    skipped.append(f"{station['call']} {station['band']}: {len(res['errors'])} Fehler\n" + "\n".join(lines))
                    continue
                name = f"{station['call'].replace('/', '-')}_{station['band']}.edi"
                z.writestr(name, exporters.export_edi(contest, station, qsos).encode("latin-1", "replace"))
            if skipped:
                z.writestr("NICHT_EXPORTIERT.txt", ("Diese Logs haben die Log-Prüfung nicht bestanden und wurden nicht exportiert.\n"
                                                    "Fehler im Logger beheben (Verwaltung → Export / Abgabe → EDI (mit Prüfung)) oder als Admin „trotzdem exportieren“.\n\n" + "\n\n".join(skipped)).encode("utf-8"))
        fname = f"{contest['name']}".replace("/", "-").replace(" ", "_") + ".zip"
        db.add_audit(f"EDI-ZIP exportiert (Contest {cid})", details=f"{fname}; nicht exportiert: {len(skipped)}" + (" [erzwungen]" if force else ""), admin=is_admin(x_admin_token), nick=nick_of(nick))
        return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={fname}"})

    @app.get("/api/stations/{sid}/export.{fmt}")
    def export(sid: int, fmt: str, force: int = 0, nick: str = "", x_admin_token: str | None = Header(default=None)):
        station = db.get_station(sid)
        if not station:
            raise HTTPException(404)
        contest = db.get_contest(station["contest_id"]) or {"name": ""}
        qsos = db.list_qsos(sid)
        base = f"{station['call'].replace('/', '-')}_{station['band']}"
        if fmt == "edi":
            # Die Log-Prüfung ist Pflicht: mit Fehlern wird nur exportiert, wenn der Admin es erzwingt.
            res = logcheck.check_station(contest, station, qsos)
            if res["errors"] and not (force and is_admin(x_admin_token)):
                db.add_audit(f"EDI-Export abgelehnt (Station {sid})", details=f"{len(res['errors'])} Fehler in der Log-Prüfung", status=409)
                raise HTTPException(409, f"Log-Prüfung nicht bestanden: {len(res['errors'])} Fehler – bitte erst beheben")
            db.add_audit(f"EDI exportiert (Station {sid})", details=f"{base}.edi, {len(qsos)} QSOs" + (" [mit Fehlern erzwungen]" if res["errors"] else ""), admin=is_admin(x_admin_token), nick=nick_of(nick))
            return Response(exporters.export_edi(contest, station, qsos).encode("latin-1", "replace"),
                            media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={base}.edi"})
        if fmt in ("adi", "adif"):
            return PlainTextResponse(exporters.export_adif(contest, station, qsos), headers={"Content-Disposition": f"attachment; filename={base}.adi"})
        if fmt == "csv":
            return PlainTextResponse(exporters.export_csv(contest, station, qsos), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={base}.csv"})
        if fmt in ("cbr", "log", "cabrillo"):
            db.add_audit(f"Cabrillo exportiert (Station {sid})", details=f"{base}.cbr, {len(qsos)} QSOs", admin=is_admin(x_admin_token), nick=nick_of(nick))
            return PlainTextResponse(exporters.export_cabrillo(contest, station, qsos), headers={"Content-Disposition": f"attachment; filename={base}.cbr"})
        raise HTTPException(404, "Unbekanntes Format")

    # ------------------------------------------------------------ Chat / WS
    @app.get("/api/stations/{sid}/opnote")
    def opnote_get(sid: int):
        return {"text": db.get_setting(f"opnote:{sid}", "") or ""}

    @app.get("/operator")
    def operator_page():
        """Operator-Fenster (zweiter Monitor): zeigt live die Eingabe des Loggers, Hinweise und die letzten QSOs."""
        return html_page("operator.html")

    @app.get("/api/chat")
    def chat_history(contest_id: int = 0):
        return db.recent_chat(contest_id)

    @app.get("/api/kst/seen")
    def kst_seen_get(station_id: int, x_nick: str | None = Header(default=None)):
        return db.get_kst_seen(station_id, nick_of(x_nick))

    @app.post("/api/kst/seen")
    def kst_seen_set(body: dict, x_nick: str | None = Header(default=None)):
        db.set_kst_seen(int(body.get("station_id") or 0), nick_of(x_nick), str(body.get("partner") or "").upper(), str(body.get("ts") or ""))
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(socket: WebSocket, nick: str = Query(default="")):
        nick = nick.strip()[:24] or "Gast"
        await hub.connect(socket, nick)
        try:
            while True:
                raw = await socket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "chat" and (msg.get("text") or "").strip():
                    entry = db.add_chat(nick, msg["text"].strip(), int(msg.get("contest_id") or 0))
                    await hub.broadcast({"type": "chat", "msg": entry})
                elif msg.get("type") == "status":
                    hub.set_status(socket, msg.get("station_id"))
                    await hub.broadcast_presence()
                elif msg.get("type") == "typing" and msg.get("station_id"):
                    # Live-Eingabe des Loggers für das Operator-Fenster (nicht gespeichert)
                    await hub.broadcast({"type": "typing", "station_id": int(msg["station_id"]), "by": nick, "data": msg.get("data") or {}})
                elif msg.get("type") == "opnote" and msg.get("station_id"):
                    text = str(msg.get("text") or "").strip()[:300]
                    db.set_setting(f"opnote:{int(msg['station_id'])}", text)
                    await hub.broadcast({"type": "opnote", "station_id": int(msg["station_id"]), "text": text, "by": nick})
        except WebSocketDisconnect:
            pass
        finally:
            await hub.disconnect(socket)

    # ------------------------------------------------------------ Sprachen
    LANG_DIR = STATIC / "lang"
    user_lang_dir = Path(db.path).parent / "lang"  # eigene Übersetzungen neben der Datenbank

    def lang_files() -> dict[str, list[Path]]:
        out: dict[str, list[Path]] = {}
        for d in (LANG_DIR, user_lang_dir):
            if d.exists():
                for f in sorted(d.glob("*.json")):
                    if f.stem.isalpha() and len(f.stem) <= 5:
                        out.setdefault(f.stem.lower(), []).append(f)
        return out

    @app.get("/api/lang")
    def lang_list():
        langs = [{"code": "de", "name": "Deutsch"}]
        for code, files in lang_files().items():
            name = code
            for f in files:
                try:
                    name = json.loads(f.read_text(encoding="utf-8")).get("_name") or name
                except (OSError, json.JSONDecodeError):
                    continue
            langs.append({"code": code, "name": name})
        return langs

    @app.get("/api/lang/template.json")
    def lang_template():
        base = json.loads((LANG_DIR / "en.json").read_text(encoding="utf-8"))
        tpl = {"_name": "Name der Sprache / language name"}
        tpl.update({k: "" for k in base if not k.startswith("_")})
        return Response(json.dumps(tpl, ensure_ascii=False, indent=1), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=xx.json"})

    @app.get("/api/lang/{code}")
    def lang_get(code: str):
        merged: dict = {}
        for f in lang_files().get(code.lower(), []):
            try:
                merged.update(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError) as e:
                raise HTTPException(500, f"Sprachdatei {f.name} fehlerhaft: {e}")
        if not merged and code.lower() != "de":
            raise HTTPException(404, "Sprache nicht gefunden")
        return {k: v for k, v in merged.items() if v and not k.startswith("_")}

    # ------------------------------------------------------------ Frontend
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def html_page(name: str) -> Response:
        """HTML-Seiten nie cachen und die eigenen Skripte/Stylesheets mit der Version stempeln – nach einem Update
        passen Seite und Skript so immer zusammen (sonst alte Seite aus dem Cache + neues app.js)."""
        html = (STATIC / name).read_text(encoding="utf-8")
        html = html.replace('"/static/app.js"', f'"/static/app.js?v={__version__}"').replace('"/static/style.css"', f'"/static/style.css?v={__version__}"')
        return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache, must-revalidate"})

    @app.get("/")
    def index():
        return html_page("index.html")

    return app


class Hub:
    """Verwaltet alle offenen WebSockets und verteilt Ereignisse."""

    def __init__(self) -> None:
        self.clients: dict[WebSocket, dict] = {}
        self.lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, nick: str) -> None:
        await ws.accept()
        async with self.lock:
            self.clients[ws] = {"nick": nick, "station_id": None}
        await self.broadcast_presence()

    async def disconnect(self, ws: WebSocket) -> None:
        async with self.lock:
            self.clients.pop(ws, None)
        await self.broadcast_presence()

    def set_status(self, ws: WebSocket, station_id) -> None:
        if ws in self.clients:
            self.clients[ws]["station_id"] = station_id

    async def broadcast_presence(self) -> None:
        await self.broadcast({"type": "presence", "users": list(self.clients.values())})

    async def broadcast(self, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.clients.pop(ws, None)
