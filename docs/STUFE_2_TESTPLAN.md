# Stufe 2: Prüfliste für Dynamik und natürliches Licht

Die lokalen Prüfungen verwenden synthetische Entities. Die Live-Prüfung übernimmt Claude
nach Öffnen des Entwurfs-PR. Es erfolgt keine automatische Installation, kein Merge und
keine Steuerung des echten Hauses durch diesen Entwicklungsauftrag.

## Automatisch vor der Übergabe

- `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`.
- Bundle erneut bauen und SHA-256 vergleichen: eingecheckte Datei muss reproduzierbar sein.
- `.venv-ha/bin/ruff check custom_components tests scripts`.
- `.venv-ha/bin/python -m pytest -q` (Fixtures: Home Assistant 2026.10.4).
- `.venv-ha-2026-11/bin/python scripts/smoke_target.py` (Home Assistant 2026.11.0).
- hassfest lokal prüfen, sofern die offizielle Prüfumgebung verfügbar ist.

## Stufe-1-Korrekturen

1. Auf schmalem Handybildschirm eine lange Raumseite ganz nach unten und oben scrollen.
   Alle fünf Reiter bleiben am unteren sichtbaren Rand, ohne letzte Bedienelemente zu verdecken.
2. Raum öffnen: der Raumname steht in der Hauptüberschrift. Zur Räume-Übersicht zurückgehen.
3. Eine bereits importierte sowie eine neu importierte Hue-Szene prüfen. Die Farbvorschau
   stammt aus den Hue-Ressourcenfarben. Keine Hue-Bilder werden geladen. Bei nicht auslesbaren
   Farbwerten erscheint weiterhin eine neutrale Ersatzvorschau.

## Dynamische Palettenszenen

1. In der Galerie Palette und Raum wählen. Eine dynamische Szene mit Intervall 5 Sekunden
   und Übergang 2 Sekunden speichern und anwenden. Szenenname, Intervall und Stopp werden angezeigt.
2. Mehrere Wechsel abwarten: Farblampen ändern sich, Weißtonlampen bleiben innerhalb ihrer
   Temperaturgrenzen, An/Aus-Lampen und Shelly-Lichtschalter erhalten keine Farbwerte.
3. Eine einzelne Lampe ausschalten. Weitere Wechsel dürfen sie nicht wieder einschalten.
4. Raum ausschalten, auch extern in Home Assistant. Keine spätere Wiederaktivierung durch die
   Dynamik. Raum wieder einschalten: nur die eingestellte Einschaltregel gilt.
5. Dynamik stoppen, eine andere dynamische/statische Szene starten und die aktive Szene löschen.
   Keine verwaisten Schleifen und keine doppelten Wechsel.
6. Während der Dynamik Freigabe entziehen, Lampe umziehen oder Entity entfernen. Es darf kein
   weiterer unzulässiger Steueraufruf erfolgen. Ausfälle müssen sichtbar/sauber beendet werden.
7. Lichtzentrale neu laden und Home Assistant neu starten: keine alten Aufgaben, keine Fehler
   im Log, keine ungewollte automatische Wiederaufnahme. Szene bleibt gespeichert.

## Adaptive Lighting

1. Mit installiertem Adaptive Lighting einen Raum zuordnen. Prüfen, dass nur echte passende
   Adaptive-Lighting-Schalter auswählbar sind und eine unzulässige Zuordnung abgelehnt wird.
2. Natürliches Licht aktivieren. Farbszene (Palette, farbiger Snapshot, Hue) starten:
   Adaptive Lighting darf die Szenenfarbe nicht überschreiben.
3. Für den Raum Einschaltregel „Natürliches Licht“ speichern. Raum aus/an: natürliches
   Licht läuft wieder. Wiederholung testen, auch bei bereits eingeschaltetem Raum.
4. Natürliches Licht während einer Dynamik einschalten: keine konkurrierenden Farbwechsel.
5. Mit nicht verfügbarem Schalter, entfernter Integration, geänderter Raumzuordnung und
   entzogener Lampenfreigabe testen. Keine Fremdräume oder nicht freigegebenen Geräte steuern.
6. Ohne Adaptive Lighting: Räume, Szenen und Galerie funktionieren unverändert, die optionalen
   Bedienelemente verschwinden, im Log steht kein Import-/Servicefehler.

## Sicherheit und echte Geräte

- Nichtadministratoren dürfen keine API-/Service-Steuerbefehle ausführen.
- Keine Schlösser, Heizung, Druckerbeleuchtung, fremden Schalter oder Gruppen steuern.
- Hue: sowohl statische als auch Bridge-dynamische Szenen mit passenden Zielen prüfen.
- Manuell prüfen: HACS-Installierbarkeit, HA-Log, reale Farbverläufe und Verhalten mit
  tatsächlich installierter Adaptive-Lighting-Version. Synthetische Tests ersetzen dies nicht.

Nach Öffnen des Entwurfs-PR beendet Codex die Arbeit. Keine weiteren Änderungen, Tests oder
CI-Überwachung, bis der Nutzer Claudes Abschluss bestätigt.

## Nachgewiesener Stand vor dem Entwurfs-PR

- Python: **207 Tests bestanden**, mit Home Assistant 2026.10.4 und den veröffentlichten Fixtures.
- Frontend: **37 Tests bestanden**, TypeScript und ESLint ohne Fehler.
- Home Assistant **2026.11.0**: erweiterter nativer Smoke-Test bestanden, einschließlich echtem
  Dynamik-Timer, Raum-Aus/Stopp, optionaler Adaptive-Anbindung, Pause/Wiederaufnahme und
  gespeicherter Raumregel. Hue-Farbvorschau zusätzlich gegen `aiohue==4.9.0`-Modelle geprüft.
- hassfest: **1 Integration, 0 ungültig**. Lokal mit Fork-Prozessen statt Forkserver ausgeführt,
  weil die Umgebung dessen IPC-Socket nicht erlaubt; keine Prüfschritte übersprungen.
- Frontend-Bundle zweimal identisch gebaut, alle drei Bundle-/Lizenzdateien per SHA-256 geprüft.
- Browser-Sichtprüfung **nicht ausgeführt**: der lokale Chromium-Start scheitert am IPC-Socket;
  der verfügbare Cloud-Browser erlaubt keine lokalen `file:`-Testseiten. Die mobile Sichtprüfung
  bleibt daher Teil von Claudes Live-Test, kein behaupteter Browser-Pass.
- HACS-GitHub-Action und PR-CI nach Eröffnung bewusst **nicht überwacht**. Keine Live-Installation.
