"""Release-Notes aus der Git-Historie: Änderungen (Commit-Texte) und Commit-Liste seit dem letzten Release-Tag.

Aufruf: python build_tools/release_notes.py v1.2.3  > RELEASE_NOTES.md
"""
from __future__ import annotations

import re
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, encoding="utf-8", errors="replace", check=False).stdout.strip()


# Reine Versions-/Protokoll-Commits sagen dem Nutzer nichts – nicht in die Notizen
_SKIP_SUBJECT = re.compile(r"^(Version \d|Änderungsprotokoll|Release v?\d|Bump version)", re.I)


def _body_item(ln: str) -> str:
    """Body-Zeile als Unterpunkt: „- Text“ bleibt Aufzählung, Fortsetzungszeilen werden angehängt."""
    return ln.strip()


def commits_between(a: str, b: str) -> list[tuple[str, str, list[str]]]:
    rng = f"{a}..{b}" if a else b
    raw = git("log", rng, "--no-merges", "--format=%H%x1f%h%x1f%s%x1f%b%x1e")
    out = []
    for rec in raw.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        full, short, subject, body = (rec.split("\x1f") + ["", "", "", ""])[:4]
        if _SKIP_SUBJECT.match(subject.strip()):
            continue
        body_lines = [ln.rstrip() for ln in body.splitlines() if ln.strip() and not re.match(r"^(Co-Authored-By|Claude-Session|Signed-off-by):", ln.strip())]
        out.append((short, subject.strip(), body_lines))
    return out


def changelog(current_version: str = "") -> str:
    """Komplettes Änderungsprotokoll über alle Tags (neueste zuerst) – wird als contestlogger/CHANGELOG.md mitgeliefert."""
    tags = [t for t in git("tag", "--list", "v*", "--sort=-v:refname").splitlines() if t]
    out = ["# Änderungsprotokoll", ""]
    head_tag = f"v{current_version}" if current_version and f"v{current_version}" not in tags else ""
    seq = ([head_tag] if head_tag else []) + tags
    for i, tag in enumerate(seq):
        prev = seq[i + 1] if i + 1 < len(seq) else ""
        ref = "HEAD" if tag == head_tag else tag
        date = git("log", "-1", "--format=%cs", ref)
        cs = commits_between(prev, ref)
        if not cs and tag != head_tag:
            continue
        out.append(f"## {tag} ({date})")
        for short, subject, body in cs:
            out.append(f"- {subject}")
            for ln in body:
                # Unterpunkte („- …“) eingerückt, Fortsetzungszeilen an den letzten Unterpunkt
                out.append(f"  {ln.strip()}" if ln.strip().startswith("- ") else f"    {ln.strip()}")
        out.append("")
    return "\n".join(out)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows-Runner: Umlaute nicht als cp1252 ausgeben
    if len(sys.argv) > 1 and sys.argv[1] == "--changelog":
        print(changelog(sys.argv[2] if len(sys.argv) > 2 else ""))
        return
    new_tag = sys.argv[1] if len(sys.argv) > 1 else ""
    tags = [t for t in git("tag", "--list", "v*", "--sort=-v:refname").splitlines() if t and t != new_tag]
    prev = tags[0] if tags else ""
    rng = f"{prev}..HEAD" if prev else "HEAD"
    raw = git("log", rng, "--no-merges", "--format=%H%x1f%h%x1f%s%x1f%b%x1e")
    commits = []
    for rec in raw.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        full, short, subject, body = (rec.split("\x1f") + ["", "", "", ""])[:4]
        if _SKIP_SUBJECT.match(subject.strip()):
            continue  # Versions-/Protokoll-Commits nicht in die Release-Notes
        # Signatur-/Session-Zeilen aus dem Body entfernen
        body_lines = [ln.rstrip() for ln in body.splitlines() if ln.strip() and not re.match(r"^(Co-Authored-By|Claude-Session|Signed-off-by):", ln.strip())]
        commits.append((short, subject.strip(), body_lines))

    out = ["Portable Versionen (kein Python nötig): ZIP entpacken, `ContestLogger.exe` bzw. `./ContestLogger` starten. Siehe START.txt im Paket.", ""]
    out.append(f"## Änderungen{' seit ' + prev if prev else ''}")
    if not commits:
        out.append("- (keine Änderungen seit dem letzten Release)")
    for short, subject, body_lines in commits:
        out.append(f"- **{subject}**")
        for ln in body_lines:
            out.append(f"  {ln.strip()}" if ln.strip().startswith("- ") else f"    {ln.strip()}")
    out.append("")
    out.append("## Commit-Historie")
    for short, subject, _ in commits:
        out.append(f"- `{short}` {subject}")
    if prev:
        repo = git("config", "--get", "remote.origin.url")
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", repo)
        if m:
            out.append("")
            out.append(f"Vollständiger Vergleich: https://github.com/{m.group(1)}/compare/{prev}...{new_tag or 'HEAD'}")
    print("\n".join(out))


if __name__ == "__main__":
    main()
