# Stufe 5d: echte mobile Einstellungen

Beide PNGs zeigen die gebaute Produktionsoberfläche bei 390 × 844 Pixeln mit
synthetischem HA-Transport. Die Bilddateien wurden nicht nachbearbeitet.

- `01-einstellungen-390.png`: Standard 1 % nach Laden der Einstellung.
- `02-einstellungen-gespeichert-390.png`: wieder auf 1 % gespeichert und vom Server neu geladen.

Die PNGs sind absichtlich bytegleich: Nach dem Prüfen von 20 % und Rücksetzen auf
1 % zeigt die Oberfläche wieder denselben bestätigten Zustand. Der Request-Nachweis
für Speichern, Navigation und erneutes Lesen steht in `qa-report.json`.
`SHA256SUMS` hält die unveränderten Originaldateien fest.

Geprüft mit Chrome 157.0.8103.38 und Playwright 1.64.0-beta-1791568591000.
Keine Live-HA-Verbindung, keine privaten Lampen oder Raumdaten. Beide Ansichten
wurden visuell geprüft: Beschriftung, Eingabe und Speichern sind lesbar;
kein horizontaler Überlauf. Die untere Reiterleiste bleibt sichtbar.

Reproduktion: QA-Site wie in `scripts/QA_STAGE5C.md` mit dem aktuellen Produktions-Bundle
und synthetischer Fixture vorbereiten, dann `scripts/qa_stage5d_capture.cjs` statt
des 5c-Runners verwenden. `--site`, `--out`, `--browser` und `QA_PLAYWRIGHT` sind identisch.
