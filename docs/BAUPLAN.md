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
  motion.py            Bewegungsautomatik: Belegung, Zeitfenster, Nachlauf und manuelle Pause
  motion_config.py     Sensor-Auswahl und geschlossene Konfigurationsprüfung
  brightness.py        Grundhelligkeit: Stufen, Eigenlicht-Lernen und manuelle Pause
  brightness_config.py Lux-/Personenauswahl und geschlossene Stufenprüfung
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
`motion/get`, `motion/save`, `motion/set_enabled`,
`brightness/get`, `brightness/save`, `brightness/set_enabled`,
`schedules/list`, `schedule/save`, `schedule/delete`, `schedule/set_enabled`, `schedule/test`.

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

### Stufe 3b – Bewegungsmelder

- **Sensoren pro Raum:** Beliebig viele zur Laufzeit ausgewählte `binary_sensor` mit
  `device_class: motion`, `occupancy` oder `presence`. Jeder aktive Sensor hält den Raum belegt.
  Erst wenn alle Sensoren sicher `off` melden, beginnt die Ausschaltzeit. Fehlende oder nicht
  verfügbare Sensoren gelten nicht als leerer Raum und verhindern ein automatisches Ausschalten.
- **Zeitfenster:** Pro Raum mehrere geordnete Fenster mit Beginn und Ende als lokale Uhrzeit
  oder Sonnenauf-/untergang, jeweils mit Versatz von −1440 bis +1440 Minuten. Mitternacht wird
  unterstützt. Gleiche Uhrzeiten bedeuten ganztägig, bei Überschneidungen gilt das erste Fenster.
  Ohne passende Zeitgrenzen (etwa fehlendes Sonnenereignis) wird nicht eingeschaltet.
  Das Fenster wird bei einer neuen Aktivierung gewählt, nicht während einer laufenden Belegung
  zwangsweise gewechselt. Allgemeine Zeitpläne bleiben Stufe 4.
- **Aktion je Fenster:** Eine gespeicherte Szene dieses Raums, „Natürliches Licht“ mit geprüfter
  optionaler Adaptive-Lighting-Zuordnung oder eine Lampenauswahl mit Helligkeit als Nachtlicht.
  Bei der Lampenaktion können der ganze Raum oder ausdrücklich ausgewählte, freigegebene
  Einzellampen und Lichtschalter auch aus mehreren Räumen gewählt werden, wie bei `toggle_lights`.
  Szenen und Natürliches Licht behalten ihre bereits geprüften eigenen Ziele.
- **Nachlauf und Abdunkeln:** Ausschalten nach 1 bis 86400 Sekunden bestätigter Leerzeit.
  Optional werden 20 Sekunden vorher nur eingeschaltete dimmbare Lampen auf höchstens 30 %
  reduziert; dunklere Nachtlichter werden nicht aufgehellt. Neue Bewegung stellt die unmittelbar
  vorherige Helligkeit wieder her. Reine Schalter werden niemals gedimmt und erhalten nur Ein/Aus.
  Optionales Adaptive Lighting wird vor Nachtlicht/Vorabdunkeln nur für die ausgewählten Lampen
  auf manuell gesetzt, nicht raumweit deaktiviert. Die nächste ausdrückliche Natürliches-Licht-
  Aktivierung hebt diese Markierung wieder auf.
  Automatisches Ausschalten betrifft ausschließlich die erfolgreich automatisch geschalteten Ziele,
  keine anderen Geräte im Raum. Freigabe, Raumzuordnung und Eignung werden vor Befehlen erneut geprüft.
- **Lux-Bedingung:** Optionaler zur Laufzeit wählbarer Illuminanzsensor mit Einheit `lx` und
  Schwelle. Nur Werte unter der Schwelle erlauben den Start. Fehlende, unbekannte oder ungültige
  Werte verhindern ihn; eine spätere Aufhellung blockiert weder Rückkehr aus dem Abdunkeln noch
  das Ausschalten eines bereits gestarteten Bewegungslichts.
