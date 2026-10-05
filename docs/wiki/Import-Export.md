# Import und Export

Alles in der Verwaltung (Admin).

![Import-Karten in der Verwaltung](img/import.png)

## WinContest-Ordner (DD3KU) übernehmen

Den kompletten Ordner von WinContest auswählen (z. B. `D:\Contest`). Übernommen werden alle Logs aus `Datenbank/*.mdb` und `*.txt`, `DD3KU/*.EXP`, `Auswertung/*.edi` und `ADIF/*.adi` als archivierte Contests; jedes Rufzeichen mit Locator landet in der Stationsdatenbank. Dasselbe Log in mehreren Dateien wird nur einmal übernommen.

- `.mdb`-Dateien werden rein in Python gelesen, auch verschlüsselte Jet4-Datenbanken – keine Zusatzsoftware nötig.
- `Contest.dat` (DD3KUs verschlüsselte Stationsdatenbank) kann nicht gelesen werden; die mitgelieferte Startdatenbank und die DARC-Ergebnislisten ersetzen sie.
- Das Ergebnis zeigt zuerst die Gesamtzahlen (Dateien, Contests, QSOs, Rufzeichen neu/bekannt), Details je Datei ausklappbar.

Kommandozeile: `ContestLogger-Import "D:\Contest" --db data\contestlogger.db`.

## Einzelne Datei importieren

EDI (Spalte „Exchange received“), ADIF (`DARC_DOK`, `SRX_STRING`) und Call-Listen mit DOK-Spalte bringen den DOK/OV mit; er landet im QSO und in der Stationsdatenbank.


WinContest `.txt`/`.EXP`/`.mdb`, EDI/REG1TEST, ADIF oder Call-Listen (`Call;Locator;Name`). Ziel: neuer Contest, bestehende Station oder nur die Stationsdatenbank.

## Ergebnislisten (DARC / IARU / UKW-Contest-Club)

Veröffentlichte Ergebnislisten enthalten Rufzeichen und Locator aller Teilnehmer. Datei (HTML, PDF, TXT, CSV), eingefügter Text oder die URL der Ergebnisseite; vor der Übernahme gibt es eine Vorschau.

## DARC-Contest-Hub direkt laden

Lädt die offiziellen `result.csv`-Dateien vom DARC-Contest-Hub (`dxhf2.darc.de`) für ein Jahr oder alle Jahre seit 2017 – pro Contest 500–900 Rufzeichen mit Locator, dazu die ODX-Gegenstationen. Braucht Internet auf dem Server.

## Export / Abgabe

![Export / Abgabe](img/export.png)

Verwaltung → **Export / Abgabe** (je Contest):

| Knopf | Ergebnis |
|---|---|
| EDI (mit Prüfung) | REG1TEST-Datei der Station/des Bandes für die Abgabe. Vorher läuft die [Log-Prüfung](Log-Pruefung.md); mit Fehlern exportiert nur der Admin nach Rückfrage. |
| ADIF | Alle QSOs der Station als ADIF (mit Frequenz, wenn CAT lief; DOK als `DARC_DOK`/`SRX_STRING`). |
| CSV | Tabelle. |
| Alle Bänder als EDI-ZIP | Die EDI-Dateien aller geprüften Stationen des Contests; nicht bestandene Logs stehen in `NICHT_EXPORTIERT.txt`. |

Der EDI-Kopf nimmt die Angaben aus der Station (Wertungsgruppe, Club, Verantwortlicher, Technik). Jeder Export steht im Aktionsprotokoll.

## Stationsdatenbank

Export als CSV, Export im Repo-Format und Abgleich mit dem Repo: siehe [Stationsdatenbank](Stationsdatenbank.md).
