# Lichtzentrale

Eine lokale Licht-App als Custom Integration für Home Assistant. Oberfläche auf Deutsch,
für schmale Bildschirme ausgelegt. Kein Cloud-Konto und keine zusätzlichen
Python-Abhängigkeiten zur Laufzeit.

**Stand: Stufe 1.** Räume und Einzellampen, gespeicherte Raum-Szenen, Hue-Import
und zwölf eigene Farbpaletten in vier Kategorien. **Taster** und **Zeitpläne** bleiben Platzhalter.
Der weitere Ausbau ist in [docs/BAUPLAN.md](docs/BAUPLAN.md) beschrieben.

## Installation über HACS

Voraussetzung: Home Assistant **2026.7 oder neuer**, Zielversion **2026.11** und HACS.

1. In HACS unter **Benutzerdefinierte Repositories**
   `https://github.com/max130595/ha-lichtzentrale` als Typ **Integration** hinzufügen.
2. Lichtzentrale herunterladen und Home Assistant neu starten.
3. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach
   **Lichtzentrale** suchen und den leeren Einrichtungsdialog bestätigen.
4. Die Seitenleiste zeigt **Lichtzentrale** für Administratoren.

Ein noch nicht zusammengeführter Entwicklungsbranch ist nicht automatisch die
HACS-Standardversion. Zum Prüfen dieses Branches den Ordner
`custom_components/lichtzentrale` aus dem Branch in ein **Testsystem** kopieren
und anschließend neu starten. Nach Zusammenführung kann HACS die eingecheckten
Frontend-Dateien direkt verwenden; Node.js wird auf dem HA-System nicht benötigt.

## Erste Farbpalette anwenden

1. In der Galerie **Lampen freigeben** öffnen und ausschließlich die gewünschten
   **Einzellampen und als Licht genutzte Shelly-Schalter** auswählen. Druckerbeleuchtung
   wird standardmäßig ausgeblendet und nur über eine ausdrückliche Anzeigeoption angeboten.
   Zunächst ist keine Lampe freigegeben.
2. Freigabe speichern. Sie wird serverseitig in Home Assistant gespeichert.
3. Eine Palette und eine oder mehrere freigegebene Lampen wählen.
4. Helligkeit und Übergang nach Bedarf einstellen und **anwenden**.

Gruppenlampen von Hue und Home Assistant werden ausgeschlossen. Paletten verteilen
Farben auf Einzellampen. Bei Weißtonlampen wird ein passender Weißton innerhalb der
Gerätegrenzen gewählt. Dimmbare Lampen erhalten nur Helligkeit, reine An/Aus-Lampen
nur den Einschaltbefehl. Nicht erreichbare oder unbekannte Lampen werden übersprungen
und gemeldet. Übergänge werden nur an Lampen gesendet, die sie unterstützen.

## Räume und Szenen

- Räume entsprechen Home-Assistant-Bereichen, unabhängig von Etagen. Eine direkte
  Bereichszuordnung der Entity hat Vorrang vor der Gerätezuordnung. Nur Räume mit
  freigegebenen Lampen erscheinen; auch reine Lichtschalter-Räume werden unterstützt.
- Raum und Einzellampen ein-/ausschalten, dimmbare Lampen regeln, Farbe oder Weißton wählen.
  Raumhelligkeit ändert nur eingeschaltete dimmbare Lampen. Lichtschalter erhalten niemals
  Farb- oder Helligkeitswerte. Die einzelnen Service-Aufrufe starten parallel.
- **Aktuellen Zustand als Szene speichern** sichert Ein/Aus und die aktive Helligkeit/Farbe
  jeder erreichbaren Lampe. Nicht verfügbare Lampen fehlen im Snapshot; die Oberfläche
  meldet dies ausdrücklich. Szene anwenden, löschen, mit Pfeilen sortieren oder favorisieren.
- **Hue-Szene importieren** bietet native Hue-Bridge-Szenen an. Vor Import und jedem Start
  werden die tatsächlichen Hue-Ziele gegen Raum und Freigaben geprüft. Unbekannte Ziele,
  nicht freigegebene Lampen, Gruppen- und Smart-Szenen werden sicher abgelehnt. Start erfolgt
  über `hue.activate_scene`; in der Hue Bridge als dynamisch angelegte Szenen (`is_dynamic`)
  starten dabei dynamisch, die Farben wandern also wie in der Hue-App weiter. Dafür wird der geladene Hue-V2-Ressourcencontroller
  verwendet; wenn dessen Ziele nicht auslesbar sind, wird kein unkontrollierter Aufruf gesendet.
