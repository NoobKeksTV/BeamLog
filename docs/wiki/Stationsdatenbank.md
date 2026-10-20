# Stationsdatenbank (Callbuch)

![Stationsdatenbank in der Verwaltung](img/stationsdatenbank.png)

Die Stationsdatenbank ordnet Rufzeichen einem Locator, ggf. einem Namen (höchstens 32 Zeichen) und dem **DOK/Ortsverband** zu. Sie liefert die Vorschläge und die Locator-Vorbelegung beim Loggen, die Plausibilitätshinweise und die Kandidaten für den Rundruf.

## Kennzahlen

Über der Tabelle (Verwaltung → Stationsdatenbank & Import) steht, wie viele Rufzeichen die Datenbank kennt und wie viele davon
einen Locator, einen DOK, beides, keins von beiden oder einen Namen haben (mit Anteil in Prozent). „Nach Ländern“ klappt eine
Tabelle auf: je Land (Deutschland zuerst, dann die größten) die Zahl der Stationen und wie viele davon Locator, DOK, beides
oder nichts haben – so sieht man sofort, wo noch Lücken sind.

## Woher die Einträge kommen

| Quelle | Wann |
|---|---|
| Startdatenbank | Beim ersten Start wird `contestlogger/seed/stationsdatenbank.csv` geladen. |
| Eigene QSOs | Jedes geloggte QSO (auch importierte Logs); bei DOK-Contests auch der empfangene DOK. |
| KST-Nutzerliste | Alle 10 Minuten je Verbindung; jeder Nutzer mit Locator. |
| Ergebnislisten / Archiv | Nur im **Betreuer-Modus** (`MAINTAINER=1` in `.env`): einzelne Listen oder das ganze Ergebnislisten-Archiv (DARC UKW/KW, IARU, siehe [Import](Import-Export.md#ergebnislisten-archiv-alle-conteste-alle-jahre)); enthält die Liste eine DOK-Spalte (DARC-Hub `result.csv`) oder einen DOK wie `G01` in der Zeile, wird er übernommen. |
| Stationslisten anderer Nutzer | Nur im Betreuer-Modus: der CSV-Export einer anderen Installation wird mit „Stationsliste einpflegen“ in die zentrale Liste übernommen. |
| HamQTH / QRZ | Online-Abfrage beim Loggen und in der Log-Prüfung (Ergebnis wird gespeichert) – und gezielt mit „Aus HamQTH / QRZ.com auffüllen“, siehe unten. |
| Von Hand | Formular unter der Tabelle in der Verwaltung. |
| Repo-Abgleich | „Nach neuen suchen (Repo)“, siehe unten. |

Regeln: Der neueste DOK gewinnt (ein Rufzeichen kann den OV wechseln). Der neueste Locator wird zum Hauptlocator, ältere wandern in „weitere Standorte“ (bis zu 5) und erscheinen im Logger zur Auswahl. Zusätze wie `/P`, `-2` oder `-23CM` werden entfernt, das Rufzeichen wird als Kern (`DN2LH`) gespeichert.

## Aus HamQTH / QRZ.com auffüllen

Die Karte „Aus HamQTH / QRZ.com auffüllen“ (Verwaltung → Stationsdatenbank & Import) fragt alle Stationen **ohne Locator**
und alle **deutschen Stationen ohne DOK** nacheinander beim eingerichteten Dienst ab (Verwaltung → Einstellungen → Externe
Rufzeichen-Abfrage). Übernommen wird nur, was noch fehlt: Locator, DOK (nur HamQTH liefert DOKs; QRZ.com nur Locator und Name)
und Name. Vorhandene Angaben aus Logs und Ergebnislisten werden nie überschrieben.

| Einstellung | Standard | Bedeutung |
|---|---|---|
| Pause | 3 s | Wartezeit zwischen zwei Abfragen (1–60 s) – schont den Dienst; bei einem Fehler wird länger gewartet. |
| Tageslimit | 1000 | Höchstens so viele Abfragen pro Tag (UTC); danach geht es am nächsten Tag weiter. |
| erneut nach | 180 Tagen | Eine schon abgefragte Station (auch ohne Treffer) kommt erst nach dieser Zeit wieder dran. |
| automatisch | aus | Der Server startet das Auffüllen alle 30 Minuten selbst, solange es offene Stationen gibt und das Tageslimit nicht erreicht ist. |

Der Lauf findet **auf dem Server** statt – die Seite muss nicht offen bleiben, ein Neustart des Servers bricht ihn ab (mit
„automatisch“ geht es danach von selbst weiter). Meldet der Dienst ein Limit, ein abgelaufenes Abo oder falsche Zugangsdaten,
oder schlagen drei Abfragen nacheinander fehl, hört der Lauf auf. Fortschritt und Ergebnis („… gefunden – x Locator, y DOK,
z Namen ergänzt“) stehen auf der Karte und im Aktionsprotokoll.

## Export

- **Stationsdatenbank exportieren (CSV)**: alle Spalten (Call, Locator, Name, DOK, QSOs, Zuletzt, weitere Locator).
- **Export im Repo-Format**: `Call;Locator;Zuletzt;DOK` – genau das Format der Startdatenbank im Repo.

## Zentrale Pflege: wer importiert was?

Die Liste wird **zentral** gepflegt, damit alle dieselben, geprüften Daten haben:

- **Normale Installation**: bekommt die Liste über „Nach neuen suchen (Repo)“ (Verwaltung → Updates). Die Quellen-Importe (Ergebnislisten, Ergebnislisten-Archiv) sind ausgeblendet. Eigene Funde (neue Rufzeichen, Locator, DOKs aus den Logs) gibt man weiter: „Stationsdatenbank exportieren (CSV)“ und die Datei an den Betreuer schicken.
- **Betreuer** (`MAINTAINER=1` oder `DEV=true` in `.env`, dann Server neu starten; die Importkarten liegen unter Verwaltung → **Stationsdatenbank & Import**): sieht zusätzlich die Importkarten und unter der Stationsdatenbank „Stationsliste einpflegen“ für die eingeschickten CSV-Dateien (DOK, Name und „zuletzt gesehen“ werden übernommen, der neuere Stand gewinnt). Danach „Export im Repo-Format“ und die Datei als `contestlogger/seed/stationsdatenbank.csv` ins Repo einchecken – beim nächsten „Nach neuen suchen“ haben alle den Stand.

  Ob der Modus wirkt, steht beim Start in der Konsole („Betreuer: an“). **Im Demo-Modus (`DEMO=1`) ist er immer aus** – die öffentliche Vorführ-Instanz soll keine Quellen-Importe anbieten; die Konsole meldet dann „Betreuer: AUS“, die Verwaltung zeigt einen Hinweis. Für die Pflege also eine eigene Installation ohne `DEMO=1` nehmen.

## Abgleich mit dem Repo

Ablauf für ein Team mit mehreren Installationen:

1. Auf dem Server mit der vollständigsten Datenbank „Export im Repo-Format“ herunterladen.
2. Die Datei als `contestlogger/seed/stationsdatenbank.csv` ins Repo einchecken.
3. Auf den anderen Installationen „Nach neuen suchen (Repo)“ klicken: der Server lädt die Datei über die GitHub-API und übernimmt neue Rufzeichen und geänderte Locator. Das Ergebnis („324 Einträge im Repo: 12 neu, 3 Locator aktualisiert“) erscheint daneben und im Aktionsprotokoll.

Die URL lässt sich ändern, z. B. auf einen eigenen Webserver. Das Repo ist öffentlich; nur für einen privaten Fork wird ein GitHub-Token mit Lesezugriff gebraucht, das als `GITHUB_TOKEN` in `.env` steht (nicht in der Oberfläche).
