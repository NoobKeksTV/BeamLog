# BeamLog – Wiki

BeamLog (früher „ContestLogger“) ist ein lokaler, webbasierter Contest-Logger für UKW-Contests (DARC/IARU Region 1), gedacht als Nachfolger von DD3KU WinContest. Ein kleiner Server im LAN ist der zentrale Speicher; geloggt wird von beliebig vielen Rechnern, Tablets oder Handys im Browser. Keine Accounts, nur ein Nickname.

![Loggen](img/loggen.png)

## Inhalt

| Seite | Inhalt |
|---|---|
| [Installation](Installation.md) | Portable Version (Windows, Linux, macOS), Start, Datenordner, Optionen |
| [Server-Deploy (Debian, nginx, systemd)](Deploy.md) | Dienst auf einem Debian-Server, nginx, Port 80, Backups, Updates |
| [Erste Schritte](Erste-Schritte.md) | Admin-Passwort, globale Stationen, Contest anlegen, Operatoren freischalten |
| [Loggen](Loggen.md) | Eingabe, Vorschläge, Dupe, Entfernung/Richtung, Karte, Bearbeiten, Nummern |
| [Tastenkürzel](Tastenkuerzel.md) | Alle Tasten im Logger, Chat und allgemein |
| [Chat, KST und DM](Chat-KST.md) | Lokaler Chat, ON4KST-Anbindung, Direktnachrichten, Rundruf |
| [Operator-Fenster](Operator-Fenster.md) | Zweiter Monitor für den Funk-Operator |
| [Statistik](Statistik.md) | Contest- und Stationsauswertung, Karte, Diagramme, Großanzeige |
| [Import und Export](Import-Export.md) | WinContest, EDI, ADIF, Ergebnislisten, DARC-Hub, Abgabe |
| [Log-Prüfung](Log-Pruefung.md) | Was vor der EDI-Abgabe geprüft wird, Online-Abgleich mit HamQTH/QRZ |
| [Stationsdatenbank](Stationsdatenbank.md) | Callbuch, Quellen, Export, Abgleich mit dem Repo |
| [Flugzeug-Scatter](Flugzeug-Scatter.md) | ADS-B-Ebene auf der Karte (wie AirScout) |
| [CAT und CW](CAT.md) | Frequenz vom Funkgerät, CW-Ausgabe über die Bridge |
| [Verwaltung](Verwaltung.md) | Alle Einstellungen, Backups, Aktionsprotokoll, Sprachen |
| [Updates](Updates.md) | Update-Prüfung, Selbst-Aktualisierung, Was ist neu |
| [Fehlersuche](Fehlersuche.md) | Häufige Probleme und Lösungen |

## Grundprinzip

- **Ein Server, viele Browser.** Der Server hält die Datenbank (SQLite), den Chat, die KST-Verbindungen und die Backups. Jeder Browser im LAN meldet sich nur mit einem Nickname an.
- **Globale Stationen → Contest.** Eure Stationen (Rufzeichen, Locator, Band, Passwort, KST-Zugang, EDI-Angaben) legt ihr einmal an. Für jeden Contest wählt ihr, welche davon teilnehmen; jede bekommt dort ihr eigenes Log mit eigener laufender Nummer.
- **Alles in UTC.** Zeiten werden immer in UTC geloggt und angezeigt.
- **Punkte wie WinContest.** 1 Punkt pro angefangenem Kilometer, gegen echte WinContest-Logs verifiziert.
