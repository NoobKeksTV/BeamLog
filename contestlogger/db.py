"""SQLite-Datenhaltung. Eine Datei (`data/contestlogger.db`) enthält alles:
Contests, Stationen, QSOs, Call-Buch, Chat und Einstellungen.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import geo, prefixes

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_utc TEXT,
    end_utc TEXT,
    scoring TEXT NOT NULL DEFAULT 'km',
    notes TEXT DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER NOT NULL REFERENCES contests(id) ON DELETE CASCADE,
    call TEXT NOT NULL,
    locator TEXT NOT NULL,
    band TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'SSB',
    password_hash TEXT NOT NULL DEFAULT '',
    serial_next INTEGER NOT NULL DEFAULT 1,
    info TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS qsos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    ts_utc TEXT NOT NULL,
    call TEXT NOT NULL,
    core_call TEXT NOT NULL,
    locator TEXT NOT NULL DEFAULT '',
    square TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    rst_sent TEXT NOT NULL DEFAULT '59',
    rst_rcvd TEXT NOT NULL DEFAULT '59',
    serial_sent INTEGER NOT NULL,
    serial_rcvd TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'SSB',
    band TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    km INTEGER NOT NULL DEFAULT 0,
    bearing INTEGER NOT NULL DEFAULT 0,
    points INTEGER NOT NULL DEFAULT 0,
    dupe INTEGER NOT NULL DEFAULT 0,
    logged_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qsos_station ON qsos(station_id, ts_utc);
CREATE INDEX IF NOT EXISTS idx_qsos_core ON qsos(core_call);
CREATE TABLE IF NOT EXISTS callbook (
    call TEXT PRIMARY KEY,
    locator TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    qso_count INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT NOT NULL DEFAULT '',
    alt_locators TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    nick TEXT NOT NULL,
    text TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_password(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(pw: str, stored: str) -> bool:
    if not stored:
        return pw == ""
    salt, _, digest = stored.partition("$")
    return hmac.compare_digest(hash_password(pw, salt), stored)


class Database:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        # FULL: jede Transaktion ist beim Rückgabezeitpunkt auf der Platte – ein Stromausfall
        # verliert höchstens das gerade laufende QSO, die Datei bleibt konsistent.
        self.conn.execute("PRAGMA synchronous = FULL")
        self.conn.executescript(SCHEMA)
        self._migrate()
        if self.get_setting("secret") is None:
            self.set_setting("secret", secrets.token_hex(32))

    def _migrate(self) -> None:
        """Spalten nachrüsten, die in älteren Datenbanken fehlen."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(qsos)")}
        with self.conn:
            if "freq" not in cols:
                self.conn.execute("ALTER TABLE qsos ADD COLUMN freq TEXT NOT NULL DEFAULT ''")

    def backup_to(self, path: str | os.PathLike) -> None:
        """Konsistente Kopie der Datenbank (auch bei laufendem Betrieb), atomar über eine temporäre Datei."""
        tmp = Path(str(path) + ".tmp")
        dest = sqlite3.connect(tmp)
        try:
            self.conn.backup(dest)
            dest.execute("PRAGMA journal_mode = DELETE")
        finally:
            dest.close()
        os.replace(tmp, path)

    @property
    def backup_dir(self) -> Path:
        return self.path.parent / "backup"

    def create_backup(self, reason: str = "auto") -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        name = f"contestlogger-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{reason}.db"
        self.backup_to(self.backup_dir / name)
        self.prune_backups()
        return self.backup_dir / name

    def list_backups(self) -> list[dict]:
        if not self.backup_dir.exists():
            return []
        out = []
        for f in sorted(self.backup_dir.glob("contestlogger-*.db"), reverse=True):
            st = f.stat()
            out.append({"name": f.name, "size": st.st_size,
                        "ts_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        return out

    def prune_backups(self, keep_auto: int = 48, keep_manual: int = 50) -> None:
        """Automatische Sicherungen: die letzten 48 behalten (bei 15 min = 12 h) plus eine pro Tag für 30 Tage."""
        files = sorted(self.backup_dir.glob("contestlogger-*-auto.db"), reverse=True)
        daily_seen: set[str] = set()
        for i, f in enumerate(files):
            day = f.name[14:22]
            if i < keep_auto:
                daily_seen.add(day)
                continue
            if day not in daily_seen and len(daily_seen) < 30:
                daily_seen.add(day)
                continue
            f.unlink(missing_ok=True)
        manual = sorted(self.backup_dir.glob("contestlogger-*-manual.db"), reverse=True)
        for f in manual[keep_manual:]:
            f.unlink(missing_ok=True)

    # ----- generische Helfer --------------------------------------------
    def rows(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def row(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        r = self.conn.execute(sql, tuple(params)).fetchone()
        return dict(r) if r else None

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        r = self.row("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r else default

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    # ----- Admin ---------------------------------------------------------
    def admin_configured(self) -> bool:
        return bool(self.get_setting("admin_hash"))

    def set_admin_password(self, pw: str) -> None:
        self.set_setting("admin_hash", hash_password(pw))

    def check_admin(self, pw: str) -> bool:
        return verify_password(pw or "", self.get_setting("admin_hash", "") or "")

    def sign(self, payload: str) -> str:
        secret = self.get_setting("secret") or ""
        return hmac.new(secret.encode(), payload.encode(), "sha256").hexdigest()[:32]

    # ----- Contests -------------------------------------------------------
    def list_contests(self, include_archived: bool = True) -> list[dict]:
        sql = "SELECT * FROM contests"
        if not include_archived:
            sql += " WHERE archived=0"
        return self.rows(sql + " ORDER BY COALESCE(start_utc, created_at) DESC, id DESC")

    def get_contest(self, cid: int) -> dict | None:
        return self.row("SELECT * FROM contests WHERE id=?", (cid,))

    def create_contest(self, name: str, start_utc: str | None, end_utc: str | None, scoring: str = "km", notes: str = "") -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO contests(name,start_utc,end_utc,scoring,notes,created_at) VALUES(?,?,?,?,?,?)",
                (name.strip(), start_utc or None, end_utc or None, scoring, notes, utcnow()),
            )
            return int(cur.lastrowid)

    def update_contest(self, cid: int, **fields: Any) -> None:
        allowed = {"name", "start_utc", "end_utc", "scoring", "notes", "archived"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        with self.conn:
            self.conn.execute(
                f"UPDATE contests SET {', '.join(k + '=?' for k in sets)} WHERE id=?",
                (*sets.values(), cid),
            )

    def delete_contest(self, cid: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM contests WHERE id=?", (cid,))

    # ----- Stationen ------------------------------------------------------
    def list_stations(self, contest_id: int | None = None) -> list[dict]:
        sql = "SELECT * FROM stations"
        params: tuple = ()
        if contest_id is not None:
            sql += " WHERE contest_id=?"
            params = (contest_id,)
        out = []
        for s in self.rows(sql + " ORDER BY band, call", params):
            s["has_password"] = bool(s.pop("password_hash"))
            s["info"] = json.loads(s["info"] or "{}")
            out.append(s)
        return out

    def get_station(self, sid: int) -> dict | None:
        s = self.row("SELECT * FROM stations WHERE id=?", (sid,))
        if s:
            s["info"] = json.loads(s["info"] or "{}")
        return s

    def create_station(self, contest_id: int, call: str, locator: str, band: str, mode: str, password: str, info: dict | None = None) -> int:
        locator = geo.normalize_locator(locator)
        if not geo.is_valid_locator(locator):
            raise ValueError("Ungültiger Locator")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO stations(contest_id,call,locator,band,mode,password_hash,info,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (contest_id, call.strip().upper(), locator, band, mode or "SSB",
                 hash_password(password) if password else "", json.dumps(info or {}), utcnow()),
            )
            return int(cur.lastrowid)

    def update_station(self, sid: int, **fields: Any) -> None:
        allowed = {"call", "locator", "band", "mode", "serial_next", "info", "password"}
        sets: dict[str, Any] = {}
        for k, v in fields.items():
            if k not in allowed or v is None:
                continue
            if k == "password":
                sets["password_hash"] = hash_password(v) if v else ""
            elif k == "info":
                sets["info"] = json.dumps(v)
            elif k == "locator":
                v = geo.normalize_locator(v)
                if not geo.is_valid_locator(v):
                    raise ValueError("Ungültiger Locator")
                sets["locator"] = v
            elif k == "call":
                sets["call"] = v.strip().upper()
            else:
                sets[k] = v
        if not sets:
            return
        with self.conn:
            self.conn.execute(
                f"UPDATE stations SET {', '.join(k + '=?' for k in sets)} WHERE id=?",
                (*sets.values(), sid),
            )
        if "locator" in sets:
            self.rescore_station(sid)

    def delete_station(self, sid: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM stations WHERE id=?", (sid,))

    def check_station_password(self, sid: int, pw: str) -> bool:
        s = self.row("SELECT password_hash FROM stations WHERE id=?", (sid,))
        return bool(s) and verify_password(pw or "", s["password_hash"])

    def station_token(self, sid: int) -> str:
        return self.sign(f"station:{sid}")

    def check_station_token(self, sid: int, token: str) -> bool:
        return hmac.compare_digest(self.station_token(sid), token or "")

    # ----- QSOs -----------------------------------------------------------
    def _enrich(self, station: dict, q: dict) -> dict:
        call = (q.get("call") or "").strip().upper()
        loc = geo.normalize_locator(q.get("locator"))
        q["call"] = call
        q["core_call"] = prefixes.core_call(call)
        q["locator"] = loc
        q["square"] = geo.square(loc)
        q["country"] = prefixes.country(call)
        if geo.is_valid_locator(loc) and geo.is_valid_locator(station["locator"]):
            q["km"] = geo.distance_km_int(station["locator"], loc)
            q["bearing"] = int(round(geo.bearing_deg(station["locator"], loc))) % 360
        else:
            q["km"] = 0
            q["bearing"] = 0
        return q

    def _is_dupe(self, station_id: int, core_call: str, band: str, exclude_id: int | None = None) -> bool:
        sql = "SELECT 1 FROM qsos WHERE station_id=? AND core_call=? AND band=? AND dupe=0"
        params: list[Any] = [station_id, core_call, band]
        if exclude_id is not None:
            sql += " AND id<>?"
            params.append(exclude_id)
        return self.row(sql + " LIMIT 1", params) is not None

    def add_qso(self, station_id: int, data: dict, logged_by: str = "") -> dict:
        station = self.get_station(station_id)
        if not station:
            raise ValueError("Station nicht gefunden")
        q = self._enrich(station, dict(data))
        if not prefixes.is_plausible_call(q["call"]):
            raise ValueError("Rufzeichen unplausibel")
        band = q.get("band") or station["band"]
        now = utcnow()
        ts = q.get("ts_utc") or now
        with self.conn:
            serial = q.get("serial_sent")
            if serial in (None, ""):
                serial = station["serial_next"]
            serial = int(serial)
            dupe = 1 if self._is_dupe(station_id, q["core_call"], band) else 0
            points = 0 if dupe else (q["km"] if q["km"] > 0 else (1 if q["locator"] else 0))
            cur = self.conn.execute(
                """INSERT INTO qsos(station_id,ts_utc,call,core_call,locator,square,country,rst_sent,rst_rcvd,
                   serial_sent,serial_rcvd,mode,band,comment,km,bearing,points,dupe,logged_by,created_at,updated_at,freq)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (station_id, ts, q["call"], q["core_call"], q["locator"], q["square"], q["country"],
                 str(q.get("rst_sent") or "59"), str(q.get("rst_rcvd") or "59"), serial,
                 str(q.get("serial_rcvd") or ""), q.get("mode") or station["mode"], band,
                 q.get("comment") or "", q["km"], q["bearing"], points, dupe, logged_by, now, now, str(q.get("freq") or "")),
            )
            qid = int(cur.lastrowid)
            # Seriennummer weiterzählen (auch wenn manuell eine kleinere eingegeben wurde: Maximum + 1)
            nxt = max(station["serial_next"], serial + 1)
            self.conn.execute("UPDATE stations SET serial_next=? WHERE id=?", (nxt, station_id))
        self.learn_call(q["call"], q["locator"], source="log", when=ts)
        return self.get_qso(qid)  # type: ignore[return-value]

    def update_qso(self, qid: int, data: dict) -> dict:
        old = self.get_qso(qid)
        if not old:
            raise ValueError("QSO nicht gefunden")
        station = self.get_station(old["station_id"])
        merged = {**old, **{k: v for k, v in data.items() if v is not None}}
        q = self._enrich(station, merged)  # type: ignore[arg-type]
        with self.conn:
            dupe = 1 if self._is_dupe(old["station_id"], q["core_call"], q["band"], exclude_id=qid) else 0
            points = 0 if dupe else (q["km"] if q["km"] > 0 else (1 if q["locator"] else 0))
            self.conn.execute(
                """UPDATE qsos SET ts_utc=?,call=?,core_call=?,locator=?,square=?,country=?,rst_sent=?,rst_rcvd=?,
                   serial_sent=?,serial_rcvd=?,mode=?,band=?,comment=?,km=?,bearing=?,points=?,dupe=?,updated_at=?,freq=? WHERE id=?""",
                (q["ts_utc"], q["call"], q["core_call"], q["locator"], q["square"], q["country"],
                 str(q["rst_sent"]), str(q["rst_rcvd"]), int(q["serial_sent"]), str(q["serial_rcvd"]),
                 q["mode"], q["band"], q["comment"] or "", q["km"], q["bearing"], points, dupe, utcnow(), str(q.get("freq") or ""), qid),
            )
        self.recheck_dupes(old["station_id"])
        self.learn_call(q["call"], q["locator"], source="log", when=q["ts_utc"])
        return self.get_qso(qid)  # type: ignore[return-value]

    def delete_qso(self, qid: int) -> int | None:
        old = self.get_qso(qid)
        if not old:
            return None
        with self.conn:
            self.conn.execute("DELETE FROM qsos WHERE id=?", (qid,))
        self.recheck_dupes(old["station_id"])
        return old["station_id"]

    def recheck_dupes(self, station_id: int) -> None:
        """Nach Änderung/Löschung: erstes QSO je Call/Band zählt, weitere sind Dupes."""
        station = self.get_station(station_id)
        if not station:
            return
        seen: set[tuple[str, str]] = set()
        with self.conn:
            for q in self.rows("SELECT id,core_call,band,km,locator,dupe,points FROM qsos WHERE station_id=? ORDER BY ts_utc, id", (station_id,)):
                key = (q["core_call"], q["band"])
                dupe = 1 if key in seen else 0
                seen.add(key)
                points = 0 if dupe else (q["km"] if q["km"] > 0 else (1 if q["locator"] else 0))
                if dupe != q["dupe"] or points != q["points"]:
                    self.conn.execute("UPDATE qsos SET dupe=?, points=? WHERE id=?", (dupe, points, q["id"]))

    def rescore_station(self, station_id: int) -> None:
        station = self.get_station(station_id)
        if not station:
            return
        with self.conn:
            for q in self.rows("SELECT id, locator FROM qsos WHERE station_id=?", (station_id,)):
                if geo.is_valid_locator(q["locator"]):
                    km = geo.distance_km_int(station["locator"], q["locator"])
                    brg = int(round(geo.bearing_deg(station["locator"], q["locator"]))) % 360
                else:
                    km, brg = 0, 0
                self.conn.execute("UPDATE qsos SET km=?, bearing=? WHERE id=?", (km, brg, q["id"]))
        self.recheck_dupes(station_id)

    def get_qso(self, qid: int) -> dict | None:
        return self.row("SELECT * FROM qsos WHERE id=?", (qid,))

    def list_qsos(self, station_id: int, limit: int | None = None, search: str = "") -> list[dict]:
        sql = "SELECT * FROM qsos WHERE station_id=?"
        params: list[Any] = [station_id]
        if search:
            sql += " AND (call LIKE ? OR locator LIKE ? OR comment LIKE ?)"
            like = f"%{search.upper()}%"
            params += [like, like, like]
        sql += " ORDER BY ts_utc DESC, id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self.rows(sql, params)

    def reset_serial(self, station_id: int, start: int = 1) -> None:
        with self.conn:
            self.conn.execute("UPDATE stations SET serial_next=? WHERE id=?", (int(start), station_id))

    # ----- Statistik ------------------------------------------------------
    def station_summary(self, station_id: int) -> dict:
        s = self.row(
            """SELECT COUNT(*) AS qsos, COALESCE(SUM(points),0) AS points, COALESCE(SUM(dupe),0) AS dupes,
                      COALESCE(MAX(km),0) AS odx_km, COALESCE(AVG(CASE WHEN dupe=0 THEN km END),0) AS avg_km,
                      MAX(ts_utc) AS last_qso
               FROM qsos WHERE station_id=?""",
            (station_id,),
        ) or {}
        squares = self.row("SELECT COUNT(DISTINCT square) AS n FROM qsos WHERE station_id=? AND dupe=0 AND square<>''", (station_id,))
        countries = self.row("SELECT COUNT(DISTINCT country) AS n FROM qsos WHERE station_id=? AND dupe=0 AND country<>'' AND country<>'?'", (station_id,))
        odx = self.row("SELECT call, locator, km FROM qsos WHERE station_id=? AND dupe=0 ORDER BY km DESC LIMIT 1", (station_id,))
        last_hour = self.row(
            "SELECT COUNT(*) AS n FROM qsos WHERE station_id=? AND ts_utc >= strftime('%Y-%m-%dT%H:%M:%SZ','now','-1 hour')",
            (station_id,),
        )
        return {
            **s,
            "avg_km": round(s.get("avg_km") or 0),
            "squares": squares["n"] if squares else 0,
            "countries": countries["n"] if countries else 0,
            "odx": odx,
            "rate_last_hour": last_hour["n"] if last_hour else 0,
        }

    def station_stats(self, station_id: int) -> dict:
        summary = self.station_summary(station_id)
        per_hour = self.rows(
            """SELECT substr(ts_utc,1,13) AS hour, COUNT(*) AS qsos, SUM(points) AS points
               FROM qsos WHERE station_id=? GROUP BY hour ORDER BY hour""",
            (station_id,),
        )
        squares = self.rows(
            """SELECT square, COUNT(*) AS qsos, SUM(points) AS points FROM qsos
               WHERE station_id=? AND dupe=0 AND square<>'' GROUP BY square ORDER BY qsos DESC, square""",
            (station_id,),
        )
        countries = self.rows(
            """SELECT country, COUNT(*) AS qsos, SUM(points) AS points, MAX(km) AS odx FROM qsos
               WHERE station_id=? AND dupe=0 GROUP BY country ORDER BY qsos DESC""",
            (station_id,),
        )
        bins = [0, 50, 100, 200, 300, 400, 500, 600, 800, 1000, 10_000]
        dist = []
        for lo, hi in zip(bins, bins[1:]):
            r = self.row("SELECT COUNT(*) AS n, COALESCE(SUM(points),0) AS p FROM qsos WHERE station_id=? AND dupe=0 AND km>=? AND km<?", (station_id, lo, hi))
            dist.append({"range": f"{lo}-{hi if hi < 10_000 else '∞'}", "qsos": r["n"], "points": r["p"]})
        bearings = [{"sector": i * 30, "qsos": 0, "points": 0} for i in range(12)]
        for q in self.rows("SELECT bearing, points FROM qsos WHERE station_id=? AND dupe=0 AND km>0", (station_id,)):
            b = bearings[(q["bearing"] % 360) // 30]
            b["qsos"] += 1
            b["points"] += q["points"]
        top = self.rows("SELECT call, locator, km, points, ts_utc FROM qsos WHERE station_id=? AND dupe=0 ORDER BY km DESC LIMIT 10", (station_id,))
        ops = self.rows("SELECT logged_by AS nick, COUNT(*) AS qsos, SUM(points) AS points FROM qsos WHERE station_id=? GROUP BY logged_by ORDER BY qsos DESC", (station_id,))
        return {"summary": summary, "per_hour": per_hour, "squares": squares, "countries": countries,
                "distance": dist, "bearings": bearings, "top": top, "operators": ops}

    def contest_summary(self, contest_id: int) -> dict:
        """Gesamtwertung über alle Bänder/Stationen eines Contests (Multi-Band)."""
        stations = self.scoreboard(contest_id)
        by_band: dict[str, dict] = {}
        for s in stations:
            b = by_band.setdefault(s["band"], {"band": s["band"], "qsos": 0, "points": 0, "squares": 0, "odx_km": 0, "stations": []})
            b["qsos"] += s["qsos"] - s["dupes"]
            b["points"] += s["points"] or 0
            b["squares"] += s["squares"]
            b["odx_km"] = max(b["odx_km"], s["odx_km"] or 0)
            b["stations"].append(s["call"])
        total_qsos = sum(b["qsos"] for b in by_band.values())
        total_points = sum(b["points"] for b in by_band.values())
        all_squares = self.row(
            """SELECT COUNT(DISTINCT q.square) AS n FROM qsos q JOIN stations s ON s.id=q.station_id
               WHERE s.contest_id=? AND q.dupe=0 AND q.square<>''""", (contest_id,))
        uniq_calls = self.row(
            """SELECT COUNT(DISTINCT q.core_call) AS n FROM qsos q JOIN stations s ON s.id=q.station_id
               WHERE s.contest_id=? AND q.dupe=0""", (contest_id,))
        return {"bands": sorted(by_band.values(), key=lambda b: int("".join(ch for ch in b["band"] if ch.isdigit()) or 0)),
                "total_qsos": total_qsos, "total_points": total_points,
                "unique_squares": all_squares["n"] if all_squares else 0,
                "unique_calls": uniq_calls["n"] if uniq_calls else 0}

    def scoreboard(self, contest_id: int) -> list[dict]:
        out = []
        for s in self.list_stations(contest_id):
            out.append({**s, **self.station_summary(s["id"])})
        out.sort(key=lambda x: -(x.get("points") or 0))
        return out

    # ----- Call-Buch und Vorschläge --------------------------------------
    def learn_call(self, call: str, locator: str, source: str = "log", when: str = "", name: str = "") -> None:
        call = (call or "").strip().upper()
        core = prefixes.core_call(call)
        if not core:
            return
        locator = geo.normalize_locator(locator)
        if locator and not geo.is_valid_locator(locator):
            locator = ""
        existing = self.row("SELECT * FROM callbook WHERE call=?", (core,))
        with self.conn:
            if not existing:
                self.conn.execute(
                    "INSERT INTO callbook(call,locator,name,source,qso_count,last_seen,alt_locators) VALUES(?,?,?,?,?,?,?)",
                    (core, locator, name, source, 1 if source == "log" else 0, when, ""),
                )
                return
            alts = [a for a in (existing["alt_locators"] or "").split(",") if a]
            new_loc = existing["locator"]
            if locator and locator != existing["locator"]:
                # Neuester Locator gewinnt, alter wird als Alternative gemerkt
                if when >= (existing["last_seen"] or "") or not existing["locator"]:
                    if existing["locator"] and existing["locator"] not in alts:
                        alts.insert(0, existing["locator"])
                    new_loc = locator
                elif locator not in alts:
                    alts.append(locator)
            self.conn.execute(
                "UPDATE callbook SET locator=?, name=COALESCE(NULLIF(?,''),name), qso_count=qso_count+?, last_seen=MAX(last_seen,?), alt_locators=? WHERE call=?",
                (new_loc, name, 1 if source == "log" else 0, when, ",".join(alts[:5]), core),
            )

    def suggest(self, partial: str, limit: int = 12, station_id: int | None = None) -> list[dict]:
        partial = (partial or "").strip().upper()
        if len(partial) < 2:
            return []
        rows = self.rows(
            """SELECT call, locator, name, qso_count, last_seen, alt_locators, source FROM callbook
               WHERE call LIKE ? ORDER BY (call=?) DESC, (call LIKE ?) DESC, qso_count DESC, call LIMIT ?""",
            (f"%{partial}%", partial, f"{partial}%", limit),
        )
        if station_id is not None:
            station = self.get_station(station_id)
            for r in rows:
                worked = self.row(
                    "SELECT ts_utc, band FROM qsos WHERE station_id=? AND core_call=? ORDER BY ts_utc DESC LIMIT 1",
                    (station_id, r["call"]),
                )
                r["worked_here"] = worked
                if station and geo.is_valid_locator(r["locator"]):
                    r["km"] = geo.distance_km_int(station["locator"], r["locator"])
                    r["bearing"] = int(round(geo.bearing_deg(station["locator"], r["locator"]))) % 360
        return rows

    def lookup_call(self, call: str) -> dict | None:
        core = prefixes.core_call(call)
        r = self.row("SELECT * FROM callbook WHERE call=?", (core,))
        if r:
            r["history"] = self.rows(
                """SELECT q.ts_utc, q.locator, q.band, s.call AS own_call, c.name AS contest FROM qsos q
                   JOIN stations s ON s.id=q.station_id JOIN contests c ON c.id=s.contest_id
                   WHERE q.core_call=? ORDER BY q.ts_utc DESC LIMIT 8""",
                (core,),
            )
        return r

    def callbook_count(self) -> int:
        r = self.row("SELECT COUNT(*) AS n FROM callbook")
        return r["n"] if r else 0

    # ----- Chat -----------------------------------------------------------
    def add_chat(self, nick: str, text: str) -> dict:
        now = utcnow()
        with self.conn:
            cur = self.conn.execute("INSERT INTO chat(ts_utc,nick,text) VALUES(?,?,?)", (now, nick[:24], text[:500]))
        return {"id": cur.lastrowid, "ts_utc": now, "nick": nick[:24], "text": text[:500]}

    def recent_chat(self, limit: int = 100) -> list[dict]:
        return list(reversed(self.rows("SELECT * FROM chat ORDER BY id DESC LIMIT ?", (limit,))))
