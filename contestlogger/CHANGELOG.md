# Änderungsprotokoll

## v0.9.29 (2026-10-06)
- Wertung je Contest mit Multiplikator, Cabrillo-Export, strengere Log-Prüfung, Offline-Kachelcache
  - Wertung im Contest wählbar: Punkte je QSO (1 je km oder fester Wert) und Multiplikator (keiner, Großfelder, DOKs,
    Großfelder + DOKs); Statistikzeile, Scoreboard, Statistik, EDI (CToSc/CQSOP) und Cabrillo nutzen dieselbe Wertung,
    bei Änderung werden alle QSOs des Contests neu bewertet
  - Cabrillo-3.0-Export je Station (Kopf mit Kategorie, Locator, Wertung, Adresse; QSO-Zeilen mit RST, Nummer, Locator, DOK;
    Dupes als X-QSO) in der Export-Karte
  - Log-Prüfung: Wertungsgruppe, Operatorenliste bei Multi, E-Mail-Format, Zahlenfelder (Leistung, Antennenhöhe, NN),
    Feldlängen, QSO mit eigenem Rufzeichen, Partner im eigenen Feld
  - Offline-Kachelcache: Kacheln über den Server laden und unter data/tiles speichern (/tiles/{z}/{x}/{y}.png), Schalter
    in der Verwaltung, „Region vorab laden“ (Locator, Radius, Zoom bis 7–10, Begrenzung für den öffentlichen OSM-Server),
    Fortschritt, Stopp, Cache leeren; Logger, Statistik und Operator-Fenster nutzen den Cache
  - Wiki (Loggen, Verwaltung, Import/Export, Log-Prüfung) und README ergänzt; Tests
- Karte: Pfeil trifft den Partnerpunkt, lesbares Label, größere Karte mit Flugzeugen; Tagestrenner im Chat; Verwaltung aufgeräumt
  - Richtungspfeil als SVG, die Spitze liegt exakt auf dem Partnerpunkt; Stations-Label mit lesbarem Hintergrund neben dem Punkt (Logger und Operator)
  - Flugzeuge: Karte wird mit eingeschalteter Flugzeug-Ebene höher (420 px), Einträge in der Liste sind anklickbar und
    springen mit der Karte zum Flugzeug (Logger und Operator-Fenster)
  - Chat, KST und DM: Trennzeile mit Datum vor der ersten Nachricht eines neuen Tages („Heute“, „Gestern“, Wochentag + Datum)
  - DM: beim Stations-/Contestwechsel wird das jüngste Gespräch der Station gezeigt statt des Partners der alten Station
    (der dort keinen Verlauf hatte); ohne Auswahl ist das jüngste Gespräch offen
  - Operator-Fenster: alle Kacheln zentriert wie Entfernung/Richtung
  - Verwaltung: ON4KST-Karte entfernt (steht bei der Station), Stationsdatenbank direkt unter den Contests, Formular
    als saubere Zeile, Repo-URL-Feld entfernt, „Nach neuen suchen (Repo)“ in die Updates-Karte, Repo-Export nur Betreuer
  - Wiki (Chat/KST, Flugzeug-Scatter, Verwaltung, Updates, Stationsdatenbank) und Screenshots aktualisiert
- Flugzeug-Scatter wie AirScout (Kreuzungszeit, Höhenreserve, Profil), Rufzeichen je Großfeld, Betreuer-Modus für Quellen-Importe
  - Flugzeuge: Hover zeigt Mindesthöhe an der Position, Höhenreserve (Flughöhe minus Mindesthöhe), Elevation von beiden
    Stationen, Größenklasse (schwer/groß/mittel/leicht), Steigen/Sinken und – bei Kurs auf den Pfad – Kreuzungszeit (UTC),
    Pfad-Kilometer, ob in der Zone und Reserve am Kreuzungspunkt; Kreuzungspunkt wird auf dem Pfad markiert
  - Status wie AirScout (hot / kreuzt bald / sichtbar / außer Reichweite / zu tief) mit Farben, schwere Flugzeuge größer
  - Pfadprofil (Seitenansicht): Mindesthöhen-Kurve, Zone, Flugzeuge in ihrer Höhe – zu-/abschaltbar; Operator-Fenster
    mit denselben Hover-Details
  - Statistik-Karte: Großfelder zeigen beim Hovern die Rufzeichen, beim Klicken alle mit Locator und km
  - Betreuer-Modus (MAINTAINER=1 in contestlogger.env): nur dann sind Ergebnislisten-Import und DARC-Contest-Hub sichtbar
    und erlaubt (API 403 sonst); normale Installationen holen die Liste über „Nach neuen suchen (Repo)“ und schicken
    ihren CSV-Export an den Betreuer, der ihn mit „Stationsliste einpflegen“ übernimmt (DOK, Name, zuletzt gesehen)
  - Stationsdatenbank-Export (CSV) ist damit auch wieder importierbar; Wiki und README ergänzt
