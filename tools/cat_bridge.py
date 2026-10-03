#!/usr/bin/env python3
"""CAT-Bridge: meldet die Frequenz des Transceivers an den ContestLogger.

Läuft auf dem Rechner, an dem das Funkgerät hängt. Liest die Frequenz von
Hamlib `rigctld` (TCP, Standard localhost:4532) und schickt sie an den Server;
die Oberfläche zeigt die Frequenz bei der Station an und speichert sie je QSO.

    rigctld -m 3081 -r /dev/ttyUSB0 -s 115200 &        # Beispiel IC-9700 (Linux)
    python tools/cat_bridge.py --server http://192.168.1.10:8000 --station 1 --password 70cm

Unter Windows: rigctld.exe aus dem Hamlib-Paket oder Omni-Rig-kompatible Tools,
die einen rigctld-Port anbieten (z. B. flrig mit --xmlrpc, dann --flrig).
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.request
import xmlrpc.client


def read_rigctld(host: str, port: int) -> tuple[float | None, str]:
    with socket.create_connection((host, port), timeout=3) as s:
        s.sendall(b"f\n")
        freq = s.recv(64).decode().strip().splitlines()[0]
        s.sendall(b"m\n")
        mode = s.recv(64).decode().strip().splitlines()[0]
    try:
        return float(freq) / 1e6, mode
    except ValueError:
        return None, mode


def read_flrig(url: str) -> tuple[float | None, str]:
    rig = xmlrpc.client.ServerProxy(url)
    return float(rig.rig.get_vfo()) / 1e6, str(rig.rig.get_mode())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", required=True, help="z. B. http://192.168.1.10:8000")
    ap.add_argument("--station", type=int, required=True, help="Stations-ID (Verwaltung → Stationen)")
    ap.add_argument("--password", default="", help="Stations-Passwort")
    ap.add_argument("--rigctld", default="localhost:4532", help="Host:Port von rigctld")
    ap.add_argument("--flrig", default="", help="statt rigctld: flrig-XML-RPC-URL, z. B. http://localhost:12345")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--cw", action="store_true", help="CW-Makros (F-Tasten) über rigctld (send_morse) ausgeben")
    a = ap.parse_args()

    base = a.server.rstrip("/")
    req = urllib.request.Request(f"{base}/api/stations/{a.station}/unlock", data=json.dumps({"password": a.password}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        token = json.load(r)["token"]
    print(f"Verbunden mit {base}, Station {a.station}. Strg+C beendet.")
    host, _, port = a.rigctld.partition(":")
    last = None
    next_poll = 0.0
    while True:
        if a.cw:
            # CW-Warteschlange zügig abfragen (alle 0,3 s), Frequenz nur alle --interval Sekunden
            try:
                rq = urllib.request.Request(f"{base}/api/stations/{a.station}/cw/next", headers={"X-Station-Token": token})
                job = json.load(urllib.request.urlopen(rq, timeout=5))
                if job.get("stop"):
                    send_rigctld(host or "localhost", int(port or 4532), "\\stop_morse")
                elif job.get("text"):
                    print(f"CW: {job['text']}")
                    send_rigctld(host or "localhost", int(port or 4532), f"b {job['text']}")
            except (OSError, ValueError) as e:
                print(f"CW-Fehler: {e}", file=sys.stderr)
            if time.time() < next_poll:
                time.sleep(0.3)
                continue
            next_poll = time.time() + a.interval
        try:
            freq, mode = read_flrig(a.flrig) if a.flrig else read_rigctld(host or "localhost", int(port or 4532))
            if (freq, mode) != last:
                body = json.dumps({"freq": freq, "mode": mode}).encode()
                rq = urllib.request.Request(f"{base}/api/stations/{a.station}/rig", data=body, method="POST",
                                            headers={"Content-Type": "application/json", "X-Station-Token": token})
                urllib.request.urlopen(rq, timeout=5).read()
                print(f"{time.strftime('%H:%M:%S')}  {freq:.3f} MHz {mode}" if freq else "keine Frequenz")
                last = (freq, mode)
        except (OSError, ValueError, xmlrpc.client.Error) as e:
            print(f"Fehler: {e}", file=sys.stderr)
            last = None
        if not a.cw:
            time.sleep(a.interval)


def send_rigctld(host: str, port: int, cmd: str) -> None:
    with socket.create_connection((host, port), timeout=3) as s:
        s.sendall((cmd + "\n").encode())
        s.recv(64)


if __name__ == "__main__":
    main()
