# Stufe-5c-Browserprüfung reproduzieren

Geändert für Lichtzentrale.

Die Dateien `qa_stage5c_fixture.html` und `qa_stage5c_fixture.js` ersetzen nur den HA-WebSocket-Transport. Der Browser lädt das aktuelle Produktions-Bundle mit dessen echtem React-Panel, Komponenten und CSS. Keine laufende HA-Installation wird angesprochen.

Voraussetzungen: Repository-Abhängigkeiten, Home Assistant in der Testumgebung (für den echten Palettenkatalog), offizielles Playwright und ein installiertes Chrome/Chromium. Playwright wird ausschließlich für QA benötigt und ist keine Produktionsabhängigkeit.

Beispiel aus dem Repository-Verzeichnis auf einem System, das einen lokalen Browser starten kann:

```sh
QA_SITE="$(mktemp -d)"
./node_modules/.bin/webpack --output-path "$QA_SITE/assets"
cp scripts/qa_stage5c_fixture.html "$QA_SITE/index.html"
cp scripts/qa_stage5c_fixture.js "$QA_SITE/fixture.js"
.venv-target/bin/python -c 'import json; from custom_components.lichtzentrale.palette_catalogue import builtin_palettes; print(json.dumps(builtin_palettes(), ensure_ascii=False))' > "$QA_SITE/palettes.json"
node scripts/qa_stage5c_capture.cjs --site "$QA_SITE" --out "$QA_SITE/screenshots" --browser /path/to/chrome
```

Falls Playwright außerhalb der Repository-Abhängigkeiten installiert ist, `QA_PLAYWRIGHT` auf das dortige Playwright-Paket setzen. Alternativ verwendet der Runner `require('playwright')`. `QA_BROWSER` kann statt `--browser` verwendet werden. Ohne Browserpfad wird der installierte Chrome-Kanal gewählt.

Der Runner startet einen nur an `127.0.0.1` gebundenen temporären HTTP-Server und einen isolierten Headless-Browser. Beide werden am Ende geschlossen. Er prüft 390 × 844 Pixel, horizontales Überlaufen, Konsolenfehler und die interaktiven Abläufe; die Ergebnisse stehen in `qa-report.json`. PNGs danach immer zusätzlich visuell prüfen. Die 15 Lifecycle-/Race-Tests in `js/LivePreview.test.tsx` decken unter anderem verspätetes Begin/Apply, Abbrechen, wiederholtes Speichern, fehlgeschlagene Wiederherstellung, Keepalive und Unmount ab.
