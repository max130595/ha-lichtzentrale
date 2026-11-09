# Lichtzentrale

Eine lokale Licht-App als Custom Integration für Home Assistant. Oberfläche auf Deutsch,
für schmale Bildschirme ausgelegt. Kein Cloud-Konto und keine zusätzlichen
Python-Abhängigkeiten zur Laufzeit.

**Stand: Stufe 5e (Entwurf zur Abnahme), Version 0.5.2.** Fünf Reiter:
Zuhause, Farben, Automationen, Taster und Mehr. 37 originale Stimmungen, eigene Paletten
und ein Live-Szenen-Editor mit Helligkeit und Verhalten pro Lampe ergänzen Räume, Zonen,
Taster und Automationen. Dynamik kann nach einem Neustart fortgesetzt werden. Alle
Einstellungen bleiben serverseitig gespeichert. Adaptive Lighting ist optional.
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

1. Unter **Mehr → Lampen freigeben** öffnen und ausschließlich die gewünschten
   **Einzellampen und als Licht genutzte Shelly-Schalter** auswählen. Druckerbeleuchtung
   wird standardmäßig ausgeblendet und nur über eine ausdrückliche Anzeigeoption angeboten.
   Zunächst ist keine Lampe freigegeben.
2. Freigabe speichern. Sie wird serverseitig in Home Assistant gespeichert.
3. Unter **Farben** eine Palette und einen Raum, eine Zone oder freigegebene Lampen wählen.
4. Helligkeit und Übergang nach Bedarf einstellen und **anwenden**.

Gruppenlampen von Hue und Home Assistant werden ausgeschlossen. Paletten verteilen
Farben auf Einzellampen. Bei Weißtonlampen wird ein passender Weißton innerhalb der
Gerätegrenzen gewählt. Dimmbare Lampen erhalten nur Helligkeit, reine An/Aus-Lampen
nur den Einschaltbefehl. `switch.*`-Lichtschalter bleiben bei statischen und dynamischen
Paletten unverändert; Snapshot-Szenen stellen ihren gespeicherten An/Aus-Wert her.
Nicht erreichbare oder unbekannte Lampen werden übersprungen
und gemeldet. Übergänge werden nur an Lampen gesendet, die sie unterstützen.

## Effekte, Ambiente und Skripte

- Im Szenen-Editor können Lampen mit passender Fähigkeit einen **Effekt** aus ihrer
  aktuellen Home-Assistant-Liste erhalten. Farbe/Helligkeit kommen zuerst, der Effekt
  etwa zwei Sekunden später separat. Auch dimmbare Filamentlampen können Effekte haben;
  reine An/Aus-Lichter nicht. Effektlampen nehmen nicht am Farbwechsel teil. Wechsel zu
  einer Szene ohne Effekt und Ausschalten stoppen den Effekt vorher.
- Taster mit **Ausgewählte Lampen umschalten** oder **Raum umschalten** bieten
  **Zur Ambiente-Zeit zuerst Szene**. Innerhalb des Uhrzeit-/Sonnenfensters startet der
  erste Druck bei ausgeschalteten Zielen die Szene im ganzen Raum oder der Zone.
  Der nächste Druck beendet das Ambiente, schaltet die Tastenziele nach ihrem normalen
  Einschaltverhalten ein und die übrigen Containerlampen aus. Danach schaltet der nächste
  Druck aus. Handbedienung beendet die Ambiente-Erkennung. Außerhalb des Fensters bleibt
  das bisherige Verhalten erhalten.
- Jede Szene kann ein vorhandenes **Home-Assistant-Skript** nach den Lichtbefehlen starten.
  Pro Szenenstart höchstens einmal, nicht in der Live-Probe oder beim Fortsetzen nach einem
  Neustart. Bei Jahreszeiten-Szenen gilt deren eigenes Skript, sonst das der aufgelösten
  Szene. Skriptfehler werden protokolliert und machen die Lichtaktion nicht rückgängig.
  Die Integration enthält keine Musikdienst-Logik; Inhalt und Wirkung des gewählten
  HA-Skripts bleiben beim Nutzer.

