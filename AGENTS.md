# AGENTS.md – Regeln für KI-Assistenten (ChatGPT/Codex, Claude)

Dieses Repository ist **Lichtzentrale**, eine private Custom Integration für Home Assistant.
Der vollständige Bauplan steht in [`docs/BAUPLAN.md`](docs/BAUPLAN.md), die Liste aller Lampen, Schalter und
Taster im Haus (`HAUS.md`) bekommst du **separat vom Nutzer** – sie liegt bewusst nicht in diesem
öffentlichen Repository. **Beides zuerst lesen.**

## Arbeitsweise

- Gearbeitet wird **stufenweise** (Stufe 0 bis 4 im Bauplan). Pro Stufe ein eigener Branch
  `stufe-<n>-<kurzname>` und ein Pull Request gegen `main`. Nie direkt auf `main` committen.
- Rollen: **ChatGPT/Codex** baut die Grundlage einer Stufe. **Claude** prüft den PR, testet gegen
  das echte Home Assistant und macht den Feinschliff. Nie gleichzeitig am selben Branch arbeiten.
- **Übergabe:** Sobald der Pull Request als Entwurf geöffnet ist, hört ChatGPT/Codex auf, am
  Branch zu arbeiten. Claude prüft, korrigiert und testet und meldet über den Nutzer, wann es fertig
  ist. Erst danach arbeitet ChatGPT/Codex weiter – und immer zuerst `git pull`, dann ändern.
  Gefundene Fehler während Claudes Prüfung nur melden, nicht selbst beheben.
- Jeder PR beschreibt: was gebaut wurde, was bewusst fehlt, wie man es testet.
- Nach jeder Stufe muss die Integration **installierbar und lauffähig** sein (HACS-Installation,
  Neustart, keine Fehler im Log).

## Feste Vorgaben

- Domain: `lichtzentrale`. Ordner: `custom_components/lichtzentrale/`.
- Basis ist der Code von [Hypfer/hass-scene_presets](https://github.com/Hypfer/hass-scene_presets)
  (Apache-2.0). `LICENSE` übernehmen, eine `NOTICE`-Datei mit Hinweis auf das Original anlegen,
  geänderte Dateien oben mit `# Geändert für Lichtzentrale` (bzw. `// …`) kennzeichnen.
- **Keine Hue-Szenennamen und keine Bilder aus der Hue-App** übernehmen. Die mitgelieferten
  Upstream-Presets (`presets.json`, `assets/*.jpeg`) werden entfernt und durch eigene Farbpaletten
  mit eigenen Namen ersetzt. Vorschaubilder werden aus den Farben erzeugt (Farbverlauf), keine Fotos.
- Oberfläche komplett **auf Deutsch**, optimiert fürs **Handy** (schmaler Bildschirm, große Kacheln).
- Keine Cloud, kein Konto, keine zusätzlichen Python-Requirements. Mindestversion Home Assistant
  2026.7, getestet wird auf 2026.11.
- Alle Daten (Szenen, Tasterbelegungen, Zeitpläne, Raumeinstellungen) speichert die Integration
  serverseitig über `homeassistant.helpers.storage.Store` – **nicht** im Browser-LocalStorage.
- Gesteuert werden nur Entities der Domains `light` und die in `HAUS.md` genannten `switch`-
  Deckenlichter. Niemals Schlösser, Heizung oder andere Domains anfassen.
- Adaptive Lighting ist **optional**: Die Integration muss ohne installiertes Adaptive Lighting
  fehlerfrei laufen und die Funktionen dann einfach ausblenden.
- Das gebaute Frontend-Bundle (`custom_components/lichtzentrale/frontend/*.js`) wird mit
  eingecheckt, weil HACS es direkt aus dem Repository installiert. Ein GitHub-Action-Workflow baut
  es bei jedem PR neu und prüft, dass das eingecheckte Bundle aktuell ist.
- Keine Zugangsdaten, Tokens, IP-Adressen oder persönlichen Daten ins Repository. Das Repository ist
  öffentlich: keine Namen von Personen, keine echten Entity-IDs aus `HAUS.md` in Code, Tests oder
  Beispielen – Geräte werden zur Laufzeit aus Home Assistant gelesen.
