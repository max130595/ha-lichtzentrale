# Bauplan Lichtzentrale

Ziel: Eine eigene Licht-App **in Home Assistant**, so übersichtlich wie eine Hersteller-App, aber
herstellerunabhängig. Die Hue-App (und andere Apps) verwalten nur noch Geräte. Räume, Szenen,
Taster, Zeitpläne und natürliches Licht laufen alle über die Lichtzentrale.

Nutzer: ein einzelner Admin. Die Seite muss nicht für Kinder oder Gäste vereinfacht werden.

## Architektur

```
custom_components/lichtzentrale/
  __init__.py          Setup, Services, Start der Manager
  manifest.json        domain lichtzentrale, config_flow, iot_class "calculated"
  config_flow.py       leerer Einrichtungsdialog (eine Instanz)
  const.py
  storage.py           Store-Wrapper: scenes, rooms, bindings, schedules, settings
  rooms.py             Räume = HA-Bereiche; Lampen je Raum ermitteln (light + erlaubte switch)
  scenes.py            Szenen speichern, anwenden, Snapshot aus aktuellem Zustand
  palettes.py          Farbpaletten (eigene, mitgeliefert + selbst erstellte)
  dynamic_scenes.py    aus Upstream übernommen, an Szenen-Modell angepasst
  adaptive.py          optionale Anbindung an Adaptive Lighting
  bindings.py          Tasterbelegung: Event-Entities abhören, Aktionen ausführen
  schedules.py         Zeitpläne: Uhrzeit, Sonnenauf/-untergang mit Versatz, Helligkeitsschwelle
  websocket_api.py     alle Befehle für die Oberfläche (siehe unten)
  services.yaml        Services für Automationen
  view.py              Panel registrieren (Seitenleiste "Lichtzentrale", Icon mdi:lightbulb-group)
  frontend/            gebautes React-Bundle
js/                    React + TypeScript Quellcode der Oberfläche (webpack, wie Upstream)
```

### Datenmodell (Store `lichtzentrale.data`, Version 1)

```jsonc
{
  "scenes": [{
    "id": "uuid",
    "name": "Filmabend",
    "area_id": "wohnzimmer",            // Szene gehört zu einem Raum
    "kind": "snapshot",                 // snapshot | palette | hue
    "lights": {                         // nur bei snapshot: Zustand je Lampe
      "light.wohnzimmer_hue_play_1": {"on": true, "brightness": 120, "xy": [0.52, 0.41]},
      "light.wohnzimmer_color": {"on": true, "brightness": 60, "color_temp_kelvin": 2400},
      "switch.wohnzimmer_wohnzimmer_deckenlicht": {"on": false}
    },
    "palette_id": null,                 // bei palette: welche Farbpalette
    "brightness": null,                 // bei palette: Gesamthelligkeit 1–255
    "hue_scene": null,                  // bei hue: scene.* Entity der Hue Bridge
    "dynamic": {"enabled": false, "interval": 60, "transition": 10},
    "favorite": true,
    "order": 0
  }],
  "palettes": [{"id": "uuid", "name": "Herbstlaub", "category": "Gemütlich",
                "bri": 140, "colors": [{"x": 0.58, "y": 0.39}, {"x": 0.52, "y": 0.43}]}],
  "rooms": {"wohnzimmer": {"cycle": ["scene-id-1", "scene-id-2"], "adaptive_switch": "switch.adaptive_lighting_wohnzimmer",
                           "default_on": "adaptive"}},   // default_on: adaptive | last | scene-id
  "bindings": [{"id": "uuid", "event_entity": "event.esszimmer_hue_tap_dial_switch_1_taste_1",
                "event_type": "short_release", "action": "toggle_room", "area_id": "esszimmer", "params": {}}],
  "schedules": [{"id": "uuid", "name": "Bunt ab Sonnenuntergang", "enabled": true,
                 "trigger": {"type": "sun", "event": "sunset", "offset_min": -15},
                 "condition": {"only_if_on": false, "lux_below": null},
                 "action": {"type": "scene", "scene_id": "uuid"}}]
}
```

