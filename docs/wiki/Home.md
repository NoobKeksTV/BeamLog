<div align="center">

<img src="img/logo.png" width="96" alt="BeamLog-Logo">

# BeamLog – Wiki

**Lokaler, webbasierter Contest-Logger für UKW-Contests (DARC / IARU Region 1)**

[![Download](https://img.shields.io/github/v/release/NoobKeksTV/BeamLog?label=Download&color=3fb3ff)](https://github.com/NoobKeksTV/BeamLog/releases/latest)
[![Live-Demo](https://img.shields.io/badge/Live--Demo-ausprobieren-ff8c1a)](https://beamlogdemo.lhprinting.de/)
[![Video](https://img.shields.io/badge/Video-YouTube-ff0000?logo=youtube&logoColor=white)](https://youtu.be/yvYb6FNvjzA)
[![Lizenz: GNU AGPLv3](https://img.shields.io/badge/Lizenz-GNU%20AGPLv3-a32d2a)](https://github.com/NoobKeksTV/BeamLog/blob/main/LICENSE)

<a href="https://youtu.be/yvYb6FNvjzA"><img src="img/video-vorschau.jpg" width="720" alt="BeamLog in 1:42 Minuten – Video auf YouTube ansehen"></a>

<sub>🎬 <a href="https://youtu.be/yvYb6FNvjzA">Video „BeamLog in 1:42 Minuten“ auf YouTube ansehen</a></sub>

</div>

BeamLog (früher „ContestLogger“) basiert auf DD3KU WinContest. Ein kleiner Server im LAN ist der zentrale Speicher; geloggt wird von beliebig vielen Rechnern, Tablets oder Handys im Browser. Keine Accounts, nur ein Nickname.

> **🧪 Live-Demo – ohne Installation ausprobieren:** **[beamlogdemo.lhprinting.de](https://beamlogdemo.lhprinting.de/)**
>
> Admin- und Stations-Passwort: `demo` · Beispiel-Contest mit drei Stationen und QSOs · wird täglich zurückgesetzt.
> Alles ist für andere Besucher sichtbar – bitte keine echten Logs oder Zugangsdaten eintragen.

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
