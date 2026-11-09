# Stufe 5c: Übergabe an Claude

## Ausgangspunkt

Branch `stufe-5c-paletten`, Version **0.5.0**, Basis `main` **996f263**.
Alle am 09.11.2026 ausdrücklich nachgereichten Aufträge sind enthalten: Punkt 6a mit
fester Einschalt-Helligkeit, Szene und Tageszeitfenstern sowie Punkt 4a Jahreszeiten-Szene
und vier Romantik-Stimmungen. Der aktuelle Remote-Stand wurde vor der Übergabe erneut
geprüft; fremde Änderungen sind erhalten. `docs/AUFTRAEGE.md` wurde nicht bearbeitet.

Die Lieferung erfolgt als Git-Bundle mit dem gebauten HACS-Frontend, Tests,
Dokumentation und echten Screenshots. Kein Draft-PR wurde eröffnet und nichts auf
GitHub geschrieben. Nach dieser Übergabe wird nicht weiter am Branch gearbeitet.

## Gebaut

- 37 eigene Stimmungen: zwölf bisherige unverändert plus 25 neue, einschließlich der
  vorgegebenen Herbstglut und vier ruhigen Romantik-Paletten.
- Eigene Paletten, sichere Referenzprüfung und Live-Szenenbearbeitung mit festen
  Lampenhelligkeiten, Farbe/Weißton, Mondlicht, Aus und unabhängigen Werten je Szene.
- Vier Tempi, Wellenliste, sanfte Helligkeitsschwankungen, begrenzte dynamische
  Befehlsrate, Fortsetzung nach Neustart und gezieltes Herausnehmen handbedienter Lampen.
- Jahreszeiten-Szenen für Raum/Zone, optionale Weihnachtszuordnung und frei einstellbare
  Datumsgrenzen. Fehlende Zuordnungen erhalten einen sichtbaren Ersatzhinweis.
- Taster-Einschalten mit fester Helligkeit, Szene oder geordneten Uhrzeit-/Sonnenfenstern
  für Helligkeit/Weißton oder Szene. Ausschalten bleibt auch bei gelöschter Einschalt-Szene möglich.
- Favoriten/Status auf Zuhause, sichere Entity-Umbenennung und atomarer Lampenersatz
  mit Vorschau; unbekannter Z2M-Farbmodus und reine An/Aus-Lichter werden berücksichtigt.

## Prüfstand

**1.107 Python-Tests**, **202 Frontendtests**, TypeScript, ESLint, Ruff und nativer
**Home-Assistant-2026.11-Smoke** bestanden. Das ausgelieferte Frontend wurde zweimal
bytegleich gebaut und entspricht dem in Chrome getesteten JavaScript. 18 echte
390 × 844-Pixel-Screenshots, kein horizontaler Überlauf und keine Browserfehler.

Details und reproduzierbare Prüfungen: [STUFE_5C_TESTPLAN.md](STUFE_5C_TESTPLAN.md).
Die Browserprüfung verwendet die tatsächliche produktive Oberfläche mit einem rein
synthetischen Transport, keine getrennte Produktvorschau und keine Verbindung zu Geräten.

## Git-Bundle übernehmen

In einem sauberen lokalen Checkout zunächst den vorhandenen Stand prüfen. Keine fremden
lokalen Änderungen überschreiben und keinen bestehenden Branch hart zurücksetzen.

```sh
git fetch origin main
git bundle verify /Pfad/ha-lichtzentrale-stufe-5c-0.5.0.bundle
git fetch /Pfad/ha-lichtzentrale-stufe-5c-0.5.0.bundle stufe-5c-paletten
git switch -c stufe-5c-review FETCH_HEAD
```

Das Bundle setzt voraus, dass die Basis `996f263` durch den Main-Fetch vorhanden ist.
Vor dem Übertragen in einen schon vorhandenen Arbeitsbranch dessen neue Commits vergleichen
und regulär integrieren. Das gebaute Frontend ist enthalten; am HA-System ist kein Node nötig.

## Bewusste Grenzen und reale Abnahme

- **Keine Live-Installation oder Live-Gerätebefehle ausgeführt.** Der Nutzertermin für
  das laufende echte System bleibt von Claudes Installation und Geräteabnahme abhängig.
- Vor Installation die bestehende Integration und deren Store sichern. Danach zuerst
  synthetisch/unwichtige freigegebene Lampen prüfen, anschließend gezielt die tatsächliche
  Abendzone. Keine bestehenden Zonenziele automatisch erweitern und keine externe
  Mond-/Zigbee2MQTT-Automation ungeprüft abschalten.
- Live-Abbrechen stellt die erfassten physischen Werte wieder her, startet eine davor
  laufende Dynamik aber nicht neu. Neuere Handbedienung bleibt erhalten. Bei gescheiterter
  Rückstellung wird eine Wiederholung angeboten; nach bereits erfolgreichem Speichern
  sind spätere Laufzeitprobleme als Warnung gekennzeichnet, nicht als fehlgeschlagene Speicherung.
- Mondbeleuchtung ist eine lokale synodische Näherung, kein präziser astronomischer Dienst.
- Jahreszeiten werden beim Auslösen aufgelöst. Ein laufender dynamischer Ablauf behält
  seine konkrete Szene bis zum nächsten Start; ein Datumssprung schaltet nichts automatisch um.
  Weihnachtsgrenzen sind einschließlich; der 29. Februar wird in Nicht-Schaltjahren am
  28. Februar wirksam. Beim gleich nahen Ersatz gilt deterministisch die Jahreszeitenreihenfolge.
- Bei einzelnen Taster-Lampen wird die gewählte Szene nur auf diese Lampen statisch
  projiziert, niemals auf zusätzliche Ziele. Bei Tageszeitfenstern gewinnt das erste passende;
  Lücken verwenden das bisherige Einschaltverhalten.
- Lampenersatz in einen anderen physischen HA-Raum wird bei betroffenen Raumreferenzen
  gesperrt. Das Ersatzgerät zuerst demselben HA-Raum zuordnen. Widersprüchliche Zielwerte
  werden nicht still überschrieben. Reine Zonenreferenzen können raumübergreifend übertragen werden.
- Physische Zigbee-Übergänge, Gerätegrenzen, Farbwirkung, Rückmeldekontexte und konkurrierende
  externe Automationen müssen am echten System geprüft werden. Keine Aussage „läuft live“.