### Websocket-Befehle (Präfix `lichtzentrale/`)

`rooms/list`, `room/toggle`, `room/brightness`, `room/position`, `light/set`,
`scenes/list`, `scene/save`, `scene/delete`, `scene/apply`, `scene/snapshot`, `scenes/reorder`,
`palettes/list`, `palette/save`, `palette/delete`,
`dynamic/list`, `dynamic/stop`,
`adaptive/status`, `adaptive/set`,
`bindings/list`, `binding/save`, `binding/delete`, `buttons/list` (alle Event-Entities mit Typen),
`schedules/list`, `schedule/save`, `schedule/delete`.

Services für eigene Automationen: `lichtzentrale.apply_scene`, `lichtzentrale.next_scene`,
`lichtzentrale.toggle_room`, `lichtzentrale.stop_dynamic`, `lichtzentrale.set_adaptive`.

## Oberfläche

Untere Leiste mit fünf Reitern:

1. **Räume** – Kachel je Raum mit Name, Anzahl an Lampen, Ein/Aus-Schalter und Farbstreifen der
   aktiven Szene. Tippen öffnet den Raum.
2. **Raum** – oben Ein/Aus und Helligkeitsregler für den Raum, Schalter „Natürliches Licht“
   (nur wenn Adaptive Lighting vorhanden). Darunter Szenen-Kacheln des Raums (Farbvorschau, Name,
   Stern für Favorit), Knopf „Aktuellen Zustand als Szene speichern“. Darunter die einzelnen Lampen
   mit Ein/Aus, Helligkeit, Farbe bzw. Farbtemperatur (Farbrad / Weißton-Regler).
3. **Galerie** – Farbpaletten nach Kategorien. Antippen → Raum wählen → anwenden, optional als
   Szene speichern, optional dynamisch.
4. **Taster** – Liste aller Taster aus `buttons/list`, gruppiert nach Gerät. Je Taste und
   Ereignis eine Aktion wählen.
5. **Zeitpläne** – Liste mit Schalter je Eintrag, Editor mit Auslöser, Bedingung, Aktion.

Lange Listen virtualisieren ist nicht nötig (unter 50 Lampen).

## Aktionen für Taster und Zeitpläne

`toggle_room`, `turn_on_room` (mit `default_on`), `turn_off_room`, `next_scene` (zyklisch durch
`rooms.<id>.cycle`, Position je Raum merken, nach 10 Minuten wieder bei der ersten), `scene`,
`dim_up` / `dim_down` (bei `repeat`-Ereignissen in Schritten von 10 %), `adaptive_on`,
`adaptive_off`, `stop_dynamic`.

Ereignisse: Hue liefert `initial_press`, `repeat`, `short_release`, `long_press`, `long_release`,
der Tap Dial zusätzlich `clock_wise` / `counter_clock_wise` (Drehen = dimmen). Shelly liefert
`single_push`, `double_push`, `triple_push`, `long_push`, `btn_down`, `btn_up`. Doppelklick bei
Hue gibt es nicht als Ereignis; wer ihn will, erkennt zwei `short_release` innerhalb von 500 ms
(einstellbar) in `bindings.py` und verzögert dann die Einfach-Aktion entsprechend – nur wenn für
diese Taste überhaupt ein Doppelklick belegt ist.

## Regeln zwischen Szenen und Adaptive Lighting

- Wird in einem Raum eine Farbszene (palette, snapshot mit Farbe, hue oder dynamisch) gestartet,
  wird Adaptive Lighting für diesen Raum ausgeschaltet bzw. per
  `adaptive_lighting.set_manual_control` für die Lampen auf manuell gesetzt.
- `turn_on_room` mit `default_on: adaptive` schaltet Adaptive Lighting wieder ein und das Licht an.
- Raum ausschalten stoppt laufende dynamische Szenen in diesem Raum.

## Stufen

