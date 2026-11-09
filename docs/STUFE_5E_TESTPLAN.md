# Stufe 5e – Effekte, Ambiente zuerst und Szenen-Skripte

## Lieferung

- Branch `stufe-5e-effekte`, Version **0.5.2**.
- Basis: aktuelles `main` beim Arbeitsbeginn,
  `e475747e565434d0bc80cfe616d225f192656ce7` (0.5.1).
- Drei Teile gemeinsam, ohne getrennte Vorschauphase. Das produktive HACS-Frontend
  ist enthalten; die Browserprüfung verwendet nur einen synthetischen HA-Transport.
- Keine Live-Installation, keine Einrichtung von Tastern oder Musik-Skripten,
  kein GitHub-Push/PR, keine Umsetzung von Stufe 6.

## Verhalten und Daten

### A: Lampeneffekte

`lamp_settings[entity_id].effect` darf nur ein aktuell angebotenes Mitglied der
`effect_list` einer geeigneten Lampe sein. Dimmbare Filamentlampen sind eingeschlossen;
reine An/Aus-Lampen und Schalter bleiben effektfrei. Die Oberfläche verwendet deutsche
Namen bekannter Effekte und zeigt unbekannte gültige Werte unter ihrem Originalnamen.

Farbe/Helligkeit werden zuerst gesendet, der Effekt nach ungefähr zwei Sekunden in
seinem eigenen `light.turn_on`. Effektlampen nehmen nicht am Farbwechsel teil. Szenen
ohne Effekt und Ausschalten stoppen einen vorherigen Effekt zuerst mit
`stop_hue_effect`, falls angeboten, andernfalls `none`. Neuere Bedienung, verlorene
Freigabe oder geänderte Zugehörigkeit dürfen einen wartenden Effekt nicht mehr starten.
Live-Probe und Rücknahme verwenden denselben Ablauf, ohne fremde Änderungen zu ersetzen.
Dynamische Szenen behalten den gemeinsamen Begrenzer von ungefähr fünf Befehlen pro
Sekunde. Beim initialen Start werden Effektlampen einschließlich ihrer Wartezeit
konservativ nacheinander verarbeitet; viele Effektlampen verlängern deshalb den Start.

### B: Ambiente zuerst

`binding.params.ambient_first = {scene_id, window}` ist optional und nur für
`toggle_lights` und `toggle_room` gültig. Eine ausgewählte Lampenmenge erhält dafür einen
expliziten Raum oder eine Zone; ihre Lampen müssen dazugehören. Außerhalb des Fensters
bleiben Toggle und `on_behavior` unverändert. Uhrzeit/Sonne mit Versatz und Fenster
über Mitternacht verwenden die vorhandene gemeinsame Fensterlogik.

Innerhalb des Fensters:

1. Laufendes Ambiente hat Vorrang, auch wenn sämtliche Tastenziele selbst noch aus sind.
   Es wird beendet, andere Containerlampen werden ausgeschaltet und Tastenziele werden
   nach dem normalen `on_behavior` eingeschaltet, nicht erneut getoggelt.
2. Andernfalls startet bei ausgeschalteten Tastenzielen die Ambiente-Szene im ganzen Container.
3. Andernfalls gilt das normale Ausschalten der Tastenziele.

Der Laufzeitbesitz stammt aus einem tatsächlichen Szenenstart und endet bei
Handbedienung. Ein gespeichertes `last_scene_id` allein erzeugt nach Neustart keinen
Besitz. Gelöschte Szene: normales Verhalten plus Protokollwarnung. Entzogene Freigaben
oder verschobene Lampen werden nicht stillschweigend weitergesteuert.

### C: Skripte

`Scene.start_script` ist optional (`null` bedeutet kein eigenes Skript). Nur vorhandene
`script.*`-Entities sind speicherbar; es werden keine Skripte erzeugt oder verändert.
Pro ausdrücklichem Szenenstart wird nach den Lichtbefehlen höchstens einmal
`script.turn_on` gesendet. Das eigene Skript einer Jahreszeiten-Szene hat Vorrang,
sonst gilt das Skript der aufgelösten Szene. Es werden niemals beide gestartet.