Die Erweiterungen bleiben serverseitig und benötigen keine Datenmigration. Prüfungen,
Grenzen und die drei echten 390-Pixel-Browseransichten stehen im
[Stufe-5e-Testplan](docs/STUFE_5E_TESTPLAN.md). Keine Live-Installation durch diese Lieferung.

## Dimm-Untergrenze

Unter **Mehr → Einstellungen** lässt sich die globale **Dimm-Untergrenze** von 1 bis
20 % speichern. Standard ist 1 % (Helligkeit 3 von 255). Beim Dunklerdimmen bleiben
bereits eingeschaltete Lampen mindestens auf dieser Grenze; eine Lampe an der Grenze
bekommt keinen weiteren Dimmbefehl. Der Wert gilt für Räume, Zonen und ausgewählte
Lampen, auch am Taster, Drehring und bei wiederholtem Halten.

Hochdimmen schaltet weiterhin keine ausgeschalteten Lampen ein. Aus-Tasten, Toggle,
Zeitpläne und Szenen mit „aus“ funktionieren unverändert. Reine An/Aus-Lichter bekommen
keine Dimmbefehle. Die Grenze liegt im Home-Assistant-Store; bestehende Installationen
verwenden den Standard ohne Datenmigration. Prüfung und Bundle-Übernahme stehen im
[Stufe-5d-Testplan](docs/STUFE_5D_TESTPLAN.md).

## Zonen, Automationen und Nachtlicht

- **Zuhause:** Zonen stehen über Räumen. „Neue Zone“ kombiniert freigegebene Lampen aus
  mehreren Bereichen. Lampen dürfen mehreren Zonen angehören. Löschen einer Zone löscht
  keine Szenen oder Regeln stillschweigend; veraltete Verweise müssen ausdrücklich repariert werden.
- **+ Neue Szene:** Lampen einstellen, Namen vergeben und speichern. Eine normale Szene
  kann je Raum/Zone als Nachtlicht markiert werden. Der kleine Nachtlichtknopf ruft sie ab.
- **Automationen:** Wann → Wo → Was. Die erste Aktion übernimmt die Ziele aus „Wo“;
  zusätzliche Aktionen wählen eigene Ziele. Aktionen werden streng nacheinander ausgeführt.
  Eine spätere Aktion gewinnt bei überschneidenden Zielen. Ein Beispiel ist Zone aus,
  danach ein Raum dieser Zone auf Nachtlicht. Eine gespeicherte Szene gehört zu genau
  einem Raum oder einer Zone; für verschiedene Szenen weitere Aktionen anlegen.
- **Zurück zur Automatik / Nachtlicht ⇄ Automatik:** Als Taster- und Automationsaktionen
  verfügbar. Die letzte zumindest teilweise ausgeführte Szene, Nachtlicht oder Aus pro Ziel bleibt
  bis zum lokalen Tageswechsel gespeichert, auch über einen Neustart. Manuelle Bedienung
  überschreibt diesen Stand nicht. Fehlt ein eigener Stand, gilt für gemeinsame Lampen der
  jüngste heutige Stand aus überlappenden Räumen/Zonen. Andere Lampen bleiben unverändert.
  Ohne passenden Stand wird nichts geschaltet und ein Hinweis ausgegeben. Kleine gerätebedingte
  Rundungen verhindern die Nachtlicht-Rückkehr nicht.
- **Taster:** Gerät und Taste wählen, Ereignis anlernen und Aktion/Ziel speichern. Bei
  Zigbee2MQTT werden Ereignisquelle, Typ und tatsächlich beobachtete Attribute gemeinsam
  verwendet. Unbekannte Ereignisse bleiben sichtbar. Die Dimmer-Vorlage schlägt passende
  Aktionen vor; reale Tastenzuordnungen werden nicht aus Namen geraten. Beobachtete Attribute
  können beim Anlernen einzeln als „egal“ markiert werden. Bei Drehen (`dial_rotate`) ist
  `speed` standardmäßig egal, damit dieselbe Drehrichtung bei jeder Geschwindigkeit passt.
  Bestehende gespeicherte genaue Zuordnungen bleiben unverändert.
