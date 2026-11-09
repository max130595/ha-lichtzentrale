# Stufe 5c: echte mobile Produktionsoberfläche

Geändert für Lichtzentrale. Prüfung am 9. November 2026.

Diese 18 PNGs zeigen das unveränderte gebaute Produktions-Panel, keine nachgebaute Vorschau. Nur der Home-Assistant-Transport ist durch reproduzierbare synthetische Daten ersetzt. Die Räume, Geräte, Zustände und Szenen sind fiktiv. Es gab keine Verbindung zu einer laufenden Home-Assistant-Installation.

## Messwerte und Ergebnis

- Alle PNGs: 390 × 844 Pixel, Geräteskalierung 1.
- Google Chrome 157.0.8103.38, Playwright 1.64.1, Sprache de-DE.
- Dokument- und Inhaltsbreite in jeder Aufnahme: 390 Pixel; keine horizontal überstehenden Bedienelemente.
- Keine Browser-Seitenfehler und keine Konsolenfehler im gesamten Durchlauf.
- Alle 18 finalen Aufnahmen wurden anhand der tatsächlichen Pixel visuell geprüft.
- Produktions-JavaScript SHA-256: `8dd74d8c1705684a8a43a24e9a154cdb6104f085d70f042af19a6008d318ca30`.

Die Karten, Beschriftungen, Auswahllisten und Farbfelder sind lesbar. Die Galerie passt zweispaltig. Die feste Speichern-Leiste bleibt beim Scrollen sichtbar; alle Bedienelemente lassen sich darüber hinaus scrollen und bedienen. Lange Formulare werden deshalb in mehreren echten Bildschirmabschnitten gezeigt. Die Jahreszeiten-Zuordnung nutzt absichtlich dieselbe synthetische Szene, um das Speichern aller vier Zuordnungen mit einem kleinen Datensatz zu prüfen.

## Erfolgreich ausgeführte Bedienprüfungen

1. Zuhause zeigt Favoriten-Chips und laufende Dynamik; Galerie zeigt 37 eingebaute Stimmungen einschließlich Herbstglut.
2. Eigene Palette anlegen, Farbe ergänzen, wiederholt ändern und die letzte Änderung live anwenden.
3. Navigation aus der Live-Probe wartet auf Abbruch/Wiederherstellung; anschließend ist keine Vorschau-Sitzung mehr offen.
4. Eigene Palette ohne Live-Probe speichern und Verwaltungsaktionen anzeigen.
5. Vorhandene Szene bearbeiten: feste Lampenhelligkeiten 18/24 %, feste Farbe, Mondlicht und Ein/Aus erhalten, Welle umsortieren, letzte Fassung speichern.
6. Jahreszeiten-Zuordnungen, Weihnachten und abweichenden Frühlingsbeginn am 20. März speichern.
7. Lampenersetzung vorschauen und abbrechen, ohne eine Ersetzung zu schreiben.
8. Taster mit fester Einschalt-Helligkeit speichern; 35 % werden als 89/255 übertragen.
9. Taster-Zeitfenster speichern: 22:30–06:30 mit Helligkeit/Weißton sowie Sonnenuntergang minus 30 Minuten mit Szene und offenem Ende.

`qa-report.json` enthält die automatisierten Ergebnisse. `sha256.json` enthält Abmessungen und Prüfsummen der unveränderten PNGs. Das prüft die Produktionsoberfläche und ihre API-Aufrufe. Reale Lampen, Funklaufzeiten, iOS/Safari und tatsächliche HA-Zustandswiederherstellung werden dadurch nicht nachgewiesen; dafür sind Integrationstests beziehungsweise die Prüfung auf dem Zielsystem nötig.

## Aufnahmen

- [01 Zuhause](01-zuhause-390.png): Favoriten-Chips und laufende Dynamik.
- [02 Galerie](02-galerie-390.png): Herbst- und Winterpaletten.
- [03 Eigene Palette](03-eigene-palette-390.png): Name, Kategorie und drei Farben.
- [04 Live-Probe](04-palette-live-390.png): Ziel, Tempo und Speichern.
- [05 Szeneneditor](05-szeneneditor-390.png): Grundlage, Palette und Gesamthelligkeit.
- [06 Welle](06-welle-390.png): Tempo, sanfte Dynamik und Reihenfolge.
- [07 Lampenhelligkeit](07-lampenhelligkeit-390.png): getrennte 18/24-%-Werte.
- [07b Feste Farbe](07b-feste-farbe-390.png): feste Farbe und Lampenhelligkeit.
- [08 Mondlicht](08-mondlicht-390.png): Mondphase, Neumond/Vollmond und Farben.
- [08b Ein/Aus](08b-ein-aus-390.png): langsames Atmen und reiner Ein/Aus-Schalter.
- [09 Lampe ersetzen](09-lampe-ersetzen-390.png): betroffene Einträge vor Bestätigung.
- [10 Einschaltverhalten](10-taster-einschalten-390.png): feste Helligkeit und unverändertes Ausschalten.
- [11 Jahreszeiten](11-jahreszeiten-390.png): Szenenzuordnung.
- [12 Weihnachten](12-weihnachten-390.png): zusätzliche Szene und Datumsbereich.
- [13 Jahreszeitenbeginn](13-jahreszeiten-beginn-390.png): vier bearbeitbare Jahresgrenzen.
- [14 Nacht-Zeitfenster](14-taster-zeitfenster-390.png): Fenster über Mitternacht.
- [15 Weißton](15-taster-weisslicht-390.png): 18 % und 2200 K.
- [16 Sonnenzeit](16-taster-sonnenzeit-390.png): Versatz, offene Grenze und Szene.