- Verwaltung: Karten auf zwei gleich hohe Spalten verteilt, Arbeitsregeln für Git-Autor
  - Die beiden sehr langen Sammelkarten (Importe; Stationsdatenbank bis Admin-Passwort) sind jetzt einzelne Karten,
    die in zwei Spalten fließen – keine überlange rechte Spalte mehr, Aktionsprotokoll ohne Scrollen erreichbar
  - Screenshot der Verwaltung (README und Wiki) aktualisiert
  - CLAUDE.md: Commits unter dem Account NoobKeksTV, ohne Signierung und ohne Zusatzzeilen
- Test: Updater-Test auf case-insensitiven Dateisystemen (macOS) reparieren
  - Testordner hieß wie die Binärdatei (contestlogger/ContestLogger), was auf macOS kollidierte
- Änderungsprotokoll für v0.9.28
- Austausch je Contest wählbar: laufende Nummer, DOK/OV oder beides (z. B. Köln-Aachen-Contest)
  - Contest-Einstellung „Austausch“: RST + Nummer (Standard), RST + DOK/OV oder RST + Nummer + DOK
  - Logger blendet die Felder passend ein (DOK erh. statt/neben Nr erh.), Leertaste und Enter springen entsprechend,
    DOK wird aus der Stationsdatenbank vorbelegt und mit jedem QSO gelernt; Bearbeiten-Dialog mit DOK
  - Operator-Fenster zeigt die DOK-Kachel bzw. blendet die Nummernkacheln aus, QSO-Liste mit DOK-Spalte
  - Statistikzeile zählt verschiedene DOKs; Log-Prüfung warnt bei fehlendem DOK und fehlendem eigenem DOK
  - Export: EDI (PExch = eigener DOK aus den EDI-Angaben, Spalte „Exchange received“, CExcs), ADIF (DARC_DOK,
    SRX_STRING, STX_STRING), CSV-Spalte „DOK erh“; Komplettes Log mit DOK-Spalte
  - Import: EDI, ADIF, DARC-Contest-Hub (DOK-Spalte), Ergebnislisten (DOK in der Zeile), Call-Listen mit DOK-Spalte
  - Stationsdatenbank: DOK-Spalte (Anzeige, Bearbeiten, Suche nach DOK), CSV-Export und Repo-Format
    Call;Locator;Zuletzt;DOK, Abgleich mit dem Repo übernimmt DOKs; neuester DOK gewinnt
  - Version 0.9.28; Wiki (Loggen, Verwaltung, Stationsdatenbank, Import/Export) und README ergänzt
- Server-Einstellungen in contestlogger.env, Token-Feld entfernt, Wiki mit Bildern
  - Alle Server-Einstellungen (Host, Port, Datenbank, Backup-Takt, öffentliche Adresse, KST-Server, GitHub-Token)
    stehen jetzt in einer .env-Datei: contestlogger.env neben dem Programm bzw. /etc/contestlogger/contestlogger.env
    auf dem Server; --config und CONTESTLOGGER_<KEY> werden ebenfalls unterstützt, Kommandozeile überstimmt alles
  - Vorlage contestlogger.env.example liegt im Paket; die systemd-Units enthalten keine Optionen mehr,
    install.sh legt die Konfiguration an und übernimmt --url bzw. eine alte --public-url aus der Unit
  - GitHub-Token-Feld aus der Verwaltung entfernt (Repo wird öffentlich); nur noch optional über GITHUB_TOKEN
  - Operator-Fenster: Karte füllt jetzt zuverlässig die ganze Fläche (Kacheln nach Layout/Resize nachgezogen)
  - README: inoffizieller Nachfolger, KST-Chat und Aircraft-Scatter in der Beschreibung, Bildergalerie repariert,
    Hauptbild mit gerenderter OSM-Karte, Footer
  - Wiki: jede Seite mit Screenshots (Erster Start, QR-Code, Import, Export, Stationsdatenbank, Backups,
    Updates, Was ist neu, Aktionsprotokoll, Rufzeichen-Abfrage, ADS-B, Frequenz, KST-Rohdaten)
