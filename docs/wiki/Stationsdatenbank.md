# Stationsdatenbank (Callbuch)

![Stationsdatenbank in der Verwaltung](img/stationsdatenbank.png)

Die Stationsdatenbank ordnet Rufzeichen einem Locator (und ggf. Namen) zu. Sie liefert die Vorschläge und die Locator-Vorbelegung beim Loggen, die Plausibilitätshinweise und die Kandidaten für den Rundruf.

## Woher die Einträge kommen

| Quelle | Wann |
|---|---|
| Startdatenbank | Beim ersten Start wird `contestlogger/seed/stationsdatenbank.csv` geladen. |
| Eigene QSOs | Jedes geloggte QSO (auch importierte Logs). |
| KST-Nutzerliste | Alle 10 Minuten je Verbindung; jeder Nutzer mit Locator. |
| Ergebnislisten / DARC-Hub | Importe in der Verwaltung. |
| HamQTH / QRZ | Online-Abfrage beim Loggen und in der Log-Prüfung (Ergebnis wird gespeichert). |
| Von Hand | Formular unter der Tabelle in der Verwaltung. |
| Repo-Abgleich | „Nach neuen suchen (Repo)“, siehe unten. |

Regeln: Der neueste Locator wird zum Hauptlocator, ältere wandern in „weitere Standorte“ (bis zu 5) und erscheinen im Logger zur Auswahl. Zusätze wie `/P`, `-2` oder `-23CM` werden entfernt, das Rufzeichen wird als Kern (`DN2LH`) gespeichert.

## Export

- **Stationsdatenbank exportieren (CSV)**: alle Spalten (Call, Locator, Name, QSOs, Zuletzt, weitere Locator).
- **Export im Repo-Format**: `Call;Locator;Zuletzt` – genau das Format der Startdatenbank im Repo.

## Abgleich mit dem Repo

Ablauf für ein Team mit mehreren Installationen:

1. Auf dem Server mit der vollständigsten Datenbank „Export im Repo-Format“ herunterladen.
2. Die Datei als `contestlogger/seed/stationsdatenbank.csv` ins Repo einchecken.
3. Auf den anderen Installationen „Nach neuen suchen (Repo)“ klicken: der Server lädt die Datei über die GitHub-API und übernimmt neue Rufzeichen und geänderte Locator. Das Ergebnis („324 Einträge im Repo: 12 neu, 3 Locator aktualisiert“) erscheint daneben und im Aktionsprotokoll.

Die URL lässt sich ändern, z. B. auf einen eigenen Webserver. Das Repo ist öffentlich; nur für einen privaten Fork wird ein GitHub-Token mit Lesezugriff gebraucht, das als `GITHUB_TOKEN` in `contestlogger.env` steht (nicht in der Oberfläche).