- Bewegung, Grundhelligkeit, Positionen und weitere seltene Einstellungen bleiben unter
  **Mehr Optionen** erreichbar. Adaptive Lighting ist weiterhin optional.

Der [Testplan für Stufe 5b](docs/STUFE_5B_TESTPLAN.md) trennt automatisierte Prüfungen und
noch erforderliche Sicht-/Geräteabnahme durch Claude. Dieser Branch wurde nicht live installiert.

## Stimmungen und Szenen pro Lampe (Stufe 5c)

- **Farben:** 37 originale Paletten, darunter die unveränderten bisherigen zwölf sowie
  25 neue Stimmungen in acht Kategorien. Eine Stimmung wählen, Ziel antippen und anwenden.
  „Als Szene speichern“ öffnet den Editor. Eingebaute Paletten lassen sich als eigene
  Variante duplizieren. Eigene Paletten haben 2–6 Farben und werden im HA-Store gespeichert.
- **Szenen-Editor:** Neue und vorhandene Palette-/Momentaufnahme-Szenen bearbeiten.
  Pro Lampe folgt die Helligkeit der Szene oder bleibt fest. Verhalten: Farbwechsel,
  feste Farbe/Weißton, Mondlicht oder aus. Reine An/Aus-Lichter zeigen keine Prozentwerte.
- **Live-Probe:** Änderungen wirken entprellt auf das gewählte Ziel. Speichern übernimmt,
  Abbrechen stellt die vor dem Öffnen erfassten Lampenwerte wieder her. Neuere manuelle
  Eingriffe bleiben erhalten. Eine vorherige Dynamik wird beim Abbrechen nicht neu
  gestartet; die vorherigen Lampenwerte werden statisch wiederhergestellt.
- **Dynamik:** Vier verständliche Tempi, sortierbare Wellenreihenfolge und optional sanfte
  Helligkeitsschwankungen. Feste Lampenwerte bleiben davon unabhängig. Laufende Dynamik
  verteilt ihre Befehle global auf höchstens ungefähr fünf Starts pro Sekunde. Engpässe
  verlängern den Takt, statt zukünftige Takte aufzustauen. Einzelbedienung nimmt nur die
  betreffende Lampe aus dem Farbwechsel; übrige Lampen laufen weiter.
- **Mondlicht:** Lokale Näherung der beleuchteten Mondfläche, ohne Zusatzintegration.
  Helligkeit und Farbe bei Neu-/Vollmond sind einstellbar, mit optionalem Vollmond-Atmen.
  Mondwerte werden während des Szenenlaufs alle 30 Minuten aktualisiert. Bestehende
  externe Automationen werden nicht automatisch verändert oder abgeschaltet.
- **Zuhause:** Lieblingsszenen als Chips, aktueller Szenenstatus und Dynamik starten/stoppen.
- **Taster, beim Einschalten:** Letzter Zustand bleibt der Standard. Optional feste
  Helligkeit, eine Szene oder „nach Tageszeit“ mit Uhrzeit-/Sonnenfenstern und Weißton; Ausschalten bleibt Ausschalten. Bei ausgewählten Lampen
  wird eine Szene nur auf diese Auswahl statisch angewendet, nie auf zusätzliche Ziele.
- **Szene nach Jahreszeit:** Pro Raum/Zone eine Zuordnung für Frühling, Sommer, Herbst,
  Winter und optional Weihnachten. Grenzen sind einstellbar, Weihnachten gilt standardmäßig
  vom 1. bis einschließlich 26. Dezember. Beim Start zählt das lokale HA-Datum. Fehlt die
  aktuelle Zuordnung, wird die zeitlich nächstliegende verfügbare Jahreszeit mit Hinweis
  gewählt. Die Jahreszeiten-Szene ist auch für Taster und Automationen auswählbar.
- **Tageszeitfenster:** Das erste passende Fenster in Listenreihenfolge gewinnt. Beginn ist
  inklusive, Ende exklusiv; Nachtfenster über Mitternacht sind erlaubt. Passt kein Fenster,
  bleibt das bisherige Einschaltverhalten. Die Einstellung wirkt nicht laufend nach dem Druck.