- **Manuelle Bedienung hat Vorrang:** Änderungen an den konfigurierten Lichtzielen, etwa durch
  Taster, App oder Szene, pausieren die Raumautomatik. Sie läuft erst wieder, nachdem alle
  Sensoren für die vollständige Ausschaltzeit leer gemeldet haben. Manuell gewählte Zustände
  werden dabei nicht automatisch ausgeschaltet. Eigene Befehle und ihre HA-Kontexte werden
  unterschieden. Adaptive-Lighting-Kontexte mit ID-Vorsilbe `adapt_lgt` gelten auch ohne Elternkontext
  als automatisch. Bei einer von Bewegung gestarteten dynamischen Hue-/Palettenszene pausieren
  reine Farb- und Helligkeitswechsel ihrer Szenenlampen nicht; externes Ein/Aus bleibt manuell.
  Die Ausnahme endet mit dem Lauf bzw. seiner Laufzeit-Zuordnung. Andere unklare Änderungen
  werden vorsichtshalber als manuell behandelt.
- **Oberfläche und Speicherung:** Ein/Aus-Schalter und deutscher Editor auf der Raumseite.
  Konfiguration liegt ausschließlich im Store unter `rooms.<area_id>.motion`; alte Daten brauchen
  keine Migration. Neue Konfigurationen starten ausgeschaltet. Speichern/Deaktivieren verwirft
  offene Timer und Besitzansprüche, ohne Lichtbefehle; die nächste Bewegung aktiviert neu.
  Laufende Timer und manuelle Pausen sind nicht persistent. Nach Neustart werden keine alten
  Ausschaltbefehle nachgeholt. Nur bestätigte Serverantworten gelten als gespeichert.
- **Prüfung/Übergabe:** Ausschließlich synthetische Räume und Geräte; keine ausgeschlossenen
  privaten Räume in Tests oder Beispielen. Details: [STUFE_3B_TESTPLAN.md](STUFE_3B_TESTPLAN.md).
  Nach Öffnen des Draft-PR endet die Arbeit einschließlich CI-Überwachung bis Claudes Rückmeldung.

### Stufe 4 – Zeitpläne

- **Auslöser:** Lokale HA-Uhrzeit; Sonnenaufgang/-untergang mit −1440 bis +1440 Minuten
  Versatz; zur Laufzeit wählbarer Illuminanzsensor mit Einheit `lx`, streng unter oder über
  einer Schwelle. Lux muss 1–86400 Sekunden ununterbrochen erfüllt sein (Editor: fünf Minuten).
  Gleichheit, unbekannte oder nicht verfügbare Werte setzen die Wartezeit zurück. Ein dauerhaft
  erfüllter Wert löst einmal aus; eine neue Schwellenseite startet die nächste Wartezeit.
- **Bedingungen:** Wochentage beziehen sich auf das tatsächliche lokale Ausführungsdatum,
  einschließlich über Mitternacht verschobener Sonnenereignisse. Optional mindestens eine
  ausgewählte `person` zu Hause; alle ausgewählten Personen müssen einen gültigen Zustand haben.
  Optional Lichtziele an (mindestens eines) oder aus (alle). Unbekannte Ziele blockieren sicher.
- **Aktionen:** Gespeicherte Szene (auch dynamisch); Natürliches Licht an/aus; Raum aus;
  freigegebene Lampen und Lichtschalter an/aus mit optionaler Helligkeit; Bewegungsautomatik
  eines Raums an/aus. Ziele, Freigaben und Bedingungen werden zur Laufzeit erneut geprüft.
  Natürliches Licht verwendet die bereits geprüfte optionale Zuordnung, verändert keine
  Freigaben und schaltet ausgeschaltete Lampen nicht ein.
- **Übergänge:** Optional 0–1800 Sekunden. Nur unterstützende Lampen erhalten den Wert,
  reine Schalter nie Helligkeit, Farbe oder Übergang. Der erste Tick dynamischer Paletten
  wartet einen längeren Startübergang ab. Spätere Ticks behalten den Szenenübergang.
