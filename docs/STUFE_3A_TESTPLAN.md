# Stufe 3A – Einzellampen am Taster

## Gebaut

- `toggle_lights`, `turn_on_lights` und `turn_off_lights` erwarten
  `params.entity_ids`: eine nicht leere Liste freigegebener Einzellampen oder
  freigegebener Lichtschalter. Ziele dürfen aus mehreren Räumen oder ohne Raumzuordnung stammen.
  Der Raum des Tasters begrenzt die Auswahl nicht. Die gespeicherte `area_id` ist bei
  einer ausdrücklichen Zielauswahl `null`.
- Bei `toggle_lights` genügt ein eingeschaltetes ausgewähltes Ziel, auch ein Switch,
  um alle ausgewählten verfügbaren Ziele auszuschalten. Andernfalls werden alle eingeschaltet.
- Helligkeit und Farbe eingeschalteter Lampen werden vor dem Ausschalten im serverseitigen
  Store unter `settings.last_light_states` gesichert. Bereits ausgeschaltete oder nicht
  verfügbare Ziele überschreiben keine gespeicherten Werte. Auch Raum-Aus, Einzellampen-Aus
  im Panel und ausschaltende Snapshot-Szenen aktualisieren diesen gemeinsamen letzten Zustand.
  Reine Switch-Lichter erhalten nur `turn_on`/`turn_off`, nie Farb- oder Helligkeitsparameter.
- Bereits eingeschaltete Lampen behalten bei `turn_on_lights` ihre aktuellen Werte. Fehlt ein
  gespeicherter Zustand, wird ein vorhandener Raum-Vor-Aus-Zustand verwendet; sonst erfolgt
  ein normaler Einschaltbefehl ohne erfundene Farbwerte. Geräteeigene Zustandswiederherstellung
  bleibt dann dem Gerät überlassen. Externe Ausschaltvorgänge außerhalb der Integration werden
  nicht zusätzlich beobachtet.
- `dim_up` und `dim_down` akzeptieren optional dieselbe Auswahl. Ohne `entity_ids` bleibt
  das bisherige Dimmen im Zielraum erhalten. Mit Auswahl werden ausschließlich eingeschaltete,
  dimmbare `light.*`-Entities um 10 % verändert. `switch.*` wird **immer übersprungen**, auch wenn
  die Entity Helligkeitsattribute meldet.
- Der Tastereditor zeigt große Checkboxen nach Raum und „Ohne Raum“ gruppiert. Nicht mehr
  freigegebene oder gefundene Ziele verhindern das Speichern, bleiben aber entfernbar.
  Es wird erst nach bestätigter Serverantwort ein Speichern gemeldet.

## Sicherheit und Nebenläufigkeit

- Die gesamte Auswahl wird vor Änderungen geprüft: keine Gruppen, fremden Domains,
  nicht freigegebenen Ziele oder fachfremden Schalter. Leere oder falsch typisierte Listen
  werden abgewiesen. Doppelte IDs werden zusammengeführt.
- Überlappende Auswahlen und Szenen/Raumsteuerung werden über geordnet erworbene Sperren
  serialisiert. Nach Wartezeiten und unmittelbar vor jedem Serviceaufruf werden Freigabe,
  Geräte-Eignung, Verfügbarkeit und Raumzuordnung erneut geprüft.
- Vor manuellen Aktionen auf ausgewählte Lampen wird lokale Dynamik in den betroffenen
  Lampenräumen gestoppt und ihr laufender Task beendet. Nicht ausgewählte Geräte erhalten
  dabei keinen Schalt- oder Freeze-Befehl. Reine Switch-Auswahlen stoppen keine Lampendynamik.
- Ein Fehler beim Sichern des Vor-Aus-Zustands verhindert die Ausschaltbefehle. Ändern sich
  Zustand oder Fähigkeiten während der Speicherung/Dispatch-Wartezeit, wird das betroffene
  Ziel übersprungen statt mit veralteten Werten ausgeschaltet. Ein Gerätefehler verhindert
  nicht die übrigen zulässigen Serviceaufrufe.
- Erfolgreicher Serviceaufruf ist keine vorweggenommene Zustandsbestätigung: weitere
  Toggle-Aktionen beurteilen weiterhin den tatsächlich gemeldeten Home-Assistant-Zustand.

## Automatisierte Prüfung

