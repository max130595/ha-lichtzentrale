# Stufe 5 – Grundhelligkeit

## Umfang und konservative Grenzen

Pro Raum werden ein Lux-Sensor, Zielhelligkeit, Hysterese, Mindestabstand
(Vorgabe drei Minuten), geordnete additive Lichtstufen sowie optional Zeitfenster
und Anwesenheit konfiguriert. Nur zur Laufzeit freigegebene Lichtziele desselben
Raums sind zulässig. Jede Entity darf nur in einer Stufe stehen.

Bei `Lux < Ziel − Hysterese` kommt eine Stufe hinzu. Eine eigene aktive Stufe
wird erst entfernt, wenn `Lux − gelernter Anteil > Ziel + Hysterese` gilt.
Gleichheit ändert nichts. Zwischen zwei Wechseln gilt die Mindestzeit, auch beim
Richtungswechsel. Switch-Lichter werden niemals gedimmt.

Eigenlicht ist eine Schätzung: Nach mindestens zehn Sekunden Beruhigungszeit
wird ein gültiger Lux-Anstieg erfasst und mit Faktor 0,25 geglättet. Ein unbekannter
Anteil ist `null`; er berechtigt nicht zum automatischen Ausschalten. Wechselndes
Tageslicht, langsame Sensoren und andere Lichtquellen können das Lernen beeinflussen.
Diese Regelung ersetzt keine kalibrierte Konstantlichtsteuerung.

Handbedienung hat Vorrang und pausiert bis zum nächsten Zeitfenster-Beginn oder
bis zum ausdrücklichen „Raum aus“. Ein Neustart oder Bearbeiten übernimmt keine
bereits eingeschalteten Geräte. Ohne Zeitfenster bleibt die Pause bis zum ausdrücklichen
Raum-Aus bestehen; nach erfolgreichem Raum-Aus wartet die Regelung eine volle Mindestzeit.
Ein neues konfiguriertes Zeitfenster beendet die manuelle Vorgabe und erlaubt die erneute
Übernahme der Stufen, ohne schon eingeschaltete Ziele als neue Lux-Messung zu lernen. Lernwerte sind serverseitig persistent; Timer,
Besitzansprüche und manuelle Pause sind es nicht. Ungültige Sensorwerte blockieren
luxbedingte Stufenwechsel. Bei sicherer Abwesenheit oder Fensterende werden ausschließlich
eigene aktive Stufen rückwärts und unter Einhaltung der Mindestzeit entfernt. Unbekannte
Personenzustände sperren dagegen alle Befehle. Ohne frische Lernmessung wird nach
120 Sekunden ohne neuen Lernwert weitergeregelt. Es gibt keine nachgeholten
Ausschaltbefehle aus früheren Laufzeiten.

## Automatische Prüfung

Die folgende Matrix beschreibt die erforderlichen Prüfbereiche, nicht die Behauptung,
dass jede manuelle Abnahme bereits durchgeführt wurde. Tests verwenden ausschließlich
synthetische Bereiche und Geräte; es wird keine echte HA-Installation angesprochen.

1. **Konfiguration und Store:** Illuminanzklasse und Einheit `lx`; positive Zielhelligkeit,
   nicht negative Hysterese, Mindestzeit 1–86400 Sekunden; geschlossene Feldmengen;
   unbekannte Personen; leere/mehrfach verwendete Ziele; fremder Raum; entzogene Freigabe;
   reine Switch-Stufe ohne Helligkeit; boolesche, unendliche und nicht numerische Werte.
   Speichern, Aktivieren/Deaktivieren und erneutes Laden. Lernwerte nicht vom Client überschreibbar.
2. **Regelung:** Stufen einzeln und kumulativ hinzufügen, Reihenfolge beim Entfernen,
   Gleichheit und Hystereseband, Mindestzeit beim Hin- und Herschalten, unbekannter
   Lernwert verhindert Entfernen. Keine Übernahme von zuvor eingeschalteten Zielen.
3. **Lernen:** Erst gültige beruhigte Messung verwenden; gleitender Mittelwert;
   fehlende/ungültige oder zwischenzeitlich gestörte Messung nicht als Erfolg speichern.
   Lernwerte nach Reload erhalten, Stufenänderung macht unpassende Zuordnungen ungültig.