- **Mehr → Lampe ersetzen:** Vorschau aller betroffenen Verweise, anschließend atomare
  Übernahme. Die neue Lampe muss zuvor ausdrücklich freigegeben sein. Unterschiedliche
  bereits vorhandene Werte blockieren den Ersatz, statt sie still zu überschreiben.
  Entity-Umbenennungen mit derselben Registry-Identität werden automatisch mitgezogen.

Der [Testplan für Stufe 5c](docs/STUFE_5C_TESTPLAN.md) dokumentiert automatisierte Abnahme,
Handy-Prüfung und noch erforderliche reale Geräteabnahme durch Claude. Es gibt keine
Live-Installation durch diesen Entwicklungsauftrag und keine automatische Änderung von Zonen.

## Räume und Szenen

- Räume entsprechen Home-Assistant-Bereichen, unabhängig von Etagen. Eine direkte
  Bereichszuordnung der Entity hat Vorrang vor der Gerätezuordnung. Nur Räume mit
  freigegebenen Lampen erscheinen; auch reine Lichtschalter-Räume werden unterstützt.
- Raum ausschalten schaltet alle freigegebenen Einzellichter und Switch-Lichtschalter aus.
  In gemischten Räumen stellt Raum einschalten ohne natürliches Licht nur die vor dem
  Ausschalten eingeschalteten Lampen und Schalter wieder her. Ohne gespeicherten Vorzustand
  werden dort vorsichtshalber keine neuen Ziele eingeschaltet.
- Räume ohne freigegebene `light`-Entities schalten ihre Switch-Lichter direkt ein/aus,
  auch ohne vorherigen Snapshot. Ihr An-Status richtet sich nach den Schaltern; in gemischten
  Räumen weiterhin nach den Lampen. Mit natürlichem Licht gehen Switch-Lichter nie an.
- Einzelbedienung, Dimmen, Farbe und Weißton bleiben verfügbar.
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
  Die Referenz ist typenunabhängig und gilt auch für dynamische Szenen.
- Zur Laufzeit angebotene Shelly-Schalter benötigen eine Beleuchtungsbezeichnung am Gerät
  oder an der Entity (etwa „Deckenlicht“). Andere Switch-Integrationen und alle anderen
  Steuerdomains bleiben gesperrt. Die zusätzliche explizite Freigabe ist immer erforderlich.

## Dynamik und natürliches Licht

- In der Galerie eine Palette und einen Raum wählen, als Raumszene speichern und
  optional **dynamisch** anwenden. Intervall: 5–3600 Sekunden; Übergang: 0–60 Sekunden,
  höchstens so lang wie das Intervall. Je Raum läuft höchstens eine dynamische Szene.
- Laufende Lichtzentrale-Palettenszenen sind mit einer Stopp-Aktion sichtbar. Stoppen hält die aktuelle Farbe.
  Raum ausschalten stoppt die Dynamik. Eine neue Szene ersetzt die bisherige.
  Ausgeschaltete Lampen werden bei späteren Farbwechseln nicht wieder eingeschaltet.
- **Dynamik stoppen** ist im Raum immer erreichbar, auch ohne lokale Palettenszene.
  Die Aktion hält eingeschaltete freigegebene Einzellichter mit ihrer aktuellen Farbe und
  Helligkeit fest und beendet damit auch Hue-Dynamik. Ausgeschaltete, nicht verfügbare Lampen
  und Switch-Deckenlichter bleiben unverändert. Gerätefehler werden einzeln angezeigt.
- **Adaptive Lighting ist optional.** Ohne die Integration bleiben die entsprechenden
  Bedienelemente verborgen. Mit installierter Integration wird im Raum ein passender
  Adaptive-Lighting-Schalter zugeordnet. Es werden nur geprüfte, freigegebene Ziele
  dieses Raums verwendet, keine beliebigen Switch-Entities.
