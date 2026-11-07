# Stufe 3 – Taster: Übergabe und Testplan

## Umfang

- Event-Entities und Ereignistypen werden aus Home Assistant ermittelt, nach Gerät gruppiert.
- Eine gespeicherte Belegung pro Taste/Ereignis: Raum an/aus, einschalten, ausschalten,
  nächste Szene, bestimmte Szene, heller, dunkler, natürliches Licht an/aus oder Dynamik stoppen.
- Raumzyklus mit sortierbaren Szenen und Einschaltregel: vorheriger Zustand, natürliches Licht
  oder eine bestimmte Raumszene. Einstellungen und Belegungen bleiben im serverseitigen Store.
- Hue-Doppelklick wird als `double_short_release` aus zwei `short_release` innerhalb des
  einstellbaren Fensters (200–1000 ms, Vorgabe 500 ms) gebildet. Die Einfachaktion wartet nur,
  wenn für diese Taste tatsächlich ein Doppelklick belegt ist. Shelly `double_push` bleibt nativ.
- Raum-Kacheln zeigen den Namen als rahmenlose Überschrift; die Navigation bleibt per Tastatur bedienbar.

## Automatisierte Prüfungen vor dem Draft-PR

```sh
npm run typecheck
npm run lint
npm test
npm run build
ruff check custom_components tests scripts
pytest -q
.venv-ha-2026-11/bin/python scripts/smoke_target.py
```

Die Pytest-Fixtures laufen gegen Home Assistant 2026.10.4; der separate native Smoke-Test
gegen 2026.11.0. Keine echten Geräte und kein Live-System werden dabei angesprochen.
Das Frontend-Bundle wird eingecheckt und muss nach erneutem Build bytegleich bleiben.
Hassfest und HACS laufen im GitHub-Workflow; nach Öffnen des Draft-PR erfolgt durch Codex
keine weitere Änderung, Testausführung oder CI-Überwachung bis zur neuen Nutzeranweisung.

## Lokaler Prüfstand dieser Übergabe

- Python: 373 Tests erfolgreich; Frontend: 68 Tests erfolgreich. TypeScript, ESLint, Ruff
  und Produktionsbuild erfolgreich. Nativer Smoke-Test mit Home Assistant 2026.11.0 erfolgreich.
- Hassfest: Manifest, JSON, Services, Übersetzungen und Config-Flow erfolgreich geprüft.
  Der vollständige Lauf ist hier am Erstellen lokaler Prozess-Sockets für die
  Dependency-Prüfung gescheitert (`PermissionError: Operation not permitted`), nicht an einer
  gemeldeten Integrationsverletzung. Vollständiges hassfest und HACS bleiben dem CI-Lauf vorbehalten.
- Ein zusätzlicher Chromium-Test bei 320/390/1280 Pixeln wurde vorbereitet, konnte hier aber
  wegen derselben Socket-Beschränkung den Browser nicht starten. Die 68 Frontend-Tests laufen
  mit jsdom; sie ersetzen keine visuelle Handy-Abnahme und keine echte Enter-/Leertasten-Browserprüfung.
- Es wurden keine Live-Geräte angesprochen. Nach dem Draft-PR wird CI nicht weiter beobachtet.

## Manuelle Abnahme durch Claude auf dem Test-/Zielsystem

1. Integration aktualisieren und neu laden bzw. Home Assistant neu starten. Keine neuen Fehler
   im Log; alle bisherigen Szenen, Positionen und Freigaben bleiben erhalten.
2. **Taster** öffnen: Hue und Shelly sind nach Gerät gruppiert, jede Taste zeigt ihre tatsächlich
   angebotenen Ereignisse. Drehen und Shelly-Doppeldruck sind getrennte Ereignisse.
3. Hue Tap Dial: Taste 1 `short_release` → Raum an/aus; Taste 2 `short_release` → nächste Szene;
   `clock_wise` → heller, `counter_clock_wise` → dunkler. Gewünschten Raum jeweils ausdrücklich wählen.
4. Im Raumzyklus zwei oder mehr gespeicherte Szenen auswählen und sortieren. Mehrfach Taste 2 drücken:
   Reihenfolge und Umlauf stimmen. Nach mindestens zehn Minuten Pause beginnt wieder Szene 1.
5. Bei eingeschalteten dimmbaren Lampen mehrfach drehen bzw. `repeat` auslösen: jeweils 10 % heller
   oder dunkler. Ausgeschaltete Lampen, reine An/Aus-Lampen und Switch-Lichter bleiben unberührt.
6. Doppelklick belegen: ein kurzer Druck wartet das gewählte Fenster, zwei kurze Drücke lösen nur
   die Doppelaktion aus. Ohne Doppelbelegung reagiert die Einfachaktion sofort. Fenster ändern,
   Abbrechen und fehlgeschlagenes Speichern prüfen. Shelly `single_push`/`double_push` separat testen.
7. Einschaltregel „bestimmte Szene“ testen, danach „vorheriger Zustand“. Optional Adaptive Lighting:
   natürliches Licht an/aus und Einschaltregel prüfen. Ohne Adaptive Lighting sind dessen Aktionen verborgen.
8. Belegung ändern und löschen; Seite neu laden. Gelöschte/umbenannte Geräte und Szenen dürfen keine
   unkontrollierte Aktion auslösen. Nicht mehr vorhandene Tasterbelegungen bleiben zur Bereinigung sichtbar.
9. Während eines wartenden Doppelklicks Integration neu laden: keine verspätete Aktion und keine
   doppelten Listener. Neustart, Entity-Wiederherstellung und reine Attributänderungen lösen nichts aus.
10. Freigabe einer Lampe entziehen: sie darf anschließend auch über alte Tasterbelegungen nicht
    gesteuert werden. Andere Domains und nicht freigegebene Schalter bleiben unangetastet.
11. Auf schmalem Handybildschirm prüfen: Gruppen, Ereignisauswahl, Raum-/Szenenauswahl, Zyklusreihenfolge
    und Fehlermeldungen sind erreichbar. Raumname hat keinen Eingabefeldrahmen, ist als Überschrift
    erkennbar und öffnet den Raum weiterhin auch per Tastatur.

## Bewusst nicht enthalten

- Zeitpläne (Stufe 4), ein eigener Paletteneditor und automatische Gerätebelegungen.
- Ein Test am echten Hue Tap Dial, Shelly oder einer echten Adaptive-Lighting-Installation.
- Verschieben des Draft-PR auf „bereit“, Merge, Release und Installation auf dem Live-System.
- Bei Tasteraktionen werden Servicefehler im Home-Assistant-Log gemeldet. Ein Tastendruck kann keine
  unmittelbare Fehlermeldung im geöffneten Panel garantieren; der Geräte-/Lichtzustand ist zu prüfen.
