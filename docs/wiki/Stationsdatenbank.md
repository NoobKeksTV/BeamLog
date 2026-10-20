# Stationsdatenbank (Callbuch)

![Stationsdatenbank in der Verwaltung](img/stationsdatenbank.png)

Die Stationsdatenbank ordnet Rufzeichen einem Locator, ggf. einem Namen (höchstens 32 Zeichen) und dem **DOK/Ortsverband** zu. Sie liefert die Vorschläge und die Locator-Vorbelegung beim Loggen, die Plausibilitätshinweise und die Kandidaten für den Rundruf.

## Kennzahlen

Über der Tabelle (Verwaltung → Stationsdatenbank & Import) steht, wie viele Rufzeichen die Datenbank kennt und wie viele davon
einen Locator haben oder nicht, einen DOK haben, wie vielen deutschen Stationen der DOK fehlt, wie viele beides, keins von
beiden oder einen Namen haben (jeweils mit Anteil in Prozent). „Nach Ländern“ klappt eine Tabelle auf: je Land (Deutschland
zuerst, dann die größten) die Zahl der Stationen und wie viele davon mit/ohne Locator, mit/ohne DOK, mit beidem oder ohne beides –
so sieht man sofort, wo noch Lücken sind. „ohne DOK“ steht nur bei Deutschland, DOKs gibt es nur dort.

„ohne Locator und DOK“ zählt nur Stationen, denen **beides** fehlt. Das Auffüllen (unten) fragt dagegen jede Station ab, der
**eins von beiden** fehlt – deshalb ist „Noch offen“ dort größer; die Karte schlüsselt das auf („… ohne Locator, … mit Locator,
aber ohne DOK“).

## Woher die Einträge kommen

