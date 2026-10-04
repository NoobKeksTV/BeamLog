"""ON4KST-Chat-Anbindung (Telnet, www.on4kst.info:23000).

Der Server hält je Station eine Verbindung, verteilt Nachrichten per WebSocket
an alle Browser und nimmt Nachrichten/Kommandos entgegen. Protokoll (aus Mitschnitten
dokumentiert, z. B. kst2mac/PROTOCOL.md, Tucnak-Wiki):

    Login:            -> Rufzeichen
    Password:         -> Passwort (Klartext!)
    Menü 1..13        -> Raumnummer (2 = 144/432 MHz, 3 = Mikrowelle, 1 = 50/70 MHz, 4 = EME, 5 = Low Band)
    Nachricht:        HHMMZ CALL Name> (ZIELCALL)  Text
    Prompt:           HHMMZ MYCALL 144/432 MHz chat>
    /SHOW USER        -> Zeilen "CALL             LOCATOR Name"
    /CQ CALL Text     -> gezielte Nachricht
    Kommandos: höchstens eines pro Minute (Nachrichten unbegrenzt)
"""
from __future__ import annotations

import asyncio
import html
import re
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable

from . import geo, prefixes

import os
HOST, PORT = os.environ.get("CONTESTLOGGER_KST_HOST", "www.on4kst.info"), int(os.environ.get("CONTESTLOGGER_KST_PORT", "23000"))
ROOMS = {1: "50/70 MHz", 2: "144/432 MHz", 3: "Microwave", 4: "EME/JT65", 5: "Low Band", 6: "50 MHz IARU R2", 7: "50 MHz IARU R2",
         8: "144/432 MHz IARU R2", 9: "144/432 MHz IARU R3", 10: "kHz", 11: "WARC", 12: "28 MHz", 13: "40 MHz"}

MSG_RE = re.compile(r"^(\d{4})Z\s+([A-Z0-9/\-]+)\s+(.*?)>\s*(?:\(([A-Z0-9/\-]+)\)\s*)?(.*)$")
PROMPT_RE = re.compile(r"^(\d{4})Z\s+([A-Z0-9/\-]+)\s+.*chat>\s*$")
USER_RE = re.compile(r"^\(?([A-Z0-9/\-]{3,12})\)?\s{2,}([A-R]{2}\d{2}[A-X]{2})?\s*(.*)$")
SYSTEM_SENDERS = {"ON4KST", "KST", "SYSOP", "ADMIN"}
CALL_IN_TEXT = re.compile(r"\b([A-Z0-9]{1,3}[0-9][A-Z0-9]{0,4}[A-Z](?:/[A-Z0-9]{1,3})?)\b")


def parse_message(line: str) -> dict | None:
    """'0846Z OZ5QF Jens 2m> (F6IFX/P)  Tnx qso' -> dict oder None."""
    m = MSG_RE.match(line.strip())
    if not m or PROMPT_RE.match(line.strip()):
        return None
    hhmm, call, name, to, text = m.groups()
    return {"time": f"{hhmm[:2]}:{hhmm[2:]}", "call": _base(call), "name": html.unescape(name.strip()),
            "to": _base(to or ""), "text": html.unescape(text.strip())}


def _base(call: str) -> str:
    """KST hängt Zusätze mit Bindestrich an (DN2LH-2 bei Mehrfach-Anmeldung, OJ7F-23CM fürs Band) – kein Teil des Rufzeichens."""
    return re.sub(r"-.*$", "", (call or "").strip().upper())


def parse_user(line: str) -> dict | None:
    m = USER_RE.match(line.rstrip())
    if not m or not m.group(2):
        return None
    call, loc, name = m.groups()
    return {"call": _base(call), "locator": loc, "name": html.unescape(name.strip()), "away": line.lstrip().startswith("(")}