- Die **zuletzt über Lichtzentrale gestartete Szene** bleibt pro Raum im Store erhalten,
  erscheint in Übersicht und Raum und lässt sich mit einem Tipp neu starten. Nur vollständig
  erfolgreiche Starts aktualisieren sie; Teilfehler erhalten den bisherigen Eintrag. Löschen
  entfernt die Referenz. Dies ist ein Startverlauf, keine Erkennung externer Aktivierungen.
  Die Referenz ist typenunabhängig und gilt auch für dynamische Hue-Szenen; eigene dynamische
  Szenen der Lichtzentrale kommen mit Stufe 2 dazu.
- Zur Laufzeit angebotene Shelly-Schalter benötigen eine Beleuchtungsbezeichnung am Gerät
  oder an der Entity (etwa „Deckenlicht“). Andere Switch-Integrationen und alle anderen
  Steuerdomains bleiben gesperrt. Die zusätzliche explizite Freigabe ist immer erforderlich.

Adaptive Lighting und eigene dynamische Szenen der Lichtzentrale (aus Paletten) folgen in Stufe 2. Automatische Anpassungen anderer
Integrationen werden noch nicht pausiert. Adaptive Lighting muss nicht installiert sein.
Services für Automationen: `lichtzentrale.apply_palette`, `lichtzentrale.apply_scene` und
`lichtzentrale.toggle_room`. Alle verwenden dieselben Administrator- und Zielprüfungen wie das Panel.

## Daten und Sicherheit

- Datenmodell: Home-Assistant-`Store`, Schlüssel `lichtzentrale.data`, Version 1.
- Vorbereitet sind `scenes`, `palettes`, `rooms`, `bindings`, `schedules`, `settings`.
  Raum-Szenen, Reihenfolge, Favoriten und der letzte Szenenstart werden gespeichert.
  Die zwölf eingebauten Paletten werden aus eigenen Farbcodes erzeugt; ein eigener
  Paletteneditor folgt später.
- Keine Datenhaltung in Browser-LocalStorage. Lampen werden zur Laufzeit ermittelt,
  Bereiche über `area_id`, ohne vorausgesetzte Etagen.
- Lampenfreigabe und API sind auf Administratoren beschränkt. Der Service
  `lichtzentrale.apply_palette` verwendet dieselbe Freigabeprüfung wie das Panel.
- Neuladen erhält Daten. Entfernen der Integration löscht ihren Store.
- `HAUS.md` bleibt privat und ist durch `.gitignore` ausgeschlossen.

## Entwicklung und Tests

Frontend mit Node.js 22 und npm:

```sh
npm ci
npm run typecheck
npm run lint
npm test
npm run build
git diff --exit-code -- custom_components/lichtzentrale/frontend
```

Python mit Python 3.14:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
ruff check custom_components tests scripts
pytest -q
```

Die festgelegte Version von `pytest-homeassistant-custom-component` enthält
Home Assistant 2026.10.4. Die veröffentlichten Fixtures sind noch nicht mit 2026.11 kompatibel
(entfernter privater Logger-Import). Ein separater Smoke-Test prüft echte APIs von
2026.11.0 ohne diese Fixtures; er ersetzt nicht die vollständige Testsuite:

```sh
uv venv --python 3.14 .venv-target
uv pip install --python .venv-target/bin/python -r requirements-ha2026.11.txt
.venv-target/bin/python scripts/smoke_target.py
```

Der GitHub-Workflow prüft TypeScript, ESLint, Frontend-Tests, Bundle-Aktualität,
Python-Tests, hassfest und HACS. Die lokale und manuelle Prüfliste steht in
[docs/STUFE_1_TESTPLAN.md](docs/STUFE_1_TESTPLAN.md).

## Herkunft und Lizenz

Ausgewählte Grundlagen stammen aus
[Hypfer/hass-scene_presets](https://github.com/Hypfer/hass-scene_presets),
Revision `b53280c76f6a94ea68f313c53865c3922d40b2d7`, und wurden für die neue Domain
und den Stufe-0-Umfang angepasst. Details: [NOTICE](NOTICE), [LICENSE](LICENSE).
Die ursprünglichen Presets, Hue-Szenennamen, Bilder und Logos sind nicht enthalten.
Vorschaubilder entstehen direkt als Farbverläufe aus den eigenen Palettenfarben.
