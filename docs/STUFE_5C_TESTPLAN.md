# Stufe 5c: Abnahme von Stimmungen und Szenen-Editor

## Umfang und sichere Prüfumgebung

Basis ist das am 09.11.2026 frisch aktualisierte `main` mit Commit `996f263` einschließlich Nachträgen 6a und 4a.
Gearbeitet wird auf `stufe-5c-paletten`. Keine getrennte Vorschauphase: Die Screenshots
zeigen die produktiven React-Komponenten mit ausdrücklich synthetischen Home-Assistant-Daten.
Kein Test spricht das echte Home Assistant, Geräte oder bestehende externe Automationen an.
`docs/AUFTRAEGE.md` bleibt unverändert in Claudes Verantwortung.

## 1. Galerie und eigene Paletten

- Mindestens 20 originale Stimmungen über Herbst, Winter, Weihnachten, Frühling, Sommer,
  Party, Entspannen und Romantik; je 3–5 Farben und sinnvolles Starttempo/Helligkeit.
- Herbstglut enthält genau die beauftragten fünf Hexfarben. Alle bisherigen 12 IDs und
  Farben bleiben erhalten, damit vorhandene Szenen weiterhin auflösbar sind.
- Eigene Palette mit 2–6 Farben erstellen, bearbeiten, aus eingebauter Palette duplizieren,
  live auf ein ausgewähltes Ziel probieren und serverseitig speichern. Verlauf aktualisiert
  sich unmittelbar. Ungültige Farben, leere Namen und ungültige Grenzen werden abgewiesen.
- Palette überall auswählbar. Löschen einer referenzierten Palette ist gesperrt und nennt
  die betroffenen Szenen. Nicht referenzierte eigene Palette kann gelöscht werden.

## 2. Szenen-Editor und Live-Bearbeitung

- Bestehende und neue Palette-/Momentaufnahme-Szenen öffnen, Namen/Typ/Tempo ändern und
  pro Lampe Helligkeit wie Szene oder fest einstellen. Feste Werte bleiben bei Änderung
  der Gesamthelligkeit unverändert. Eine gemeinsame Lampe kann in verschiedenen Szenen
  unterschiedliche Einstellungen haben.
- Verhalten Farbwechsel, feste Palettenfarbe/eigene Farbe/Weißton, Mondlicht und Aus prüfen.
  Reine Ein/Aus-Lichter, einschließlich `switch_as_x`, zeigen An/Aus und erhalten keine
  Helligkeits-, Temperatur- oder Farbfelder in Gerätebefehlen.
- Änderungen werden entprellt live probiert. Speichern übernimmt; Abbrechen stellt den
  Zustand vor dem Öffnen wieder her. Auch Zielwechsel, Reiterwechsel, Schließen, verspätete
  Antworten, mehrfaches Klicken und eine unterbrochene Sitzung prüfen. Neuere Handbedienung
  darf durch verspätetes Zurücksetzen nicht überschrieben werden.
- Während einer Sitzung entzogene Freigaben, entfernte Ziele oder geänderte Zonen dürfen
  nie zu zusätzlichen Gerätebefehlen außerhalb der noch gültigen Auswahl führen.

## 3. Dynamik, Helligkeit und Zigbee-Last

- Synthetische Zonen-Szene mit mindestens drei Takten: zwei feste dunkle Helligkeiten,
  eine feste Farbe, ein Mondlicht, ein Aus-Ziel und weitere Farbwechsel-Lampen.
- Sehr langsam 180/60 s, Langsam 90/40 s, Mittel 30/15 s und Schnell 8/3 s; alte freie
  Sekundenwerte bleiben erhalten und unter Mehr Optionen bearbeitbar.
- Sortierbare Wellenliste gibt die Reihenfolge vor. Altes Raster bleibt als seltene Option.
  Sanft lebendig bleibt im Bereich ±10 % der jeweiligen Farbwechsel-Helligkeit; feste
  Farben, Mondlicht und Aus-Ziele werden dadurch nicht ungewollt verändert.
- Befehle werden verteilt. Gleichzeitig laufende Szenen zusammen überschreiten ungefähr
  fünf Lichtbefehle pro Sekunde nicht. Langsame Dienste und Überlast erzeugen keinen
  anwachsenden Befehlsstau; der Takt verlängert sich mit Protokollhinweis.
