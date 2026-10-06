"""Wertung je Contest: Punkte je QSO und optionaler Multiplikator.

Die Wertung steht als Zeichenkette im Contest (Spalte `scoring`):
    km                  1 Punkt je km (IARU-Region-1-/DARC-UKW-Contest), Standard
    fix1 / fix2 / fix3  fester Wert je QSO
    …*squares           × Anzahl der gearbeiteten Großfelder (JO31 …)
    …*doks              × Anzahl der verschiedenen DOKs/OVs (z. B. Köln-Aachen-Contest)
    …*squares_doks      × (Großfelder + DOKs)
Beispiele: "km", "km*squares", "fix1*doks".
"""
from __future__ import annotations

import re

MULTS = ("", "squares", "doks", "squares_doks")
_RE = re.compile(r"^(km|fix(\d{1,3}))(?:\*(squares|doks|squares_doks))?$")


def parse(scoring: str | None) -> dict:
    m = _RE.match((scoring or "km").strip().lower())
    if not m:
        return {"points": "km", "fixed": 0, "mult": "", "key": "km"}
    points = "fix" if m.group(1).startswith("fix") else "km"
    fixed = int(m.group(2)) if m.group(2) else 0
    mult = m.group(3) or ""
    return {"points": points, "fixed": fixed, "mult": mult, "key": m.group(0)}


def normalize(scoring: str | None) -> str:
    return parse(scoring)["key"]


def qso_points(scoring: str | None, km: int, locator: str, dupe: bool = False) -> int:
    """Punkte eines einzelnen QSOs (Dupes zählen 0)."""
    if dupe:
        return 0
    p = parse(scoring)
    if p["points"] == "fix":
        return p["fixed"]
    return km if km > 0 else (1 if locator else 0)


def multiplier(scoring: str | None, squares: int, doks: int) -> int | None:
    """Multiplikator laut Wertung oder None, wenn die Wertung keinen hat."""
    mult = parse(scoring)["mult"]
    if not mult:
        return None
    n = (squares if "squares" in mult else 0) + (doks if "doks" in mult else 0)
    return max(1, n) if n else 0


def total(scoring: str | None, sum_points: int, squares: int, doks: int) -> dict:
    """Gesamtwertung: {score, multiplier}; ohne Multiplikator ist score = sum_points."""
    m = multiplier(scoring, squares, doks)
    if m is None:
        return {"score": int(sum_points), "multiplier": None}
    return {"score": int(sum_points) * m, "multiplier": m}


def label(scoring: str | None) -> str:
    p = parse(scoring)
    base = "1 Punkt je km" if p["points"] == "km" else f"{p['fixed']} Punkt{'e' if p['fixed'] != 1 else ''} je QSO"
    mult = {"": "", "squares": " × Großfelder", "doks": " × DOKs", "squares_doks": " × (Großfelder + DOKs)"}[p["mult"]]
    return base + mult
