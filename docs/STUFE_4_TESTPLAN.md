# Stufe 4: Zeitpläne und Übergänge

Dieser Branch ist eine Grundlage zur Abnahme. Alle automatisierten Tests nutzen ausschließlich
synthetische Räume und Geräte, aufgezeichnete Serviceaufrufe und temporäre Store-Dateien.
Kein Entwicklungstest schaltet reale Geräte. Die Prüfung am echten Home Assistant übernimmt
Claude nach Öffnen des Draft-PR; danach werden keine Änderungen oder CI-Prüfungen fortgesetzt.

## Automatische Prüfungen

```sh
npm ci
npm run typecheck
npm run lint
npm test
npm run build
ruff check custom_components tests scripts
python -m pytest -q
```

Die Pytest-Fixtures aus `requirements-test.txt` verwenden HA 2026.10.4. Der eigenständige
Smoke-Test in einer separaten Umgebung mit `requirements-ha2026.11.txt` prüft die Zielversion:

```sh
python scripts/smoke_target.py
```

Der gebaute Stand in `custom_components/lichtzentrale/frontend/` wird eingecheckt. Ein erneuter
Build muss diesen Stand unverändert lassen. hassfest/HACS laufen im vorhandenen GitHub-Workflow;
es gibt nach dem Draft-PR bewusst keine lokale CI-Überwachung.

## Lokal geprüfter Stand

- Python 3.14 / Home Assistant 2026.10.4: 612 Tests bestanden.
- Frontend: 103 Tests bestanden, TypeScript und ESLint ohne Fehler.
- Nativer Smoke-Test auf Home Assistant 2026.11.0 bestanden.
- Frontend-Build erfolgreich; webpack meldet nur seine Größenempfehlung für das Bundle.
- Keine realen Geräte, kein Live-HA-Zugriff und keine Änderungen am laufenden System.

## Daten und API

Jeder Plan enthält `id`, `name`, `enabled`, `trigger`, `condition`, `action`, `transition`.
Die geschlossenen Schemas lehnen unbekannte Felder, ungültige Zahlen, fremde Domains und
nicht freigegebene Ziele ab. IDs und Entity-Auswahlen stammen ausschließlich aus HA zur Laufzeit.

- `schedules/list`: Pläne mit `next_run` (ISO oder null), `last_error`, Lux-Sensoren, Personen
  und `time_zone`. Die Oberfläche zeigt HA-Zeit an, auch bei einer anderen Browser-Zeitzone.
- `schedule/save`: vollständiges `schedule`; neue Pläne ohne ID, Bearbeitung mit vorhandener ID.
- `schedule/set_enabled`: `schedule_id`, `enabled`; ungültig gewordene Pläne bleiben deaktivierbar.
- `schedule/delete`: `schedule_id`; alte Bearbeitungsstände können gelöschte IDs nicht neu anlegen.
- `schedule/test`: `schedule_id`; einmalige echte Aktion, auch bei deaktiviertem Plan, unter
  Beachtung der Bedingungen. Antwort: `condition_met`, `applied`, `skipped`, optional `failed`.

Alle Befehle erfordern einen Administrator. Store-Schreibfehler verändern weder den bestätigten
Stand noch laufende Timer. Beim Entladen oder Ändern werden Timer und wartende Befehle verworfen.
Nicht erreichte Termine werden nach Neustart nicht nachgeholt. Neue Lux-Pläne beginnen ihre
Mindestdauer erst nach vollständigem HA-Start. Laufzeitfehler sind im Plan sichtbar.

## Auslöser und Bedingungen

1. Uhrzeit: synthetische Lampenauswahl in einem Testbereich, Zeit wenige Minuten in die Zukunft.
   Neue Pläne ausgeschaltet; aktivieren, nächste Zeit prüfen, einmalige Ausführung erwarten.
2. Sonne: Sonnenaufgang und Sonnenuntergang mit negativem, null und positivem Minutenversatz.
   Über Mitternacht verschobene Termine nutzen den Wochentag des tatsächlichen Ausführungsdatums.
   Ein nicht vorhandenes Sonnenereignis führt nicht zu einem erfundenen Termin.
3. Sommerzeit: nicht existierende Uhrzeit überspringen, doppelte Uhrzeit genau einmal ausführen.
   Die nächste Anzeige und der Timer verwenden dieselbe Zeitzone.
4. Lux: synthetischen Illuminanzsensor mit `lx` auswählen; unter und über einer Schwelle testen.
   Kürzer als die Mindestdauer wechseln: keine Aktion. Ununterbrochen fünf Minuten: eine Aktion.
   Weitere Werte auf derselben Schwellenseite: keine Wiederholung. Erst Verlassen und erneutes
   Erfüllen startet einen neuen Lauf. Gleichheit setzt zurück; ungültige, negative, nicht verfügbare
   oder wiederhergestellte Werte blockieren. Nach Neustart volle Dauer abwarten.
