"""SQLite-Datenhaltung. Eine Datei (`data/beamlog.db`, bis 0.9 `contestlogger.db`) enthält alles:
Contests, Stationen, QSOs, Call-Buch, Chat und Einstellungen.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import hmac
import json
import os
import secrets
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import geo, prefixes
from .logcheck import norm_rst
from . import scoring as scoring_mod

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
    exchange TEXT NOT NULL DEFAULT 'serial',
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
    kst_user TEXT NOT NULL DEFAULT '',
    kst_pass TEXT NOT NULL DEFAULT '',
    kst_room INTEGER NOT NULL DEFAULT 2,
    kst_autostart INTEGER NOT NULL DEFAULT 0,
    kst_my_calls TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS station_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call TEXT NOT NULL,
    locator TEXT NOT NULL,
    band TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'SSB',
    password_hash TEXT NOT NULL DEFAULT '',
    info TEXT NOT NULL DEFAULT '{}',
    kst_user TEXT NOT NULL DEFAULT '',
    kst_pass TEXT NOT NULL DEFAULT '',
    kst_room INTEGER NOT NULL DEFAULT 2,
    kst_autostart INTEGER NOT NULL DEFAULT 0,
    kst_my_calls TEXT NOT NULL DEFAULT '',
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
    exch_rcvd TEXT NOT NULL DEFAULT '',
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
    alt_locators TEXT NOT NULL DEFAULT '',
    dok TEXT NOT NULL DEFAULT '',
    ext_locator TEXT NOT NULL DEFAULT '',
    ext_source TEXT NOT NULL DEFAULT '',
    ext_checked TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS kst_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    time TEXT NOT NULL,
    call TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    to_call TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    own INTEGER NOT NULL DEFAULT 0,
    to_me INTEGER NOT NULL DEFAULT 0,
    station_id INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    nick TEXT NOT NULL DEFAULT '',
    admin INTEGER NOT NULL DEFAULT 0,
    action TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    status INTEGER NOT NULL DEFAULT 0,
    details TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    nick TEXT NOT NULL,
    text TEXT NOT NULL,
    contest_id INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS kst_seen (
    station_id INTEGER NOT NULL,
    nick TEXT NOT NULL,
    partner TEXT NOT NULL,
    ts_utc TEXT NOT NULL,
    PRIMARY KEY (station_id, nick, partner)
);
"""



# Austausch je Contest: laufende Nummer, DOK/OV (z. B. Köln-Aachen-Contest) oder beides
EXCHANGES = ("serial", "dok", "serial_dok")


def normalize_dok(v: Any) -> str:
    """DOK/OV-Kennung vereinheitlichen (Großschreibung, ohne Leerzeichen, max. 8 Zeichen)."""
    return re.sub(r"\s+", "", str(v or "")).upper()[:8]

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


NAME_MAX = 32  # Name in der Stationsdatenbank (Vorname bzw. kurzer Name, wie aus HamQTH/QRZ)


class _Rows:
    """Ergebnis einer Abfrage, schon vollständig gelesen (unter der Sperre) – verhält sich wie ein sqlite3-Cursor."""
    __slots__ = ("_rows", "lastrowid", "rowcount", "description")

    def __init__(self, cur: sqlite3.Cursor):
        self._rows = cur.fetchall() if cur.description else []
        self.lastrowid, self.rowcount, self.description = cur.lastrowid, cur.rowcount, cur.description

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list:
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class SafeConnection:
    """Eine SQLite-Verbindung für alle Threads – Zugriffe laufen nacheinander. Ohne die Sperre kollidieren gleichzeitige
    Anfragen (Web-Server-Threads und Hintergrundaufgaben) in derselben Verbindung: „sqlite3.InterfaceError: bad parameter
    or other API misuse“. „with conn:“ hält die Sperre für die ganze Transaktion."""

    def __init__(self, conn: sqlite3.Connection):
        self._c = conn
        self._lock = threading.RLock()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> _Rows:
        with self._lock:
            return _Rows(self._c.execute(sql, tuple(params)))

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> _Rows:
        with self._lock:
            return _Rows(self._c.executemany(sql, seq))

    def executescript(self, script: str) -> None:
        with self._lock:
            self._c.executescript(script)

    def commit(self) -> None:
        with self._lock:
            self._c.commit()

    def rollback(self) -> None:
        with self._lock:
            self._c.rollback()

    def backup(self, target: sqlite3.Connection, **kw: Any) -> None:
        with self._lock:
            self._c.backup(target, **kw)

    def close(self) -> None:
        with self._lock:
            self._c.close()

    def __enter__(self) -> "SafeConnection":
        self._lock.acquire()
        try:
            self._c.__enter__()
        except BaseException:
            self._lock.release()
            raise
        return self

    def __exit__(self, *exc: Any) -> bool:
        try:
            return bool(self._c.__exit__(*exc))
        finally:
            self._lock.release()

    def __getattr__(self, name: str) -> Any:  # total_changes, in_transaction …
        return getattr(self._c, name)