```sh
npm run typecheck
npm run lint
npm test
npm run build
ruff check custom_components tests scripts
pytest -q
.venv-ha-2026-11/bin/python scripts/smoke_target.py
```

- Python: **441 Tests erfolgreich** auf Home Assistant 2026.10.4.
- Frontend: **77 Tests erfolgreich**, TypeScript, ESLint und Produktionsbuild erfolgreich.
- Home Assistant **2026.11.0**: nativer Smoke-Test erfolgreich, erweitert um echte synthetische
  Taster-Ereignisse, raumübergreifendes Lampen-/Switch-Toggle, Store-Neuladen, Farb-/Helligkeits-
  Wiederherstellung und selektives Dimmen ohne Switch-Aufruf.
- Eigenständige Switch-Dimm-Regression: beide Aktionen und Switch-Zustände an/aus mit
  vorgetäuschten Dimmfähigkeiten. Alle vier Fälle überspringen den Switch ohne Serviceaufruf.
- Erneuter Frontend-Build erzeugt bytegleiche Dateien; Bundle wird eingecheckt.
- Vollständiges hassfest scheitert lokal am Start eines Prozess-Sockets für die
  Dependency-Prüfung (`PermissionError: Operation not permitted`). Die separat ausführbaren
  Manifest-, JSON-, Services-, Übersetzungs- und Config-Flow-Prüfungen sind erfolgreich.
  Vollständiges hassfest und HACS bleiben dem GitHub-Workflow vorbehalten.
- Keine Live-Geräte kontaktiert; keine visuelle Browser-/Handy-Abnahme durchgeführt.
  Nach Öffnen des Draft-PR keine weitere Änderung, Prüfung oder CI-Überwachung.

## Manuelle Abnahme auf einem Testsystem

1. Branch installieren und Home Assistant neu starten. Bestehende Raumbelegungen bleiben erhalten.
2. Im Tastereditor für `toggle_lights` zwei Lampen aus verschiedenen Räumen und einen Lichtschalter
   wählen. Neue Belegung speichern und nach Neuladen prüfen.
3. Ein Ziel einschalten, die anderen ausschalten: Tastendruck schaltet alle aus. Zweiter Druck nach
   bestätigtem Aus schaltet alle ein. XY-Farbe, Weißtemperatur und Helligkeit werden passend zum
   jeweiligen Gerät wiederhergestellt. Switch erhält nur einen Ein/Aus-Befehl.
4. Mehrfach ausschalten, Home Assistant neu starten, danach einschalten: gespeicherte Werte bleiben
   erhalten. Ebenso nach neuer Farbwahl und anschließendem Raum-Aus oder Snapshot-Aus prüfen.
5. `turn_on_lights`/`turn_off_lights` getrennt prüfen; bereits eingeschaltete Lampen nicht auf einen
   älteren Zustand zurücksetzen. Nicht verfügbare Geräte werden übersprungen.
6. `dim_up`/`dim_down` mit ausgewähltem Switch und dimmbarer Lampe prüfen: nur die eingeschaltete
   Lampe ändert sich. Nur Switch auswählen: keine Schaltaktion. Dimmziel „Ganzer Zielraum“ prüft
   das unveränderte bisherige Verhalten.
7. Freigabe entziehen oder Lampe in einen anderen Raum verschieben, während eine Aktion wartet:
   alte Ziele dürfen nicht unkontrolliert geschaltet werden. Nicht mehr freigegebene Auswahl im
   Editor sichtbar entfernen und neu speichern.
8. Lokale Dynamik starten, dann ausgewählte Lampen schalten: betroffene Raumdynamik endet, keine
   zusätzlichen Geräte werden geschaltet. Unterschiedliche Taster mit überlappenden Raumlisten
   rasch betätigen; keine hängenbleibenden Aktionen.
9. Auf schmalem Handybildschirm Auswahlgruppen, Checkboxen, Abbrechen, wiederholtes Speichern,
   fehlgeschlagenes Speichern und Neuladen prüfen. Raum-/Einzellampen-Dimmwechsel sendet nur
   die passenden Parameter.

## Bewusst nicht enthalten

Stufe 3B, Zeitpläne, Live-Installation, Merge, Release, CI-Überwachung nach dem Draft-PR und
zusätzliche Beobachtung externer Lichtsteuerungen.
