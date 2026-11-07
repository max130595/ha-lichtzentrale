# Stufe 3b – Bewegungsmelder

## Gebaut

- Raumweise Bewegungsautomatik mit beliebig vielen zur Laufzeit ausgewählten Sensoren der
  Klassen `motion`, `occupancy` und `presence`. Keine fest eingebauten Gerätekennungen.
- Geordnete lokale Uhrzeit-/Sonnenfenster mit Versatz und Mitternachtswechsel. Das erste passende
  Fenster wird bei Aktivierung gewählt. Gleiche Uhrzeiten gelten ganztägig.
- Je Fenster Raum-Szene, optionales Natürliches Licht oder Nachtlicht mit einstellbarer Helligkeit.
  Nachtlicht kann den gesamten Raum oder ausdrücklich ausgewählte freigegebene Lampen und
  Lichtschalter aus mehreren Räumen steuern. Szenen/Adaptive Lighting behalten ihre eigenen Ziele.
- Nachlauf ab bestätigtem Aus aller Sensoren. Optionale Vorwarnung 20 Sekunden vor Ablauf:
  dimmbare Lampen auf höchstens 30 %, Schalter unverändert. Neue Bewegung stellt die vorherige
  Helligkeit wieder her. Dunklere Nachtlichter werden dabei nicht aufgehellt.
- Optionale Lux-Bedingung mit Sensor-Auswahl und striktem „unter der Schwelle“.
- Manuelle Änderungen an den konfigurierten Zielen pausieren die Automatik, bis alle Sensoren
  für die ganze Nachlaufzeit leer melden. Manuelle Zustände werden nicht automatisch ausgeschaltet.
- Deutscher Editor und serverbestätigter Ein/Aus-Schalter auf der Raumseite. Speicherung im
  Home-Assistant-Store, keine Migration und keine Browser-Speicherung.

## Sicherheitsregeln und Grenzen

- Nur bereits freigegebene Einzellampen und passende Shelly-Lichtschalter. Bestehende
  Gruppenausschlüsse, Freigaben, Bereichsprüfungen und geordnete Zielsperren werden weiter genutzt.
  Manuelle Änderungen, entzogene Freigaben und verschobene Geräte werden vor Dispatch berücksichtigt.
- Vor Nachtlicht und Vorabdunkeln wird bei vorhandenem Adaptive Lighting nur für die betroffenen
  freigegebenen Lampen `manual_control` gesetzt, auch bei raumübergreifender Auswahl. Andere Lampen
  und AL-Hauptschalter bleiben unverändert. Diese Markierung bleibt bis zur nächsten ausdrücklichen
  Natürliches-Licht-Aktivierung erhalten, damit eine spätere manuelle Wahl nicht zurückgesetzt wird.
- Nur erfolgreich automatisch angesprochene Ziele gehören zum Nachlauf. Keine pauschalen
  Ausschaltbefehle an andere Raumgeräte. Teilfehler erscheinen im Automatikstatus.
- Fehlende, nicht verfügbare, wiederhergestellte oder deaktivierte Bewegungsmelder liefern
  keine sichere Leer-Meldung. Countdown und Abschaltung werden dann blockiert. Lux-Werte müssen
  endlich, nicht negativ und in `lx` sein. Fehlende Sonnenereignisse verhindern das jeweilige Fenster.
- Eigene Kontexte und ihre Nachfolger gelten nicht als manuelle Bedienung. Adaptive-Lighting-
  Kontexte mit der ID-Vorsilbe `adapt_lgt` werden auch ohne `parent_id` als automatisch erkannt.
- Bei einer von der Bewegungsautomatik gestarteten dynamischen Szene bleiben reine Farb- und
  Helligkeitswechsel ihrer tatsächlich geschalteten Lampen automatisch, auch ohne Kontext.
  Externes Ein/Aus und nicht verfügbare Ziele pausieren weiterhin. Die Ausnahme gilt nicht für
  statische Szenen, andere konfigurierte Ziele oder einen fremd gestarteten lokalen Dynamiklauf.
  Lokale Dynamik muss noch mit derselben Start-ID laufen; Hue-Meldungen `dynamics: none` beenden
  die Ausnahme. Speichern, manuelle Pause und Ablauf entfernen die Laufzeit-Zuordnung.
- Andere Änderungen ohne zuordenbaren Kontext werden vorsichtshalber manuell behandelt.
  Geräte-/Bridge-Verhalten bleibt Bestandteil der Live-Abnahme.
- Speichern/Deaktivieren und Entladen stoppen Timer und laufende Aufgaben ohne zusätzliche
  Gerätebefehle. Bei Neustart oder neuer Konfiguration wartet die Automatik auf ein Sensorereignis;
  alte Laufzeit-Zustände und manuelle Pausen werden nicht rekonstruiert. Es werden keine alten
  Ausschaltbefehle nachgeholt. Ein fehlender Sensor verhindert nicht das Ausschalten der Automatik.
- Zeitfenster und Lux werden beim Beginn einer Aktivierung ausgewertet. Ein laufender Aufenthalt
  wird nicht mitten im Fensterwechsel auf eine andere Szene umgestellt. Wiederkehr nach dem
  Vorabdunkeln stellt auch bei inzwischen höheren Lux-Werten die Helligkeit wieder her.
