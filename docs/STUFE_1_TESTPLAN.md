# Stufe 1: Räume und Szenen prüfen

## Automatisch

- `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`.
- `ruff check custom_components tests scripts`, `python -m pytest -q`.
- Separat mit Home Assistant 2026.11.0: `python scripts/smoke_target.py`.
- Nach eingechecktem Build: erneut bauen und `git diff --exit-code -- custom_components/lichtzentrale/frontend`.
- GitHub Actions: Frontend/Bundle, vollständige Python-Suite auf 2026.10.4,
  nativer 2026.11-Smoke-Test, hassfest und HACS. Fixture-Version siehe README.

Die automatischen Tests verwenden ausschließlich synthetische Entities und lokale Service-Mocks.
Sie steuern keine Geräte. Der Native-Smoke-Test ist keine vollständige 2026.11-Integrationssuite;
ein echter Hue-Bridge-Recall und HACS-Installation/Neustart bleiben manuell zu prüfen.

## Manueller Test im freigegebenen Testsystem

1. Branch installieren, Neustart. Integration einrichten bzw. bestehende Stufe-0-Installation
   aktualisieren. Panel und Log prüfen. Bestehende Freigaben müssen erhalten bleiben.
2. Freigaben öffnen: Hue-/HA-Gruppen fehlen, eindeutig benannte Shelly-Lichtschalter sind
   sichtbar. Bambu-Beleuchtung ist ausgeblendet. Anzeigeoption schaltet nur die Sichtbarkeit,
   nicht die Freigabe. Vorhandene Bambu-Freigaben müssen zum Widerrufen sichtbar bleiben.
3. Nur gewünschte Beleuchtung freigeben. Direkte Entity-Bereiche sowie Gerätebereiche prüfen;
   eine fehlende Etage darf keinen Raum verbergen. Raum nur mit einem Lichtschalter testen.
4. Raum und einzelne Lampen ein-/ausschalten. Raumhelligkeit ändert nur bereits eingeschaltete
   dimmbare Lampen. Farb- und Weißtonregler erscheinen nur bei unterstützten Lampen;
   Switches bieten ausschließlich Ein/Aus. Gerätegrenzen für Weißton prüfen.
5. Einen Raum mit Farb-, Weißton-, Helligkeits-, Ein/Aus-Lampe und Lichtschalter einstellen.
   Snapshot speichern, alle Zustände ändern, Szene anwenden. Zustand jedes Geräts vergleichen,
   besonders ausgeschalteter Lichtschalter und aktive Farbtemperatur statt veralteter XY-Werte.
6. Favorit markieren, Szenen nach oben/unten sortieren, Seite neu laden und HA neu starten.
   Szene/Favorit/Reihenfolge müssen erhalten bleiben. Eine Szene löschen und Abbrechen testen.
7. Native Hue-Szene wählen und importieren. Sie muss zum Raum gehören, alle tatsächlichen
   Ziele müssen freigegeben sein. Szenenstart über `hue.activate_scene` prüfen. Fremde
   `scene.*`-Entities, unbekannte Ziele, Smart-Szenen und raumübergreifende Ziele ablehnen.
8. Snapshot und Hue-Szene starten: Übersicht und Raum zeigen den letzten erfolgreichen Start,
   mit einer Schaltfläche zum Neustart. Nach HA-Neustart muss er weiterhin abrufbar sein.
   Externes Schalten darf nicht als neue Lichtzentrale-Aktivierung erscheinen. Die Anzeige
   heißt deshalb ausdrücklich „Zuletzt über Lichtzentrale gestartet“.
9. Lampe unerreichbar machen, Freigabe widerrufen, Lampe in anderen Bereich verschieben.
   Szenen müssen übersprungene/fehlgeschlagene Lampen melden bzw. unsichere Ziele vor jedem
   Aufruf ablehnen. Kein Teilfehler darf den vorherigen erfolgreichen Szenenstart ersetzen.
10. Doppelklick auf Anwenden/Speichern, Tabwechsel während einer Anfrage, Abbrechen,
    unterbrochene Verbindung und erneutes Laden testen. Keine doppelten Befehle oder späten
    Rückmeldungen in einem neuen Raum. Ausgeblendete Lampen anzeigen, ohne ungespeicherte
    Freigaben zu verlieren. Kleine Bildschirmbreite und große Schrift prüfen.
11. Dienste `apply_scene` und `toggle_room` in einer autorisierten Testautomation prüfen.
    Nicht-Administratoren dürfen weder Lesen noch Steuern. Neuladen darf keine doppelten
    Websocket-Handler erzeugen. Entladen entfernt alle drei Dienste, Daten bleiben erhalten.

## Bewusst noch nicht enthalten

Dynamische Szenen und Adaptive Lighting (Stufe 2), Taster (Stufe 3), Zeitpläne (Stufe 4).
Die gespeicherte letzte Szenenreferenz kann später auch dynamische Szenen adressieren;
Stufe 1 startet diese noch nicht. Keine Installation auf dem produktiven HA-System im Rahmen
von Entwicklung oder automatischen Tests.