- Farbszenen pausieren natürliches Licht. Bei Raum-Einstellung **Beim Einschalten:
  Natürliches Licht** wird es nach Raum aus/an wieder aktiviert. Diese Einstellung
  und die Zuordnung bleiben serverseitig gespeichert. Raum einschalten aktiviert dabei nur
  die von Adaptive Lighting gesteuerten Einzellichter, nicht alle Raumlampen.
- Aktive lokale Dynamik bleibt serverseitig gespeichert und wird nach einem Neustart
  auf weiterhin freigegebenen, eingeschalteten Lampen fortgesetzt. Ausgeschaltete oder
  inzwischen ausgeschlossene Lampen werden dabei nicht geweckt. Aus, eine neue Szene
  oder eine ablösende Automation beendet den bisherigen Lauf. Aufgaben und Listener
  werden beim Entladen beendet, die Fortsetzungsabsicht bleibt erhalten.

Services für Automationen: `lichtzentrale.apply_palette`, `lichtzentrale.apply_scene`,
`lichtzentrale.toggle_room`, `lichtzentrale.next_scene`, `lichtzentrale.stop_dynamic`, `lichtzentrale.set_adaptive`.
Alle verwenden dieselben Administrator- und Zielprüfungen wie das Panel.

## Lampenpositionen und räumliche Effekte

- Unter **Lampen anordnen** eine Lampe antippen, dann ein Feld im 3×3-Raster auswählen.
  Vorne ist die obere Rasterzeile, hinten die untere. Die Höhe separat einstellen:
  Boden, Möbelhöhe, indirekter Hintergrund oder Decke. Mehrere Lampen je Feld sind möglich.
- Positionen werden ausschließlich im Home-Assistant-Store gespeichert und können entfernt werden.
  Nicht positionierte Lampen folgen bei räumlichen Effekten nach den positionierten Lampen.
- In der Galerie **Farbverteilung** wählen: bisherige Verteilung, links → rechts,
  vorne → hinten oder nach Höhe. Hintergrundlichter bekommen bei Höhe die kräftigste Palettenfarbe.
- Bei dynamischen Palettenszenen lässt **Welle** die Palette schrittweise entlang der gewählten
  Achse wandern. Dafür wird eine räumliche Verteilung benötigt; bei Aktivierung aus der bisherigen
  Verteilung wird links → rechts gewählt. Ein ausdrücklicher Szenenstart schaltet die Ziele wie
  bisher ein; spätere Farbwechsel lassen ausgeschaltete Lampen aus. Positionen und Verteilung
  gelten auch nach Neuladen.
- Die konkrete Wirkung auf einer echten Hue Bridge und die Handy-Abnahme stehen in
  [Stufe-2b-Testplan](docs/STUFE_2B_TESTPLAN.md) für Claudes Prüfung.

## Taster

- Unter **Taster** werden Event-Entities nach Gerät gruppiert, mit den vom Gerät gemeldeten Ereignissen.
  Pro Taste und Ereignis eine Aktion und einen Zielraum wählen. Es werden keine privaten Gerätekennungen
  vorausgesetzt; vorhandene Hue- und Shelly-Taster werden zur Laufzeit ermittelt.
- Aktionen: Raum an/aus, einschalten, ausschalten, nächste Szene, bestimmte Szene, heller/dunkler,
  natürliches Licht an/aus (nur mit Adaptive Lighting) und Dynamik stoppen.
- Für **Nächste Szene** im Raumzyklus Szenen auswählen und sortieren. Nach zehn Minuten ohne
  erfolgreichen Zykluswechsel beginnt die Folge wieder bei der ersten Szene, ebenso nach Neustart.
  Gelöschte oder nicht mehr zulässige Szenen werden übersprungen. Fehlerhafte Ausführungen
  setzen den Zyklus nicht weiter.
- Dimmen ändert eingeschaltete dimmbare Einzellichter relativ um 10 % je Ereignis, auch bei
  `repeat` und Tap-Dial-Drehen. Ausgeschaltete Lampen und Switch-Lichter bleiben unverändert.
