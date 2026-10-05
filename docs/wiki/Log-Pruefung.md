# Log-Prüfung

![Log-Prüfung](img/logpruefung.png)

Vor jedem EDI-Export läuft automatisch die Log-Prüfung; im Reiter **Log** lässt sie sich jederzeit mit „Log prüfen“ starten. Klick auf einen Eintrag öffnet das QSO zum Bearbeiten.

## Fehler (verhindern den Export)

- Eigener Locator ungültig oder nicht 6-stellig, eigenes Rufzeichen unplausibel.
- QSO ohne Locator, ungültiger Locator, unplausibles Rufzeichen.
- RST außerhalb des erlaubten Formats, doppelte oder fehlende Seriennummern, Zeiten außerhalb des Contestzeitraums oder in der Zukunft.
- Rufzeichen und Locator passen nicht zusammen (z. B. deutsches Rufzeichen mit Locator in Spanien – bei Portabelbetrieb im Ausland gehört der Landespräfix vor das Rufzeichen, `EA/DL1ABC`).
- Leeres Log.

Der Admin kann trotz Fehlern exportieren („Trotzdem exportieren (Admin)“); der Auswerter wird diese QSOs aber wahrscheinlich streichen.

## Hinweise (Export erlaubt)

- 4-stelliger Locator (Entfernung ungenau).
- Fehlende Angaben im EDI-Kopf (Verantwortlicher, Adresse, Technik …) – in der Verwaltung bei der Station eintragen.
- Abweichungen zur Stationsdatenbank oder zum Online-Abgleich.

## Online-Abgleich mit HamQTH / QRZ

Ist in der Verwaltung eine Rufzeichen-Abfrage eingerichtet (HamQTH ist kostenlos, braucht aber einen HamQTH-Account; QRZ.com ein XML-Abo), schlägt die Prüfung jedes noch nicht geprüfte Rufzeichen nach und merkt sich das Ergebnis in der Stationsdatenbank. Beim nächsten Mal wird nur Neues abgefragt (max. 150 je Durchlauf, dann nochmal starten).

- Abweichendes **Großfeld**: „HamQTH kennt DL8NAS mit JN59LF (Log: JN59LE) – Locator prüfen“.
- Abweichender **6-stelliger Locator** im selben Großfeld: „… – Portabelbetrieb?“.

Dieselbe Abfrage läuft auch beim Loggen: Kennt die eigene Datenbank ein Rufzeichen nicht, wird es online nachgeschlagen und der Locator vorbelegt.