- Updates, Was-ist-neu, README mit Badges und Bildern, komplettes Wiki
  - Update-Prüfung gegen die GitHub-Releases (stündlich, Token für privates Repo), grüner Knopf
    „⬆ vX“ im Kopf, Verwaltung → Updates: prüfen, Release-Notes, „Jetzt aktualisieren“ (portable
    Version lädt das ZIP, ersetzt die Dateien, data/ bleibt, Sicherung vorher, Neustart;
    Linux/macOS per exec, Windows per update.bat), „automatisch prüfen“ abschaltbar.
  - „Was ist neu in vX“ beim ersten Aufruf eines Browsers nach einem Update; „News anzeigen“
    mit den letzten Versionen. Grundlage: CHANGELOG.md aus der Git-Historie (im Build erzeugt,
    mitgeliefert; nur veröffentlichte Versionen werden gezeigt).
  - README neu: Badges (Release, Build, Downloads, Commit, Python, Plattformen, Stars),
    Funktionsübersicht, Schnellstart, Bildergalerie, Links ins Wiki. LICENSE ergänzt.
  - Wiki unter docs/wiki (16 Seiten): Installation, Deploy (nginx/systemd/Port 80), Erste
    Schritte, Loggen, Tastenkürzel, Chat/KST/DM/Rundruf, Operator-Fenster, Statistik,
    Import/Export, Log-Prüfung, Stationsdatenbank, Flugzeug-Scatter, CAT/CW, Verwaltung,
    Updates, Fehlersuche – mit Screenshots aus einem echten Log.
- Flugzeug-Scatter (ADS-B) wie AirScout: zuschaltbare Flugzeug-Ebene auf Logger- und Operator-Karte
  - Quelle wählbar: adsb.fi (frei, nicht-kommerziell, 1 Abfrage/s, Daten © adsb.fi) oder eigener
    ADS-B-Empfänger (dump1090/readsb/tar1090 aircraft.json). Server holt und cached (4 s).
  - Auswertung nach AirScout-Prinzip (ohne Geländemodell): Zone gemeinsamer Sichtbarkeit auf dem Pfad
    (Funkhorizont 4,12·√h), Flugzeuge im Korridor (±12 km, einstellbar) mit Sichtbarkeit von beiden
    Stationen, Querabstand, Position auf dem Pfad und geschätzter Kreuzungszeit.
  - Karte: Knopf „✈ Flugzeuge“, grüner Balken = Zone, orange = nutzbare Flugzeuge, Liste darunter;
    Aktualisierung alle 5 s, Einstellung bleibt gespeichert. Operator-Fenster mit gleicher Ebene.
  - Verwaltung: Quelle, URL des Empfängers, Korridorbreite, Antennenhöhe. Hilfe-Eintrag.
  - airplanes.live wurde geprüft: nur noch auf Anfrage nutzbar, daher nicht eingebaut.