- **Oberfläche:** Deutsche Liste mit Ein/Aus, Bearbeiten, Löschen, nächster Ausführung und
  „Jetzt testen“. Der Test führt eine echte Aktion aus, auch bei deaktiviertem Plan, aber nur
  wenn seine Bedingungen erfüllt sind. Bei Lux wird eine nächste Uhrzeit nur während der
  Mindestdauer angezeigt, ansonsten ist der Auslöser ereignisabhängig. Keine Erfolgsmeldung
  vor Serverbestätigung, Fehler und Teilergebnisse werden angezeigt.
- **Speicherung/Lebenszyklus:** Ausschließlich Store `schedules`, keine Migration alter Daten
  nötig, neue Pläne ausgeschaltet. Editieren, Deaktivieren, Löschen und Entladen verwerfen alte
  Timer und wartende Befehle. Nach Neustart werden verpasste Termine nicht nachgeholt.
  Lokale Uhrzeiten in einer Sommerzeitlücke entfallen, doppelte Uhrzeiten laufen einmal.
- **Stufe-3b-Korrektur:** Bei reinen Switch-Zielen einer Bewegungsregel ist `brightness`
  optional und darf `null` sein. Für eine Auswahl mit Lampen bleibt 1–255 erforderlich.
- **Prüfung/Übergabe:** Ausschließlich synthetische Räume und Geräte in Tests und Beispielen.
  [Stufe-4-Testplan](STUFE_4_TESTPLAN.md). Nach Öffnen des Draft-PR endet die Arbeit
  einschließlich CI-Überwachung bis Claudes Rückmeldung.
- **Fertig wenn:** Eine synthetische Szene zum Sonnenuntergang startet, Schwellendauer und
  Bedingungen eingehalten werden, Schalter nur Ein/Aus erhalten und gespeicherte Pläne nach
  Neuladen unverändert vorhanden sind.

### Stufe 4a – Zeitfenster-Bedingung

- Optionales `condition.time_window` für alle Zeitpläne mit `after` und `before`,
  jeweils Uhrzeit, Sonnenereignis mit Versatz oder `null` für eine offene Grenze.
  Beginn inklusive, Ende exklusive; Mitternacht und lokale Zeitumstellungen werden unterstützt.
- Lux-Auslöser behalten eine vor dem Fenster erfüllte Mindestdauer und prüfen zum
  Fensterstart erneut. Höchstens eine automatische Ausführung pro lokalem Tag wird
  vor der Aktion dauerhaft reserviert; auch Neustarts erlauben keine Wiederholung.
  Ohne Fenster bleibt die bisherige Lux-Auslöselogik unverändert.
- Bestehende Zeitpläne werden im Store einmalig um `time_window: null` ergänzt.
- Deutscher Editor und Übersicht mit Uhrzeit/Sonnenstand, Versatz und offenen Grenzen.
- Prüfung und genaue Grenzsemantik: [STUFE_4A_TESTPLAN.md](STUFE_4A_TESTPLAN.md).
  Keine echten Geräteaktionen; nach dem Draft-PR sofort stoppen, auch CI-Überwachung.

### Stufe 5 – Grundhelligkeit

- **Konfiguration je Raum:** Ein Illuminanzsensor mit `device_class: illuminance` und
  Einheit `lx`, Zielhelligkeit, Hysterese, Mindestabstand zwischen Stufenwechseln
  (Vorgabe 180 Sekunden), optional Zeitfenster aus Stufe 4a und ausgewählte `person`-Entities.
  Neue Konfigurationen sind zunächst ausgeschaltet. Lichtziele müssen ausdrücklich freigegeben
  sein und zu diesem Raum gehören. Ein Ziel darf nur einmal in der Stufenliste vorkommen.
- **Geordnete, additive Stufen:** Unter `Ziel − Hysterese` wird genau die nächste Stufe
  zugeschaltet. Helligkeit gilt nur für dimmbare Lampen; Switch-Lichter erhalten ausschließlich
  Ein/Aus. Abgeschaltet wird in umgekehrter Reihenfolge und nur, wenn nach Abzug des gelernten
  Anteils der letzten Stufe noch mehr als `Ziel + Hysterese` verbleibt. Gleichheit schaltet nicht.
  Auch Gegenbewegungen halten den Mindestabstand ein.