class Database:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(self.path, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        self.conn = SafeConnection(raw)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        # FULL: jede Transaktion ist beim Rückgabezeitpunkt auf der Platte – ein Stromausfall
        # verliert höchstens das gerade laufende QSO, die Datei bleibt konsistent.
        self.conn.execute("PRAGMA synchronous = FULL")
        self.conn.executescript(SCHEMA)
        self._migrate()
        with self.conn:  # Namen in der Stationsdatenbank sind höchstens NAME_MAX Zeichen lang (ältere Importe waren länger)
            self.conn.execute(f"UPDATE callbook SET name=substr(name,1,{NAME_MAX}) WHERE length(name)>{NAME_MAX}")
        if self.get_setting("secret") is None:
            self.set_setting("secret", secrets.token_hex(32))

    def _migrate(self) -> None:
        """Spalten nachrüsten, die in älteren Datenbanken fehlen."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(qsos)")}
        scols = {r["name"] for r in self.conn.execute("PRAGMA table_info(stations)")}
        kcols = {r["name"] for r in self.conn.execute("PRAGMA table_info(kst_messages)")}
        with self.conn:
            if "freq" not in cols:
                self.conn.execute("ALTER TABLE qsos ADD COLUMN freq TEXT NOT NULL DEFAULT ''")
            if "exch_rcvd" not in cols:
                self.conn.execute("ALTER TABLE qsos ADD COLUMN exch_rcvd TEXT NOT NULL DEFAULT ''")
            if "exchange" not in {r["name"] for r in self.rows("PRAGMA table_info(contests)")}:
                self.conn.execute("ALTER TABLE contests ADD COLUMN exchange TEXT NOT NULL DEFAULT 'serial'")
            if "dok" not in {r["name"] for r in self.rows("PRAGMA table_info(callbook)")}:
                self.conn.execute("ALTER TABLE callbook ADD COLUMN dok TEXT NOT NULL DEFAULT ''")
            if "kst_user" not in scols:
                # KST-Zugang ist jetzt je Station; bisherige globale Einstellung auf alle Stationen übernehmen
                for col, typ in (("kst_user", "TEXT NOT NULL DEFAULT ''"), ("kst_pass", "TEXT NOT NULL DEFAULT ''"), ("kst_room", "INTEGER NOT NULL DEFAULT 2"),
                                 ("kst_autostart", "INTEGER NOT NULL DEFAULT 0"), ("kst_my_calls", "TEXT NOT NULL DEFAULT ''")):
                    self.conn.execute(f"ALTER TABLE stations ADD COLUMN {col} {typ}")
                g = {k: self.get_setting(k, "") or "" for k in ("kst_user", "kst_pass", "kst_room", "kst_autostart")}
                if g["kst_user"]:
                    self.conn.execute("UPDATE stations SET kst_user=?, kst_pass=?, kst_room=?, kst_autostart=?",
                                      (g["kst_user"], g["kst_pass"], int(g["kst_room"] or 2), int(g["kst_autostart"] == "1")))
            if "station_id" not in kcols:
                self.conn.execute("ALTER TABLE kst_messages ADD COLUMN station_id INTEGER NOT NULL DEFAULT 0")
            if "contest_id" not in {r["name"] for r in self.conn.execute("PRAGMA table_info(chat)")}:
                self.conn.execute("ALTER TABLE chat ADD COLUMN contest_id INTEGER NOT NULL DEFAULT 0")
            ccols = {r["name"] for r in self.conn.execute("PRAGMA table_info(callbook)")}
            for col in ("ext_locator", "ext_source", "ext_checked"):
                if col not in ccols:
                    self.conn.execute(f"ALTER TABLE callbook ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
            # globale Stationen: beim ersten Start aus den vorhandenen Contest-Stationen ableiten (je Call+Band die neueste)
            if not self.conn.execute("SELECT value FROM settings WHERE key='templates_migrated'").fetchone():
                self.conn.execute("INSERT INTO settings(key,value) VALUES('templates_migrated','1')")
                seen: set[tuple[str, str]] = set()
                for s in self.conn.execute("SELECT * FROM stations ORDER BY id DESC").fetchall():
                    key = (s["call"], s["band"])
                    if key in seen:
                        continue
                    seen.add(key)
                    self.conn.execute(
                        "INSERT INTO station_templates(call,locator,band,mode,password_hash,info,kst_user,kst_pass,kst_room,kst_autostart,kst_my_calls,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (s["call"], s["locator"], s["band"], s["mode"], s["password_hash"], s["info"], s["kst_user"], s["kst_pass"], s["kst_room"], s["kst_autostart"], s["kst_my_calls"], utcnow()))
            # Einträge wie DN2LH-2 (KST-Mehrfachanmeldung) mit dem Basis-Rufzeichen zusammenführen
            for r in self.conn.execute("SELECT call, locator FROM callbook WHERE call LIKE '%-%'").fetchall():
                base = prefixes.core_call(r["call"])
                if base and base != r["call"]:
                    if self.conn.execute("SELECT 1 FROM callbook WHERE call=?", (base,)).fetchone():
                        self.conn.execute("DELETE FROM callbook WHERE call=?", (r["call"],))
                    else:
                        self.conn.execute("UPDATE callbook SET call=? WHERE call=?", (base, r["call"]))

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
        name = f"beamlog-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{reason}.db"
        self.backup_to(self.backup_dir / name)
        self.prune_backups()
        self.add_audit("Backup erstellt", details=f"{name} ({reason})", nick="Server")
        return self.backup_dir / name

    # ------------------------------------------------------------ Aktionsprotokoll
    def add_audit(self, action: str, details: str = "", nick: str = "", admin: bool = False, method: str = "", path: str = "", status: int = 0) -> None:
        """Eintrag ins Aktionsprotokoll (wer hat wann was gemacht) – zusätzlich auf der Konsole."""
        ts = utcnow()
        with self.conn:
            self.conn.execute("INSERT INTO audit(ts_utc,nick,admin,action,method,path,status,details) VALUES(?,?,?,?,?,?,?,?)",
                              (ts, nick or "", int(admin), action, method, path, status, details[:1000]))
        who = f"{nick or '?'}{' [Admin]' if admin else ''}"
        print(f"[{ts}] {who}: {action}{' – ' + details if details else ''}{' (' + str(status) + ')' if status >= 400 else ''}", flush=True)

    def list_audit(self, limit: int = 200, q: str = "") -> list[dict]:
        if q:
            like = f"%{q}%"
            return self.rows("SELECT * FROM audit WHERE action LIKE ? OR details LIKE ? OR nick LIKE ? OR path LIKE ? ORDER BY id DESC LIMIT ?",
                             (like, like, like, like, limit))
        return self.rows("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))

    def prune_audit(self, keep: int = 20000) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM audit WHERE id < (SELECT COALESCE(MAX(id),0) FROM audit) - ?", (keep,))

    def _backup_files(self, pattern: str) -> list[Path]:
        """Sicherungen, neueste zuerst – beamlog-… und die alten contestlogger-… (bis 0.9) gemeinsam, nach Zeitstempel sortiert."""
        files = [f for pre in ("beamlog-", "contestlogger-") for f in self.backup_dir.glob(pre + pattern)]
        return sorted(files, key=lambda f: f.name.split("-", 1)[1], reverse=True)

    def list_backups(self) -> list[dict]:
        if not self.backup_dir.exists():
            return []
        out = []
        for f in self._backup_files("*.db"):
            st = f.stat()
            out.append({"name": f.name, "size": st.st_size,
                        "ts_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        return out

    def prune_backups(self, keep_auto: int = 48, keep_manual: int = 50) -> None:
        """Automatische Sicherungen: die letzten 48 behalten (bei 15 min = 12 h) plus eine pro Tag für 30 Tage."""
        files = self._backup_files("*-auto.db")
        daily_seen: set[str] = set()
        for i, f in enumerate(files):
            m = re.search(r"-(\d{8})-\d{6}-", f.name)
            day = m.group(1) if m else f.name
            if i < keep_auto:
                daily_seen.add(day)
                continue
            if day not in daily_seen and len(daily_seen) < 30:
                daily_seen.add(day)
                continue
            f.unlink(missing_ok=True)
        manual = self._backup_files("*-manual.db")
        for f in manual[keep_manual:]:
            f.unlink(missing_ok=True)

    def close(self) -> None:
        self.conn.close()

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

    def create_contest(self, name: str, start_utc: str | None, end_utc: str | None, scoring: str = "km", notes: str = "", exchange: str = "serial") -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO contests(name,start_utc,end_utc,scoring,notes,exchange,created_at) VALUES(?,?,?,?,?,?,?)",
                (name.strip(), start_utc or None, end_utc or None, scoring_mod.normalize(scoring), notes, exchange if exchange in EXCHANGES else "serial", utcnow()),
            )
            return int(cur.lastrowid)

    def update_contest(self, cid: int, **fields: Any) -> None:
        allowed = {"name", "start_utc", "end_utc", "scoring", "notes", "archived", "exchange"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if "exchange" in sets and sets["exchange"] not in EXCHANGES:
            sets["exchange"] = "serial"
        if "scoring" in sets:
            sets["scoring"] = scoring_mod.normalize(sets["scoring"])
        if not sets:
            return
        with self.conn:
            self.conn.execute(
                f"UPDATE contests SET {', '.join(k + '=?' for k in sets)} WHERE id=?",
                (*sets.values(), cid),
            )

    def rescore_contest(self, cid: int) -> None:
        """Nach Änderung der Wertung: Punkte aller QSOs des Contests neu berechnen."""
        for s in self.list_stations(cid):
            self.recheck_dupes(s["id"])

    def _scoring_of(self, station: dict) -> str:
        c = self.get_contest(station["contest_id"]) if station else None
        return (c or {}).get("scoring") or "km"

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
            out.append(self._station_public(s))
        return out

    @staticmethod
    def _station_public(s: dict) -> dict:
        s["has_password"] = bool(s.pop("password_hash"))
        s["kst_pass_set"] = bool(s.pop("kst_pass", ""))
        s["info"] = json.loads(s["info"] or "{}")
        return s

    def get_station(self, sid: int, secrets: bool = False) -> dict | None:
        """Station; ohne secrets=True werden Passwort-Hash und KST-Passwort entfernt."""
        s = self.row("SELECT * FROM stations WHERE id=?", (sid,))
        if not s:
            return None
        if secrets:
            s["info"] = json.loads(s["info"] or "{}")
            return s
        return self._station_public(s)

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

    # ------------------------------------------------------------ globale Stationen (Vorlagen für Contests)
    def list_templates(self) -> list[dict]:
        return [self._station_public(s) for s in self.rows("SELECT * FROM station_templates ORDER BY call, band")]

    def get_template(self, tid: int, secrets: bool = False) -> dict | None:
        s = self.row("SELECT * FROM station_templates WHERE id=?", (tid,))
        if not s:
            return None
        if secrets:
            s["info"] = json.loads(s["info"] or "{}")
            return s
        return self._station_public(s)

    def create_template(self, call: str, locator: str, band: str, mode: str = "SSB", password: str = "", info: dict | None = None, **kst: Any) -> int:
        locator = geo.normalize_locator(locator)
        if not geo.is_valid_locator(locator):
            raise ValueError("Ungültiger Locator")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO station_templates(call,locator,band,mode,password_hash,info,kst_user,kst_pass,kst_room,kst_autostart,kst_my_calls,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (call.strip().upper(), locator, band, mode or "SSB", hash_password(password) if password else "", json.dumps(info or {}),
                 str(kst.get("kst_user") or "").upper(), str(kst.get("kst_pass") or ""), int(kst.get("kst_room") or 2), int(bool(kst.get("kst_autostart"))), str(kst.get("kst_my_calls") or "").upper(), utcnow()))
            return int(cur.lastrowid)

    def update_template(self, tid: int, **fields: Any) -> None:
        allowed = {"call", "locator", "band", "mode", "info", "password", "kst_user", "kst_pass", "kst_room", "kst_autostart", "kst_my_calls"}
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
                sets["call"] = str(v).strip().upper()
            else:
                sets[k] = v
        if sets:
            with self.conn:
                self.conn.execute(f"UPDATE station_templates SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), tid))

    def delete_template(self, tid: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM station_templates WHERE id=?", (tid,))

    def create_station_from_template(self, contest_id: int, tid: int) -> int:
        """Contest-Station aus globaler Station anlegen (eigenes Log, eigene Nummer, eigener KST-Chat)."""
        s = self.row("SELECT * FROM station_templates WHERE id=?", (tid,))
        if not s:
            raise ValueError("Globale Station nicht gefunden")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO stations(contest_id,call,locator,band,mode,password_hash,info,kst_user,kst_pass,kst_room,kst_autostart,kst_my_calls,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (contest_id, s["call"], s["locator"], s["band"], s["mode"], s["password_hash"], s["info"], s["kst_user"], s["kst_pass"], s["kst_room"], s["kst_autostart"], s["kst_my_calls"], utcnow()))
            return int(cur.lastrowid)

    def set_ext_lookup(self, call: str, locator: str, source: str) -> None:
        core = prefixes.core_call(call)
        with self.conn:
            self.conn.execute("UPDATE callbook SET ext_locator=?, ext_source=?, ext_checked=? WHERE call=?", (locator or "", source, utcnow(), core))
            if self.conn.total_changes == 0 or not self.row("SELECT 1 FROM callbook WHERE call=?", (core,)):
                self.conn.execute("INSERT OR IGNORE INTO callbook(call,locator,name,source,qso_count,last_seen,alt_locators,ext_locator,ext_source,ext_checked) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                  (core, locator or "", "", source, 0, "", "", locator or "", source, utcnow()))

    def update_station(self, sid: int, **fields: Any) -> None:
        allowed = {"call", "locator", "band", "mode", "serial_next", "info", "password", "kst_user", "kst_pass", "kst_room", "kst_autostart", "kst_my_calls"}
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
        q["exch_rcvd"] = normalize_dok(q.get("exch_rcvd"))
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
            points = scoring_mod.qso_points(self._scoring_of(station), q["km"], q["locator"], bool(dupe))
            cur = self.conn.execute(
                """INSERT INTO qsos(station_id,ts_utc,call,core_call,locator,square,country,rst_sent,rst_rcvd,
                   serial_sent,serial_rcvd,mode,band,comment,km,bearing,points,dupe,logged_by,created_at,updated_at,freq,exch_rcvd)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (station_id, ts, q["call"], q["core_call"], q["locator"], q["square"], q["country"],
                 norm_rst(q.get("rst_sent") or "59"), norm_rst(q.get("rst_rcvd") or "59"), serial,
                 str(q.get("serial_rcvd") or ""), q.get("mode") or station["mode"], band,
                 q.get("comment") or "", q["km"], q["bearing"], points, dupe, logged_by, now, now, str(q.get("freq") or ""), q["exch_rcvd"]),
            )
            qid = int(cur.lastrowid)
            # Seriennummer weiterzählen (auch wenn manuell eine kleinere eingegeben wurde: Maximum + 1)
            nxt = max(station["serial_next"], serial + 1)
            self.conn.execute("UPDATE stations SET serial_next=? WHERE id=?", (nxt, station_id))
        self.learn_call(q["call"], q["locator"], source="log", when=ts, dok=q["exch_rcvd"])
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
            points = scoring_mod.qso_points(self._scoring_of(station), q["km"], q["locator"], bool(dupe))
            self.conn.execute(
                """UPDATE qsos SET ts_utc=?,call=?,core_call=?,locator=?,square=?,country=?,rst_sent=?,rst_rcvd=?,
                   serial_sent=?,serial_rcvd=?,mode=?,band=?,comment=?,km=?,bearing=?,points=?,dupe=?,updated_at=?,freq=?,exch_rcvd=? WHERE id=?""",
                (q["ts_utc"], q["call"], q["core_call"], q["locator"], q["square"], q["country"],
                 norm_rst(q["rst_sent"]), norm_rst(q["rst_rcvd"]), int(q["serial_sent"]), str(q["serial_rcvd"]),
                 q["mode"], q["band"], q["comment"] or "", q["km"], q["bearing"], points, dupe, utcnow(), str(q.get("freq") or ""), q["exch_rcvd"], qid),
            )
        self.recheck_dupes(old["station_id"])
        self.learn_call(q["call"], q["locator"], source="log", when=q["ts_utc"], dok=q["exch_rcvd"])
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
        sc = self._scoring_of(station)
        with self.conn:
            for q in self.rows("SELECT id,core_call,band,km,locator,dupe,points FROM qsos WHERE station_id=? ORDER BY ts_utc, id", (station_id,)):
                key = (q["core_call"], q["band"])
                dupe = 1 if key in seen else 0
                seen.add(key)
                points = scoring_mod.qso_points(sc, q["km"], q["locator"], bool(dupe))
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
            sql += " AND (call LIKE ? OR locator LIKE ? OR comment LIKE ? OR exch_rcvd LIKE ?)"
            like = f"%{search.upper()}%"
            params += [like, like, like, like]
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
        exchanges = self.row("SELECT COUNT(DISTINCT exch_rcvd) AS n FROM qsos WHERE station_id=? AND dupe=0 AND exch_rcvd<>''", (station_id,))
        odx = self.row("SELECT call, locator, km FROM qsos WHERE station_id=? AND dupe=0 ORDER BY km DESC LIMIT 1", (station_id,))
        last_hour = self.row(
            "SELECT COUNT(*) AS n FROM qsos WHERE station_id=? AND ts_utc >= strftime('%Y-%m-%dT%H:%M:%SZ','now','-1 hour')",
            (station_id,),
        )
        station = self.get_station(station_id) or {}
        sc = self._scoring_of(station) if station else "km"
        tot = scoring_mod.total(sc, s.get("points") or 0, squares["n"] if squares else 0, exchanges["n"] if exchanges else 0)
        return {
            **s,
            "avg_km": round(s.get("avg_km") or 0),
            "squares": squares["n"] if squares else 0,
            "countries": countries["n"] if countries else 0,
            "exchanges": exchanges["n"] if exchanges else 0,
            "scoring": sc, "scoring_label": scoring_mod.label(sc), "multiplier": tot["multiplier"], "score": tot["score"],
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
            b = by_band.setdefault(s["band"], {"band": s["band"], "qsos": 0, "points": 0, "score": 0, "squares": 0, "odx_km": 0, "stations": []})
            b["qsos"] += s["qsos"] - s["dupes"]
            b["points"] += s["points"] or 0
            b["score"] += s.get("score") or s["points"] or 0
            b["squares"] += s["squares"]
            b["odx_km"] = max(b["odx_km"], s["odx_km"] or 0)
            b["stations"].append(s["call"])
        total_qsos = sum(b["qsos"] for b in by_band.values())
        total_points = sum(b["points"] for b in by_band.values())
        total_score = sum(b["score"] for b in by_band.values())
        all_squares = self.row(
            """SELECT COUNT(DISTINCT q.square) AS n FROM qsos q JOIN stations s ON s.id=q.station_id
               WHERE s.contest_id=? AND q.dupe=0 AND q.square<>''""", (contest_id,))
        uniq_calls = self.row(
            """SELECT COUNT(DISTINCT q.core_call) AS n FROM qsos q JOIN stations s ON s.id=q.station_id
               WHERE s.contest_id=? AND q.dupe=0""", (contest_id,))
        return {"bands": sorted(by_band.values(), key=lambda b: int("".join(ch for ch in b["band"] if ch.isdigit()) or 0)),
                "total_qsos": total_qsos, "total_points": total_points, "total_score": total_score,
                "unique_squares": all_squares["n"] if all_squares else 0,
                "unique_calls": uniq_calls["n"] if uniq_calls else 0}

    def contest_stats(self, contest_id: int) -> dict:
        """Globale Contest-Statistik über alle Stationen/Bänder."""
        summary = self.contest_summary(contest_id)
        stations = self.scoreboard(contest_id)
        per_hour = self.rows(
            """SELECT substr(q.ts_utc,1,13) AS hour, s.band AS band, COUNT(*) AS qsos, SUM(q.points) AS points
               FROM qsos q JOIN stations s ON s.id=q.station_id WHERE s.contest_id=? AND q.dupe=0
               GROUP BY hour, s.band ORDER BY hour""", (contest_id,))
        recent = self.rows(
            """SELECT q.id, q.ts_utc, q.call, q.locator, q.km, q.points, q.dupe, q.logged_by, s.call AS own_call, s.band
               FROM qsos q JOIN stations s ON s.id=q.station_id WHERE s.contest_id=?
               ORDER BY q.ts_utc DESC, q.id DESC LIMIT 40""", (contest_id,))
        countries = self.rows(
            """SELECT q.country, COUNT(*) AS qsos, SUM(q.points) AS points, MAX(q.km) AS odx
               FROM qsos q JOIN stations s ON s.id=q.station_id WHERE s.contest_id=? AND q.dupe=0
               GROUP BY q.country ORDER BY qsos DESC""", (contest_id,))
        operators = self.rows(
            """SELECT q.logged_by AS nick, COUNT(*) AS qsos, SUM(q.points) AS points
               FROM qsos q JOIN stations s ON s.id=q.station_id WHERE s.contest_id=?
               GROUP BY q.logged_by ORDER BY qsos DESC""", (contest_id,))
        odx = self.rows(
            """SELECT s.band, q.call, q.locator, q.km FROM qsos q JOIN stations s ON s.id=q.station_id
               WHERE s.contest_id=? AND q.dupe=0 AND q.km = (SELECT MAX(q2.km) FROM qsos q2 JOIN stations s2 ON s2.id=q2.station_id WHERE s2.contest_id=s.contest_id AND s2.band=s.band AND q2.dupe=0)
               GROUP BY s.band""", (contest_id,))
        last_hour = self.row(
            """SELECT COUNT(*) AS n FROM qsos q JOIN stations s ON s.id=q.station_id
               WHERE s.contest_id=? AND q.ts_utc >= strftime('%Y-%m-%dT%H:%M:%SZ','now','-1 hour')""", (contest_id,))
        return {**summary, "stations": stations, "per_hour": per_hour, "recent": recent, "countries": countries,
                "operators": operators, "odx": odx, "rate_last_hour": last_hour["n"] if last_hour else 0,
                "unique_countries": len([c for c in countries if c["country"] not in ("", "?")])}

    def scoreboard(self, contest_id: int) -> list[dict]:
        out = []
        for s in self.list_stations(contest_id):
            out.append({**s, **self.station_summary(s["id"])})
        out.sort(key=lambda x: -(x.get("score") or x.get("points") or 0))
        return out

    # ----- Call-Buch und Vorschläge --------------------------------------
    def learn_call(self, call: str, locator: str, source: str = "log", when: str = "", name: str = "", dok: str = "") -> str:
        """Rufzeichen ins Call-Buch übernehmen. Rückgabe: "new" (neu), "known" (schon vorhanden) oder "" (ungültig).
        dok: DOK/OV des Rufzeichens (DARC-Ortsverband), falls bekannt – der neueste gewinnt."""
        call = (call or "").strip().upper()
        core = prefixes.core_call(call)
        if not core:
            return ""
        name = (name or "").strip()[:NAME_MAX]
        locator = geo.normalize_locator(locator)
        if locator and not geo.is_valid_locator(locator):
            locator = ""
        dok = normalize_dok(dok)
        existing = self.row("SELECT * FROM callbook WHERE call=?", (core,))
        with self.conn:
            if not existing:
                self.conn.execute(
                    "INSERT INTO callbook(call,locator,name,source,qso_count,last_seen,alt_locators,dok) VALUES(?,?,?,?,?,?,?,?)",
                    (core, locator, name, source, 1 if source == "log" else 0, when, "", dok),
                )
                return "new"
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
            new_dok = existing["dok"] or ""
            if dok and (not new_dok or when >= (existing["last_seen"] or "")):
                new_dok = dok
            self.conn.execute(
                "UPDATE callbook SET locator=?, name=COALESCE(NULLIF(?,''),name), qso_count=qso_count+?, last_seen=MAX(last_seen,?), alt_locators=?, dok=? WHERE call=?",
                (new_loc, name, 1 if source == "log" else 0, when, ",".join(alts[:5]), new_dok, core),
            )
        return "known"

    def suggest(self, partial: str, limit: int = 12, station_id: int | None = None) -> list[dict]:
        partial = (partial or "").strip().upper()
        if len(partial) < 2:
            return []
        rows = self.rows(
            """SELECT call, locator, name, qso_count, last_seen, alt_locators, source, dok FROM callbook
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

    @contextmanager
    def bulk(self):
        """Viele Einzel-Schreibvorgänge (z. B. 6000 Einträge der Startdatenbank) ohne Plattensync je Eintrag –
        mit synchronous=FULL dauerte das unter Windows Minuten. Danach wieder voll abgesichert."""
        self.conn.execute("PRAGMA synchronous = OFF")
        try:
            yield
        finally:
            self.conn.execute("PRAGMA synchronous = FULL")
            self.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

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

    _stats_cache: tuple[Any, dict] | None = None

    def callbook_stats(self) -> dict:
        """Kennzahlen der Stationsdatenbank: Rufzeichen gesamt, mit Locator/DOK/Name, je Land (Deutschland zuerst).
        Zwischengespeichert, bis sich in der Datenbank etwas ändert."""
        key = (self.conn.total_changes, self.callbook_count())
        if self._stats_cache and self._stats_cache[0] == key:
            return self._stats_cache[1]
        def empty() -> dict:
            return {"total": 0, "locator": 0, "dok": 0, "both": 0, "none": 0, "name": 0}
        tot, by_country = empty(), {}
        for call, loc, dok, name in self.conn.execute("SELECT call, locator, dok, name FROM callbook").fetchall():
            c = by_country.setdefault(prefixes.country(call), empty())
            for d in (tot, c):
                d["total"] += 1
                d["locator"] += bool(loc)
                d["dok"] += bool(dok)
                d["both"] += bool(loc and dok)
                d["none"] += not (loc or dok)
                d["name"] += bool(name)
        countries = sorted(({"country": k, **v} for k, v in by_country.items()),
                           key=lambda c: (c["country"] != "Deutschland", -c["total"], c["country"]))
        out = {**tot, "countries": countries}
        self._stats_cache = (key, out)
        return out

    def callbook_fill_candidates(self, checked_before: str) -> list[str]:
        """Rufzeichen, denen Locator oder (deutsche Stationen) DOK fehlt und die noch nie bzw. vor checked_before online
        abgefragt wurden – nie abgefragte und solche ohne Locator zuerst."""
        out = []
        for call, loc, dok in self.conn.execute(
                "SELECT call, locator, dok FROM callbook WHERE (locator='' OR dok='') AND (ext_checked='' OR ext_checked<?) "
                "ORDER BY ext_checked, locator<>'', call", (checked_before,)).fetchall():
            if not prefixes.is_plausible_call(call):
                continue
            if loc and prefixes.country(call) != "Deutschland":  # DOKs gibt es nur in Deutschland
                continue
            out.append(call)
        return out

    def fill_from_lookup(self, call: str, res: dict, source: str) -> dict:
        """Ergebnis einer Online-Abfrage übernehmen: nur leere Felder füllen (Locator, DOK nur bei deutschen Stationen, Name),
        die Abfrage merken (auch ohne Treffer). Rückgabe: welche Felder neu sind."""
        core = prefixes.core_call(call)
        row = self.row("SELECT locator, dok, name FROM callbook WHERE call=?", (core,)) or {"locator": "", "dok": "", "name": ""}
        loc = geo.normalize_locator(res.get("locator", ""))
        loc = loc if loc and geo.is_valid_locator(loc) else ""
        dok = normalize_dok(res.get("dok")) if prefixes.country(core) == "Deutschland" else ""
        name = (res.get("name") or "").strip()[:NAME_MAX]
        got = {"locator": bool(loc and not row["locator"]), "dok": bool(dok and not row["dok"]), "name": bool(name and not row["name"])}
        with self.conn:
            self.conn.execute("UPDATE callbook SET locator=CASE WHEN locator='' THEN ? ELSE locator END, dok=CASE WHEN dok='' THEN ? ELSE dok END, "
                              "name=CASE WHEN name='' THEN ? ELSE name END WHERE call=?", (loc, dok, name, core))
        self.set_ext_lookup(core, loc, source)
        return got

    # ----- Chat -----------------------------------------------------------
    def add_chat(self, nick: str, text: str, contest_id: int = 0) -> dict:
        now = utcnow()
        with self.conn:
            cur = self.conn.execute("INSERT INTO chat(ts_utc,nick,text,contest_id) VALUES(?,?,?,?)", (now, nick[:24], text[:500], contest_id))
        return {"id": cur.lastrowid, "ts_utc": now, "nick": nick[:24], "text": text[:500], "contest_id": contest_id}

    def recent_chat(self, contest_id: int = 0, limit: int = 300) -> list[dict]:
        """Chat-Verlauf eines Contests (contest_id 0 = ohne Contest)."""
        return list(reversed(self.rows("SELECT * FROM chat WHERE contest_id=? ORDER BY id DESC LIMIT ?", (contest_id, limit))))

    # ------------------------------------------------------------ KST-Lesemarken (je Station und Nutzer, serverseitig)
    def get_kst_seen(self, station_id: int, nick: str) -> dict[str, str]:
        return {r["partner"]: r["ts_utc"] for r in self.rows("SELECT partner, ts_utc FROM kst_seen WHERE station_id=? AND nick=?", (station_id, nick))}

    def set_kst_seen(self, station_id: int, nick: str, partner: str, ts_utc: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO kst_seen(station_id,nick,partner,ts_utc) VALUES(?,?,?,?) ON CONFLICT(station_id,nick,partner) DO UPDATE SET ts_utc=MAX(ts_utc, excluded.ts_utc)",
                              (station_id, nick, partner, ts_utc))
