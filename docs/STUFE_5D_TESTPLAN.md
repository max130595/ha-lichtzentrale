# Stufe 5d: Dimm-Untergrenze und Übergabe

## Umfang

Branch `stufe-5d-dimmgrenze`, Version **0.5.1**, Basis des aktualisierten `main`:
`8633cafaf810d9139e3b148b86c2c09be3429a65`.

- **Mehr → Einstellungen → Dimm-Untergrenze**: ganze Prozentwerte von 1 bis 20,
  Standard 1 % entsprechend 3/255. Speicherung erst nach bestätigter Serverantwort.
- `settings.dim_min_pct` wird im vorhandenen Home-Assistant-Store gespeichert.
  Fehlende Werte erhalten den Standard ohne Migration oder Wechsel der Store-Version.
  Andere Einstellungen, Freigaben und unbekannte zukünftige Felder bleiben erhalten.
- Räume, Zonen und ausgewählte Lampen verwenden dieselbe Berechnung. An oder unter
  der Grenze wird nichts gesendet. Ein Schritt, der sie erreicht oder unterschreitet,
  sendet die absolute Grenze; sonst bleibt der native relative Schritt erhalten.
- Der zuletzt bekannte Lampenzustand und die Einstellung werden unmittelbar vor dem
  eigenen Dienstaufruf erneut geprüft. Die Berechnung berücksichtigt die native
  Home-Assistant-Rundung von Helligkeit auf Prozent und zurück.
- Nur eingeschaltete dimmbare Einzellichter bekommen Dimmwerte. Ausgeschaltete Lampen,
  nicht verfügbare Geräte, unbekannte Helligkeiten und reine An/Aus-Lichter bleiben ausgenommen.
- Hochdimmen sowie ausdrücklich verlangtes Aus/Toggle bleiben unverändert. Bewegung
  und Grundhelligkeit verwenden im bestehenden Code absolute Werte, keine relativen
  Dimm-Schritte, und wurden nicht verändert. Szenen dürfen weiterhin dunkler sein.
- Neue Admin-WebSocket-Befehle: `settings/get` und `settings/dimming` mit `dim_min_pct`.
  Die bestehende Lampenfreigabe über `settings/save` bleibt getrennt.

## Automatisierte Prüfung

```sh
.venv-test/bin/python -m pytest -q
.venv-test/bin/ruff check custom_components tests scripts
.venv-target/bin/python scripts/smoke_target.py
.venv-target/bin/python scripts/smoke_stage5c_review.py
.venv-target/bin/python scripts/smoke_stage5d.py
npm run typecheck
npm run lint
npm test -- --maxWorkers=2
npm run build
git diff --check
```

Die regulären pytest-Fixtures verwenden Home Assistant **2026.10.4**. Die separaten
nativen Smoke-Tests laufen unter **2026.11.0**, ohne alte pytest-Fixtures oder
Änderungen an internen HA-Symbolen. Alle Lampen und Ereignisse sind synthetisch.

Zu prüfen sind 5 % → 3/255, kein Befehl bei 3/255, normaler Schritt bei 50 %,
gemischte Zielhelligkeiten, Raum/Zone/Einzellampen, Halten/Wiederholungen,
Drehring-Ereignisse, Einstellgrenzen und ungültige Werte, Store-Neuladen,
Speicherfehler, unverändertes Hochdimmen und unveränderte Aus-Aktionen.

## Nachgewiesener Stand

- **1.222 Python-Tests bestanden**, letzter Gesamtlauf 32,08 Sekunden unter Python
  3.14.9 / pytest 9.0.3 / HA 2026.10.4. Dazu gehören 74 neue Dimm-/Ereignisfälle.
- **218 Frontendtests bestanden** mit zwei Vitest-Workern, darunter 16 neue
  Einstellungs-/Integrationstests. TypeScript und ESLint bestanden.
- Alle drei nativen Smoke-Skripte unter **HA 2026.11.0 bestanden**. Der neue Dimm-Smoke
  prüft **5.100 Kombinationen** mit dem echten HA-Licht-Diensthandler, außerdem
  Zustandwechsel vor Dispatch und wiederholtes Dimmen an der Grenze.