- **Eigenlicht lernen:** Nach dem Zuschalten wird ein gültiger Lux-Anstieg nach mindestens
  zehn Sekunden Beruhigungszeit als Schätzung gespeichert. Ohne frische Messung wird nach
  120 Sekunden ohne neuen Lernwert weitergeregelt. Weitere Messungen verwenden einen
  gleitenden Mittelwert mit Faktor 0,25. Ein unbekannter Anteil bleibt `null`, niemals vermeintlich
  null Lux. Ohne verlässlichen Anteil wird die betreffende Stufe nicht automatisch abgeschaltet.
  Tageslichtänderungen und Sensorverzögerung begrenzen die Genauigkeit dieser Schätzung.
- **Vorrang und Sicherheit:** Manuelle Änderungen durch Taster, Szene oder App pausieren die
  Regelung bis zum nächsten Zeitfenster-Beginn oder ausdrücklichem „Raum aus“. Bereits beim
  Start oder Bearbeiten eingeschaltete Lampen werden nicht als eigene Stufen übernommen.
  Fehlende/ungültige Lux-Werte sperren luxbedingte Stufenwechsel. Bei sicherer Abwesenheit
  oder Fensterende werden nur eigene aktive Stufen rückwärts und mit Mindestabstand entfernt;
  unbekannte Personen sperren alle Befehle. Ohne Zeitfenster bleibt eine manuelle Pause bis
  zum ausdrücklichen Raum-Aus bestehen. Nach erfolgreichem Raum-Aus wartet die Regelung eine
  volle Mindestzeit. Am nächsten tatsächlichen Fensterbeginn darf sie die Stufen wieder
  übernehmen, lernt dabei aber nicht aus schon eingeschalteten Zielen.
  Freigabe, Raumzuordnung und Geräteeignung werden vor Serviceaufrufen erneut geprüft.
  Bestehende Raum-/Zielsperren verhindern konkurrierende Schaltfolgen.
- **Natürliches Licht:** Eine vorhandene, gültige Adaptive-Lighting-Zuordnung liefert den
  Weißton für geeignete Lampen; die gewählte Stufenhelligkeit bleibt maßgeblich. Ohne diese
  optionale Integration funktioniert die Regelung ebenfalls.
- **Store und API:** `rooms.<area_id>.brightness` enthält `enabled`, `lux_sensor_entity_id`,
  `target_lux`, `hysteresis_lux`, `min_interval_seconds`, `time_window`, `person_entity_ids`
  und `stages` mit jeweils `entity_ids` und `brightness`. Separate
  `rooms.<area_id>.brightness_learned` enthalten die numerischen/null-Anteile in Stufenreihenfolge.
  Laufzeitbesitz, Timer und manuelle Pause werden nicht gespeichert. Alte Räume brauchen keine
  neue Konfiguration. `brightness/get`, `brightness/save` und `brightness/set_enabled` bedienen
  den deutschen Raumeditor und den Status mit aktuellem Lux, Ziel, aktiver Stufe und Lernwerten.
- **Prüfung/Übergabe:** Nur synthetische Räume, Sensoren, Personen und Geräte.
  [Stufe-5-Testplan](STUFE_5_TESTPLAN.md) trennt automatisierte Prüfung und praktische Abnahme.
  Keine Bereitstellung und keine echten Geräteaktionen. Nach Öffnen des Draft-PR endet die
  Arbeit einschließlich CI-Überwachung bis Claudes Rückmeldung.

### Stufe 5a – Besitz beim Speichern und Abschalten

- `brightness/save` erhält eigene aktive Stufen, wenn die Lampenlisten und ihre
  Reihenfolge unverändert sind. Zielwertänderungen verlieren weder die Besitzzuordnung
  noch die laufende Mindestzeit. Handbedienung bleibt vorrangig; eine bestehende Pause
  wird durch eine reine Zielwertänderung nicht aufgehoben.