## v0.9.27 (2026-10-04)
- Globale Stationen, Online-Abgleich in der Log-Prüfung, Stationsdatenbank aus dem Repo, Operator-Fenster wie Logger, Chat-Zähler (v0.9.27)
  - Stationen sind jetzt global (Verwaltung → „Stationen (global)“ mit Call, Locator, Band, Passwort,
    KST-Zugang, EDI-Angaben). Beim Anlegen eines Contests wählt man die teilnehmenden Stationen; jede
    bekommt dort ihr eigenes Log, eigene Nummer und eigenen KST-Chat. Nachträglich „+ aufnehmen“ oder
    „+ einmalig“. Vorhandene Contest-Stationen werden beim ersten Start einmalig als globale Stationen übernommen.
  - Log-Prüfung gleicht Rufzeichen/Locator automatisch mit HamQTH/QRZ ab (falls eingerichtet), jedes
    Rufzeichen nur einmal; Abweichungen im Großfeld bzw. 6-stelligen Locator erscheinen als Hinweis.
  - Stationsdatenbank: Export als CSV (Knopf), Export im Repo-Format (Call;Locator;Zuletzt), „Nach neuen
    suchen (Repo)“ lädt contestlogger/seed/stationsdatenbank.csv über die GitHub-API und übernimmt neue
    Einträge; URL und Token (für privates Repo) einstellbar.
  - Operator-Fenster: Aufbau wie der Logger (RST geg. vor Nr geg.), Statistikzeile, Karte mit Richtungspfeil,
    Entfernung/Richtung zentriert, Hinweis blinkt kurz.
  - Chat-Reiter zeigt wie KST/DM einen Zähler für ungelesene Nachrichten.
  - Deploy: Unit für Port 80 ohne nginx (CAP_NET_BIND_SERVICE), README-Befehle für Dienst und nginx.
- Operator-Fenster: Aufbau wie im Logger (RST geg. vor Nr geg.), Statistikzeile, Karte mit Richtungspfeil, blinkender Hinweis
  - Kacheln in Logger-Reihenfolge: Rufzeichen · RST geg. · Nr geg. · RST erh. · Nr erh. · Locator · Entfernung/Richtung;
    Entfernung und Richtung zentriert und groß untereinander.
  - Statistikzeile wie im Logger (QSOs, Punkte, Großfelder, Ø km, QSOs/letzte h, Dupes, ODX).
  - Karte mit eigener Station, Richtungslinie und Pfeil zum eingegebenen Locator sowie allen QSO-Punkten;
    daneben die QSO-Liste (mit RST), auf schmalen Fenstern untereinander.
  - Neuer Hinweis vom Logger blinkt kurz (2,5 s) auf.
- Deploy: Unit für Betrieb direkt auf Port 80 ohne nginx (CAP_NET_BIND_SERVICE), README-Abschnitt dazu
- Release-Notes: Git-Ausgabe als UTF-8 lesen (Umlaute in Commit-Texten auf Windows)

## v0.9.26 (2026-10-04)
- Release-Notes: UTF-8-Ausgabe auf dem Windows-Runner (Umlaute)
- Version 0.9.26: Linux-ZIP mit ergänzter Deploy-README (Befehle für Dienst und nginx)
- Deploy-README: Befehle zum Kopieren, Aktivieren und Starten des Dienstes (manuelle Installation) und zur Bedienung

## v0.9.25 (2026-10-04)
- Linux-ZIP enthält Deploy-Paket (nginx, systemd, Backup) für Debian-Server; Linux-Build auf Ubuntu 22.04 für Debian-12-Kompatibilität (v0.9.25)
  - deploy/ im Linux-ZIP: install.sh (Erstinstallation/--update/--url), contestlogger.service
    (Binary auf 127.0.0.1:8000, Daten in /var/lib/contestlogger), nginx-Site mit WebSocket,
    tägliches Backup per sqlite3, README. Kein Python auf dem Server nötig.
  - Linux-Binary wird auf Ubuntu 22.04 gebaut (glibc 2.35): behebt
    "GLIBC_2.38 not found" auf Debian 12.
  - Enthält außerdem das Operator-Fenster für den zweiten Monitor und die automatischen Release-Notes.
- Operator-Fenster für den zweiten Monitor (🖥 Operator in der Stationsleiste, /operator?station=ID)
  - Zeigt live, was der Logger eingibt: Rufzeichen, Nr gegeben/erhalten, RST, Locator,
    Entfernung und Richtung, dazu Kommentar; Dupe-Warnung mit Uhrzeit/Locator des früheren QSOs
    (ohne weitere Details).
  - Hinweisfeld über der Karte im Loggen-Reiter: Text (z. B. Frequenz, QSY, Antennenrichtung)
    erscheint groß im Operator-Fenster, wird je Station gespeichert und bleibt bis zum Löschen.
  - Liste der letzten 40 QSOs (neu geloggte grün hervorgehoben), CAT-Frequenz, UTC-Uhr,
    Verbindungsanzeige mit automatischem Neuverbinden; läuft auch auf einem anderen PC im Netz.
  - Übertragung per WebSocket (typing/opnote), nicht gespeichert außer dem Hinweis.
