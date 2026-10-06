# Verwaltung

![Verwaltung](img/verwaltung.png)

Der Reiter **Verwaltung** ist nur mit Admin-Passwort zugänglich und enthält alle Einstellungen.

## Stationen (global)
Stammdaten eurer Stationen (Rufzeichen, Locator, Band, Modus, Passwort, KST-Zugang, EDI-Angaben). Beim Anlegen eines Contests wählt ihr die teilnehmenden. Siehe [Erste Schritte](Erste-Schritte.md).

## Contests
Anlegen (mit Stationsauswahl), bearbeiten (Name, Zeitraum, Notizen, **Austausch**: laufende Nummer, DOK/OV oder beides – siehe [Loggen](Loggen.md#austausch-je-contest-nummer-dok-oder-beides)), archivieren, löschen, „EDI-ZIP“ für alle Bänder. „wählen“ macht den Contest in der Stationsleiste aktiv.

![Contest anlegen mit Austausch](img/contest-austausch.png)

## Stationen im Contest
Die Stationen des gewählten Contests mit ID, Nummer und Passwortstatus. „+ aufnehmen“ fügt eine globale Station hinzu, „+ einmalig“ eine nur für diesen Contest. Je Station: EDI, ADIF, ✎ bearbeiten, Nr. setzen, ✕ löschen.

## Export / Abgabe
EDI je Station (mit Prüfung), ADIF, CSV, alle Bänder als EDI-ZIP. Siehe [Import und Export](Import-Export.md).

## Importe
WinContest-Ordner, Ergebnislisten, DARC-Contest-Hub, einzelne Datei. Siehe [Import und Export](Import-Export.md).

## Stationsdatenbank (Callbuch)
Suche, Bearbeiten (auch DOK), Löschen, Export (CSV; Repo-Format nur im Betreuer-Modus). Der Abgleich mit dem Repo („Nach neuen suchen“) steht unter **Updates**. Siehe [Stationsdatenbank](Stationsdatenbank.md).

## Backups auf dem Server
Der Server sichert die Datenbank automatisch (nur bei Änderungen) in den Ordner `backup/` neben der Datenbank, zusätzlich beim Beenden und vor jedem Update. „Jetzt sichern“ erzeugt eine Sicherung sofort. Die Liste zeigt die vorhandenen Sicherungen. Es gibt bewusst keine Sicherung im Browser und keinen Offline-Modus: die Daten liegen nur auf dem Server.

## Updates
Update-Prüfung, Selbst-Aktualisierung, „News anzeigen“ und „Nach neuen suchen (Repo)“ für die Stationsdatenbank. Siehe [Updates](Updates.md).

## Aktionsprotokoll

![Aktionsprotokoll](img/aktionsprotokoll.png)

Jede Änderung (QSOs, Stationen, Contests, Importe, Einstellungen, KST, Backups, Exporte, Anmeldungen) mit Zeit, Nutzername, Admin-Kennzeichen und Ergebnis; Passwörter werden maskiert. Suche, Aktualisieren, Download als Textdatei. Die gleichen Zeilen stehen auf der Server-Konsole bzw. im `journalctl`.

## Externe Rufzeichen-Abfrage

![Externe Rufzeichen-Abfrage](img/rufzeichen-abfrage.png)

HamQTH (kostenlos, aber Account nötig) oder QRZ.com (XML-Abo) für unbekannte Rufzeichen und den Online-Abgleich in der Log-Prüfung. „Testen“ prüft die Zugangsdaten.

## Karte
Kachel-URL für die Karten. Standard OpenStreetMap; für Offline-Betrieb ein eigener Kachelserver.

## Flugzeug-Scatter (ADS-B)
Quelle (adsb.fi oder eigener Empfänger), Korridor, Antennenhöhe. Siehe [Flugzeug-Scatter](Flugzeug-Scatter.md).

## Sprachen
Übersetzungsvorlage herunterladen, Werte übersetzen, als `lang/<code>.json` neben der Datenbank ablegen (z. B. `data/lang/nl.json`), Server neu starten. Die Sprache erscheint dann in der Auswahl im Kopf. Mitgeliefert: Deutsch und Englisch.

## Admin-Passwort
Ändern und Abmelden.