- Bei geänderten Lampenlisten, Gruppierung oder Reihenfolge werden die bisherigen
  eigenen Stufen zuerst rückwärts ausgeschaltet. Erst danach werden neue Einstellungen
  gespeichert und die Besitzzuordnung zurückgesetzt. Helligkeits- und Sensoränderungen
  behalten die Zielzuordnung, verwerfen aber wie bisher unpassende persistierte Lernwerte.
  Bei unverändertem Sensor bleiben laufende Messungen und bekannte Eigenlichtanteile der
  bereits eingeschalteten Stufen bis zum Abschalten erhalten; ihre tatsächliche Helligkeit
  wurde durch das Speichern nicht verändert. Ein Sensorwechsel verwirft diese Anteile.
- `brightness/set_enabled` mit `enabled: false` schaltet eigene aktive Stufen ebenfalls
  rückwärts aus. Mit dem optionalen booleschen `keep_lights: true` bleiben sie an und
  werden aus der Besitzverwaltung freigegeben. Erneutes Aktivieren übernimmt sie nicht.
  Auch `brightness/save` mit `enabled: false` schaltet eigene Stufen aus.
- Diese ausdrücklich angeforderten Abschaltungen warten nicht auf Lux, Anwesenheit oder
  die Mindestzeit. Freigabe, Raum und Geräteeignung werden weiterhin unmittelbar vor
  jedem Befehl geprüft. Unbeteiligte und manuell übernommene Lampen bleiben unangetastet.
- Speichern/Deaktivieren und vollständige Stufenwechsel sind je Raum serialisiert.
  Bei einem Abschaltfehler wird die Änderung nicht gespeichert, die Regelung pausiert
  und die noch nicht abgeschalteten eigenen Ziele bleiben für einen erneuten Versuch
  bekannt. Bereits erfolgreiche Abschaltungen werden nicht rückgängig gemacht. Scheitert
  anschließend das Speichern, gelten weiter die alten Einstellungen; bereits abgeschaltete
  Stufen sind auch dann nicht mehr als aktiv verzeichnet.
- Automatisierte Abnahme: [Stufe-5-Testplan](STUFE_5_TESTPLAN.md). Keine echten Geräte,
  Bereitstellung oder Zusammenführung. Nach dem Draft-PR vollständig stoppen.

### Stufe 5b – Einfache Bedienung, Teil 1: Vorschau

- Separater Bedienentwurf unter [vorschau-5b/index.html](vorschau-5b/index.html), vollständig
  mit synthetischen Daten und ohne Verbindung zu Home Assistant. Keine Produktivänderung,
  kein Speichern von Nutzerdaten, keine Gerätebefehle.
- Vorgeschlagene Reiter: Zuhause, Farben, Automationen, Taster, Mehr. Räume/Zonen direkt
  schalten und dimmen; Automationen mit Wann → Wo → Was; Taster über ihre Zeichnung belegen.
- Klickbare Kernabläufe für Zonen, Sonnenversatz, mehrere Aktionen und Nachtlicht ⇄ Automatik.
  Erweiterte Funktionen bleiben unter „Mehr Optionen“ auffindbar.
- [Funktionszuordnung](STUFE_5B_FUNKTIONSZUORDNUNG.md) dokumentiert die neuen Plätze der
  bisherigen Funktionen und grenzt Demo, künftige Migration und produktive Umsetzung ab.
- Teil 1 endet mit dem Entwurfs-PR. Teil 2 einschließlich Servermodell, dauerhafter Speicherung
  und tatsächlicher Zigbee2MQTT-Ereignisverarbeitung benötigt eine separate Nutzerfreigabe.
  [Prüfliste](STUFE_5B_TESTPLAN.md) trennt Vorschau-Abnahme von späteren Integrationstests.

### Stufe 5b – Teil 2: Produktive Umsetzung nach Vorschaufreigabe

- Fünf feste Reiter unten: Zuhause, Farben, Automationen, Taster und Mehr. Die vier
  benannten Reiter haben schlichte Überschriften ohne Werbezeilen. Zuhause zeigt Zonen
  vor kompakten Raumkacheln; seltene Einstellungen bleiben unter „Mehr Optionen“.
