#!/usr/bin/env python3
"""Importiert einen kompletten WinContest-Ordner (DD3KU) in BeamLog.

    python tools/import_dd3ku.py /pfad/zu/Contest            # alles importieren
    python tools/import_dd3ku.py /pfad/zu/Contest --callbook-only
    python tools/import_dd3ku.py /pfad/zu/Contest --db data/beamlog.db

Gelesen werden Datenbank/*.mdb (falls mdbtools installiert) bzw. Datenbank/*.txt,
DD3KU/*.EXP, Auswertung/**/*.edi und ADIF/*.adi. Jede Log-Datei wird zu einem
archivierten Contest mit einer Station; alle Rufzeichen + Locator wandern ins
Call-Buch. Bereits vorhandene QSOs (gleiches Rufzeichen + Zeit) werden übersprungen.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contestlogger import importers  # noqa: E402
from contestlogger.db import Database  # noqa: E402
from contestlogger.prefixes import core_call  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--db", default="data/beamlog.db")
    ap.add_argument("--callbook-only", action="store_true", help="nur Rufzeichen/Locator lernen, keine Contests anlegen")
    a = ap.parse_args()

    db = Database(a.db)
    files: list[Path] = []
    files += sorted(a.folder.glob("Datenbank/*.mdb")) + sorted(a.folder.glob("Datenbank/*.txt"))
    files += sorted(a.folder.glob("DD3KU/*.EXP")) + sorted(a.folder.glob("DD3KU/*.exp"))
    files += sorted(a.folder.rglob("*.edi")) + sorted(a.folder.rglob("*.EDI"))
    files += sorted(a.folder.glob("ADIF/*.adi")) + sorted(a.folder.glob("ADIF/*.ADI"))
    if not files:
        files = [p for p in a.folder.rglob("*") if p.suffix.lower() in (".mdb", ".txt", ".exp", ".edi", ".adi")]

    seen_logs: set[tuple[str, str]] = set()  # (eigenes Call+Band, erstes QSO) -> gleiche Logs nicht mehrfach anlegen
    for f in files:
        try:
            res = importers.parse_file(f.name, f.read_bytes())
        except ValueError as e:
            print(f"  ! {f}: {e}")
            continue
        if not res.qsos and not res.callbook:
            continue
        for call, loc, name in res.callbook:
            db.learn_call(call, loc, source="import", name=name)
        learned = 0
        for q in res.qsos:
            db.learn_call(q.call, q.locator, source="import", when=q.ts_utc)
            learned += 1
        print(f"  {f.relative_to(a.folder)}: {res.kind}, {len(res.qsos)} QSOs, {learned + len(res.callbook)} Calls gelernt")
        if a.callbook_only or not res.qsos or not res.header.get("locator"):
            continue
        band = res.header.get("band") or res.qsos[0].band or "144MHz"
        first = min(q.ts_utc for q in res.qsos)
        key = (f"{core_call(res.header.get('call', ''))}/{band}", first)
        if key in seen_logs:
            continue
        seen_logs.add(key)
        name = res.header.get("name") or f"{f.stem} ({band})"
        # Existiert bereits ein Contest mit diesem Namen? Dann dort anhängen.
        existing = next((c for c in db.list_contests() if c["name"] == name), None)
        cid = existing["id"] if existing else db.create_contest(name, first, max(q.ts_utc for q in res.qsos))
        if not existing:
            db.update_contest(cid, archived=1)
        st = next((s for s in db.list_stations(cid) if s["band"] == band), None)
        sid = st["id"] if st else db.create_station(cid, res.header.get("call") or "IMPORT", res.header["locator"], band, "SSB", "")
        have = {(q["core_call"], q["ts_utc"]) for q in db.list_qsos(sid)}
        n = 0
        for q in sorted(res.qsos, key=lambda x: x.ts_utc):
            if (core_call(q.call), q.ts_utc) in have:
                continue
            d = q.__dict__.copy()
            d["band"] = d["band"] or band
            try:
                db.add_qso(sid, d, logged_by="import")
                n += 1
            except ValueError as e:
                print(f"    ! {q.call}: {e}")
        print(f"    -> Contest „{name}“, Station #{sid}: {n} neue QSOs")
    print(f"\nCall-Buch enthält jetzt {db.callbook_count()} Rufzeichen.")


if __name__ == "__main__":
    main()
