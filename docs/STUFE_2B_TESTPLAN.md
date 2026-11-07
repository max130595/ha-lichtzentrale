# Stufe 2b – Prüfliste für Lampenpositionen und räumliche Effekte

Keine Prüfung hier spricht echte Geräte an. Die abschließende Installation, Handy-Sichtprüfung
und Hue-/Adaptive-Lighting-Abnahme führt Claude nach Öffnen des Draft-PRs durch.
Die ursprüngliche Prüfliste steht in [STUFE_2_TESTPLAN.md](STUFE_2_TESTPLAN.md);
die hier beschriebenen Switch- und Einschaltregeln ersetzen deren ältere Erwartungen.

## Automatische Prüfungen

- `npm run typecheck`, `npm run lint`, `npm test`.
- `ruff check custom_components tests scripts`, `pytest -q` mit den veröffentlichten
  HA-2026.10.4-Fixtures aus `requirements-test.txt`.
- `.venv-ha-2026-11/bin/python scripts/smoke_target.py`: native HA-2026.11-Registries,
  echter Store, Timer/Farbwechsel, Positionen, Welle, Farb-Festsetzen und Einschaltregeln.
  Synthetische Services ersetzen echte Geräte. Die Fixture-Suite ist separat, weil das
  veröffentlichte pytest-Plugin mit HA 2026.11 noch nicht kompatibel ist.
- Frontend zweimal bauen und SHA-256-Werte des Bundles sowie der Lizenzdateien vergleichen.
- hassfest und HACS durch den bestehenden CI-Workflow. Nach Draft-Eröffnung keine
  CI-Beobachtung durch Codex; dies gehört zur vereinbarten Übergabe.

## Positionseditor und Persistenz

1. Auf Handybreite (320 und 390 px) einen Raum öffnen. **Lampen anordnen** zeigt nur
   freigegebene Raumlampen. Ein Feld kann erst nach Auswahl einer Lampe gespeichert werden.
2. Jede der neun Zellen testen: x=0 links/x=2 rechts, y=0 vorne/y=2 hinten. Keine Drag-Geste nötig.
3. Alle Höhen prüfen: Boden, Möbelhöhe, Hintergrund, Decke. Mehrere Lampen in dasselbe Feld
   legen. Lange Lampennamen dürfen das Raster nicht über die Bildschirmbreite drücken.
4. Position entfernen, Raum neu laden, Integration neu laden: bestätigte Werte bleiben erhalten,
   entfernte Positionen bleiben weg. Speicherung ausschließlich im Home-Assistant-Store.
5. Schnelles Doppeltippen, Raum-/Reiterwechsel während einer Antwort, fehlgeschlagener Speicher-
   oder Höhenwechsel: keine doppelten Befehle, kein falscher Erfolg und kein dauerhaft gesperrter Editor.
6. Zwei Browser bearbeiten verschiedene Lampen gleichzeitig: keine verlorenen Nachbarpositionen.
   Eine entzogene Freigabe oder geänderte Raumzuordnung darf nicht mehr gespeichert werden.

## Paletten und Welle

1. Statische und gespeicherte dynamische Palette für jede Verteilung anwenden.
   Nicht positionierte Lampen stehen zuletzt; ohne Positionen bleibt die bisherige Reihenfolge erhalten.
2. Links/rechts und vorne/hinten: dieselbe Achsenkoordinate hat dieselbe Palettenfarbe.
   Bei Höhe bekommt Boden die erste Farbe, Möbel die mittlere, Decke die letzte;
   Hintergrund erhält die höchste HSV-Sättigung der XY→RGB-Farben (erste gewinnt Gleichstand).
3. Welle aktivieren. Aus Zufällig wird links → rechts gewählt. Mit Intervall 5 s und
   Übergang 0–2 s wandern die Farben je Schritt zur höheren Achsenkoordinate.
   Hintergrund bleibt bei Höhenverteilung die kräftigste Farbe.
4. Einzelne Lampe während des Laufs ausschalten, entfernen, einem anderen Raum zuordnen
   oder ihre Freigabe entziehen: kein späterer `turn_on`, übrige Wellenpositionen bleiben stabil.
   Die ausdrückliche erstmalige Szenenaktivierung darf freigegebene Einzellichter einschalten.
5. Dynamisch + Welle aktivieren → Dynamisch ausschalten → Zufällig wählen → Dynamisch einschalten:
   keine ungültige Welle/Zufällig-Kombination. Gespeicherte Szene erneut anwenden.
6. **Statische und dynamische Paletten schalten keinerlei `switch.*`-Entities.**
   Ein Shelly-Schalter bleibt sowohl im An- als auch im Aus-Zustand unverändert, verbraucht
   keinen Farbplatz und hält allein keinen dynamischen Lauf aktiv. Ein erfolgreicher Palettenstart
   wird trotz dieser absichtlichen Auslassung als letzter Szenenstart gespeichert.