- Zonen stehen serverseitig in `zones` mit eigener ID, Name und freigegebenen Lampen.
  Die Zielkennung `zone:<id>` erweitert die bestehenden Raumfunktionen. Räume und Freigaben
  werden nicht verändert; Mehrfachmitgliedschaft ist erlaubt. Entfernte Geräte bleiben als
  reparierbare Verweise erhalten und erweitern niemals automatisch die Freigabe.
- Szenen können pro Raum/Zone mit `night: true` als Nachtlicht markiert werden. Die neue
  Szene entsteht direkt im Ziel: Lampen einstellen, Namen eingeben, speichern. Nachtlicht
  bleibt ein kleiner Knopf; Rückkehr zur Automatik steht nur Tastern und Automationen offen.
- Neue Automationen nutzen Wann → Wo → Was. Die erste Aktion übernimmt die Ziele aus Wo,
  nur weitere Aktionen haben eine zusätzliche Zielauswahl. `actions` werden vollständig
  in Listenreihenfolge abgewartet, auch wenn Ziele überlappen. Innerhalb einer allgemeinen
  Lichtaktion werden gleiche Lampen zusammengeführt; zwischen Aktionen niemals. Eine
  Szene gehört genau einem Raum/einer Zone. Mehrere individuelle Szenen benötigen getrennte
  Aktionen. Nachtlicht/Automatik für mehrere Ziele führt deren jeweilige Szene in Zielreihenfolge
  aus; bei gemeinsamen Lampen gilt dabei der spätere Zielauftrag.
- Alte Ein-Aktions-Pläne und ihre erweiterten Auslöser/Bedingungen bleiben ausführbar und
  bearbeitbar. Der bestehende Editor bleibt für diese Daten erreichbar. Store-Erweiterungen
  sind additiv; unbekannte Zusatzfelder werden beim Bearbeiten beibehalten.
- `automatic_state` speichert automatische Szene-, Nachtlicht- oder Aus-Aktionen je Raum/Zone
  samt lokalem Datum, sobald mindestens eine zugehörige Lampe geschaltet wurde. Teilergebnisse
  werden mit übersprungenen/fehlgeschlagenen Zielen im Protokoll vermerkt. Manuelle Bedienung ersetzt diesen Stand
  nicht. Neustart am selben Tag erhält ihn; Neustart am Folgetag und lokales Mitternacht
  verwerfen ihn. Der eigene heutige Stand hat Vorrang. Fehlt er, werden heutige Stände
  überlappender Räume/Zonen herangezogen: je gemeinsamer Lampe gewinnt der jüngste Stand.
  Es werden nur gemeinsame, weiterhin freigegebene Lampen geändert. Ohne passenden Stand
  bleibt die Rückkehr wirkungslos mit Protokollhinweis. Die Nachtlicht-Erkennung toleriert
  Geräte-Rundungen von ±3 Helligkeit, ±50 K und ±0,01 je xy-Koordinate.
- Taster werden anhand tatsächlicher Event-Entities angeboten. Anlernen erfasst Quelle,
  Ereignistyp und beobachtete Ereignisattribute gemeinsam, statt Tastenattribute zu raten.
  Eine zeitlich begrenzte Anlernsitzung unterdrückt die alte Aktion des erfassten Ereignisses.
  Gerätezeichnungen und Vorlagen helfen bei der Zuordnung; jede physische Taste wird
  ausdrücklich zugeordnet. Unbekannte Typen bleiben mit Rohnamen auswählbar. Beim Anlernen
  kann jedes beobachtete Attribut als „egal“ markiert werden. Bei `dial_rotate` ist `speed`
  anfangs „egal“, die Richtung bleibt unterscheidbar; bestehende genaue Belegungen werden
  nicht nachträglich aufgeweicht.
- Zonen funktionieren auch für Positionen, Farbverteilung, Dynamik und seltene Raumoptionen.
  Einzellampen-/Raumaktionen beenden überlappende lokale Farbdynamik. Gemeinsame physische
  Raumsperren verhindern konkurrierende Szenenbefehle. Switch-Lichter erhalten weiterhin
  ausschließlich Ein/Aus und nie Helligkeits-, Temperatur- oder Farbbefehle.
