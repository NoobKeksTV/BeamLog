"""Aktionsprotokoll: jede ändernde API-Anfrage (POST/PATCH/DELETE) wird mit Nutzer, Admin-Status,
Aktion, Ergebnis und einer gekürzten, passwortfreien Zusammenfassung der Daten festgehalten."""
from __future__ import annotations

import json
import re
from typing import Callable

# (Methode, Pfad-Muster) -> Beschreibung; {sid}/{cid}/{qid} werden aus dem Pfad übernommen
ACTIONS: list[tuple[str, str, str]] = [
    ("POST", r"/api/setup$", "Admin-Passwort festgelegt (Ersteinrichtung)"),
    ("POST", r"/api/admin/login$", "Admin-Anmeldung"),
    ("POST", r"/api/admin/password$", "Admin-Passwort geändert"),
    ("POST", r"/api/settings$", "Einstellungen geändert"),
    ("POST", r"/api/lookup/test$", "Rufzeichen-Abfrage getestet"),
    ("POST", r"/api/contests$", "Contest angelegt"),
    ("POST", r"/api/templates$", "Globale Station angelegt"),
    ("PATCH", r"/api/templates/(?P<tid>\d+)$", "Globale Station {tid} geändert"),
    ("DELETE", r"/api/templates/(?P<tid>\d+)$", "Globale Station {tid} gelöscht"),
    ("POST", r"/api/contests/(?P<cid>\d+)/stations/from_template$", "Station aus globaler Station in Contest {cid} aufgenommen"),
    ("POST", r"/api/callbook/sync_repo$", "Stationsdatenbank aus dem Repo abgeglichen"),
    ("POST", r"/api/update/check$", "Update-Prüfung"),
    ("POST", r"/api/update/apply$", "Update eingespielt"),
    ("PATCH", r"/api/contests/(?P<cid>\d+)$", "Contest {cid} geändert"),
    ("DELETE", r"/api/contests/(?P<cid>\d+)$", "Contest {cid} gelöscht"),
    ("POST", r"/api/contests/(?P<cid>\d+)/stations$", "Station in Contest {cid} angelegt"),
    ("PATCH", r"/api/stations/(?P<sid>\d+)$", "Station {sid} geändert"),
    ("DELETE", r"/api/stations/(?P<sid>\d+)$", "Station {sid} gelöscht"),
    ("POST", r"/api/stations/(?P<sid>\d+)/unlock$", "Station {sid} freigeschaltet"),
    ("POST", r"/api/stations/(?P<sid>\d+)/serial$", "Seriennummer Station {sid} gesetzt"),
    ("POST", r"/api/stations/(?P<sid>\d+)/qsos$", "QSO geloggt (Station {sid})"),
    ("PATCH", r"/api/qsos/(?P<qid>\d+)$", "QSO {qid} geändert"),
    ("DELETE", r"/api/qsos/(?P<qid>\d+)$", "QSO {qid} gelöscht"),
    ("POST", r"/api/stations/(?P<sid>\d+)/cw$", "CW-Text gesendet (Station {sid})"),
    ("POST", r"/api/backups$", "Backup manuell ausgelöst"),
    ("POST", r"/api/callbook$", "Stationsdatenbank: Eintrag bearbeitet"),
    ("DELETE", r"/api/callbook/(?P<call>[^/]+)$", "Stationsdatenbank: {call} gelöscht"),
    ("POST", r"/api/import$", "Datei importiert"),
    ("POST", r"/api/import/folder$", "Ordner importiert"),
    ("POST", r"/api/import/results$", "Ergebnisliste importiert"),
    ("POST", r"/api/darc/import$", "DARC-Ergebnislisten importiert"),
    ("POST", r"/api/kst/start$", "KST verbunden"),
    ("POST", r"/api/kst/stop$", "KST getrennt"),
    ("POST", r"/api/kst/send$", "KST-Nachricht gesendet"),
    ("POST", r"/api/kst/broadcast$", "KST-Rundruf gesendet"),
    ("POST", r"/api/kst/refresh_users$", "KST-Nutzerliste angefordert"),
    ("POST", r"/api/kst/rundruf_texts$", "Rundruf-Texte gespeichert"),
    ("POST", r"/api/lang/(?P<code>[^/]+)$", "Sprache {code} gespeichert"),
]
SKIP = (re.compile(r"/api/aircraft$"), re.compile(r"/api/tiles/status$"), re.compile(r"/api/stations/\d+/rig$"), re.compile(r"/api/stations/\d+/cw/next$"), re.compile(r"/api/kst/seen$"))
SECRET_KEYS = ("pass", "password", "token", "secret", "kst_pass", "lookup_pass")


def describe(method: str, path: str) -> str:
    for m, pat, label in ACTIONS:
        if m == method:
            mo = re.match(pat, path)
            if mo:
                return label.format(**mo.groupdict())
    return f"{method} {path}"


def summarize(body: bytes, content_type: str) -> str:
    if not body:
        return ""
    if content_type.startswith("multipart/"):
        names = re.findall(rb'filename="([^"]*)"', body)
        return f"{len(names)} Datei(en): " + ", ".join(n.decode("utf-8", "replace") for n in names[:5]) if names else "Formulardaten"
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return body[:200].decode("utf-8", "replace")
    if isinstance(data, dict):
        clean = {}
        for k, v in data.items():
            if any(s in k.lower() for s in SECRET_KEYS):
                clean[k] = "***" if v else ""
            elif isinstance(v, (list, dict)):
                clean[k] = f"[{len(v)}]"
            else:
                clean[k] = v
        return json.dumps(clean, ensure_ascii=False)[:400]
    return json.dumps(data, ensure_ascii=False)[:400]


class AuditMiddleware:
    """Reines ASGI-Middleware: liest den Body mit (max. 64 KB), merkt sich den Status und protokolliert danach."""

    def __init__(self, app, record: Callable[..., None], is_admin: Callable[[str | None], bool]):
        self.app, self.record, self.is_admin = app, record, is_admin

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PATCH", "DELETE", "PUT") or not scope["path"].startswith("/api/") \
                or any(p.match(scope["path"]) for p in SKIP):
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        chunks: list[bytes] = []
        total = 0

        async def rx():
            nonlocal total
            msg = await receive()
            if msg["type"] == "http.request":
                b = msg.get("body", b"")
                if total < 65536:
                    chunks.append(b[: 65536 - total])
                total += len(b)
            return msg

        status = {"code": 0}

        async def sx(msg):
            if msg["type"] == "http.response.start":
                status["code"] = msg["status"]
            await send(msg)

        try:
            await self.app(scope, rx, sx)
        finally:
            try:
                nick = headers.get("x-nick", "").strip()[:24]
                admin = self.is_admin(headers.get("x-admin-token"))
                path = scope["path"]
                details = summarize(b"".join(chunks), headers.get("content-type", ""))
                self.record(describe(scope["method"], path), details=details, nick=nick or ("Admin" if admin else ""), admin=admin,
                            method=scope["method"], path=path, status=status["code"] or 500)
            except Exception:  # noqa: BLE001
                pass
