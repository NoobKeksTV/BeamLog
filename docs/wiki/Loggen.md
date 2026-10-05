# Loggen

![Loggen](img/loggen.png)

## Das Eingabeformular

| Feld | Hinweise |
|---|---|
| **Rufzeichen** | Wird automatisch in Großbuchstaben gesetzt. Beim Tippen erscheinen Vorschläge aus der Stationsdatenbank und allen eigenen Logs mit Locator, Entfernung, Richtung und „schon gearbeitet“-Hinweis. |
| **RST geg. / RST erh.** | Vorbelegt mit 59 (bzw. 599 bei CW). |
| **Nr geg.** | Laufende Nummer, automatisch hochzählend, orange hervorgehoben. Rücksetzen über den Knopf „Nr. zurücksetzen“ oder in der Verwaltung. |
| **Nr erh.** | Empfangene Nummer. |
| **Locator** | Wird aus der Stationsdatenbank vorbelegt (grau = automatisch, wird bei eigener Eingabe überschrieben). Hat ein Rufzeichen mehrere bekannte Standorte, erscheinen sie darunter zur Auswahl. |
| **Kommentar** | Frei. |

Unter dem Formular: Entfernung in km und Richtung in Grad, Dupe-Warnung („⚠ DL8NAS bereits gearbeitet um 10:12 UTC (JN59LE) – DUPE!“) und Plausibilitätshinweise (z. B. deutsches Rufzeichen mit Locator im Ausland, oder Stationsdatenbank kennt den Partner mit anderem Locator).

## Ablauf mit der Tastatur

- **Rufzeichen tippen → Leertaste** springt zu *Nr erh.*, gleichzeitig wird die Stationsdatenbank (und ggf. HamQTH/QRZ) abgefragt und der Locator vorbelegt.
- **Nr erh. → Leertaste** springt zum Locator, **Locator → Leertaste** zum Kommentar.
- **Enter** loggt, sobald Rufzeichen und Locator stehen (in *Nr erh.*, *Locator* oder *Kommentar*).
- **Esc** leert das Formular.
- Pfeiltasten blättern in den Vorschlägen, Enter/Tab übernimmt den markierten Vorschlag.

Alle Kürzel unter [Tastenkürzel](Tastenkuerzel.md) oder mit F1 im Programm.

## Was beim Loggen passiert

- Zeit in **UTC**, Entfernung nach WinContest-Methode (angefangene km = Punkte), Großfeld, Land (DXCC).
- **Dupe-Erkennung** je Rufzeichen und Band: Dupes werden gespeichert, zählen aber 0 Punkte und erscheinen durchgestrichen.
- Das Rufzeichen mit Locator landet in der **Stationsdatenbank** (siehe [Stationsdatenbank](Stationsdatenbank.md)).
- Alle anderen Browser bekommen das QSO sofort (Ton „Tick“), das Operator-Fenster hebt es grün hervor.
- Bei laufender CAT-Bridge wird die Frequenz zum QSO gespeichert (ADIF `FREQ`).

## Töne

🔔 im Kopf schaltet die Töne: Pling beim eigenen QSO, Brummen bei Dupe, Ping bei Chat/DM/„an mich“, Tick wenn eine andere Station loggt. Töne sind gedrosselt (max. ein Hinweiston je 1,5 s) und kommen nur aus dem Hauptfenster, nicht aus ausgepoppten Fenstern.

## Karte und Antennenrichtung

Die Karte unter dem Formular zeigt die eigene Station (blau), das Feld des Partners (rot) und die Richtungslinie mit Pfeil. Beschriftung: Rufzeichen, km, Grad. Kacheln kommen von OpenStreetMap (oder einem eigenen Kachelserver, Verwaltung → Karte); ohne Internet funktionieren Linien und Marker trotzdem. Mit „✈ Flugzeuge“ kommt die ADS-B-Ebene dazu, siehe [Flugzeug-Scatter](Flugzeug-Scatter.md).

## Statistikzeile

Direkt unter dem Formular: QSOs, Punkte, Großfelder, Ø km, QSOs in der letzten Stunde, Dupes, ODX. Aktualisiert sich live.

## Letzte QSOs, Bearbeiten, Löschen

Die Liste unter der Karte zeigt die letzten QSOs mit ✎ (bearbeiten) und ✕ (löschen). Beim Bearbeiten wandern die Werte ins Formular; Punkte und Dupes werden danach neu berechnet. Der Reiter **Log** zeigt das komplette Log mit Suche und dem Knopf „Log prüfen“.

## Hinweis für das Operator-Fenster

Das Feld über der Karte („Hinweis für das Operator-Fenster“) schickt einen Text, z. B. die Frequenz oder „QSY 432.250“, groß an das [Operator-Fenster](Operator-Fenster.md). Er bleibt je Station gespeichert, bis er mit ✕ gelöscht wird.

## Sprachbausteine (F2–F8)

Vorformulierte Texte („CQ Contest DN2LH/P …“), die bei Tastendruck groß eingeblendet und, wenn die CAT-Bridge mit `--cw` läuft, als CW gesendet werden. F9 blendet die Makroleiste mit allen Bausteinen ein, ✎ öffnet den Editor. Platzhalter: `{mycall} {myloc} {call} {rst} {nr} {loc} {band} {nick}`.

## Mehrere Operatoren

Mehrere Browser können dieselbe Station bedienen; die laufende Nummer vergibt der Server, Kollisionen gibt es nicht. Wer was geloggt hat, steht im Log (Spalte Op) und im Aktionsprotokoll.
