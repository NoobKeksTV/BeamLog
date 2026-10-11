# Import und Export

Alles in der Verwaltung (Admin).

![Import-Karten in der Verwaltung](img/import.png)

## WinContest-Ordner (DD3KU) übernehmen

Den kompletten Ordner von WinContest auswählen (z. B. `D:\Contest`). Übernommen werden alle Logs aus `Datenbank/*.mdb` und `*.txt`, `DD3KU/*.EXP`, `Auswertung/*.edi` und `ADIF/*.adi` als archivierte Contests; jedes Rufzeichen mit Locator landet in der Stationsdatenbank. Dasselbe Log in mehreren Dateien wird nur einmal übernommen.

- `.mdb`-Dateien werden rein in Python gelesen, auch verschlüsselte Jet4-Datenbanken – keine Zusatzsoftware nötig.
- `Contest.dat` (DD3KUs verschlüsselte Stationsdatenbank) kann nicht gelesen werden; die mitgelieferte Startdatenbank und die DARC-Ergebnislisten ersetzen sie.
- Das Ergebnis zeigt zuerst die Gesamtzahlen (Dateien, Contests, QSOs, Rufzeichen neu/bekannt), Details je Datei ausklappbar.

Kommandozeile: `BeamLog-Import "D:\Contest" --db data\beamlog.db`.

## Einzelne Datei importieren

Nimmt WinContest `.txt`/`.EXP`/`.mdb`, EDI/REG1TEST, ADIF oder Call-Listen (`Call;Locator;Name[;DOK]`). Rufzeichen und Locator aller Einträge landen **immer** in der Stationsdatenbank – das Ziel entscheidet nur, was mit den **QSOs** passiert:

| Ziel | Was passiert |
|---|---|
| **Automatisch** (Standard) | Enthält die Datei QSOs, wird ein **neuer Contest** mit einer **neuen Station** angelegt (Name, Zeitraum, Rufzeichen, Locator und Band aus dem Dateikopf; bei einem eigenen Contest-Namen im Feld darunter wird der genommen). Enthält sie nur Rufzeichen/Locator (Call-Liste), geht alles nur in die Stationsdatenbank. Richtig für alte Logs, die als Archiv übernommen werden sollen. |
| **Nur ins Call-Buch** | Die QSOs werden **nicht** als Log übernommen, nur Rufzeichen, Locator und DOK der Gegenstationen wandern in die Stationsdatenbank. Richtig für fremde Logs oder Listen, deren QSOs euch nicht gehören. |
| **QSOs in bestehende Station übernehmen** | Die QSOs werden der **gewählten Station** des gewählten Contests hinzugefügt (Band der Station, wenn die Datei keins nennt). Schon vorhandene QSOs (gleiches Rufzeichen und gleiche Zeit) werden übersprungen, die laufende Nummer zählt weiter. Richtig, um ein Papier-/Zweitlog nachzutragen oder ein Backup-Log in eine laufende Station zu mischen. |

Hinweise: Beim automatischen Import braucht die Datei den eigenen Locator im Kopf (EDI `PWWLo`, ADIF-Kopf), sonst „Zielstation auswählen“. EDI (Spalte „Exchange received“), ADIF (`DARC_DOK`, `SRX_STRING`) und Call-Listen mit DOK-Spalte bringen den DOK/OV mit; er landet im QSO und in der Stationsdatenbank. Das Ergebnis zeigt Anzahl QSOs, Call-Buch-Einträge und Warnungen (übersprungene Zeilen).

## Ergebnislisten (DARC / IARU / UKW-Contest-Club)