### Stufe 0 – Grundgerüst
- Upstream-Code übernehmen, auf Domain `lichtzentrale` umbenennen, Lizenz/NOTICE.
- Upstream-Presets und -Bilder entfernen, 12 eigene Paletten in 4 Kategorien mitliefern
  (z. B. Gemütlich, Frisch, Party, Jahreszeiten; Namen frei erfunden).
- Store anlegen, leeres Panel „Lichtzentrale“ mit den fünf Reitern.
- GitHub Action: Frontend bauen + hassfest + HACS-Validierung.
- **Fertig wenn:** über HACS installierbar, Panel erscheint, Paletten lassen sich auf Lampen anwenden.

### Stufe 1 – Räume und Szenen
- Räume-Übersicht und Raum-Seite inklusive Einzellampen.
- Szenen speichern (Snapshot), anwenden, löschen, sortieren, Favoriten.
- Hue-Szenen der Bridge als Szenentyp `hue` importierbar (Auswahl aus `scene.*`, Aktivierung
  über `hue.activate_scene`).
- **Fertig wenn:** Szene „Filmabend“ im Wohnzimmer speichern, Licht ändern, Szene wieder anwenden
  stellt alle Lampen inkl. Deckenlicht-Switch korrekt her.

### Stufe 2 – Dynamik und natürliches Licht
- Dynamische Szenen auf das Szenenmodell umstellen, Anzeige laufender Szenen mit Stopp.
- Adaptive-Lighting-Anbindung nach den Regeln oben.
- **Fertig wenn:** Farbszene pausiert natürliches Licht, Raum aus und wieder an startet es wieder.

### Stufe 2b – Lampenpositionen und räumliche Effekte

- **Positionen:** Jede freigegebene Lampe bekommt pro Raum optional eine Position in einem
  3×3-Raster (vorne/mitte/hinten × links/mitte/rechts) und eine Höhe: `boden` (unter 50 cm),
  `moebel` (Möbelhöhe, um 1,20 m), `hintergrund` (hinter TV/Möbeln, indirekt), `decke`.
  Speicherung im Store unter `rooms.<area_id>.positions.<entity_id> = {"cell": [x, y], "height": "..."}`.
  `x` zählt von links (0) nach rechts (2), `y` von vorne (0) nach hinten (2).
  Mehrere Lampen dürfen dasselbe Feld belegen. Lampen ohne Position werden bei Effekten ans Ende sortiert.
- **Editor:** Auf der Raum-Seite gibt es **Lampen anordnen**: Lampe antippen, ein Feld des
  3×3-Rasters antippen und die Höhe auswählen. Handytauglich, ohne Ziehen und Ablegen.
  Positionen lassen sich wieder entfernen. Nur bestätigte Serverantworten gelten als gespeichert.
  `room/position` speichert oder entfernt genau eine Position atomar, `rooms/list` liefert sie mit.
- **Verteilung bei Paletten (statisch und dynamisch):** Neue Option `verteilung` mit `zufall`
  (bisheriges Verhalten), `verlauf_links_rechts`, `verlauf_vorne_hinten` und `hoehe`
  (Farbe 1 unten, letzte Farbe oben). Bei `hoehe` erhält `hintergrund` die kräftigste Farbe
  der Palette, bestimmt durch die höchste HSV-Sättigung nach Umrechnung von XY nach RGB.
  Bei gleicher Sättigung gewinnt die erste Farbe. Möbelhöhe liegt in der Mitte.
  Die Einstellung wird in Palettenszenen gespeichert und ist auch bei `apply_palette` verfügbar.
- **Welle bei dynamischen Szenen:** Neue boolesche Option `dynamic.welle`. Die Palette wandert
  entlang der gewählten Verteilungsachse Schritt für Schritt durch den Raum. Beim Aktivieren
  wird nötigenfalls links → rechts gewählt; eine Welle benötigt eine räumliche Verteilung.
  Der ausdrückliche Szenenstart schaltet die freigegebenen Ziele wie bisher ein. Bei späteren
  Farbwechseln werden ausgeschaltete, nicht verfügbare oder nicht mehr freigegebene Lampen nicht eingeschaltet.