- Release-Notes automatisch aus der Commit-Historie; Arbeitsregeln in CLAUDE.md (eine Version pro Session)
  - Workflow: komplette Historie auschecken, Notes mit build_tools/release_notes.py erzeugen
    (Änderungen seit letztem Tag mit Commit-Text, Commit-Liste, Vergleichslink) und als Release-Text verwenden.
  - CLAUDE.md hält fest: gesammelte Wünsche werden am Ende der Session als ein Release veröffentlicht.

## v0.9.24 (2026-10-04)
- Statistik: Karte zeigt QSO-Punkte und Großfelder (CSS-Konflikt mit Leaflet behoben, Karte wird je Aufruf neu angelegt), Diagramme doppelt so breit mit lesbarer Schrift, Tabellen nicht mehr abgeschnitten (v0.9.24)

## v0.9.23 (2026-10-04)
- KST: Verlaufs-Wiederholung nach Neustart toleranter erkannt, Rohdaten-Ansicht je Station; grüne Partner-Markierung entfernt (v0.9.23)

## v0.9.22 (2026-10-04)
- Verlauf serverseitig und je Contest: lokaler Chat pro Contest, DM-Lesemarken auf dem Server, vollständige DM-Historie beim Laden; DM-Fenster scrollt; kein Umspringen auf fremde DMs bei aktivem Gespräch; Tab-Wechsel springt ans Ende (v0.9.22)

## v0.9.20 (2026-10-04)
- Rundruf: Stationen, die von dieser Station schon eine gerichtete Nachricht bekommen haben, erscheinen nicht mehr als Kandidaten (v0.9.20)

## v0.9.19 (2026-10-04)
- Rundruf: breiterer Dialog, Hinweis statt stummer Rotation bei zu wenigen Kandidaten; KST-Tab: Antworten an mich orange, Nachrichten von DM-Partnern grün markiert; DM-Gespräch ohne Markierungen (v0.9.19)

## v0.9.18 (2026-10-04)
- KST-Tab: eigene Nachrichten farblich abgesetzt (v0.9.18)
- KST-DM: eigene gerichtete Nachrichten aus anderen KST-Clients (gleicher Login) öffnen das DM-Gespräch automatisch (v0.9.17)

## v0.9.16 (2026-10-04)
- Hilfeseite mit allen Tastenkürzeln (F1 / '?' im Kopf); F1 ist jetzt Hilfe, Sprachbausteine F2–F8 (v0.9.16)

## v0.9.15 (2026-10-04)
- Chat: kein Zwangsscroll beim Hochscrollen, Knopf '↓ Neueste'; DMs beim Öffnen als gelesen markiert; kein doppelter Ton im Popup (v0.9.15)

## v0.9.14 (2026-10-04)
- Töne gedrosselt (max. 1 Hinweiston je 1,5 s, Ruhe nach Neuverbinden), KST-Verlauf nach Reconnect nicht doppelt (v0.9.14)

## v0.9.13 (2026-10-04)
- Rundruf: Auswahl rotieren ('Nächste →'), bereits angeschriebene werden übersprungen (v0.9.13)

## v0.9.12 (2026-10-04)
- Aktionsprotokoll (Audit-Log) für alle Änderungen, Export nur noch im Admin-Panel (v0.9.12)
  - Jede ändernde API-Anfrage (QSOs, Stationen, Contests, Einstellungen,
    Importe, KST, Backups, Exporte) wird mit Zeit, Nutzer, Admin-Kennzeichen,
    Ergebnis und passwortfreier Zusammenfassung in der Datenbank festgehalten
    und auf der Server-Konsole ausgegeben. Verwaltung: Karte 'Aktionsprotokoll'
    mit Suche und Download als Textdatei.
  - Export/Abgabe-Karte und Export-Knopf aus dem Log-Bereich entfernt; die
    Abgabe läuft über die Verwaltung. 'Log prüfen' bleibt im Log-Reiter.

