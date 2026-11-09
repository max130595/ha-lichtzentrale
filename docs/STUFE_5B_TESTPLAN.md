# Stufe 5b: Vorschau und freigegebene Umsetzung prüfen

## Teil 1: Freigegebene Vorschau

Teil 1 ist eine eigenständige Handy-Vorschau unter `docs/vorschau-5b/index.html`.
Alle Daten sind erfunden und bleiben nur im Arbeitsspeicher der Seite. Die Vorschau
verbindet sich weder mit Home Assistant noch mit Geräten. Die Vorschau selbst verändert weder produktiven Quellcode noch gespeicherte Nutzerdaten.
Nach ihrer ausdrücklichen Freigabe enthält dieser Branch nun zusätzlich die produktive
Umsetzung (Version 0.4.0). Die folgenden Vorschauprüfungen bleiben getrennt davon.

`index.html` herunterladen und in einem Browser öffnen. Kein Build und kein Konto nötig.
Die Datei funktioniert auch offline. Auf einem breiten Bildschirm kann die Prüfbreite mit `?width=320`, `?width=390` oder
`?width=430` am Ende der Adresse gewählt werden. Auf dem Handy passt sie sich dem Bildschirm an.
Neuladen oder „Vorschau zurücksetzen“ stellt die Ausgangsbeispiele wieder her.

## Teil 1: Bedienung zur Freigabe

1. **Alle Reiter:** Zuhause, Farben, Automationen, Taster und Mehr öffnen. Die Reiterleiste
   bleibt unten erreichbar. Keine waagerechte Scrollleiste bei 320, 390 und 430 Pixeln.
   Zonen stehen vor Räumen, ohne Werbetexte oder Hero-Karte. Die kompakten Kacheln zeigen
   nur Name, An/Aus und Helligkeit. Raumdetails haben den Raumnamen als Überschrift. Die Beispieldaten und Grenzen der
   Vorschau sind erkennbar; keine echten Entity-IDs oder privaten Wohnungsdaten erscheinen.
2. **Zonen:** Eine neue Zone aus Leselicht und Pendelleuchte anlegen. Beide gehören weiterhin
   zu ihren Räumen und dürfen zusätzlich in einer anderen Zone liegen. In Zuhause direkt
   schalten/dimmen, Details öffnen und eine Szene starten. Reine Schalter nicht dimmen.
3. **Sonnenuntergang:** Automationen → Neue Automation → Sonnenuntergang → −15 → Weiter →
   Zone Wohnbereich → Weiter → Szene Abend → speichern. Satz in der Übersicht prüfen.
   Alle Wochentage sind anfangs ausgewählt. Freien Versatz, Sonnenaufgang und Uhrzeit prüfen.
   Die erste Zielauswahl erfolgt nur in „Wo“; „Was“ zeigt die übernommenen Ziele ohne weitere
   Auswahl. Zusätzliche Aktionen haben eigene Ziele. Zurück/Weiter sowie Bearbeiten darf
   die Ziele zusätzlicher Aktionen nicht in die erste Aktion übernehmen.
4. **Mehrere Aktionen:** Einen Plan für 22:30 Uhr anlegen: Wohnbereich aus, Flur Nachtlicht.
   „Jetzt testen“ muss beide Demoaktionen **streng nacheinander in der angezeigten Reihenfolge**
   ausführen. Das Orientierungslicht liegt sowohl im Wohnbereich als auch im Flur:
   erst Zone aus, danach Flur Nachtlicht ergibt dort **an, 12 %**; die übrigen Zonenlampen
   bleiben aus. Reihenfolge umkehren: erst Flur Nachtlicht, dann Wohnbereich aus ergibt
   für die gemeinsame Lampe **aus**. Keine globale Zusammenfassung/Deduplizierung über
   mehrere Aktionen hinweg. Die Liste zeigt einen verständlichen Satz, einen Schalter
   rechts statt einer Checkbox und die ausdrücklich simulierte nächste Ausführung.