- Für Hue ist **Doppelklick** ein zusätzliches Ereignis aus zwei `short_release` im gewählten
  Zeitfenster (500 ms, einstellbar von 200 bis 1000 ms). Nur bei belegtem Doppelklick wird die
  Einfachaktion verzögert. Shelly bietet `double_push` direkt an.
- Unter den Raumeinstellungen auf der Taster-Seite die Einschaltregel wählen: vorheriger Zustand,
  optional natürliches Licht oder eine bestimmte gespeicherte Szene dieses Raums.
- Alle Änderungen gelten erst nach bestätigter Serverantwort und bleiben über Neuladen erhalten.
  Fehlende Tasterbelegungen lassen sich bereinigen. Neustart, Wiederherstellung, Verfügbarkeits-
  und reine Attributänderungen werden nicht als Tastendruck ausgeführt; beim Entladen werden
  wartende Klicks und Aufgaben beendet. Fehler einer Tasteraktion stehen im HA-Log.
- Der [Stufe-3-Testplan](docs/STUFE_3_TESTPLAN.md) beschreibt die manuelle Geräte- und Handy-Abnahme.

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
[docs/STUFE_3A_TESTPLAN.md](docs/STUFE_3A_TESTPLAN.md).

## Herkunft und Lizenz

Ausgewählte Grundlagen stammen aus
[Hypfer/hass-scene_presets](https://github.com/Hypfer/hass-scene_presets),
Revision `b53280c76f6a94ea68f313c53865c3922d40b2d7`, und wurden für die neue Domain
und den Stufe-0-Umfang angepasst. Details: [NOTICE](NOTICE), [LICENSE](LICENSE).
Die ursprünglichen Presets, Hue-Szenennamen, Bilder und Logos sind nicht enthalten.
Vorschaubilder entstehen direkt als Farbverläufe aus den eigenen Palettenfarben.


## Zeitpläne (Stufe 4)

Im Reiter **Zeitpläne** lassen sich Pläne erstellen, bearbeiten, deaktivieren und löschen.
Neue Pläne starten ausgeschaltet. Änderungen gelten erst nach bestätigter Serverantwort.

- Auslöser: lokale HA-Uhrzeit, Sonnenaufgang/-untergang mit Minutenversatz oder ein zur
  Laufzeit ausgewählter Illuminanzsensor (`lx`) über/unter einer Schwelle. Lux benötigt eine
  ununterbrochene Mindestdauer (standardmäßig fünf Minuten); ein dauerhafter Wert löst nur
  einmal aus. Nach Neustart beginnt die Mindestdauer neu.
- Bedingungen: Wochentage, mindestens eine ausgewählte Person zu Hause, Ziele bereits an
  (mindestens eines) oder aus (alle). Unbekannte Zustände werden sicher blockiert.
- Aktionen: gespeicherte Szene einschließlich Dynamik, Natürliches Licht an/aus, Raum aus,
  freigegebene Lampenauswahl an/aus mit optionaler Helligkeit oder Raum-Bewegungsautomatik an/aus.
- Optionaler Übergang: 0–1800 Sekunden für unterstützende Lampen. Switch-Lichtschalter
  erhalten ausschließlich Ein/Aus. Ein langer Startübergang verzögert den ersten Farbwechsel
  dynamischer Paletten. Natürliches Licht schaltet die Automatik um; ausgeschaltete Lampen
  bleiben aus. Dafür wird die vorhandene optionale Adaptive-Lighting-Zuordnung verwendet.
- Die Liste zeigt die nächste geplante Uhrzeit in der HA-Zeitzone. Für Lux ist sie erst während
  der laufenden Mindestdauer bekannt. Bedingungen werden erst bei der Ausführung geprüft.
- **Jetzt testen** führt die echte Aktion einmal aus, auch bei ausgeschaltetem Plan. Bedingungen
  bleiben wirksam. Es ist keine Simulation. Automatisierte Entwicklungstests verwenden nur
  synthetische Geräte; die Prüfung am echten System übernimmt Claude nach der Übergabe.

Details und Abnahmefälle: [Stufe-4-Testplan](docs/STUFE_4_TESTPLAN.md).