## v0.9.11 (2026-10-04)
- Rundruf: eigene gespeicherte Texte, ON4KST nie anschreiben; 'an mich' über Kern-Rufzeichen inkl. Stations-Call (v0.9.11)
  - Nachrichtenfilter für ON4KST aus v0.9.10 zurückgenommen: alle Nachrichten
    bleiben sichtbar, nur der Rundruf schließt den Chat-Server aus.
  - Rundruf: eigene Texte speichern/wählen/löschen (für alle Operatoren,
    ohne Admin), keine Vorgaben mehr.
  - 'An mich'/DM: Vergleich über das Kern-Rufzeichen (ohne /P, -2 …);
    KST-Login und Stations-Call zählen immer, Zusatzliste bleibt möglich.

## v0.9.10 (2026-10-04)
- KST: Systemmeldungen des Absenders ON4KST herausfiltern (v0.9.10)

## v0.9.9 (2026-10-04)
- Rufzeichen: alles ab dem Bindestrich abschneiden (OJ7F-23CM -> OJ7F), Callbuch bereinigen (v0.9.9)

## v0.9.8 (2026-10-04)
- KST-Reconnect nach Netzausfall, Rufzeichen-Suffix -2/-3 entfernt, Standort-Auswahl, Rundruf verbessert (v0.9.8)
  - KST-Client verbindet sich nach Internetausfall wieder: Sitzung endet bei
    Verbindungsabbruch sofort (statt ewig auf ein Kommando zu warten), Wächter
    erkennt stille Ausfälle, Kommandodrossel gilt je Verbindung.
  - 'DN2LH-2'/'-3' (KST-Mehrfachanmeldung) wird überall als DN2LH geführt;
    vorhandene Callbuch-Einträge mit Suffix werden beim Start zusammengeführt.
  - Mehrere bekannte Standorte eines Rufzeichens erscheinen im Logger als
    anklickbare Auswahl unter dem Formular und im Callbuch in Klammern.
  - Rundruf: Text aus Textbausteinen wählbar, Liste der bereits angeschriebenen
    Stationen, eigene Rufzeichen (Station, KST-Login, 'An mich') ausgeschlossen,
    Knopfzeile ausgerichtet.
- Export/Abgabe deutlicher: Knopf in der Stationsleiste, Export-Karte in der Verwaltung (v0.9.7)

## v0.9.6 (2026-10-04)
- KST-DM: Rufzeichen im Gespräch anklickbar, Knopf '→ Log' (v0.9.6)
  Im DM-Gespräch übernimmt ein Klick auf das Rufzeichen im Kopf, auf den
  neuen Knopf '→ Log' oder auf das Rufzeichen einer Nachricht Call und
  Locator in den Logger. Locator wird aus der Nutzerliste oder der
  Nachricht genommen.

## v0.9.5 (2026-10-04)
- KST je Station, Filter 'an mich' einstellbar, Textbausteine an alle, Import-Zusammenfassung (v0.9.5)
  - ON4KST-Verbindung pro Station: Zugangsdaten, Raum, Autostart und
    'An mich'-Rufzeichen stehen bei der Station (Verwaltung → ✎); jede
    Station hat eigenen Chat, eigene Nutzerliste und DMs. Bisherige globale
    KST-Einstellung wird beim Start auf alle Stationen übernommen.
  - 'An mich' richtet sich nach dem KST-Login bzw. einer einstellbaren
    Liste von Rufzeichen (z. B. DN2LH, DN2LH/P), nicht mehr nach dem
    Stations-Call. Reiter 'An mich' entfällt (DMs decken das ab).
  - Textbausteine im KST-Reiter gehen unadressiert an alle; nur im DM-Reiter
    und beim Rundruf werden Nutzer gezielt angeschrieben.
  - Nutzerliste wird alle 10 Minuten geholt, Rufzeichen mit Locator wandern
    automatisch in die Stationsdatenbank.
  - Ordner-Import zeigt zuerst die Gesamtzahlen (Dateien, Contests, QSOs,
    Rufzeichen neu/bekannt), Details je Datei ausklappbar.

