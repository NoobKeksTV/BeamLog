"""Externe Rufzeichen-Abfrage (optional, braucht Internet): HamQTH oder QRZ.com.

Liefert Locator, Name und QTH zu einem vollständigen Rufzeichen. Ergebnisse werden
vom Aufrufer in der Stationsdatenbank gecacht, damit jede Abfrage nur einmal nötig ist.
"""
from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import geo, prefixes

TIMEOUT = 5.0
PROVIDERS = {"none": "aus", "hamqth": "HamQTH", "qrz": "QRZ.com (XML-Abo)"}


class LookupError_(Exception):
    pass


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ContestLogger"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _text(root: ET.Element, tag: str) -> str:
    for el in root.iter():
        if el.tag.split("}")[-1].lower() == tag.lower() and el.text:
            return el.text.strip()
    return ""


class Lookup:
    def __init__(self, provider: str, user: str, password: str):
        self.provider = provider if provider in PROVIDERS else "none"
        self.user, self.password = user, password
        self._session: str = ""
        self._session_ts = 0.0

    @property
    def enabled(self) -> bool:
        return self.provider != "none" and bool(self.user and self.password)

    # ------------------------------------------------------------ HamQTH
    def _hamqth_session(self) -> str:
        if self._session and time.time() - self._session_ts < 50 * 60:
            return self._session
        url = f"https://www.hamqth.com/xml.php?u={urllib.parse.quote(self.user)}&p={urllib.parse.quote(self.password)}"
        root = ET.fromstring(_get(url))
        sid = _text(root, "session_id")
        if not sid:
            raise LookupError_(_text(root, "error") or "HamQTH: Anmeldung fehlgeschlagen")
        self._session, self._session_ts = sid, time.time()
        return sid

    def _hamqth(self, call: str) -> dict:
        sid = self._hamqth_session()
        root = ET.fromstring(_get(f"https://www.hamqth.com/xml.php?id={sid}&callsign={urllib.parse.quote(call)}&prg=ContestLogger"))
        err = _text(root, "error")
        if err:
            if "session" in err.lower():
                self._session = ""
                return self._hamqth(call)
            return {}
        return {"locator": _text(root, "grid"), "name": _text(root, "nick") or _text(root, "name"), "qth": _text(root, "qth"), "country": _text(root, "country")}

    # ------------------------------------------------------------ QRZ.com
    def _qrz_session(self) -> str:
        if self._session and time.time() - self._session_ts < 50 * 60:
            return self._session
        url = f"https://xmldata.qrz.com/xml/current/?username={urllib.parse.quote(self.user)}&password={urllib.parse.quote(self.password)}&agent=ContestLogger"
        root = ET.fromstring(_get(url))
        key = _text(root, "Key")
        if not key:
            raise LookupError_(_text(root, "Error") or "QRZ: Anmeldung fehlgeschlagen")
        self._session, self._session_ts = key, time.time()
        return key

    def _qrz(self, call: str) -> dict:
        key = self._qrz_session()
        root = ET.fromstring(_get(f"https://xmldata.qrz.com/xml/current/?s={key}&callsign={urllib.parse.quote(call)}"))
        err = _text(root, "Error")
        if err:
            if "session" in err.lower() or "invalid" in err.lower() and "key" in err.lower():
                self._session = ""
                return self._qrz(call)
            return {}
        name = " ".join(x for x in (_text(root, "fname"), _text(root, "name")) if x)
        return {"locator": _text(root, "grid"), "name": _text(root, "nickname") or name, "qth": _text(root, "addr2"), "country": _text(root, "country")}

    # ------------------------------------------------------------ öffentlich
    def lookup(self, call: str) -> dict:
        """Gibt {} zurück, wenn nichts gefunden; wirft LookupError_ bei Verbindungs-/Loginproblemen."""
        core = prefixes.core_call(call)
        if not self.enabled or not prefixes.is_plausible_call(core):
            return {}
        try:
            res = self._hamqth(core) if self.provider == "hamqth" else self._qrz(core)
        except (OSError, ET.ParseError) as e:
            raise LookupError_(f"{PROVIDERS[self.provider]}: {e}") from e
        loc = geo.normalize_locator(res.get("locator", ""))
        if loc and not geo.is_valid_locator(loc):
            loc = loc[:6] if geo.is_valid_locator(loc[:6]) else ""
        res["locator"] = loc
        res["source"] = self.provider
        return res if (loc or res.get("name")) else {}

    def test(self) -> str:
        """Verbindungstest: Anmeldung + Abfrage des eigenen Rufzeichens."""
        if not self.enabled:
            return "Keine Zugangsdaten eingetragen."
        call = self.user if re.match(r"^[A-Z0-9/]{3,}$", self.user.upper()) else "DL1ABC"
        res = self.lookup(call)
        return f"OK – {PROVIDERS[self.provider]} antwortet. {call}: {res.get('locator') or '?'} {res.get('name') or ''}".strip()