| Quelle | Wann |
|---|---|
| Startdatenbank | Beim ersten Start wird `contestlogger/seed/stationsdatenbank.csv` geladen – rund 127 000 Stationen mit Locator, davon 18 000 mit DOK (Ergebnislisten DARC/IARU 1985–2026, Einzel-Logs, HamQTH/QRZ.com). Das dauert beim allerersten Start einige Sekunden. Bestehende Installationen holen sie mit „Nach neuen suchen (Repo)“. |
| Eigene QSOs | Jedes geloggte QSO (auch importierte Logs); bei DOK-Contests auch der empfangene DOK. |
| KST-Nutzerliste | Alle 10 Minuten je Verbindung; jeder Nutzer mit Locator. |
| Ergebnislisten / Archiv | Nur im **Betreuer-Modus** (`MAINTAINER=1` in `.env`): einzelne Listen oder das ganze Ergebnislisten-Archiv (DARC UKW/KW, IARU, siehe [Import](Import-Export.md#ergebnislisten-archiv-alle-conteste-alle-jahre)); enthält die Liste eine DOK-Spalte (DARC-Hub `result.csv`) oder einen DOK wie `G01` in der Zeile, wird er übernommen. |
| Stationslisten anderer Nutzer | Nur im Betreuer-Modus: der CSV-Export einer anderen Installation wird mit „Stationsliste einpflegen“ in die zentrale Liste übernommen. |
| HamQTH / QRZ | Online-Abfrage beim Loggen und in der Log-Prüfung (Ergebnis wird gespeichert) – im Betreuer-Modus auch gezielt mit „Aus HamQTH / QRZ.com auffüllen“, siehe unten. |
| Von Hand | Formular unter der Tabelle in der Verwaltung. |
| Repo-Abgleich | „Nach neuen suchen (Repo)“, siehe unten. |

Regeln: Der neueste DOK gewinnt (ein Rufzeichen kann den OV wechseln). Der neueste Locator wird zum Hauptlocator, ältere wandern in „weitere Standorte“ (bis zu 5) und erscheinen im Logger zur Auswahl. Zusätze wie `/P`, `-2` oder `-23CM` werden entfernt, das Rufzeichen wird als Kern (`DN2LH`) gespeichert.

## Aus HamQTH / QRZ.com auffüllen

*Nur im Betreuer-Modus* (`MAINTAINER=1` in `.env`), wie die übrigen Quellen-Importe: die aufgefüllte Liste kommt über das Repo
(„Nach neuen suchen“) zu allen Installationen, statt dass jede Installation selbst Hunderttausende Abfragen stellt. Das
Nachschlagen einzelner unbekannter Rufzeichen beim Loggen und in der Log-Prüfung bleibt für alle.

Die Karte „Aus HamQTH / QRZ.com auffüllen“ (Verwaltung → Stationsdatenbank & Import) fragt alle Stationen **ohne Locator**
und alle **deutschen Stationen ohne DOK** online ab. Übernommen wird nur, was noch fehlt: Locator, DOK und Name. Vorhandene
Angaben aus Logs und Ergebnislisten werden nie überschrieben. Die Zugangsdaten stehen unter Verwaltung → Einstellungen →
Externe Rufzeichen-Abfrage – dort lassen sich **HamQTH und QRZ.com gleichzeitig** eintragen.

So läuft es:

- **Beide Dienste zugleich**, je Dienst mehrere Abfragen parallel (einstellbar 1–8).
- **Deutsche Stationen gehen zuerst an HamQTH**, weil nur HamQTH DOKs kennt; ausländische Stationen nimmt, wer gerade frei ist.
  Findet ein Dienst keinen Locator, fragt der andere nach. Stationen, denen nur der DOK fehlt, fragt QRZ.com nicht ab.
- Die Antworten landen in einem **Puffer**; ein einzelner Schreiber übernimmt sie gesammelt (bis zu 200 je Transaktion) in die
  Datenbank. Die Abfragen warten also nie auf die Datenbank, und die Oberfläche bleibt bedienbar.
- Der Lauf findet **auf dem Server** statt – die Seite muss nicht offen bleiben. Ein Neustart des Servers bricht ihn ab; mit
  „automatisch“ geht es danach von selbst weiter.

| Einstellung | Standard | Bedeutung |
|---|---|---|
| nutzen | an | Dienst beim Auffüllen verwenden (nur wenn Zugangsdaten eingetragen sind). |
| parallel | HamQTH 2, QRZ.com 4 | Abfragen gleichzeitig je Dienst (1–8). |
| Pause | HamQTH 0,5 s, QRZ.com 0 s | Wartezeit je Abfrage-Strang nach jeder Abfrage. |
| Tageslimit | 0 | Höchstens so viele Abfragen pro Tag (UTC) je Dienst; 0 = kein eigenes Limit. |
| erneut nach | 180 Tagen | Eine schon abgefragte Station (auch ohne Treffer) kommt erst nach dieser Zeit wieder dran. |
| automatisch | aus | Der Server startet das Auffüllen alle 30 Minuten selbst, solange es offene Stationen gibt. |

Meldet ein Dienst ein Limit, ein abgelaufenes Abo, eine Sperre oder falsche Zugangsdaten, oder schlagen fünf Abfragen nacheinander
fehl, hört **nur dieser Dienst** auf, der andere macht weiter. Bei einzelnen Fehlern wird kurz gewartet (2, 4, 8 … s). Die Karte
zeigt je Dienst unter „Stand“:

- **heute … abgefragt**: Abfragen des Auffüllens heute (UTC) – dafür gilt das Tageslimit.
- **Antwort Ø**: mittlere Antwortzeit des Dienstes.
- **24 h: BeamLog … Anfragen**: *alle* Anfragen, die BeamLog in den letzten 24 Stunden an den Dienst geschickt hat – Auffüllen,
  Nachschlagen beim Loggen, Online-Abgleich der Log-Prüfung, „Testen“, Anmeldungen und Wiederholungen nach Fehlern.
- **QRZ.com meldet …**: der Zähler, den QRZ.com selbst für die letzten 24 Stunden zurückgibt. Er zählt auch Abfragen anderer
  Programme mit demselben Account. Liegt er deutlich über BeamLogs eigener Zahl, fragt noch etwas anderes mit dem Account ab.

Darunter Fortschritt, Abfragen je Minute, die geschätzte Restzeit und den Puffer. Wird der Lauf abgebrochen, speichert BeamLog
auch die Stationen, die schon ein Dienst beantwortet hat und die nur noch auf die Nachfrage beim anderen warteten – sie werden
nicht ein zweites Mal abgefragt.

**Limits der Dienste:** HamQTH nennt für die XML-Abfrage kein Limit (nur ein Account ist nötig) – es ist aber ein kostenloser
Dienst, deshalb die vorsichtigen Standardwerte. QRZ.com zählt die Abfragen je 24 Stunden und meldet bei Überschreitung
„daily limit exceeded“, nennt die Grenze aber nicht; ohne XML-Abo liefert QRZ.com fast keine Daten. Wird ein Dienst zu stark
belastet, kann er den Zugang sperren (QRZ.com: „Connection refused“ für mindestens 24 Stunden) – Parallelität also mit Augenmaß
erhöhen.

## Export

- **Stationsdatenbank exportieren (CSV)**: alle Spalten (Call, Locator, Name, DOK, QSOs, Zuletzt, weitere Locator).
- **Export im Repo-Format**: `Call;Locator;Zuletzt;DOK` – genau das Format der Startdatenbank im Repo. Enthält nur Stationen **mit Locator**.

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