## v0.9.4 (2026-10-04)
- KST-DM: Gespräch zeigt nur Nachrichten zwischen mir und dem Kontakt (v0.9.4)
  Im DM-Tab erscheinen nur noch eingehende Nachrichten des Kontakts an mich
  und eigene Nachrichten an den Kontakt. Nachrichten des Kontakts an Dritte
  oder öffentliche Nachrichten werden nicht mehr angezeigt.
  Fake-KST-Server um /FAKEMSGS für Tests erweitert.

## v0.9.3 (2026-10-04)
- KST-DM als Messenger: Kontaktliste links (nach Aktivität sortiert, ungelesen), Gespräch rechts, Eingabe geht direkt an den Kontakt, neues Gespräch per +
  - Version 0.9.3

## v0.9.2 (2026-10-04)
- KST: DM-Reiter als Gesprächsliste (nach letzter Nachricht sortiert, ungelesen-Zähler), „An mich“ nur eingehende Nachrichten mit Ton/Popup/Badge, größeres Chat-Fenster, Rundruf an ungearbeitete Stationen im Umkreis
  - Version 0.9.2

## v0.9.1 (2026-10-04)
- MDB-Import rein in Python (RC4-entschlüsselte Jet4-Dateien, gebündelter access_parser) – kein mdbtools mehr nötig; Verwaltung: Abschnitte getrennt, lange Namen abgeschnitten; Dialoge über der Karte; Hinweistext und Scoreboard-Karte im Logger entfernt
  - Version 0.9.1

## v0.9.0 (2026-10-04)
- Tests: KST-Client-Test ohne pytest-asyncio
- KST-Nachrichten fließend umbrechen, Seitenleiste etwas breiter
- ON4KST-Chat (Telnet-Client im Server, Reiter KST/An mich/DM, Nutzerliste mit km/Grad, Antworten, Textbausteine, Klick übernimmt Call+Locator), Chat als eigenes Fenster, DARC-Contest-Hub-Direktimport (result.csv aller Jahre)
  - Version 0.9.0

## v0.8.2 (2026-10-04)
- Ergebnislisten-Import (DARC/IARU/UKW-CC: HTML, PDF, Text, URL) mit Vorschau in die Stationsdatenbank; HamQTH-Hinweis (Account nötig); Fußzeile ohne Zusatztext
  - Version 0.8.2

## v0.8.1 (2026-10-04)
- Loggen: Stations-Statistik als kompakte einzeilige Leiste unter der Eingabe, Karte volle Breite
  - Version 0.8.1

## v0.8.0 (2026-10-03)
- Externe Rufzeichen-Abfrage (HamQTH / QRZ.com) mit Caching in der Stationsdatenbank, Einstellungen und Test in der Verwaltung; Roadmap ON4KST-Chat
  - Version 0.8.0

## v0.7.3 (2026-10-03)
- Plausibilitätsprüfung Rufzeichen-Land ↔ Locator (live und in der Log-Prüfung), Locator/km/Grad automatisch aus der Stationsdatenbank beim Eingeben, Export-Bereich sichtbar im Log-Reiter und je Station/Contest in der Verwaltung
  - Version 0.7.3
- Kopfzeile: Copyright entfernt (steht in der Fußzeile)

## v0.7.2 (2026-10-03)
- Eingabe: Leertaste springt Rufzeichen → Nr. erhalten → Locator → Kommentar
- Oberfläche: Karte und Stations-Statistik unter der Eingabe (Chat rückt hoch), laufende Nummer farblich hervorgehoben, Stationen ohne Passwort automatisch freigeschaltet, Contest- und Statistik-Reiter zusammengelegt
  - Version 0.7.2

## v0.7.1 (2026-10-03)
- Stationsdatenbank: mitgelieferte Startdaten aus den eigenen WinContest-Logs (beim ersten Start geladen), ganzen WinContest-Ordner im Browser importieren, durchsuchbare Call-Liste in der Verwaltung
  - Version 0.7.1
