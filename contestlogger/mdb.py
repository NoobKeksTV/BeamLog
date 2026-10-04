"""Access-/Jet-Datenbanken (WinContest *.mdb) rein in Python lesen.

Jet4-Dateien sind standardmäßig „verschlüsselt“ (RC4 je Seite mit einem Schlüssel aus Seite 0,
so wie mdbtools es handhabt). Nach dem Entschlüsseln übernimmt der gebündelte access_parser
(Apache 2.0, ClarotyICS) das Auslesen der Tabellen – damit funktioniert der MDB-Import ohne
mdbtools, auch in der portablen Windows-Version.
"""
from __future__ import annotations

import struct
import tempfile
from pathlib import Path

JET4_PAGE = 4096
JET3_PAGE = 2048
PAGE0_KEY = bytes([0xC7, 0xDA, 0x39, 0x6B])


def rc4(key: bytes, data: bytes) -> bytes:
    S = list(range(256))
    j = 0
    kl = len(key)
    for i in range(256):
        j = (j + S[i] + key[i % kl]) & 0xFF
        S[i], S[j] = S[j], S[i]
    out = bytearray(len(data))
    i = j = 0
    for n, b in enumerate(data):
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        out[n] = b ^ S[(S[i] + S[j]) & 0xFF]
    return bytes(out)


def decrypt_mdb(data: bytes) -> bytes:
    """Liefert die entschlüsselte Datei (unverändert, wenn nicht verschlüsselt)."""
    if len(data) < 0x100 or data[:4] != b"\x00\x01\x00\x00":
        raise ValueError("Keine Access-Datenbank")
    jet3 = data[0x14] == 0
    page = JET3_PAGE if jet3 else JET4_PAGE
    head_len = 126 if jet3 else 128
    page0 = bytearray(data[:page])
    page0[0x18:0x18 + head_len] = rc4(PAGE0_KEY, bytes(page0[0x18:0x18 + head_len]))
    db_key = struct.unpack_from("<I", page0, 0x3E)[0]
    out = bytearray(data)
    out[:page] = page0
    if db_key:
        for pg in range(1, (len(data) + page - 1) // page):
            key = struct.pack("<I", db_key ^ pg)
            start = pg * page
            out[start:start + page] = rc4(key, bytes(data[start:start + page]))
    return bytes(out)


def read_tables(data: bytes) -> dict[str, dict[str, list]]:
    """Alle Benutzertabellen als {Tabelle: {Spalte: [Werte…]}}."""
    from .vendor.access_parser import AccessParser
    plain = decrypt_mdb(data)
    with tempfile.NamedTemporaryFile(suffix=".mdb", delete=False) as fh:
        fh.write(plain)
        path = fh.name
    try:
        db = AccessParser(path)
        out: dict[str, dict[str, list]] = {}
        for name in list(db.catalog.keys()):
            if name.startswith("MSys"):
                continue
            try:
                out[name] = db.parse_table(name)
            except Exception:  # noqa: BLE001 – defekte/leere Tabelle überspringen
                continue
        return out
    finally:
        Path(path).unlink(missing_ok=True)
