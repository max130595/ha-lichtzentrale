# Prüfliste Stufe 0

## Umfang

- Domain, Config Flow und lokales Panel `lichtzentrale`, eine Instanz.
- Fünf deutsche Reiter; Galerie ist funktional, weitere Reiter erklären ihren späteren Ausbau.
- Zwölf eigene Paletten in vier Kategorien; Farbverläufe statt Bilder.
- Explizite, serverseitige Freigabe von Einzellampen. Keine vorab ausgewählten Geräte.
- Native Store-Struktur, Setup/Unload/Reload, lokales Frontend-Bundle und HACS-Metadaten.
- GitHub-Prüfungen für Frontend, Bundle, Python, Zielversions-Smoke-Test, hassfest und HACS.

Nicht enthalten: Räume-Steuerung, Schalter-Steuerung, eigene Szenen/Paletten,
Hue-Szenenimport, dynamische Szenen, Adaptive Lighting, Tasterbelegungen und Zeitpläne.

## Automatisierte Prüfläufe

Siehe [README](../README.md) für Befehle und festgelegte Abhängigkeiten.

- 69 Python-Tests mit `pytest-homeassistant-custom-component` und HA 2026.10.4:
  Store-Erststart, Laden, Entfernen, Fehler beim Speichern, Datenerhalt und Kopierschutz;
  Config Flow/Einzelinstanz; echtes Setup/Unload/Reload einschließlich Panel, statischem
  Pfad und Service; zwölf Paletten; XY/RGB/RGBW/RGBWW/HS, begrenzte Farbtemperatur,
  Helligkeit und An/Aus; unbekannte/nicht verfügbare Lampen; Kontextweitergabe;
  Sperre nicht freigegebener Lampen, Gruppen und fremder Domains; Bereichsauflösung;
  WebSocket-Protokoll, Adminschutz und Eingabevalidierung.
- 12 Frontend-Tests: Laden/erneuter Versuch, fünf Reiter, gespeicherte Freigaben,
  Fehler beim Speichern/Anwenden, nicht verfügbare Lampen, genaue Anfrageparameter,
  Schutz vor doppelten Klicks, Teilergebnisse, geänderte Freigaben, Unmount/Reconnect.
- TypeScript, ESLint und Ruff.
- Wiederholter Produktionsbuild: Bundle und beide Lizenzdateien byteidentisch.
- Separater Smoke-Test mit echten HA-2026.11-APIs ohne alte pytest-Fixtures.

Die verfügbare pytest-Fixture-Version 0.13.375 ist auf HA 2026.10.4 abgestimmt.
Ein Override auf HA 2026.11 scheitert bereits vor Testbeginn, weil die Fixtures einen
entfernten privaten Logger-Namen importieren. Das ist keine bestandene 2026.11-Testsuite.

## Noch am echten Testsystem prüfen

Nicht gegen das produktive Haus testen, bevor der Branch geprüft wurde.

1. Integration über HACS nach Zusammenführung installieren, HA neu starten und Log prüfen.
2. Lichtzentrale hinzufügen: genau ein Eintrag, Seitenleiste mit `mdi:lightbulb-group`.
3. Mobil und am Desktop öffnen: Navigation bleibt innerhalb des Panels; lange Namen
   umbrechen; kein horizontaler Bildlauf; Lichtauswahl und Regler mit Tastatur bedienbar.
4. Alle fünf Reiter, Galerie scrollen, Palette wählen, Abbrechen/erneut öffnen und
   HA-Seitenleiste testen. Browser-Zurück/Vorwärts und erneutes Öffnen prüfen.
5. Ausdrücklich nur Testlampen freigeben. Gruppenlampen dürfen nicht erscheinen.
   Drucker-/Funktionsbeleuchtung nicht freigeben.
6. Eine Farb-, Weißton-, dimmbare und reine An/Aus-Testlampe anwenden. Nur erlaubte,
   ausgewählte Lampen dürfen reagieren; Weißton bleibt im Gerätebereich.
7. Testlampe nicht verfügbar machen: übersprungen melden; keinen Gesamterfolg vortäuschen.
8. Service-Fehler simulieren: Fehlermeldung prüfen. Bereits zuvor angewendete Lampen
   können verändert sein; der Vorgang ist keine atomare Transaktion.
9. Freigabe entfernen, Panel und Integration neu laden, HA neu starten: Freigabe bleibt
   entfernt; keine doppelten Routen, Sidebar-Einträge oder Services.
10. Als Nicht-Administrator prüfen: kein Panel und keine nutzbare Lichtzentrale-API.
11. Ohne Adaptive Lighting starten: keine Fehler oder leeren Adaptive-Bedienelemente.
12. Integration entfernen: Panel/Service weg und eigener Store entfernt.

## Grenzen des aktuellen lokalen Prüflaufs

- Kein Kontakt zu produktivem Home Assistant und keine Lampen im Haus verändert.
- Die lokale Browserdarstellung konnte wegen fehlender Socket-Unterstützung der
  Ausführungsumgebung nicht gestartet werden; Unit-Tests ersetzen keine Sichtprüfung.
- hassfest auf HA-2026.11-Quellen lief mit Ausnahme des Dependencies-Plugins ohne
  Befund. Das Dependencies-Plugin benötigt hier nicht verfügbare Multiprocessing-Sockets.
  Der vollständige hassfest- und HACS-Lauf erfolgt im GitHub-Workflow.
- Die Mindestversion HA 2026.7 ist vorgesehen, aber noch nicht separat getestet.