7. Snapshot mit Schalter an und Snapshot mit Schalter aus getrennt anwenden:
   der Schalter folgt ausschließlich dem jeweils gespeicherten Wert.

## Raum aus/an und natürliches Licht

1. Gemischter Raum ohne natürliches Licht: zwei Lampen an, eine aus, ein freigegebener
   Switch an und einer aus. Raum aus schaltet alle verfügbaren freigegebenen Ziele aus.
   Im serverseitigen Vor-Aus-Snapshot stehen beide Switches nur mit ihrem An/Aus-Wert.
   Raum ein stellt nur die zuvor eingeschalteten Lampen und Switches wieder her.
2. Raum mehrfach ausschalten, dann an: der gespeicherte Vor-Aus-Zustand bleibt erhalten.
   Nach Integration-Neuladen wiederholen. Auch Teilfehler beim Ausschalten von Lampen oder
   Switches mit anschließendem erneutem Ausschalten dürfen vorherige An-Zustände nicht verlieren.
   Neue, verschobene oder nicht mehr freigegebene Ziele werden nicht eingeschaltet.
3. Ohne vorher gespeicherten Zustand schaltet Raum an in gemischten Räumen vorsichtshalber
   keine neuen Ziele ein. Eine ausgeschaltete oder nicht verfügbare `light`-Entity macht
   einen gemischten Raum nicht zu einem reinen Switch-Raum.
4. Natürliches Licht nur für eine Teilmenge der Raumlampen konfigurieren. Im gespeicherten
   Vor-Aus-Zustand einen Switch mit an haben. Raum ein mit Natürliches Licht aktiviert nur
   die Adaptive-Lighting-Teilmenge; alle Switch-Lichter bleiben aus. Eine ungültige/entfernte
   Zuordnung darf nicht auf „alles an“ zurückfallen.
5. Reiner Switch-Raum: explizit ein, aus und umschalten testen, auch ohne vorherigen Snapshot.
   Alle freigegebenen verfügbaren Switch-Lichter folgen direkt. Der Raum-An-Status richtet
   sich nach den Schaltern. Nicht verfügbare Switches, fremde Räume und entzogene Freigaben
   werden sicher ausgelassen. Mit Einschaltverhalten Natürliches Licht werden keine Switches eingeschaltet.
6. In gemischten Räumen weiterhin prüfen: ein allein eingeschalteter Switch bestimmt nicht
   den Raum-An-Status. Einzelbedienung und gespeicherte Snapshot-Szenen bleiben möglich.
7. Ohne installierte Adaptive-Lighting-Integration bleiben deren Bedienelemente verborgen.

## Dynamik stoppen, einschließlich Hue

1. Eine native dynamische Hue-Szene starten, auch außerhalb der Lichtzentrale. Der Raum-Stopp
   muss erreichbar sein, obwohl keine lokale dynamische Palettenszene läuft.
2. Stoppen: jede aktuell eingeschaltete freigegebene Einzellampe bekommt `light.turn_on`
   mit aktueller Helligkeit und ausschließlich ihrem aktiven nativen Farbmodus.
   Kein Umschalten zwischen XY/CT oder Wiedereinspielen veralteter abgeleiteter Farben.
3. Off-/unavailable-Lampen, Gruppen, fremde Räume, widerrufene Freigaben und Switches bleiben unverändert.
4. Lokale Welle stoppen: keine weiteren Timerwechsel; aktuelle Farben bleiben stehen.
5. Gerätefehler simulieren: erfolgreiche und fehlgeschlagene Lampen werden getrennt gemeldet.
   Bei Fehlern nicht behaupten, die gesamte Hue-Dynamik sei beendet. Erneuten Stopp testen.
6. Bei unvollständigen/ungültigen aktuellen Farbattributen wird die Lampe sicher übersprungen.
   Diese Einschränkung mit den tatsächlichen Hue-Zustandsattributen abnehmen.

## Grenzen / Übergabe

- Keine Live-Installation und keine realen Lampen verändert.
- Mobile Browser-Sichtprüfung hier technisch blockiert: Chromium kann den erforderlichen
  lokalen IPC-Socket nicht öffnen. Die DOM-Tests ersetzen keine Sichtprüfung.
- Der echte Hue-Bridge-Stopp und das Verhalten der installierten Adaptive-Lighting-Version
  müssen an der realen Installation geprüft werden.
- Sobald der Draft-PR offen ist: keinerlei weitere Änderungen, Tests, CI-Beobachtung oder Merge
  durch Codex, bis der Nutzer Claudes Abschluss meldet.
