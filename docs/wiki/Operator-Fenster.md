# Operator-Fenster (zweiter Monitor)

![Operator-Fenster](img/operator.png)

Das Operator-Fenster zeigt dem Funk-Operator nur das Wichtigste, groß und live – während der Logger am anderen Platz eintippt.

## Öffnen

- Knopf **🖥 Operator** in der Stationsleiste öffnet es als eigenes Fenster; auf den zweiten Monitor ziehen und mit F11 auf Vollbild.
- Auf einem anderen Rechner: `http://<server>/operator?station=<ID>` – die Stations-ID steht in der Verwaltung in der Stationstabelle.

## Inhalt

| Bereich | Was zu sehen ist |
|---|---|
| Kopf | Station, Band, Locator, Contest, CAT-Frequenz (wenn die Bridge läuft), UTC-Uhr, Verbindungspunkt. |
| Hinweis (gelb) | Text aus dem Feld „Hinweis für das Operator-Fenster“ im Logger, z. B. Frequenz oder QSY. Blinkt kurz, wenn er neu kommt, und bleibt bis zum Löschen. |
| Dupe (rot) | „⚠ DL8NAS bereits gearbeitet um 10:12 UTC (JN59LE)“, sobald der Logger ein schon gearbeitetes Rufzeichen tippt. |
| Kacheln | Rufzeichen · RST geg. · Nr geg. · RST erh. · Nr erh. · Locator · Entfernung/Richtung – in der Reihenfolge des Eingabeformulars, live bei jedem Tastendruck. |
| Statistikzeile | QSOs, Punkte, Großfelder, Ø km, QSOs/letzte Stunde, Dupes, ODX. |
| Karte | Eigene Station, Richtungslinie mit Pfeil zum eingegebenen Locator, alle QSOs als Punkte; „✈ Flugzeuge“ blendet die ADS-B-Ebene ein. |
| QSO-Liste | Die letzten 60 QSOs mit UTC, Rufzeichen, RST, Nummern, Locator, km und Grad; neu geloggte grün. |

Bei schmalen Fenstern stehen Karte und Liste untereinander, die Seite scrollt. Die Verbindung zum Server baut sich bei Abbruch selbst wieder auf.

## Technik

Die Live-Eingabe kommt per WebSocket (`typing`-Ereignisse, nicht gespeichert); der Hinweis (`opnote`) wird je Station auf dem Server gespeichert. Mehrere Operator-Fenster für dieselbe Station sind möglich.