Kachel, Taster, Zeitplan und Jahreszeiten nutzen dieselbe Ausführung. Live-Probe,
Abbruch/Rücknahme, Dynamik-Ticks und Neustart-Fortsetzung starten kein Skript. Ein
fehlgeschlagener Start erzeugt einen Hinweis und nimmt das Licht nicht zurück.
`script.turn_on` wartet nicht auf den gesamten Ablauf des Benutzerskripts; spätere
Fehler innerhalb dieses Ablaufs protokolliert Home Assistant. Die Integration enthält
keine Spotify-/Music-Assistant-Logik. Diese ausdrücklich beauftragte Skriptaktion ist
keine allgemeine Erweiterung der Lampenfreigaben auf andere Domains.

Alle Felder werden additiv im vorhandenen Store gespeichert, ohne Versionswechsel
oder Migration. Unbekannte Zusatzfelder, alte Szenen und Taster bleiben erhalten.

## Automatisierte Prüfung

```sh
.venv-test/bin/python -m pytest -q
.venv-test/bin/ruff check custom_components tests scripts
.venv-target/bin/python scripts/smoke_target.py
.venv-target/bin/python scripts/smoke_stage5c_review.py
.venv-target/bin/python scripts/smoke_stage5d.py
.venv-target/bin/python scripts/smoke_stage5e.py
npm run typecheck
npm run lint
npm test -- --maxWorkers=2
npm run build
git diff --check
```

Die regulären pytest-Fixtures verwenden HA **2026.10.4**. Vier native Smoke-Skripte
verwenden **2026.11.0** ohne alte Fixtures oder Anpassungen interner HA-Symbole.
Der neue Smoke misst die echte Zweissekunden-Pause mit echten Service-/State-Events,
prüft Effektabbruch, Live-Probe, den dreistufigen Tasterablauf und den Skriptstart
bei Jahreszeiten bzw. dessen Ausbleiben beim Neustart. Alle Daten sind synthetisch.

## Prüffälle

- Aktuelle Effektliste, ungültiger Effekt, Helligkeitslampe, reine An/Aus-Lampe.
- Farbe vor Effekt, Stop vor Szenenwechsel/Aus, Fallback `none`, keine Farbwechsel
  auf Effektlampen, Jahreszeitenauflösung, Abbruch der Live-Probe während Verzögerung.
- Fremder Service, fremder Ein/Aus-Wechsel, Nutzerattributänderung, geänderte Fähigkeit,
  Raum-/Zonenzugehörigkeit und entzogene Freigabe während eines wartenden Effekts.
- Ambiente: drei Zustände, Akzentlampen außerhalb der Tastenziele, außerhalb des
  Zeitfensters, Mitternacht, Sonne mit Versatz, Jahreszeiten und laufende Dynamik.
- `on_behavior`: letzte Werte, Helligkeit, Szene und nach Tageszeit; Zeitlücken fallen
  auf das bisherige Einschalten zurück. Keine Ausweitung auf fremde Räume.
- Gelöschte Szene, Handbedienung, Neustart, Freigabeentzug, Lampenersatz/Umbenennung.
- Skript genau einmal für Kachel/Taster/Zeitplan/Jahreszeit; Wrapper/Teil-Szene;
  keine Wiedergabe bei Preview, Rücknahme, Tick oder Neustart.
- Ungültige/fehlende Skripte beim Speichern, Store-Neuladen, explizites Entfernen,
  Laufzeitfehler ohne Rücknahme erfolgreicher Lichtbefehle.
- Mobile Formulare: übersetzte Effekte, Filament, kein Effekt an An/Aus-Lampen,
  Auswahl/Fehler/erneutes Speichern, Erhalt nach Neuladen und Abbruch bei Navigation.

## Nachgewiesener Stand

- **1.317 Python-Tests bestanden**, finaler Gesamtlauf 39,24 Sekunden unter
  Python 3.14.9 / pytest 9.0.3 / HA 2026.10.4; 95 Fälle mehr als die Main-Basis.
- **229 Frontendtests in 17 Dateien bestanden**, finaler begrenzter Lauf 27,50 Sekunden.
  TypeScript und ESLint bestanden. Ein unbeschränkt paralleler Vorlauf traf die bekannte
  Worker-Startzeitgrenze; der vollständige Lauf mit zwei Workern ist erfolgreich.
- **Alle vier nativen Smoke-Skripte unter HA 2026.11.0 bestanden**. Darunter die
  bisherigen K1/K2-Fälle mit echter Zehnsekundenpause, 5.100 Dimm-Kombinationen und
  die neuen A/B/C-Abläufe mit gemessenen 2,002 Sekunden bis zum separaten Effekt.
