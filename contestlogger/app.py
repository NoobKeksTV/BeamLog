"""HTTP-/WebSocket-Server (FastAPI). Zentraler Speicher, Live-Updates und Chat
für alle im LAN angemeldeten Browser.
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __app_name__, __copyright__, __version__, exporters, importers, logcheck, lookup
from .db import Database

STATIC = Path(__file__).parent / "static"
SEED = Path(__file__).parent / "seed" / "stationsdatenbank.csv"


def create_app(db_path: str | os.PathLike | None = None, backup_interval_min: float | None = None, public_url: str = "") -> FastAPI:
    db = Database(db_path or os.environ.get("CONTESTLOGGER_DB", "data/contestlogger.db"))
    interval = backup_interval_min if backup_interval_min is not None else float(os.environ.get("CONTESTLOGGER_BACKUP_MIN", "15"))

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
            db.learn_call(call, loc, source="seed", name="" if when else name, when=when)
        db.set_setting("seeded", "1")
        return len(res.callbook)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        n = seed_callbook()
        if n:
            print(f"Stationsdatenbank: {n} Rufzeichen aus der mitgelieferten Startdatei geladen.")
        task = asyncio.create_task(backup_loop()) if interval > 0 else None
        yield
        if task:
            task.cancel()
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

    def require_station(sid: int, token: str | None, admin: str | None) -> dict:
        station = db.get_station(sid)
        if not station:
            raise HTTPException(404, "Station nicht gefunden")
        if is_admin(admin) or db.check_station_token(sid, token or ""):
            return station
        raise HTTPException(403, "Station ist nicht freigeschaltet")

    def nick_of(x_nick: str | None) -> str:
        return (x_nick or "").strip()[:24]

    # ------------------------------------------------------------ Allgemein
    @app.get("/api/info")
    def info():
        return {
            "app": __app_name__, "version": __version__, "copyright": __copyright__,
            "admin_configured": db.admin_configured(), "callbook_count": db.callbook_count(),
            "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "public_url": public_url or os.environ.get("CONTESTLOGGER_URL", ""),
            "tile_url": db.get_setting("tile_url", "") or "",
            "lookup_provider": db.get_setting("lookup_provider", "none") or "none",
            "mdbtools": bool(__import__("shutil").which("mdb-tables")),
        }

    @app.get("/api/qr.svg")
    def qr_svg(text: str = Query(..., max_length=500)):
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
        return Response(img.to_string(), media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

    @app.post("/api/settings", dependencies=[Depends(require_admin)])
    def set_settings(body: dict):
        for k in ("tile_url", "lookup_provider", "lookup_user", "lookup_pass"):
            if k in body:
                db.set_setting(k, str(body[k] or ""))
        lookup_state["client"] = None
        lookup_cache.clear()
        return {"ok": True}

    @app.get("/api/settings", dependencies=[Depends(require_admin)])
    def get_settings():
        return {"tile_url": db.get_setting("tile_url", ""), "lookup_provider": db.get_setting("lookup_provider", "none") or "none",
                "lookup_user": db.get_setting("lookup_user", ""), "lookup_pass_set": bool(db.get_setting("lookup_pass", "")),
                "providers": lookup.PROVIDERS}

    @app.post("/api/lookup/test", dependencies=[Depends(require_admin)])
    async def lookup_test():
        try:
            return {"ok": True, "msg": await asyncio.to_thread(lookup_client().test)}
        except lookup.LookupError_ as e:
            return {"ok": False, "msg": str(e)}

    @app.get("/api/lookup")
    async def lookup_call(call: str):
        """Rufzeichen nachschlagen: erst Stationsdatenbank, dann (wenn eingerichtet) HamQTH/QRZ."""
        from . import prefixes
        core = prefixes.core_call(call)
        known = db.lookup_call(core)
        if known and known.get("locator"):
            return {"source": "local", **{k: known[k] for k in ("call", "locator", "name")}}
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
        cid = db.create_contest(body["name"], body.get("start_utc"), body.get("end_utc"), body.get("scoring", "km"), body.get("notes", ""))
        await hub.broadcast({"type": "update", "scope": "contests"})
        return db.get_contest(cid)

    @app.patch("/api/contests/{cid}", dependencies=[Depends(require_admin)])
    async def update_contest(cid: int, body: dict):
        if not db.get_contest(cid):
            raise HTTPException(404)
        db.update_contest(cid, **body)
        await hub.broadcast({"type": "update", "scope": "contests"})
        return db.get_contest(cid)

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
        await hub.broadcast({"type": "update", "scope": "contests"})
        await hub.broadcast({"type": "update", "scope": "qsos", "station_id": sid})
        return db.get_station(sid)

    @app.delete("/api/stations/{sid}", dependencies=[Depends(require_admin)])
    async def delete_station(sid: int):
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

    @app.get("/api/calc")
    def calc(my: str, loc: str, call: str = ""):
        from . import geo, prefixes
        if not (geo.is_valid_locator(my) and geo.is_valid_locator(loc)):
            return {"valid": False}
        out = {"valid": True, "km": geo.distance_km_int(my, loc), "bearing": round(geo.bearing_deg(my, loc)) % 360, "warnings": []}
        if call:
            pl = prefixes.check_plausibility(call, loc)
            if not pl["ok"]:
                out["warnings"].append(pl["msg"])
            known = db.lookup_call(call)
            if known and known["locator"] and known["locator"] != geo.normalize_locator(loc):
                out["warnings"].append(f"Stationsdatenbank kennt {prefixes.core_call(call)} mit {known['locator']} (zuletzt {known['last_seen'][:10] if known['last_seen'] else '–'})")
        return out

    @app.get("/api/callbook")
    def callbook_list(q: str = "", limit: int = 200):
        q = q.strip().upper()
        sql = "SELECT call, locator, name, qso_count, last_seen, alt_locators, source FROM callbook"
        params: list = []
        if q:
            sql += " WHERE call LIKE ? OR locator LIKE ? OR name LIKE ?"
            params = [f"%{q}%", f"{q}%", f"%{q}%"]
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
        from . import prefixes
        report: dict[str, Any] = {"files": [], "contests": 0, "qsos": 0, "callbook": 0, "skipped": []}
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
            for call, loc, nm in res.callbook:
                db.learn_call(call, loc, source="import", name=nm)
                report["callbook"] += 1
            for q in res.qsos:
                db.learn_call(q.call, q.locator, source="import", when=q.ts_utc)
            report["callbook"] += len(res.qsos)
            entry = {"file": name, "kind": res.kind, "qsos": len(res.qsos), "imported": 0}
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

    @app.post("/api/import/results", dependencies=[Depends(require_admin)])
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
                req = urllib.request.Request(url.strip(), headers={"User-Agent": "Mozilla/5.0 ContestLogger"})
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
        pairs = [{"call": c, "locator": loc} for c, loc, _ in res.callbook]
        if not commit:
            known = {r["call"]: r["locator"] for r in db.rows("SELECT call, locator FROM callbook")}
            from . import prefixes
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
            db.learn_call(pr["call"], pr["locator"], source="results")
            n += 1
        return {"imported": n}

    @app.get("/api/callbook/export.csv")
    def callbook_export():
        rows = db.rows("SELECT * FROM callbook ORDER BY call")
        return PlainTextResponse(exporters.export_callbook_csv(rows), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=callbook.csv"})

    @app.post("/api/callbook", dependencies=[Depends(require_admin)])
    def callbook_edit(body: dict):
        db.learn_call(body.get("call", ""), body.get("locator", ""), source="manual", name=body.get("name", ""))
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
            db.learn_call(call, loc, source="import", name=name)
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
        from . import prefixes
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
    def check(sid: int):
        station = db.get_station(sid)
        if not station:
            raise HTTPException(404)
        contest = db.get_contest(station["contest_id"]) or {"name": ""}
        return logcheck.check_station(contest, station, db.list_qsos(sid))

    @app.get("/api/contests/{cid}/export.zip")
    def export_contest_zip(cid: int, force: int = 0, x_admin_token: str | None = Header(default=None)):
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
                    skipped.append(f"{station['call']} {station['band']}: {len(res['errors'])} Fehler")
                    continue
                name = f"{station['call'].replace('/', '-')}_{station['band']}.edi"
                z.writestr(name, exporters.export_edi(contest, station, qsos).encode("latin-1", "replace"))
            if skipped:
                z.writestr("NICHT_EXPORTIERT.txt", "Diese Logs haben die Prüfung nicht bestanden:\n" + "\n".join(skipped))
        fname = f"{contest['name']}".replace("/", "-").replace(" ", "_") + ".zip"
        return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={fname}"})

    @app.get("/api/stations/{sid}/export.{fmt}")
    def export(sid: int, fmt: str, force: int = 0, x_admin_token: str | None = Header(default=None)):
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
                raise HTTPException(409, f"Log-Prüfung nicht bestanden: {len(res['errors'])} Fehler – bitte erst beheben")
            return Response(exporters.export_edi(contest, station, qsos).encode("latin-1", "replace"),
                            media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={base}.edi"})
        if fmt in ("adi", "adif"):
            return PlainTextResponse(exporters.export_adif(contest, station, qsos), headers={"Content-Disposition": f"attachment; filename={base}.adi"})
        if fmt == "csv":
            return PlainTextResponse(exporters.export_csv(contest, station, qsos), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={base}.csv"})
        raise HTTPException(404, "Unbekanntes Format")

    # ------------------------------------------------------------ Chat / WS
    @app.get("/api/chat")
    def chat_history():
        return db.recent_chat()

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
                    entry = db.add_chat(nick, msg["text"].strip())
                    await hub.broadcast({"type": "chat", "msg": entry})
                elif msg.get("type") == "status":
                    hub.set_status(socket, msg.get("station_id"))
                    await hub.broadcast_presence()
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

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

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