5. **Szenen und Nachtlicht:** Im Raum oder in der Zone den sichtbaren Knopf „+ Neue Szene“
   wählen, Lampen einstellen, Namen eingeben und speichern. Der Name bleibt beim Ändern
   der Lampen erhalten. Abbrechen oder Reiterwechsel speichert nichts; ein leerer Name
   wird abgewiesen. Die gespeicherte Szene mit ihren eingestellten Werten starten.
   Nachtlicht ist ein kleiner Knopf, seine Einstellungen bleiben aufklappbar. Auf der
   Raumseite stehen weder „Zurück zur Automatik“ noch „Automatik heute“.
   Für die Rückkehr zuerst den Abend-Plan mit „Jetzt testen“ ausführen, dann Nachtlicht
   aktivieren und am Dimmer die Hue-Taste „Nachtlicht ⇄ Automatik“ testen: Abend kehrt
   zurück. Beide Automatik-Aktionen bleiben für Taster und Automationen verfügbar.
   Manuelle Bedienung ersetzt den Automatikstand nicht. Ohne Stand bleibt die Rückkehr
   wirkungslos und schreibt einen Protokollhinweis. Tageswechsel in Mehr simulieren.
6. **Dimmer:** Taster → Hue Dimmer → Vorlage verwenden, Ziel Wohnbereich wählen. An = volle
   Helligkeit mit neutralem Weiß, Hue = Nachtlicht ⇄ Automatik, Hoch/Runter = dimmen,
   Aus = ausschalten. Tasten in der Zeichnung antippen, Kurz/Lang/Drehen und Ziele ändern.
   Das Feld „Szene“ ist nur bei der Aktion „Szene“ sichtbar; andere Aktionen lassen sich
   ohne dieses Feld speichern und testen. Andere Gerätezeichnungen öffnen. Ein Raum, eine Zone und einzelne Lampen sind wählbar.
7. **Zigbee2MQTT:** Zwei simulierte Ereignisse mit gleichem allgemeinen Ereignistyp, aber
   anderen Tastenattributen anlernen. Die Zuordnungen bleiben getrennt. Ein unbekanntes
   Ereignis bleibt mit seinem Rohnamen sichtbar. Das ist eine Anlern-Vorschau, kein echter
   Geräteadapter; reale Attributnamen müssen später zur Laufzeit ermittelt werden.
8. **Erhaltene Funktionen:** Die [Funktionszuordnung](STUFE_5B_FUNKTIONSZUORDNUNG.md) mit
   der bisherigen Oberfläche abgleichen. Bewegung, Grundhelligkeit, Positionen, Dynamik,
   Freigaben, Bedingungen und optional natürliches Licht finden. Die erweiterten Abläufe
   sind teilweise nur platzierte Bedienelemente, nicht ihre produktiven Algorithmen.
9. **Trennung:** Browser neu laden: Demoänderungen sind weg. Kein Store, LocalStorage,
   Cookie, HA-Service oder Netzwerkzugriff wird durch die Vorschau benötigt. Das bestehende
   Panel bleibt unverändert. Keine echte Installation oder Live-Abnahme behaupten.

## Automatisierte Vorschauprüfungen

Nach `npm ci` im Projektstamm: `node --test docs/vorschau-5b/preview.check.cjs`.
Die Tests laden ausschließlich die eigene HTML-Datei in einer isolierten DOM-Umgebung.
Sie prüfen die Kernabläufe, ausgeschlossene Schalter sowie die Abwesenheit von Netzwerk-
und Browser-Persistenzzugriffen. Sie ersetzen keine Prüfung mit Home Assistant.

Vorhandene Frontend-Regression: `npm run typecheck`, `npm run lint`, `npm test`.
Der genaue ausgeführte Stand und die manuellen Handyprüfungen stehen im PR.

## Teil 2: Produktive Umsetzung nach ausdrücklicher Freigabe

Die folgenden Abnahmekriterien gelten für den produktiven Code. Automatisierte Tests
verwenden ausschließlich synthetische Daten; eine Prüfung mit echten Geräten bleibt offen:

- Serverseitiges Speichern und additives Migrieren: Bestehende Szenen, Paletten,
  Tasterbelegungen, Ein-Aktions-Zeitpläne, Bewegungs- und Grundhelligkeitsregeln samt
  Aktivierungszustand und unbekannten Feldern bleiben erhalten. Vergleich eines
  repräsentativen alten Stores vor und nach Migration, wiederholte Migration idempotent.
- Zonenüberlappung, gelöschte/fehlende Lampen und nur einmalige Ausführung pro Ziel prüfen.
  Switches erhalten nie Helligkeit/Farbtemperatur/Farbe. Bestehende Freigaben bleiben gültig.