class KstClient:
    """Verbindung zum KST-Chat mit automatischem Reconnect. on_event(dict) wird für alles aufgerufen."""

    def __init__(self, user: str, password: str, room: int, on_event: Callable[[dict], Awaitable[None]], my_calls: list[str] | None = None):
        self.user, self.password, self.room = user.strip().upper(), password, int(room or 2)
        self.on_event = on_event
        # Nachrichten "an mich": Zielcall (oder Call im Text) steht in dieser Liste – Standard ist nur der KST-Login
        self.my_calls = {c.strip().upper() for c in (my_calls or []) if c.strip()} or {self.user}
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.state = "aus"
        self.error = ""
        self.users: dict[str, dict] = {}
        self.messages: list[dict] = []
        self._task: asyncio.Task | None = None
        self._cmd_queue: asyncio.Queue[str] = asyncio.Queue()
        self._last_cmd = 0.0
        self._last_rx = 0.0
        self._stop = False
        self._disconnected: asyncio.Event | None = None

    # ------------------------------------------------------------ Steuerung
    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop = True
        if self.writer:
            try:
                self.writer.close()
            except Exception:  # noqa: BLE001
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self.state = "aus"
        await self._emit({"type": "kst_status", "state": self.state, "error": self.error})

    def status(self) -> dict:
        return {"state": self.state, "error": self.error, "user": self.user, "room": self.room, "room_name": ROOMS.get(self.room, str(self.room)),
                "users": len(self.users), "messages": len(self.messages)}

    async def send_text(self, text: str) -> None:
        """Chat-Nachricht (oder /CQ …) senden – keine Ratenbegrenzung."""
        text = text.strip()
        if not text or not self.writer or self.state != "verbunden":
            raise RuntimeError("Nicht mit dem KST-Chat verbunden")
        self.writer.write((text + "\r\n").encode("latin-1", "replace"))
        await self.writer.drain()

    async def send_command(self, cmd: str) -> None:
        """Kommando (z. B. /SHOW USER) – wird gedrosselt (1/min) aus der Warteschlange gesendet."""
        await self._cmd_queue.put(cmd)

    # ------------------------------------------------------------ intern
    async def _emit(self, ev: dict) -> None:
        try:
            await self.on_event(ev)
        except Exception:  # noqa: BLE001
            pass

    RECONNECT_WAIT = 5.0  # Sekunden bis zum ersten Neuverbinden (verdoppelt sich bis 120 s)

    async def _run(self) -> None:
        backoff = self.RECONNECT_WAIT
        while not self._stop:
            try:
                await self._session()
                backoff = self.RECONNECT_WAIT
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.error = str(e)
                self.state = "getrennt"
                await self._emit({"type": "kst_status", "state": self.state, "error": self.error})
            if self._stop:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)

    async def _read_until(self, markers: tuple[str, ...], timeout: float = 20) -> str:
        buf = b""
        end = time.time() + timeout
        while time.time() < end:
            chunk = await asyncio.wait_for(self.reader.read(512), timeout=max(0.1, end - time.time()))  # type: ignore[union-attr]
            if not chunk:
                raise ConnectionError("Verbindung geschlossen")
            buf += chunk
            text = buf.decode("latin-1", "replace")
            if any(m.lower() in text.lower() for m in markers):
                return text
        raise TimeoutError(f"Warte auf {markers}")

    async def _session(self) -> None:
        self.state = "verbinde"
        self.error = ""
        await self._emit({"type": "kst_status", "state": self.state, "error": ""})
        self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(HOST, PORT), timeout=15)
        await self._read_until(("Login:",))
        self.writer.write((self.user + "\r\n").encode())
        await self._read_until(("Password:",))
        self.writer.write((self.password + "\r\n").encode())
        menu = await self._read_until(("Your choice", "chat>", "Login:"), timeout=25)
        if "Login:" in menu and "Your choice" not in menu and "chat>" not in menu:
            raise PermissionError("KST: Anmeldung abgelehnt (Rufzeichen/Passwort prüfen)")
        if "Your choice" in menu:
            self.writer.write((f"{self.room}\r\n").encode())
        await self.writer.drain()
        self.state = "verbunden"
        await self._emit({"type": "kst_status", "state": self.state, "error": ""})
        self._last_cmd = 0.0  # neue Sitzung: Kommandodrossel gilt je Verbindung
        await self._cmd_queue.put("/SHOW USER")
        self._disconnected = asyncio.Event()
        self._last_rx = time.time()
        reader_task = asyncio.create_task(self._reader_loop())
        roster_task = asyncio.create_task(self._roster_loop())
        try:
            while not self._stop:
                # auf nächstes Kommando ODER Verbindungsabbruch warten – sonst würde die Sitzung nach einem
                # Internetausfall ewig auf ein Kommando warten und sich nie neu verbinden
                get_task = asyncio.create_task(self._cmd_queue.get())
                dead_task = asyncio.create_task(self._disconnected.wait())
                done, _ = await asyncio.wait({get_task, dead_task}, return_when=asyncio.FIRST_COMPLETED)
                if dead_task in done:
                    get_task.cancel()
                    raise ConnectionError(self.error or "Verbindung verloren")
                dead_task.cancel()
                cmd = get_task.result()
                wait = 61 - (time.time() - self._last_cmd)
                if wait > 0:
                    await asyncio.sleep(wait)
                if self.state != "verbunden":
                    break
                self._in_roster = cmd.upper().startswith("/SHOW US")
                self.writer.write((cmd + "\r\n").encode())
                await self.writer.drain()
                self._last_cmd = time.time()
        finally:
            reader_task.cancel()
            roster_task.cancel()
            try:
                self.writer.close()
            except Exception:  # noqa: BLE001
                pass

    _in_roster = False
    _roster_buf: dict[str, dict]
    ROSTER_INTERVAL = int(os.environ.get("CONTESTLOGGER_KST_ROSTER_SEC", "600"))  # Nutzerliste alle 10 min -> Stationsdatenbank wächst automatisch

    async def _roster_loop(self) -> None:
        while not self._stop:
            await asyncio.sleep(min(self.ROSTER_INTERVAL, 30))
            if self.state != "verbunden":
                continue
            # Wächter: kommt deutlich länger als ein Abfrage-Intervall nichts mehr vom Server, gilt die
            # Verbindung als tot (stiller Ausfall ohne TCP-Reset, z. B. Router/Internet weg)
            if time.time() - self._last_rx > self.ROSTER_INTERVAL + 180:
                self.error = "keine Antwort vom Server – verbinde neu"
                self._mark_dead()
                continue
            if time.time() - self._last_cmd >= self.ROSTER_INTERVAL and self._cmd_queue.empty():
                await self._cmd_queue.put("/SHOW USER")

    def _mark_dead(self) -> None:
        self.state = "getrennt"
        if self.writer:
            try:
                self.writer.close()
            except Exception:  # noqa: BLE001
                pass
        if self._disconnected:
            self._disconnected.set()

    async def _reader_loop(self) -> None:
        self._roster_buf = {}
        while True:
            try:
                raw = await self.reader.readline()  # type: ignore[union-attr]
            except Exception as e:  # noqa: BLE001  (ConnectionReset, OSError bei Netzausfall)
                raw = b""
                self.error = str(e) or "Verbindung verloren"
            if not raw:
                self.error = self.error or "Verbindung geschlossen"
                await self._emit({"type": "kst_status", "state": "getrennt", "error": self.error})
                self._mark_dead()
                return
            self._last_rx = time.time()
            line = raw.decode("latin-1", "replace").rstrip("\r\n")
            await self._handle_line(line)

    async def _handle_line(self, line: str) -> None:
        if not line.strip():
            return
        if PROMPT_RE.match(line.strip()):
            if self._in_roster and self._roster_buf:
                self.users = self._roster_buf
                self._roster_buf = {}
                self._in_roster = False
                await self._emit({"type": "kst_users", "users": list(self.users.values())})
            return
        msg = parse_message(line)
        if msg and msg["call"] in SYSTEM_SENDERS:
            return  # Systemmeldungen des Chat-Servers (ON4KST) nicht als Nachricht führen
        if msg:
            msg["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            msg["own"] = msg["call"] == self.user
            msg["to_me"] = bool(msg["to"] and msg["to"] in self.my_calls) or any(c in self.my_calls for c in CALL_IN_TEXT.findall(msg["text"].upper()))
            u = self.users.get(msg["call"])
            msg["locator"] = u["locator"] if u else ""
            self.messages.append(msg)
            del self.messages[:-800]
            await self._emit({"type": "kst", "msg": msg})
            return
        user = parse_user(line)
        if user and (self._in_roster or user["call"] in self.users):
            self._roster_buf[user["call"]] = user
            if not self._in_roster:
                self.users[user["call"]] = user
            return
        if "Please wait" in line:
            self._last_cmd = time.time()
        await self._emit({"type": "kst_raw", "line": line})
