# ContestLogger – Arbeitsregeln (vom Auftraggeber festgelegt)

- **Eine Version pro Session.** Kommen mehrere Wünsche hintereinander, werden sie gesammelt umgesetzt und am Ende
  der Session als **ein** Release veröffentlicht (nicht pro Wunsch eine Version). Zwischendurch nur committen und pushen.
- **Release-Notes auf GitHub** enthalten immer die Änderungen und die Commit-Historie seit dem letzten Release.
  Das macht der Workflow automatisch über `build_tools/release_notes.py` (Commit-Betreff + -Text, Commit-Liste, Vergleichslink).
  Deshalb aussagekräftige Commit-Nachrichten schreiben: Betreff = was sich für den Nutzer ändert, Body = Details als Liste.
- Versionsnummer in `contestlogger/__init__.py` je Release erhöhen; sie erscheint in der Oberfläche. Copyright: Lars Hölker.
- Immer auf `main` pushen (zusätzlich zum Feature-Branch). Release-Build über `workflow_dispatch` des Workflows „Portable Builds“.
- Vor dem Push: `python -m pytest -q` muss grün sein; Oberflächenänderungen mit Playwright gegen einen lokalen Server prüfen
  (Fake-KST-Server: `tests/fake_kst.py`, Umgebungsvariablen `CONTESTLOGGER_KST_HOST/PORT`).