- **Stopp für Hue-Dynamik:** Der immer erreichbare Stopp-Knopf eines Raums stoppt lokale
  Dynamik und setzt eingeschaltete freigegebene Einzellichter mit ihrer aktuellen Farbe und
  Helligkeit per `light.turn_on` fest. Dadurch endet auch Hue-Dynamik. Ausgeschaltete Lampen,
  nicht verfügbare Geräte und reine Switch-Deckenlichter bleiben unverändert.
  Teilfehler werden angezeigt; ein Stopp wird nicht fälschlich als vollständig erfolgreich gemeldet.
- **Korrekturen aus der Stufe-2-Abnahme:** Statische und dynamische Paletten schalten keine
  `switch.*`-Entities; Snapshot-Szenen behalten den gespeicherten An/Aus-Zustand dieser Schalter.
  Raum aus schaltet alle freigegebenen Lampen und Switch-Lichter des Raums aus.
  Raum einschalten mit natürlichem Licht aktiviert nur die Adaptive-Lighting-Ziele und nie
  Switch-Lichter. Sonst werden in gemischten Räumen nur die vor dem letzten Raum-Aus
  eingeschalteten Lampen und Schalter aus dem serverseitigen Vor-Aus-Snapshot wiederhergestellt.
  Räume ohne freigegebene `light`-Entities schalten ihre Switch-Lichter direkt ein/aus; ihr
  An-Status richtet sich dann nach den Schaltern, in gemischten Räumen nach den Lampen.
- **Kompatibilität:** Alte Räume brauchen keine Migration; fehlende Positionen bleiben optional.
  Alte Szenen verwenden weiterhin `zufall` und `welle: false`. Keine zusätzlichen Requirements.
- **Fertig wenn:** Positionen über Neuladen erhalten bleiben; beide Rasterachsen und die Höhe
  die Farbverteilung bestimmen; die Welle sichtbar in Schritten wandert; der Raum-Stopp
  eine dynamische Hue-Szene einfriert, ohne ausgeschaltete Lampen einzuschalten.

### Stufe 3 – Taster
- `buttons/list`, Belegungseditor, `bindings.py` mit allen Aktionen, Szenenzyklus, Dimmen.
- **Fertig wenn:** ein Hue Tap Dial: Taste 1 an/aus, Taste 2 nächste Szene, Drehen dimmt.

### Stufe 3A – Einzellampen am Taster
- `toggle_lights`, `turn_on_lights`, `turn_off_lights` mit einer nicht leeren Liste
  `params.entity_ids` freigegebener Einzellampen und Lichtschalter, auch raumübergreifend.
- Ist mindestens ein ausgewähltes Ziel an, schaltet Toggle alle aus, sonst alle ein.
  Vor-Aus-Werte für Helligkeit/Farbe werden serverseitig gespeichert und wiederhergestellt.
- `dim_up` / `dim_down` optional mit derselben Auswahl; ohne Liste unverändert raumweise.
  Switch-Lichter werden beim Dimmen immer übersprungen und erhalten keinen Serviceaufruf.
- Tastereditor mit Mehrfachauswahl gruppiert nach Raum, inklusive „Ohne Raum“.
- Details, Sicherheitsregeln und Abnahme: [STUFE_3A_TESTPLAN.md](STUFE_3A_TESTPLAN.md).

### Stufe 4 – Zeitpläne
- Auslöser Uhrzeit, Sonnenauf-/-untergang mit Versatz, Außenhelligkeit unter Schwelle
  (ein in den Einstellungen wählbarer Lux-Sensor), Bedingungen, Wochentage.
- **Fertig wenn:** „Bunt ab Sonnenuntergang“ im Wohnzimmer läuft zur richtigen Zeit an.

## Tests

- Python: `pytest-homeassistant-custom-component` für Store, Szenen-Snapshot/Anwenden,
  Szenenzyklus und Doppelklick-Erkennung.
- Frontend: TypeScript ohne Fehler bauen, ESLint sauber.
- Manueller Test durch Claude am echten System nach jeder Stufe.