- Die Statusanzeige wird mit „Bewegungsautomatik neu laden“ aktualisiert. Kein Live-Push-Abonnement.

## Automatisierte Prüfung

```sh
.venv-ha/bin/python -m pytest -q
.venv-ha/bin/ruff check custom_components tests scripts
npm run typecheck
npm run lint
npm test
npm run build
.venv-ha-2026-11/bin/python scripts/smoke_target.py
git diff --check
```

- 537 Python-Tests erfolgreich mit Home Assistant 2026.10.4, inklusive Konfiguration, Admin-Schutz,
  atomarer Speicherung und Lifecycle sowie Bewegungslogik und Laufzeit-Rennen.
- Frontend: 90 Tests, darunter 13 Bewegungs-Tests; TypeScript und ESLint erfolgreich.
- Native Home-Assistant-2026.11.0-Prüfung erweitert um Bewegungslicht, Lampen-/Schalterauswahl,
  Vorabdunkeln ohne Switch-Dimmen, Rückkehr, manuelle Pause und Store-Neuladen. Die Review-
  Regressionen prüfen außerdem Abschalten nach parentlosen `adapt_lgt`-Updates und nach
  kontextlosen Farbwechseln einer von Bewegung gestarteten dynamischen Palette.
- Zwei aufeinanderfolgende Produktionsbuilds liefern bytegleiche Dateien. Das Bundle wird
  eingecheckt. Webpack meldet lediglich seine Größenempfehlung für das etwa 250-KiB-Bundle.
- Die vollständige pytest-Suite nutzt weiter 2026.10.4 wegen der bekannten Inkompatibilität des
  Test-Plugins mit 2026.11. Die separate native 2026.11-Prüfung verwendet keine solchen Shims.
- hassfest/HACS werden in dieser Stufe lokal nicht ausgeführt; sie bleiben dem PR-Workflow
  vorbehalten. Nach dem Draft werden weder Workflow noch Branch weiter beobachtet.
- Keine Live-Geräte, keine Installation im privaten Home Assistant und keine visuelle
  Browser-/Handy-Abnahme. Sämtliche Testgeräte und Räume sind synthetisch.

## Manuelle Abnahme durch Claude auf einem isolierten Testsystem

1. Branch installieren, neu starten, Raum öffnen. Neue Automatik ist ausgeschaltet. Zwei oder
   mehr passende Test-Sensoren auswählen, speichern, neu laden und erst dann einschalten.
2. Einen Sensor einschalten: gewünschte Aktion läuft einmal. Zweiter Sensor hält die Belegung,
   auch wenn der erste bereits aus ist. Erst Aus aller Sensoren startet den vollständigen Nachlauf.
3. Bei 60 Sekunden Nachlauf nach 40 Sekunden Vorabdunkeln prüfen. Switch unverändert, dunkles
   Nachtlicht nicht heller. Bewegung während der Vorwarnung stellt die vorherige Helligkeit wieder her.
4. Nachtlicht mit einer Lampe und einem Lichtschalter auswählen, auch raumübergreifend.
   Andere Raumgeräte bleiben bei Ein, Dimmen, Wiederherstellung und Aus unberührt.
5. Taster, App und Szene während Belegung sowie während Vorwarnung bedienen. Automatik pausiert,
   keine eigene Abschaltung mehr. Nach kompletter Leerzeit erfolgt die nächste Aktivierung wieder normal.
6. Lux unter, gleich und über der Schwelle prüfen, dazu `unknown`, `unavailable` und falsche Einheit.
   Nur der Start wird beschränkt. Während aktiver Belegung steigende Lux dürfen Nachlauf nicht blockieren.
7. Tages-/Nachtfenster, Mitternacht, geordnete Überschneidung und Sonnenversatz prüfen. Ohne passendes
   Fenster keine Aktivierung. Szene und Natürliches Licht kontrollieren; ohne Adaptive Lighting bleibt
   dessen Auswahl verborgen. Periodische Änderungen optionaler Lichtintegrationen mitprüfen.
8. Sensor während Nachlauf nicht verfügbar machen: keine Abschaltung. Nach sicherer Rückkehr auf Aus
   beginnt eine neue volle Leerzeit. Ziel-Freigabe entziehen oder Bereich ändern: keine weiteren Befehle
   an nicht mehr passende Ziele. Fehlendes Gerät im Editor entfernen und erneut speichern.
9. Automatik deaktivieren, Einstellungen ändern, Integration entladen und HA neu starten:
   keine veralteten Timer. Aktuelle Lampenzustände werden durch diese Verwaltungsaktionen nicht verändert.
10. Auf schmalem Bildschirm Mehrfachauswahl, Speichern, wiederholte Klicks, Abbrechen, Neuladen,
    Raumwechsel während Anfrage und Fehlermeldungen prüfen. Ein/Aus-Zustand erst nach Serverantwort ändern.

## Bewusst nicht enthalten

Allgemeine Zeitpläne (Stufe 4), Installation/Tests gegen private Geräte, Merge, Release sowie
Änderungen oder CI-Überwachung nach Öffnen des Draft-PR. Ab dort übernimmt Claude.
