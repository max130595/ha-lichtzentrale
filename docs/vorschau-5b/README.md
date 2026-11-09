# Lichtzentrale: klickbare Handy-Vorschau

**Teil 1 von Stufe 5b, nur zur Freigabe der Bedienung.**

[Index herunterladen](index.html) und im Browser öffnen. Die einzelne HTML-Datei enthält
alles, funktioniert offline und steuert keine Geräte. Keine Installation, kein Konto und
keine Verbindung zu Home Assistant nötig. Alle Änderungen verschwinden beim Neuladen.

Fünf Reiter: **Zuhause, Farben, Automationen, Taster, Mehr**. Räume und Zonen direkt
schalten/dimmen, eine Sonnenuntergangs-Automation erstellen, die Dimmer-Vorlage belegen
und Nachtlicht ⇄ Automatik über Taster oder Automationen ausprobieren. Die Beispiele sind vollständig synthetisch.

- [Wo landen bisherige Funktionen?](../STUFE_5B_FUNKTIONSZUORDNUNG.md)
- [Prüfschritte und offene Tests für Teil 2](../STUFE_5B_TESTPLAN.md)

## Überarbeitung nach Rückmeldung zu PR #12

- Zonen zuerst, kompakte Raumkacheln ohne Werbetexte.
- Ziele nur einmal für die erste Aktion; zusätzliche Aktionen mit eigener Zielauswahl.
- Aktionen strikt nacheinander, auch bei überlappenden Zielen.
- Schalter rechts in der Automationenliste.
- Sichtbares „+ Neue Szene“ mit Lampeneinstellungen und Namen; kleiner Nachtlichtknopf.
- Reiter „Farben“; Szenenfeld am Taster nur bei Aktion „Szene“.

## Prüfung dieses Entwurfs

Nach `npm ci` im Projektstamm:

```sh
node --test docs/vorschau-5b/preview.check.cjs
```

22 Tests prüfen die Kernabläufe, optionale Funktionen, Schalter-Ausnahmen und die Trennung
von Netzwerk und Browser-Persistenz. Die Prüfbreiten 320, 390 und 430 sind über
`?width=320`, `?width=390` und `?width=430` an der Adresse wählbar. Die feste Reiterleiste
und die Karten sind auf den Handyrahmen begrenzt.

**Nicht behauptet:** Eine visuelle Browser-/Screenshot-Abnahme konnte in der aktuellen
Prüfumgebung nicht stattfinden, weil der Prüfbrowser den lokalen Server nicht erreicht.
Die Tests prüfen DOM-Verhalten, keine Pixel oder echte Touchbedienung. Bitte die Ansicht
bei der Freigabe im eigenen Handy-Browser ansehen.

Erweiterte Bewegung, Grundhelligkeit, Dynamik und importierte Bridge-Szenen zeigen in
Teil 1 nur ihre geplante Platzierung. Kalender-/Sonnenberechnung, dauerhafte Speicherung,
Store-Migration, echte Ereigniserkennung und Gerätesteuerung gehören erst zur separat
freizugebenden Umsetzung. Der produktive Code bleibt in diesem PR unverändert.