- Version 0.4.0 enthält das neu gebaute HACS-Frontend. Keine Live-Installation, keine Änderung
  externer Zigbee2MQTT-Automationen. Tests und verbleibende Abnahme mit echten Geräten:
  [STUFE_5B_TESTPLAN.md](STUFE_5B_TESTPLAN.md). Nach Aktualisierung des Draft-PR wieder stoppen.

### Stufe 5c – Stimmungen und Feineinstellung pro Lampe

- Version 0.5.0 ergänzt 25 originale Stimmungen in acht Kategorien zu den unveränderten
  zwölf bisherigen Paletten. Eigene Paletten, Duplikate und referenzgeschütztes Löschen
  bleiben im serverseitigen Store. Bestehende IDs und unbekannte Store-Felder bleiben erhalten.
- Ein gemeinsamer Live-Editor für Palette-/Momentaufnahme-Szenen bietet feste oder
  szenengeführte Helligkeit sowie Farbwechsel, feste Farbe/Weißton, Mondlicht und Aus pro Lampe.
  Entprellte, socketgebundene Probesitzungen stellen bei Abbruch nur noch eigene Änderungen
  zurück. Freigaben und Zielmitgliedschaft werden erneut geprüft. Vorherige Dynamik bleibt
  nach Abbruch gestoppt; ihr vorheriger physischer Lampenzustand wird wiederhergestellt.
- Vier Tempovorgaben, sortierbare Wellenliste und sanfte ±10-%-Helligkeitsschwankungen.
  Ein gemeinsamer Dispatcher begrenzt laufende Dynamik auf ungefähr fünf Befehle pro Sekunde.
  Persistierte Laufabsicht ermöglicht Neustart-Fortsetzung ohne ausgeschaltete Lampen zu wecken.
  Einzelbedienung löst nur die betreffende Lampe aus dem Lauf bis zum nächsten Szenenstart.
- Mondlicht nutzt eine lokale synodische Näherung mit einstellbaren Endwerten und optionalem
  Atmen. Keine Cloud, keine weitere Integration und keine neuen Produktionsabhängigkeiten.
- Lieblingsszenen und Dynamikstatus stehen auf Zuhause. Taster erlauben beim Einschalten
  optional feste Helligkeit oder eine zielbegrenzte Szene, bestehende Belegungen bleiben gleich.
- Jahreszeiten-Szenen ordnen je Raum/Zone normale Szenen lokalen Jahreszeitabschnitten und
  optional einem Weihnachtszeitraum zu. Auflösung erfolgt beim Start, dynamische Läufe
  behalten ihre konkrete Szene. Fehlende Zuordnungen wählen den nächstliegenden verfügbaren
  Jahreszeitabschnitt mit Hinweis. Keine verschachtelten oder fremden Zielreferenzen.
- Taster können beim Einschalten nach Uhrzeit-/Sonnenfenstern Helligkeit/Weißton oder eine
  Szene wählen. Das erste passende Fenster gewinnt, Lücken erhalten das bisherige Verhalten.
- Identitätsgeprüfte Registry-Umbenennung und „Lampe ersetzen“ übertragen ausschließlich
  bekannte Entity-Verweise, keine Namen oder freien Texte. Ersatz benötigt eine aktuelle
  Vorschau und vorherige Freigabe. Konflikte verhindern die gesamte Store-Transaktion.
- Farbmodus unbekannt und Helligkeit null werden nicht als aus/0 % interpretiert. Unterstützte
  Farbe/Weißton initialisiert neue Farblampen; An/Aus-Lichter bekommen niemals Dimmwerte.
- Keine Live-Änderung. Tatsächliche Zigbee-Farben, Übergänge, Geräte-Rückmeldungen und externe
  Automationskonflikte prüft Claude anhand [STUFE_5C_TESTPLAN.md](STUFE_5C_TESTPLAN.md).

## Tests

- Python: `pytest-homeassistant-custom-component` für Store, Szenen-Snapshot/Anwenden,
  Szenenzyklus und Doppelklick-Erkennung.
- Frontend: TypeScript ohne Fehler bauen, ESLint sauber.
- Manueller Test durch Claude am echten System nach jeder Stufe.