- Automatikstand pro Raum/Zone: Szene, Nachtlicht und Aus merken; manuelle Aktionen nicht
  merken; Neustart am gleichen Tag überleben; um lokales Mitternacht zurücksetzen.
  Neustart nach Mitternacht sowie Sommer-/Winterzeit und Ausfall eines Ziels prüfen.
- Echte Sonnenzeiten, beliebige Versätze, Wochentage, mehrere Aktionen, Bedingungen,
  streng serielle Ausführungsreihenfolge auch bei überlappenden Zielen (spätere Aktion
  gewinnt), nächste Ausführung, deaktivierte Pläne und Fehlerfälle testen.
- Nachtlicht als normale, frei einstellbare markierte Szene; Rückkehr ohne Stand nur
  Protokollhinweis; ausgeschalteter Automatikstand; Volle Helligkeit nur mit unterstützten
  Fähigkeiten. Taster und Automationen nutzen dieselben klar definierten Aktionen.
- Zigbee2MQTT mit einer Event-Entity: Quelle + Typ + zur Laufzeit gelernte Attribute;
  zwei Tasten mit gleichem Typ, Richtung/Geschwindigkeit, unbekannte Typen, Doppel-/Langdruck,
  Wiederholungen und Neustart prüfen. Bestehende Hue-Belegungen bleiben gültig.
- Home Assistant 2026.11: Installation, Neustart, HACS-Bundle, Logs und echte Geräte
  gemeinsam mit Claude prüfen. Ohne Adaptive Lighting dürfen dessen Funktionen nicht
  angeboten werden; mit Integration nur passende verfügbare Ziele anbieten.
- Erst nach erfolgreicher Abnahme schaltet Claude die bisherigen einzelnen
  Zigbee2MQTT-Automationen im echten System ab. Dieser Draft verändert sie nicht.

### Reproduzierbare Prüfungen

