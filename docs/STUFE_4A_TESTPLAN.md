# Stufe 4a – Zeitfenster für Zeitpläne

## Gebaut

- Optionale Bedingung `condition.time_window`: `null` oder ein Objekt mit `after`
  und `before`, jeweils `null`, lokale Uhrzeit oder Sonnenereignis mit Minutenversatz.
- Beginn inklusive, Ende exklusive. `22:00` bis `06:00` läuft über Mitternacht.
  Gleiche Grenzen bedeuten ganztägig. Eine offene Seite reicht bis/von lokaler
  Mitternacht des aufgelösten Grenzdatums. Zwei offene Seiten werden zu `null`.
- Sonnenversatz bleibt bei −1440 bis +1440 Minuten und zählt reale vergangene
  Minuten. Fehlende Sonnenereignisse sperren das betreffende Fenster.
- Lokale Zeitlücken entfallen. Bei doppelter Uhrzeit gilt die erste Grenze;
  absolute Zeitvergleiche halten das Fenster während der zurückgestellten Stunde
  konsistent. Wochentage beziehen sich auf den tatsächlichen Ausführungstag.
- Lux muss weiterhin die konfigurierte Mindestdauer ununterbrochen erfüllen.
  Wird sie vor Fensterbeginn erfüllt, bleibt der Plan wartend und prüft zum
  Fensterbeginn erneut, auch ohne weiteres Sensorereignis. Aufhellung, Gleichheit,
  ungültige Werte oder fehlende Verfügbarkeit verwerfen diese Wartephase.
- Lux-Pläne **mit** Zeitfenster starten automatisch höchstens einmal pro lokalem
  Kalendertag, auch nach Neustart oder erneuter Schwellenunterschreitung. Bei
  dauerhaft erfülltem Lux wird die nächste zulässige Tagesausführung geplant.
  Bei einem Nachtfenster ist Mitternacht ein neuer Kalendertag, kein neuer Abend.
  Die tägliche Reservierung wird vor der Aktion gespeichert. Ein Fehler oder
  Teilfehler danach wird vorsichtshalber nicht am selben Tag automatisch wiederholt.
- Bestehende Pläne erhalten beim Laden einmalig `time_window: null`; andere Daten
  bleiben erhalten. Pläne ohne Fenster behalten die bisherige Lux-Auslöselogik.
- Deutsche Oberfläche mit „Nur zwischen … und …“, offenen Grenzen, Uhrzeit oder
  Sonnenstand plus Versatz und Zusammenfassung direkt in der Übersicht.
- „Jetzt testen“ ignoriert Auslöser, Aktivierung und Tageslimit, prüft jedoch
  weiterhin alle Bedingungen einschließlich des Zeitfensters. Laufende dynamische
  Szenen enden nicht automatisch am Fensterende; das Fenster begrenzt ihren Start.

## Automatische Prüfung

Ausschließlich synthetische Geräte und isolierte Home-Assistant-Testinstanzen:

1. Validierung und Migration: Altformat, fehlende/null/offene Grenzen, ungültige
   Werte, unbekannte Felder, atomarer Speicherfehler, erneutes Laden.
2. Tages- und Nachtfenster: Anfang/Ende, Mitternacht, Wochentage, Sonnenversatz,
   fehlende Sonnenereignisse, Sommerzeitlücke und doppelte Herbststunde.
3. **Fall 3:** Sensor fällt vor dem Fenster unter die Schwelle, Mindestdauer ist
   erfüllt, bis zum Fensterbeginn entsteht kein neuer Sensorwert. Genau dann
   erfolgt eine Ausführung, falls der aktuelle Wert weiterhin passt. Erneutes
   Über-/Unterschreiten am selben Tag löst nicht nochmals aus.
4. Lux-Unterbrechung während Wartephase oder asynchroner Aktionsvorbereitung,
   neue Mindestdauer, Neustart-Tageslimit, Bearbeiten/Deaktivieren/Löschen.
5. Oberfläche: Uhrzeit und Sonnenstand, Versatz, einseitige Fenster, Speichern,
   erneutes Bearbeiten/Neuladen, Abbrechen, Fehlerantwort und Ausschalten der Bedingung.

Befehle: `python -m pytest -q`, `ruff check custom_components tests scripts`,
`npm run typecheck`, `npm run lint`, `npm test`, `npm run build`.
Zielversions-Smoke-Test separat mit `requirements-ha2026.11.txt` und
`python scripts/smoke_target.py`.

## Bewusst nicht ausgeführt

Keine Verbindung zur echten Installation, keine echten Geräteaktionen, keine
Bereitstellung oder Zusammenführung. Claude übernimmt die praktische Abnahme.
Nach Öffnen des Draft-PR endet diese Arbeit einschließlich CI-Überwachung.
