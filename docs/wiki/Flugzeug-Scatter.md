# Flugzeug-Scatter (ADS-B)

![Karte mit Flugzeugen](img/karte-flugzeuge.png)

Wie AirScout zeigt ContestLogger Flugzeuge zwischen dir und dem Partner und bewertet, ob sie für Aircraft-Scatter taugen. Einschalten mit **✈ Flugzeuge** an der Karte (Logger und Operator-Fenster); die Einstellung bleibt gespeichert, Aktualisierung alle 5 Sekunden.

## Darstellung

- **Grüner Balken** auf dem Pfad: Zone gemeinsamer Sichtbarkeit bei Reiseflughöhe – nur dort kann ein Flugzeug von beiden Stationen über dem Funkhorizont gesehen werden.
- **Orange Flugzeuge**: im Korridor (Standard ±12 km um den Pfad) und von beiden Stationen sichtbar – die nutzbaren.
- **Hellblau**: beidseitig sichtbar, aber außerhalb des Korridors. **Grau**: nicht von beiden sichtbar.
- Liste unter der Karte: Flug, Typ, Flugfläche, Abstand vom Pfad, Position auf dem Pfad (km ab eigener Station) und Flugzeuge, die den Pfad in den nächsten 15 Minuten kreuzen („kreuzt in ~6 min“).
- Ohne Partner-Locator: Flugzeuge im Umkreis von 150 km um die eigene Station.

Flugzeuge am Boden und unter 1500 m werden ignoriert.

## Datenquellen (Verwaltung → Flugzeug-Scatter)

![Einstellungen Flugzeug-Scatter](img/adsb-einstellungen.png)

| Quelle | Hinweise |
|---|---|
| **adsb.fi** (Standard) | Frei, ohne Schlüssel, nicht-kommerziell, max. 1 Abfrage/s, Daten © adsb.fi. Der Server fragt nur, solange die Ebene in einem Browser eingeschaltet ist, und cached 4 s. |
| **Eigener Empfänger** | dump1090/readsb/tar1090: `http://<host>:8080/data/aircraft.json`. Gleiches Format, keine Internetabhängigkeit. |

Weitere Einstellungen: Korridorbreite (± km) und Antennenhöhe (geht in den Funkhorizont ein).

## Rechnung

Funkhorizont für ein Flugzeug in Höhe h: `d ≈ 4,12 · (√h + √Antennenhöhe)` km (4/3-Erde). Die Zone gemeinsamer Sichtbarkeit ist der Teil des Pfads, der von beiden Stationen innerhalb dieses Horizonts liegt. Für jedes Flugzeug: Querabstand zum Großkreis, Position entlang des Pfads, Entfernung zu beiden Stationen, und aus Kurs und Geschwindigkeit die Zeit bis zum Kreuzen.

**Grenzen gegenüber AirScout:** kein Geländemodell (Berge im Pfad bleiben unberücksichtigt) und keine Vorhersage über die reine Kreuzungszeit hinaus. Andere Quellen wie airplanes.live (nur auf Anfrage) oder OpenSky (anonym 400 Abfragen/Tag) sind deshalb nicht eingebaut.