1. `npm ci`, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`.
   Den Build wiederholen und Bundle/Lizenzdateien auf identische Bytes prüfen.
2. `node --test docs/vorschau-5b/preview.check.cjs` für die getrennte Vorschau.
3. Python 3.14 mit `requirements-test.txt`: `ruff check custom_components tests scripts`
   und `python -m pytest -q`. Die pytest-Abhängigkeit verwendet HA 2026.10.4.
4. Getrennte Python-3.14-Umgebung mit `requirements-ha2026.11.txt`:
   `python scripts/smoke_target.py`. Dieser native HA-2026.11.0-Lauf prüft Registry,
   Services und echten Store mit synthetischen Entities, nicht echte Hardware.

### Gezielte Abdeckung im Repository

- `tests/test_stage5b_targets.py`: überlappende Zonen/Freigaben, entfernte Referenzen,
  Nachtlicht-Kennzeichnung, unbekannte Szenenfelder, deduplizierte allgemeine Aktionen,
  Switch-Fähigkeiten, Tagesstand/Neustart, Fehler/No-op und gemeinsame Raumsperren.
- `tests/test_zone_runtime.py`: zoneneigene Positionen/Farbverteilung, Mitgliedschaft vor
  jedem Dynamiktick, Stopp überlappender Dynamik, kein Wecken ausgeschalteter Ziele und
  Zonenvalidierung bei Bewegung/Grundhelligkeit.
- `tests/test_schedule_actions.py` und bestehende Zeitplantests: streng serielle
  Mehrfachaktionen, Zone aus → Raum-Nachtlicht und umgekehrt, Conditions vor der Folge,
  deaktivierte Pläne, Fehler, Unterbrechungen sowie alte Pläne und Zusatzfelder.
- `tests/test_bindings.py` / `test_bindings_api.py`: gleiche generische Ereignistypen mit
  unterschiedlichen tatsächlich gelernten Attributen, Richtungs-/Geschwindigkeitswerte,
  ablaufende/abgebrochene Anlernsitzungen, persistente Zuordnung und alte Hue-Belegungen.
- `js/AutomationWizard.test.tsx`, `js/Zones.test.tsx` und erweiterte App-/Rooms-/Buttons-
  Tests: neue Bedienabläufe, Back/Cancel, Zielübernahme, weitere Aktionen, Schalter,
  Szene erstellen, Vorlagen und Ausblenden des Szenenfelds bei anderen Aktionen.
- `scripts/smoke_target.py`: zusätzlich Zonen über Raumgrenzen, Nachtlicht-Markierung,
  volle Helligkeit, manuelle Änderungen ohne Verlust des Automatikstands, erneutes Laden
  vom Datenträger und Rückkehr zum gespeicherten Aus-Stand.

### Noch durch Claude am echten System abzunehmen

- Handy-Sichtprüfung bei 320/390/430 px, Scrollen, Daumenbedienung und HA-Theme. DOM-Tests
  sind kein Nachweis für Pixel-Layout oder echte Browserdarstellung.
- HACS-Installation, vollständiger Konfigurationseintrag-/Panel-/WebSocket-Lebenszyklus,
  Neustart, reale Logs und Geräteantworten unter HA 2026.11.
- Tatsächliche Zigbee2MQTT-Attribute für jede physische Taste und Drehgeste anlernen.
  Die Vorlage rät keine Quellenzuordnung. Erst nach erfolgreichem Test die bisherigen
  externen Automationen abschalten; dieser Branch tut das nicht.
- Optionales Adaptive Lighting am vorhandenen System prüfen, falls später installiert.
  Ohne Integration werden dessen Bedienelemente nicht angeboten.
- Rückkehr zu Hue-/dynamischen Nachtlichtszenen und Gerätefarbrundung prüfen. Ein fehlender
  oder ungültiger Automatikstand darf keine Ersatzszene oder beliebige Lampe auslösen.
- Bei gelöschter Zone bleiben verknüpfte Szenen/Pläne erhalten und melden das fehlende Ziel,
  statt still Daten zu löschen. Die Zuordnung muss der Nutzer ausdrücklich reparieren.

**Haltepunkt:** Nach Aktualisierung des Draft-PRs mit Teil 2 endet die Arbeit wieder.
Keine weitere Branch-Änderung, Live-Aktion oder CI-Überwachung bis zur Rückmeldung.

## Bereits geprüfter Entwicklungsstand 7c8ce3c, Teil 2

- Python-Gesamtsuite: **821 bestanden** unter HA 2026.10.4 / Python 3.14.
- Frontend: **141 bestanden in 10 Dateien** mit `npm test -- --maxWorkers=1`.
  Der anfängliche parallele Lauf hatte zwei Startzeitüberschreitungen im Vitest-Pool;
  der vollständige serielle Lauf ist ohne Fehler abgeschlossen.
- TypeScript, ESLint und Ruff: bestanden. Getrennte Vorschau: **22 bestanden**.
- Native Smoke-Prüfung mit HA **2026.11.0**: bestanden, ausschließlich synthetische Geräte.
- Webpack-Build zweimal erfolgreich und Bundle/Lizenzen bytegleich. Die drei bekannten
  Größenhinweise von Webpack (Bundle über der empfohlenen Grenze) sind keine Buildfehler.
- Keine visuelle Handy-/Browser-Abnahme, echte Installation oder Hardwareprüfung erfolgt.
  GitHub-CI, HACS-Action und hassfest werden nach Übergabe ausdrücklich nicht überwacht.


## Review-Korrekturen nach 7c8ce3c

Nur die vier vom Nutzer weitergegebenen Reviewpunkte, als neues Git-Bundle ohne eigene
Veröffentlichung. Vor Beginn wurde `origin/stufe-5b-einfach` geholt und per Fast-forward
abgeglichen; Remote und lokal standen auf 7c8ce3c. Keine fremden Änderungen überschrieben.

1. **Überlappende Automatikstände:** Synthetische Zone Wohnbereich enthält eine Flurlampe
   und eine Lampe aus einem anderen Raum. Sonnenuntergang setzt eine Zonenszene. Flur
   besitzt keinen eigenen heutigen Automatikstand. Erster `night_auto`-Druck setzt sein
   Nachtlicht, zweiter stellt nur die Flurlampe aus der Zonenszene wieder her. Die andere
   Zonenlampe bleibt unverändert, auch wenn sie zwischenzeitlich manuell geändert wurde.
   Umgekehrte Richtung Raum → Zone sowie mehrere überlappende Stände prüfen. Ein eigener
   heutiger Stand hat Vorrang; sonst gewinnt je Lampe der jüngste passende Stand. Neustart,
   lokale Tagesgrenze, entfernte Mitgliedschaften und entzogene Freigaben berücksichtigen.
2. **Rundungstoleranz:** Nachtlicht bleibt bei Helligkeit ±3, Farbtemperatur ±50 K und xy
   ±0,01 je Koordinate erkannt. Exakte Grenzwerte und knapp außerhalb testen. Ungültige
   Werte oder geänderter Ein/Aus-Zustand dürfen nicht als aktives Nachtlicht gelten.
3. **Teilergebnisse:** Szene/Nachtlicht/Aus mit mindestens einer erfolgreich geschalteten
   Lampe bleibt als Automatikstand gespeichert, auch wenn andere Ziele übersprungen wurden
   oder fehlschlugen. Protokoll nennt das Teilergebnis. Ohne jede erfolgreiche Lampe keinen
   neuen Stand erfinden. Eine spätere Rückkehr darf wieder verfügbare gemeinsame Ziele
   erneut versuchen; die gespeicherte Aktion wird nicht auf erfolgreiche Lampen reduziert.
4. **Attribute „egal“:** Beim Anlernen jedes beobachtete Attribut einzeln umstellen.
   `press`/`press_release` mit `button_1` und `button_2` bleiben getrennt; `dial_rotate`
   rechts mit verschiedenen `speed`-Werten trifft dieselbe Belegung, links nicht.
   `brightness_step` unterscheidet die Richtung. Unbekannte Attribute sind ebenfalls
   konfigurierbar. Abbrechen schreibt nichts, Bearbeiten/Neustart erhalten die Wahl.
   Alte genaue Belegungen werden nicht migriert. Überlappende Muster dürfen pro Ereignis
   nicht mehrere Aktionen ungewollt auslösen.

Der native HA-2026.11-Smoke wurde um den Zweifach-Druck am Raum mit gerundeter Helligkeit
und unveränderter anderer Zonenlampe sowie persistierte Drehrichtung mit beliebiger
Geschwindigkeit ergänzt. Eine echte Geräte-/Handyprüfung bleibt Claude vorbehalten.

### Bewusste Grenzen beim geerbten Szenenabruf

- Eine geerbte Palette behält ihre Farbpositionen relativ zur vollständigen Quelle, wird
  aber nur auf gemeinsame Lampen angewendet. Eine geerbte dynamische Szene wird dort
  statisch wiederhergestellt, damit kein größerer Quellenlauf neu gestartet wird.
- Eine geerbte Hue-Szene wird in verifizierte einzelne Lichtbefehle zerlegt. Es wird nie
  die gesamte Hue-Szene aktiviert. Nicht sicher abbildbare native Gradienten/Effekte
  werden mit Hinweis übersprungen; sie lösen keine breitere Ersatzaktion aus.
- Alte Tagesstände ohne Zeitstempel bleiben lesbar. Neu gespeicherte Stände tragen UTC-Zeit
  und eine persistierte Reihenfolge. Bei identischer Zeit gewinnt der spätere Schreibvorgang;
  bei vollständig alten Gleichständen ist die Auswahl stabil, nicht eine erfundene Historie.
- Bei mehreren passenden Tasterbelegungen gewinnt die spezifischere. Gleich spezifische,
  überschneidende Muster werden beim Speichern zurückgewiesen. Alte genaue Belegungen
  bleiben genau; nur neu angelerntes `dial_rotate.speed` wird zunächst „egal“.

### Nachgewiesener Stand der Review-Korrekturen

- Gesamte Python-Suite: **883 bestanden**, HA 2026.10.4 / Python 3.14.
- Gesamtes Frontend: **145 bestanden in 10 Dateien**, seriell mit `--maxWorkers=1`.
- Getrennte Vorschau: **22 bestanden**.
- Erweiterter nativer Smoke mit **Home Assistant 2026.11.0**: bestanden.
- TypeScript, ESLint, Ruff und `git diff --check`: bestanden.
- Frontend zweimal gebaut; Bundle und Lizenzdateien bytegleich. Die drei bekannten
  Webpack-Größenhinweise bleiben unverändert, keine Buildfehler.
- Keine GitHub-Veröffentlichung, CI-Überwachung, Live-Installation oder Geräteaktion.
  Übergabe als Git-Bundle auf Basis von 7c8ce3c; danach Arbeit stoppen.