4. **Bedingungen:** Tages-/Nachtfenster, offene Grenzen, Beginn inklusive/Ende exklusive,
   Sonnenversatz und fehlendes Sonnenereignis. Optional mindestens eine Person zu Hause;
   unbekannte/nicht verfügbare Personen sperren. Bedingungen nach Wartephasen neu prüfen.
5. **Manuelle Priorität:** Fremdes Ein/Aus und Helligkeitsänderung, Szene/Taster/App,
   eigene Kontexte und erlaubte Adaptive-Lighting-Änderungen unterscheiden.
   Pause zurücksetzen durch nächsten Fensterbeginn oder ausdrückliches Raum-Aus.
6. **Sicherheit und Lebenszyklus:** Freigabeentzug, Raumwechsel, deaktivierte/nicht verfügbare
   Geräte, Änderung/Deaktivierung während wartender Sperre, Entladen und Neustart.
   Keine veralteten Timer, fremden Zielabschaltungen oder Switch-Dimmpayloads.
   Teilfehler dürfen keine vollständige erfolgreiche Stufe vortäuschen.
7. **Oberfläche:** Ein/Aus, Lux/Ziel/Stufenstatus/Lernwerte, Mehrfachauswahl,
   Stufen hinzufügen/entfernen/umordnen, Uhrzeit/Sonnenstand und Personenauswahl.
   Abbrechen, Serverfehler, wiederholtes Speichern und Neuladen; keine Erfolgsmeldung
   vor Serverbestätigung. Optionales Adaptive Lighting darf nicht vorausgesetzt werden.

## Reproduzierbare Befehle

Die pytest-Fixtures sind auf HA 2026.10.4 abgestimmt. Der native Zielversions-Smoke
läuft deshalb getrennt gegen echtes HA 2026.11.0 ohne Kompatibilitäts-Shims.
Beide Umgebungen benötigen Python 3.14; die Integration erhält keine Zusatzrequirements.

```sh
uv venv --python 3.14 .venv-test
uv pip install --python .venv-test/bin/python -r requirements-test.txt
.venv-test/bin/python -m pytest -q
.venv-test/bin/ruff check custom_components tests scripts
npm ci
npm run typecheck
npm run lint
npm test
npm run build
uv venv --python 3.14 .venv-target
uv pip install --python .venv-target/bin/python -r requirements-ha2026.11.txt
.venv-target/bin/python scripts/smoke_target.py
```

Der native Smoke verwendet echte HA-Registries, Service-Dispatch und temporären
Store mit synthetischen Zuständen und Serviceempfängern. Er prüft zusätzlich den
Grundhelligkeitsstart, die Helligkeitspayload, Mindestzeit, manuelle Pause und
Persistenz. Er ersetzt weder vollständige WebSocket-/Panel-Prüfung noch echte Geräteabnahme.
Das gebaute Frontend-Bundle gehört zum Entwurf; ein Build allein ist kein visueller UI-Test.

## Praktische Abnahme durch Claude nach dem Draft

- In einem ausdrücklich geeigneten Testraum Lux-Sensor, erlaubte Lampen und optional
  erlaubtes Deckenlicht auswählen. Keine ausgeschlossenen privaten Räume verwenden.
- Mit langsamer Änderung des Umgebungslichts Stufenfolge, dreiminütige Mindestzeit,
  Eigenlichtlernen und rückwärts gerichtetes Abschalten beobachten.
- Taster, gespeicherte Szene und App manuell bedienen; Pause und ihre Freigabe prüfen.
- Zeitfenster und Anwesenheit, fehlenden Sensor sowie Neustart kontrollieren.
- Optional Adaptive Lighting: Weißton passt, Stufenhelligkeit bleibt erhalten.
- Auf schmalem Bildschirm Editor, Fehleranzeige, Speichern und Reload abnehmen.

Es wurden für die Entwicklung keine echten Geräteaktionen, Bereitstellung oder
Zusammenführung veranlasst. Nach Öffnen des Draft-PR endet die Arbeit einschließlich
CI-Überwachung bis zur Rückmeldung durch Claude über den Nutzer.