- Persistierten aktiven Lauf neu laden und wieder aufnehmen. Aus, Szenenwechsel und eine
  ablösende Automation verhindern unerwünschten Wiederanlauf. Handbedienung einer Lampe
  entfernt nur diese aus der Dynamik bis zum nächsten Szenenstart.

## 3a. Taster: Verhalten beim Einschalten

- Lampen und Raum/Zone ein/aus: letzter Zustand bleibt Standard ohne Datenmigration.
- Feste Helligkeit 1–100 % wirkt nur beim Einschalten; erneutes Umschalten schaltet aus.
  Reine Ein/Aus-Lichter erhalten weiterhin ausschließlich An/Aus, auch bei 100 %.
- Eine Einschalt-Szene für einen Raum gehört genau zu diesem Ziel. Bei ausgewählten
  Lampen wirkt sie nur auf diese und darf keine weiteren Lampen mit einschalten.
- Speichern/Neuladen, ungültige Werte, entfernte Szenen sowie während eines wartenden
  Tastendrucks entzogene Freigaben prüfen. Alte Belegungen behalten ihre Parameter.

- Nach Tageszeit: Uhrzeit- und Sonnenauf-/untergangsgrenzen mit Minutenversatz, Fenster
  über Mitternacht und lokale Sommer-/Winterzeit prüfen. Anfang inklusive, Ende exklusiv.
  Erstes passendes Fenster gewinnt in Listenreihenfolge; Lücken nutzen den letzten Zustand.
  Passendes Fenster wählt Helligkeit/Weißton oder eine Szene, ausschließlich beim Einschalten.
  Weißeinstellungen werden bei RGB-/XY-Lichtern sicher als Farbwerte umgesetzt.

## 3b. Jahreszeiten-Szene

- Eine Jahreszeiten-Szene pro Raum/Zone mit vier Zuordnungen und optional Weihnachten.
  Meteorologische Standardgrenzen und frei gewählter Weihnachtszeitraum werden gespeichert.
- Auswahl in Kacheln, Tastern und Automationen löst zum Ausführungszeitpunkt nach HA-Ortsdatum
  die passende Szene auf. Fehlende aktuelle Zuordnung nutzt einen gekennzeichneten nahen Ersatz.
- Keine Rekursion und keine Zuordnung fremder Raum-/Zonenszenen. Entfernte Szenen bleiben
  reparierbar; nachträgliche Fremdziele oder entzogene Freigaben dürfen nie ausgeführt werden.
- Datumsgrenzen, Jahreswechsel, Schaltjahr, benutzerdefinierte Grenzen, leere Zuordnung,
  Weihnachten, doppelte Jahreszeiten-Szene, Speicherung und Fortsetzung einer dynamischen
  konkreten Szene nach Neustart prüfen. Romantik enthält mindestens vier ruhige Stimmungen.

## 4. Mondlicht

- Mondfläche wird ohne Netz, Zusatzintegration oder zusätzliche Python-Abhängigkeit lokal
  aus dem synodischen Monat berechnet. Wertebereich und bekannte Neu-/Vollmondnähe prüfen.
- Standard 10/80 %, einstellbare Endfarben und Helligkeiten, stetiger Übergang. Laufende
  Szene aktualisiert spätestens nach 30 Minuten. Vollmond-Atmen ist optional und begrenzt.
- Keine vorhandene Mond-Automation wird automatisch abgeschaltet. Eine bisher nicht zur
  Zone gehörende Akzentlampe wird nicht ungefragt aufgenommen.

## 5. Startseite, Umbenennen und Ersetzen

- Lieblingsszenen-Chips auf Raum-/Zonenkacheln; aktuelle Szene und Dynamikstatus sichtbar.
  Antippen des Status stoppt/startet die Dynamik ohne unbeabsichtigten Zielwechsel.
- Registry-Umbenennung über `old_entity_id`: Freigaben, Zonen, Szenenwerte, Positionen,
  Taster, Zeitpläne, Bewegung, Grundhelligkeit, Automatikstand und neue Laufdaten bleiben
  konsistent. Nur vollständige Referenzen werden ersetzt, keine Namen oder Teilzeichenfolgen.
- Lampe ersetzen zeigt vor Ausführung die betroffenen Einträge. Veraltete Vorschau,
  Kollisionen, nicht geeignete Ziele und fehlgeschlagene Persistenz werden sicher behandelt.
  Mehrfache Referenzen und unbekannte Zusatzfelder gehen nicht still verloren.