- Ruff und Whitespace-Prüfung bestanden. Version 0.5.2 in Manifest, Python-Konstante
  und npm-Metadaten konsistent. Keine neuen Produktionsabhängigkeiten.
- Finales Frontend zweimal bytegleich gebaut, einschließlich Lizenzdateien. Drei
  bekannte Webpack-Größen-/Performancewarnungen, keine Buildfehler.
- Chrome **157.0.8103.38**: alle drei **390 × 844-Pixel-Aufnahmen**, Speichervorgänge
  samt Fehler/Wiederholen und Navigation erfolgreich; kein horizontaler Überlauf,
  keine Browser-/Konsolenfehler. Nur synthetische Daten.
- Geprüftes und ausgeliefertes Produktions-JavaScript, SHA-256:
  `2031c9a739b6ee47cc8e1b2c7ec360c2fa158aa5bd1641304c8604a38e0fc637`.

Keine GitHub-CI, externe hassfest-/HACS-Prüfung oder Live-Abnahme wurde ausgelöst.
Die zusätzlichen nativen Smoke-Skripte sind für künftige CI-Läufe eingetragen.

## Echte Browseransichten

Die Originalaufnahmen zeigen das gebaute React-Panel in Chrome bei **390 × 844 Pixeln**.
Nur der Home-Assistant-Transport ist synthetisch. Es gibt keine Verbindung zum echten
System, keine Gerätesteuerung und keine separat nachgezeichnete Vorschau.

- [Effekt-Feld pro Lampe](screenshots/stufe5e/01-lampen-effekt-390.png)
- [Tasterdialog: Ambiente zuerst](screenshots/stufe5e/02-taster-ambiente-zuerst-390.png)
- [Skript-Feld der Szene](screenshots/stufe5e/03-szenen-skript-390.png)

Runner: `scripts/qa_stage5e_capture.cjs`, Transport: `scripts/qa_stage5e_fixture.js`,
Messwerte: `docs/screenshots/stufe5e/qa-report.json`. Geprüft werden außerdem fehlgeschlagenes
Speichern mit erneutem Versuch, Erhalt gespeicherter Werte, Navigation/Abbruch,
An/Aus-Lampenausschluss, Browser-/Konsolenfehler und horizontaler Überlauf.

## Bundle übernehmen

Im sauberen lokalen Checkout, ohne vorhandene Änderungen zu überschreiben:

```sh
git fetch origin main
git bundle verify /Pfad/ha-lichtzentrale-stufe-5e-0.5.2.bundle
git fetch /Pfad/ha-lichtzentrale-stufe-5e-0.5.2.bundle stufe-5e-effekte
git switch -c stufe-5e-review FETCH_HEAD
```

Bei einem schon vorhandenen Reviewbranch erst dessen neue Commits vergleichen und
normal integrieren. Kein erzwungenes Zurücksetzen. Das Bundle setzt die oben genannte
Main-Basis voraus und enthält das gebaute Frontend.

## Abnahme am echten System durch Claude

1. Farbige Hue-Lampe und dimmbares Filament: gespeicherte Farbe/Helligkeit kommt zuerst,
   danach der gewählte Effekt. Ohne Effekt bzw. Aus stoppt er zuverlässig.
2. Während der Verzögerung andere Szene/Aus/Handbedienung auslösen: kein verspäteter
   Effekt darf diese Bedienung überschreiben. Geräte-Rückmeldungen und Zigbee-Latenz beobachten.
3. Ambiente-Taster im erlaubten Fenster dreimal drücken, einschließlich Szene, die nur
   Akzentlampen außerhalb der Tastenziele einschaltet. Tageszeitverhalten und übrige
   Lampen prüfen. Außerhalb des Fensters, über Mitternacht und nach Handbedienung prüfen.
4. Gewünschtes Musik-Skript separat in HA erstellen und bewusst auswählen. Kachel,
   Taster, Zeitplan und Jahreszeiten starten es einmal. Live-Probe und Neustart nicht.
5. Gleichzeitige externe Automationen, Effektrückmeldungen und langsame Geräte auf
   dem echten System prüfen; isolierte Service-Tests können diese nicht vollständig abbilden.

Nach Bundle und Screenshots endet die Arbeit bis zur nächsten Freigabe.