- Tests: Datenbank sauber schließen (Windows-Dateisperren), tmp_path statt TemporaryDirectory; Build-Matrix ohne fail-fast
- Build-Workflow: Release auch bei manuellem Start, Tag aus der Versionsnummer

## v0.7.0 (2026-10-03)
- Build-Workflow: Release-Rechte und Release-Beschreibung
- Builder: portable Einzeldateien (Server, CAT-Bridge, Import) per PyInstaller, ZIP-Paket, build.bat/build.sh, GitHub-Workflow für Windows/Linux/macOS
  - Portabler Build legt data/ neben der ausführbaren Datei an und öffnet unter Windows den Browser
  - Version 0.7.0
- Mehrsprachigkeit (Deutsch/Englisch, eigene Sprachen per JSON in data/lang), Sprachauswahl, Übersetzungsvorlage; README
  - Version 0.6.0
- Karte (Leaflet lokal gebündelt): Großkreis-Pfeil vom eigenen zum Partner-Locator, alle QSOs als Punkte, Kachel-URL einstellbar
- Contest-Statistik: SQL-Spaltenname eindeutig gemacht
- Contest-Ansicht: globale Statistik über alle Stationen/Bänder, Stundenverlauf je Band, Live-Feed, Großanzeige-Modus
- Tastatur-Makros F1–F8 mit Platzhaltern, F9-Übersicht, Editor je Station, CW-Ausgabe über CAT-Bridge (--cw), Esc stoppt
- Log-Prüfung (Pflicht vor EDI-Export): Fehler/Hinweise je QSO, Admin kann erzwingen; ZIP-Export aller Bänder eines Contests
- Töne (QSO/Dupe/Chat/andere Station, abschaltbar) und QR-Code mit Server-Adresse
- Backups automatisch auf dem Server (Intervall, beim Beenden, manuell), atomar geschrieben; SQLite synchronous=FULL
- Multi-Band-Gesamtwertung, CAT-Bridge (rigctld/flrig), Backup-Download, Countdown, weltweite DXCC-Präfixe; Debian-Deployment
  - deploy/: systemd-Unit, nginx-Site (HTTP + optional HTTPS), install.sh, tägliches Backup per Cron
  - Frequenz je QSO gespeichert und im ADIF (FREQ) exportiert
  - Version 0.5.0
- Start-Skripte für Windows/Linux; Tabelle nach Freischalten/Admin-Login sofort aktualisieren
  - start.bat / start.sh legen eine venv an und starten den Server
  - Version 0.4.1
- Web-Frontend: Loggen mit Vorschlägen, Live-Scoreboard, Chat, Statistik, Verwaltung; Bulk-Import-Tool; README
  - Responsives Layout, Hell/Dunkel, UTC-Uhr, Version und Copyright im Kopf
  - Vorschläge aus Call-Buch + alten Logs mit km/Grad und Dupe-Hinweis
  - QSO bearbeiten/löschen, Seriennummer rücksetzen, EDI/ADIF/CSV-Export
  - tools/import_dd3ku.py importiert einen ganzen WinContest-Ordner
  - Version 0.4.0
- Server: FastAPI-REST-API, WebSocket-Hub für Live-Updates/Chat/Anwesenheit, Import/Export-Endpunkte
  - Admin-Setup beim ersten Start, Stationen mit Passwort freischalten (Token)
  - Nicknames ohne Accounts (X-Nick), Operator wird je QSO gespeichert
  - run.py zeigt LAN-Adresse an
  - Version 0.3.0
- Import/Export: DD3KU TXT/EXP/MDB, EDI (REG1TEST), ADIF, Call-Listen; Band-Normalisierung
  - Alle Formate gegen die echten WinContest-Dateien (111 QSOs) geprüft
  - EDI-Export mit Wertung (CQSOs, CQSOP, CWWLs, CDXCs, CODXC)
  - Version 0.2.0
- Kern: Locator-Geometrie, DXCC-Präfixe, SQLite-Datenmodell mit Contests/Stationen/QSOs/Call-Buch
  - Entfernung wie WinContest (angefangene km, verifiziert gegen DD3KU-Log)
  - Dupe-Erkennung je Call/Band, automatische Seriennummer, Call-Buch lernt aus Logs
  - Version 0.1.0