Nur im Betreuer-Modus sichtbar (`MAINTAINER=1` in `beamlog.env`), siehe [Stationsdatenbank](Stationsdatenbank.md#zentrale-pflege-wer-importiert-was).

Veröffentlichte Ergebnislisten enthalten Rufzeichen und Locator aller Teilnehmer. Datei (HTML, PDF, TXT, CSV), eingefügter Text oder die URL der Ergebnisseite; vor der Übernahme gibt es eine Vorschau.

## Ergebnislisten-Archiv: alle Conteste, alle Jahre

*Nur im Betreuer-Modus (Verwaltung → Stationsdatenbank & Import).* „Verfügbare Listen suchen“ fragt alle Quellen ab und zeigt
jede veröffentlichte Ergebnisliste zum Anhaken – einzeln, je Contest/Jahrgang oder je Quelle:

| Quelle | Zeitraum | Inhalt |
|---|---|---|
| DARC UKW-Conteste, Contest-Hub `dxhf2.darc.de` | ab 2017 | Rufzeichen, Locator, DOK, ODX-Station (`result.csv`) |
| DARC UKW-Conteste, Archiv auf darc.de | 2008–2016 | Rufzeichen, DOK, Locator, ODX-Station (Textlisten) |
| DARC-KW-Conteste (WAG, WAE CW/SSB/RTTY, 10 m, Fieldday CW/SSB, Oster-, Weihnachts-, Ausbildungs-, FT4-, RTTY-/Hell-Kurzcontest) | ab 2014 | nur Rufzeichen und DOK – Kurzwelle tauscht keinen Locator aus |
| IARU-Region-1-UKW-Conteste (September, Oktober UHF, Marconi, Subregionals, Mikrowelle) und OK-Conteste, Archiv OK2KKW | ab 1985 | Rufzeichen und Locator |
| IARU-Region-1-UKW-Conteste, Contest-Robot `iaru.oevsv.at` (Ergebnis-CSV je Contest, dazu die Gesamtliste `vhf.csv`) | ab 2019 | Rufzeichen und Locator |
| IARU-Contest-Robot: **Einzel-Logs** aller Teilnehmer (je Teilnehmer alle QSOs) | ab 2019 | Rufzeichen und Locator aller QSO-Partner – auch Stationen ohne eigenes Log; als „unique“ (vermutlich verhört) oder ungültig markierte QSOs werden ausgelassen. Dauert 10–30 Minuten je Contest. |

Zusammen rund 800 Listen (ohne die Einzel-Logs). Der Import läuft im Hintergrund (Fortschrittsbalken, abbrechbar, läuft auch nach dem Neuladen der
Seite weiter) und schont die Server der Veranstalter mit einer kurzen Pause je Liste; alles auf einmal dauert etwa 20–30 Minuten.
Bereits importierte Listen sind markiert und werden mit „nur noch nicht importierte“ übersprungen.

- Neuere Angaben gewinnen (das Datum der Liste zählt); ein älterer Locator bleibt als Alternative erhalten.
- KW-Listen ergänzen standardmäßig nur den **DOK** bereits bekannter Stationen. Mit „Stationen ohne Locator neu aufnehmen“
  kommen auch alle übrigen KW-Teilnehmer dazu (nur Rufzeichen und DOK – ohne Entfernung/Richtung).
- Der IARU-Contest-Robot wird mit Erlaubnis des Betreibers abgerufen.

## Export / Abgabe

![Export / Abgabe](img/export.png)

Verwaltung → **Export / Abgabe** (je Contest):

| Knopf | Ergebnis |
|---|---|
| EDI (mit Prüfung) | Öffnet die [Log-Prüfung](Log-Pruefung.md) der Station (ohne die aktive Station im Logger zu wechseln); bei Erfolg steht darin „EDI herunterladen“, mit Fehlern exportiert nur der Admin nach Rückfrage. |
| ADIF | Alle QSOs der Station als ADIF (mit Frequenz, wenn CAT lief; DOK als `DARC_DOK`/`SRX_STRING`). |
| CSV | Tabelle. |
| Cabrillo | Cabrillo 3.0 (`.cbr`) für Auswerter, die kein EDI annehmen: Kopf mit Kategorie, Locator, Wertung, Adresse; QSO-Zeilen mit RST, Nummer, Locator und ggf. DOK; Dupes als `X-QSO`. |
| Alle Bänder als EDI-ZIP | Zeigt erst die Prüfung aller Stationen des Contests (✔/✖ mit den ersten Fehlern, Klick öffnet die Prüfung der Station) und lädt dann das ZIP mit den bestandenen Logs; der Admin kann alle erzwingen. Nicht bestandene Logs stehen mit ihren Fehlern in `NICHT_EXPORTIERT.txt`. Enthält das ZIP nur diese Datei, hat kein Log die Prüfung bestanden. |

Der EDI-Kopf nimmt die Angaben aus der Station (Wertungsgruppe, Club, Verantwortlicher, Technik). Jeder Export steht im Aktionsprotokoll.

## Stationsdatenbank

Export als CSV, Export im Repo-Format und Abgleich mit dem Repo: siehe [Stationsdatenbank](Stationsdatenbank.md).