- Ruff und Whitespace-Prüfung bestanden. Unabhängige Codeprüfung ohne Blocker.
- Frontend zweimal bytegleich gebaut, einschließlich Lizenzdateien. Drei bekannte
  nicht blockierende Webpack-Größen-/Performancewarnungen, keine Buildfehler.
- Der zunächst unbeschränkt parallele Frontend-Testlauf hatte Worker-Startzeitüberschreitungen;
  der vollständige Lauf mit `--maxWorkers=2` bestand. Kein Testfehler wurde verdeckt.
- Chrome **157.0.8103.38**, Playwright **1.64.0-beta-1791568591000**: zwei echte
  **390 × 844-Pixel-Aufnahmen**, kein Überlauf und keine Browser-/Konsolenfehler.
- Getestetes und ausgeliefertes JavaScript, SHA-256:
  `147e931276ff9feb4227ed515906eda063dd0732c5b4f4e694f0adc92c4d2964`.

Es wurde keine GitHub-CI, externe HACS-/hassfest-Prüfung oder Live-Abnahme ausgelöst.

## Echte Browseransicht

Der 390-Pixel-Screenshot zeigt das gebaute produktive React-Panel. Nur der HA-Transport
ist durch synthetische Daten ersetzt; es gibt keine getrennte Produktvorschau und
keine Verbindung zum echten HA-System. Der Runner `scripts/qa_stage5d_capture.cjs`
prüft Laden, Speichern, Navigation, erneutes Laden, Konsolenfehler und horizontalen
Überlauf. Bilder und Ergebnisprotokoll liegen unter `docs/screenshots/stufe5d/`.

## Bundle übernehmen

Das Bundle enthält nur den Entwicklungsbranch und setzt die oben angegebene Main-Basis
voraus. Im eigenen sauberen Checkout, ohne vorhandene Änderungen zu überschreiben:

```sh
git fetch origin main
git bundle verify /Pfad/ha-lichtzentrale-stufe-5d-0.5.1.bundle
git fetch /Pfad/ha-lichtzentrale-stufe-5d-0.5.1.bundle stufe-5d-dimmgrenze
git switch -c stufe-5d-review FETCH_HEAD
```

Vor dem Übernehmen in einen bestehenden Branch dessen neue Commits regulär vergleichen
und integrieren. Kein erzwungenes Zurücksetzen. Das gebaute HACS-Frontend ist enthalten.

## Grenzen und praktische Abnahme

Keine Live-Installation, kein Zugriff auf echte Lampen, kein GitHub-Push und kein PR
wurden ausgeführt. Stufe 6 ist ausdrücklich nicht Teil dieser Lieferung. Nach dem
Bundle und Screenshot endet die Arbeit bis zur nächsten Freigabe.

Claude bzw. der Nutzer prüft nach Sicherung und Installation am echten System:

1. Einstellung 1 % speichern und nach Neuladen/Neustart wiederfinden.
2. Eine freigegebene dimmbare Lampe bei 5 % herunterdimmen: sie bleibt an bei 3/255.
3. Weiteres Drücken, Drehen und Halten erzeugt an der Grenze keinen weiteren Befehl.
4. Hochdimmen funktioniert anschließend; ausgeschaltete Lampen bleiben dabei aus.
5. Gemischte Zielgruppe: jede Lampe stoppt an ihrer Grenze, An/Aus-Lichter bleiben ungedimmt.
6. Testweise 20 % speichern und erneut prüfen; danach den gewünschten Wert setzen.
7. Toggle, Aus-Taste, Aus-Zeitplan und Szene mit „aus“ schalten weiterhin aus.

Der Assistent kann die Geräte-Rückmeldegeschwindigkeit, Übergänge und gleichzeitig
arbeitende externe Automationen nur am echten System bewerten. Normale relative
Schritte bleiben auftragsgemäß native HA-Befehle; eine externe Änderung nach unserer
letzten Prüfung kann weiterhin mit deren späterer Verarbeitung konkurrieren.
