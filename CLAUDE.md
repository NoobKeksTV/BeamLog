# BeamLog – Arbeitsregeln (vom Auftraggeber festgelegt)

- **Branches: Gearbeitet wird ausschließlich im Branch `development`.** Alle Commits und Pushes gehen nur dorthin
  (`git push -u origin development`). **`main` ist der öffentliche, veröffentlichte Stand und wird nicht angefasst:**
  nichts direkt auf `main` committen oder pushen, nichts automatisch nach `main` mergen. `main` wird erst zum nächsten
  festen Release aktualisiert – und nur, wenn der Auftraggeber das ausdrücklich verlangt.

- **Releases nur auf ausdrücklichen Wunsch.** Wünsche werden in `development` gesammelt umgesetzt und nur committet
  und gepusht. Ein Release (Version erhöhen, nach `main` bringen, Build starten) gibt es erst, wenn der Auftraggeber es verlangt.
- **Release-Notes auf GitHub** enthalten immer die Änderungen und die Commit-Historie seit dem letzten Release.
  Das macht der Workflow automatisch über `build_tools/release_notes.py` (Commit-Betreff + -Text, Commit-Liste, Vergleichslink).
  Deshalb aussagekräftige Commit-Nachrichten schreiben: Betreff = was sich für den Nutzer ändert, Body = Details als Liste.
- Versionsnummer in `contestlogger/__init__.py` je Release erhöhen; sie erscheint in der Oberfläche. Copyright: Lars Hölker.
- Release-Build über `workflow_dispatch` des Workflows „Portable Builds“ – nur für ein vom Auftraggeber freigegebenes Release von `main`.
  Testbuilds aus `development` nicht als Release veröffentlichen.
- Vor dem Push: `python -m pytest -q` muss grün sein; Oberflächenänderungen mit Playwright gegen einen lokalen Server prüfen
  (Fake-KST-Server: `tests/fake_kst.py`, Umgebungsvariablen `BEAMLOG_KST_HOST/PORT`).
- **Git-Commits immer unter dem Account des Auftraggebers:** Autor `NoobKeksTV <zockerboyshd@outlook.de>`
  (`git config user.name "NoobKeksTV" && git config user.email "zockerboyshd@outlook.de"`), Signierung aus
  (`git config commit.gpgsign false`), **keine** „Co-Authored-By“- oder „Claude-Session“-Zeilen in Commit-Nachrichten,
  keine Signaturschlüssel vorgeben oder erfragen. Kein Claude-Feature-Branch – nur `development`.
