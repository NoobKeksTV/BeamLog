"""docs/wiki/ ins GitHub-Wiki (eigenes Repo <repo>.wiki.git) übertragen.

Das GitHub-Wiki liest nichts aus dem Hauptrepo – egal wie der Ordner heißt. Quelle bleibt docs/wiki/ (versioniert,
im Repo und in den Release-Paketen lesbar); dieses Skript macht daraus die Wiki-Seiten:
- Seiten-Links „Installation.md#abschnitt“ → „Installation#abschnitt“ (Wiki-Seiten haben keine Endung)
- Bilder (img/) werden mitkopiert und als feste Adresse eingebunden, entfernte Seiten/Bilder im Wiki gelöscht
- _Sidebar.md (Inhaltsverzeichnis aus der Tabelle in Home.md) und _Footer.md werden erzeugt

Aufruf: python build_tools/wiki_sync.py docs/wiki <ausgecheckter-wiki-ordner>
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO = "https://github.com/NoobKeksTV/BeamLog"
RAW = "https://raw.githubusercontent.com/wiki/NoobKeksTV/BeamLog"  # Dateien im Wiki-Repo (Bilder)
LINK = re.compile(r"\]\((?!https?:|mailto:|#)([^)#\s]+)\.md(#[^)\s]*)?\)")


def convert(text: str) -> str:
    """Relative Links auf andere Wiki-Seiten ohne .md (GitHub-Wiki-Schreibweise); Bilder (img/…) als feste Adresse auf
    die Datei im Wiki-Repo – relative Pfade in HTML-<img> zeigt das Wiki sonst nicht an."""
    text = LINK.sub(lambda m: f"]({m.group(1)}{m.group(2) or ''})", text)
    return re.sub(r'(\]\(|src=")(?:\./)?img/', lambda m: f"{m.group(1)}{RAW}/img/", text)


def sidebar(home: str) -> str:
    """Inhaltsverzeichnis aus den Seiten-Links der Tabelle in Home.md (Reihenfolge bleibt)."""
    pages = re.findall(r"^\|\s*\[([^\]]+)\]\(([^)#\s]+)\.md\)", home, re.M)
    lines = ["**[BeamLog-Wiki](Home)**", ""] + [f"- [{title}]({page})" for title, page in pages]
    lines += ["", f"[⬇ Download]({REPO}/releases/latest) · [Quellcode]({REPO})",
              "", "[▶ Video (YouTube)](https://youtu.be/yvYb6FNvjzA) · [🧪 Live-Demo](https://beamlogdemo.lhprinting.de/)"]
    return "\n".join(lines) + "\n"


def sync(src: Path, dst: Path) -> list[str]:
    written: set[Path] = set()
    for f in sorted(src.rglob("*")):
        if f.is_dir():
            continue
        rel = f.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if f.suffix == ".md":
            target.write_text(convert(f.read_text(encoding="utf-8")), encoding="utf-8")
        else:
            shutil.copyfile(f, target)
        written.add(target)
    home = (src / "Home.md").read_text(encoding="utf-8") if (src / "Home.md").exists() else ""
    for name, text in (("_Sidebar.md", sidebar(home)),
                       ("_Footer.md", f"BeamLog – © Lars Hölker (DN2LH) · GNU AGPLv3 · Quelle dieser Seiten: "
                                      f"[docs/wiki im Repo]({REPO}/tree/main/docs/wiki) – Änderungen bitte dort.\n")):
        (dst / name).write_text(text, encoding="utf-8")
        written.add(dst / name)
    removed = []
    for f in sorted(dst.rglob("*")):
        if f.is_file() and ".git" not in f.relative_to(dst).parts and f not in written:
            f.unlink()
            removed.append(str(f.relative_to(dst)))
    return removed


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    gone = sync(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"Wiki übertragen; entfernt: {', '.join(gone) or '–'}")