5. Wochentage: nur ein ausgewählter Tag darf auslösen. Leere Auswahl wird im Editor blockiert.
6. Anwesenheit: mindestens eine gewählte Person muss `home` melden. Leere Auswahl deaktiviert die
   Bedingung. Fehlende oder unbekannte ausgewählte Personen blockieren vorsichtshalber.
7. Lampenstatus: „an“ heißt mindestens ein Ziel an, „aus“ heißt alle Ziele aus. Nicht verfügbare
   Ziele blockieren. Änderungen während des Wartens auf eine Raum-/Lampen-Sperre werden vor
   der Aktion erneut geprüft; eigene Änderungen während derselben Aktion blockieren nicht den Rest.
8. „Jetzt testen“: Auslöser und Ein/Aus des Plans werden übergangen, Bedingungen nicht. Eine
   blockierte Ausführung bekommt keine falsche Erfolgsmeldung. Doppelklick während eines
   laufenden Befehls darf keinen zweiten Auftrag erzeugen.

## Aktionen und Übergänge

- Snapshot-Szene: Lichtfarbe/Helligkeit und gespeicherte Schalter-An/Aus-Zustände wiederherstellen.
- Statische und dynamische Palette: freigegebene Einzellampen; Switch-Lichter bleiben unberührt.
  Startübergang 1800 Sekunden: erster dynamischer Tick frühestens nach Ende des Übergangs;
  spätere Ticks behalten das Szenenintervall und den Szenenübergang.
- Hue-Szene: vorhandenen geprüften Hue-V2-Aufruf mit `transition` verwenden. Native Dynamik bleibt
  gemäß importierter Szene aktiv. Das tatsächliche Bridge-/Lampenverhalten prüft Claude.
- Natürliches Licht an/aus: nur vorhandene geprüfte AL-Zuordnung verwenden. Es ist ein
  Automatikschalter, kein Raum-an/aus. Ausgeschaltete Lampen bleiben aus. Ein Übergang wird an
  den finalen AL-Apply-Aufruf weitergegeben; AL kann bei bereits eingeschalteten Lampen zuvor
  seinen konfigurierten Anfangsübergang anwenden. Keine Änderungen an den AL-Einstellungen.
- Raum aus: laufende lokale Dynamik stoppen, Vor-Aus-Zustände behalten, freigegebene Lichtziele
  ausschalten; späteres Wiedereinschalten behält die bestehende Wiederherstellungslogik.
- Lampenauswahl: explizite Ziele auch über Bereiche hinweg; optional Helligkeit 1–255 beim
  Einschalten. Ohne Helligkeit bleiben bisherige Wiederherstellungswerte erhalten. Ausschalten
  erlaubt keinen Helligkeitswert. Reine Switch-Ziele erhalten nur Ein/Aus.
- Bewegungsautomatik: vorhandene Raumkonfiguration aktivieren/deaktivieren, ohne dabei direkt
  Lampen zu schalten. Vorhandene Timer/Besitzansprüche der Bewegungsautomatik werden verworfen.
- Übergänge: null übernimmt das bisherige Verhalten, 0 ist sofort, 1800 ist die Obergrenze.
  Übergänge werden nur für unterstützende `light`-Entities verwendet. `switch`-Entities erhalten
  weder Helligkeit noch Farbe noch Übergang. Das Gerät kann physisch eigene Grenzen haben.
- Stufe-3b-Korrektur: reine Switch-Auswahl (auch ganzer Switch-Raum) akzeptiert fehlende oder
  null-Helligkeit. Bei gemischten oder reinen Lampenzielen bleibt ein Wert 1–255 erforderlich.

## Oberfläche, Persistenz und Grenzen

- Auf schmalem Bildschirm: Auslöser, Sensoren/Personen, Aktionen und Lampengruppen gut bedienbar.
- Speichern, Abbrechen, Löschen und Neu laden; fehlgeschlagene Schreibvorgänge behalten Entwurf
  und bestätigten Zustand. Veraltete Poll-Antworten überschreiben keinen neueren Schreibstand.
- Neu laden/HA-Neustart: gespeicherte Pläne bleiben, abgebrochene Timer werden nicht nachgeholt.
- Optionales Adaptive Lighting fehlt: keine auswählbare neue AL-Aktion, gespeicherte ungültige
  Auswahl sichtbar und korrigierbar. Keine zusätzlichen Python-Requirements.
- Nicht automatisch geprüft: echte Hardware-Fades, Hue-Bridge-Dynamik, Live-AL-Verhalten,
  tatsächliche HACS-Installation und visuelle Darstellung im echten HA-Panel.