## 6. Gerätefähigkeit und Regression

- Zigbee2MQTT-Lampen mit `color_mode: unknown` und `brightness: null` werden nicht als
  ausgeschaltet/0 % dargestellt. Der erste passende Befehl enthält Farbe oder Weißton.
- xy-Farben werden am bekannten Lampengamut begrenzt; Weißtonlampen erhalten einen
  passenden unterstützten Weißton. Unbekannte/nicht verfügbare Geräte sicher behandeln.
- Alle bisherigen Szenen, Zonen, Automationen, Taster, Bewegungs- und Grundhelligkeitsregeln
  einschließlich Aktivierungszustand und unbekannter Zusatzfelder bleiben erhalten.
- Gesamte Python- und Frontend-Suiten, Typprüfung, Lint, nativer HA-2026.11-Smoke und
  zweimaliger bytegleicher Frontend-Build vor Übergabe. Ergebnisse werden unten ergänzt.

## Sichtprüfung und echte Abnahme

390-px-Screenshots: Galerie, eigene Palette, Szenen-Editor mit einzelnen Lampen,
Welle/Mondlicht und schnelle Startseite. Tatsächliche Pixel auf Überlauf, Überdeckung,
lesbare Beschriftungen und erreichbare Bedienelemente prüfen; DOM-Tests allein reichen nicht.
Die Bildunterschriften nennen synthetische Daten, keine Live-Abnahme behaupten.

Claude prüft anschließend Installation, Neustart, Logs, Zigbee-Verhalten und Bedienung
am echten System. Der Nutzertermin ist der Folgetag bis 15:00 Uhr; diese Lieferung nimmt
weder die Live-Installation noch deren erfolgreiches Ergebnis vorweg. Nach Draft-PR bzw.
Bundle mit Screenshots stoppen, keine weiteren Branch-Änderungen oder CI-Überwachung.

## Nachgewiesener Stand am 09.11.2026

- Python 3.14.9, Home Assistant 2026.10.4: **1.107 Tests bestanden** (`pytest -q`).
- Nativer separater Smoke-Test mit **Home Assistant 2026.11.0 bestanden**. Einschließlich
  Store-Schreiben/Neuladen, neuer Paletten, per-Lampen-Helligkeit, Dynamik-Neustart,
  Taster-Helligkeit/Tageszeit und Jahreszeiten-Auflösung. Keine Geräteverbindung.
- Frontend: **202 Tests in 15 Dateien bestanden**, `npm run typecheck` und `npm run lint` sauber.
  Der bestätigte Gesamtlauf nutzte `npm test -- --maxWorkers=2`, nachdem ein früherer
  hochparalleler Lauf ein Prozess-Startzeitlimit hatte. Node 24.22.1, npm 11.9.0.
- `ruff check --no-cache custom_components tests scripts` und `git diff --check` sauber.
- `npm run build` zweimal: JavaScript und beide Lizenzdateien bytegleich. Nur die bekannten
  unverbindlichen Webpack-Größenhinweise, keine Build-Fehler.
- Ausgeliefertes und in Chrome geprüftes JavaScript: SHA-256
  `8dd74d8c1705684a8a43a24e9a154cdb6104f085d70f042af19a6008d318ca30`.
- Tatsächliches Chrome bei **390 × 844 Pixeln**, 18 Screenshots mit synthetischen Daten.
  Keine horizontal überlaufenden Bedienelemente und keine Seiten-/Konsolenfehler.
  Durchgeklickt: eigene Palette, Live-Änderung/Abbruch bei Navigation, Lampenwerte,
  Wellenreihenfolge, Mondlicht/Aus, Jahreszeiten/Weihnachten, Ersatz-Vorschau und
  Tasterfenster mit Nachtzeiten, Weißton und Sonnenuntergangsversatz.

Screenshots und zugehöriger Browserbericht liegen unter `screenshots/stufe5c/`.
Die Darstellung und Befehlsanforderungen sind damit geprüft; echte Zigbee-Farben,
physische Rückmeldungen, vollständige Installation und reale externe Automationen sind
noch nicht abgenommen. GitHub-CI/HACS/hassfest wurden für dieses lokale Bundle nicht gestartet.
