# Stufe 6 – Urlaubsmodus

## Lieferung und Basis

- Branch `stufe-6-urlaub`, Version **0.6.0**.
- Basis `main`: `425df037b1a0cd05bd54e5f27791cbac76fd8f65` (0.5.2), einschließlich
  Claudes Korrektur: keine Effekt-Stoppbefehle an bereits ausgeschaltete Lampen.
- Ein Git-Bundle mit produktivem HACS-Frontend und echten Browseransichten bei 390 px.
  Keine getrennte Vorschauphase, keine Live-Installation, kein GitHub-Push oder PR.
- Sämtliche Entwicklungstests verwenden synthetische Lampen, Räume, Zonen und Dienste.
  Abnahme am echten System übernimmt Claude ausschließlich mit dem Probelauf.
  **Kinderzimmer und Bad OG dürfen nicht in die reale Testauswahl aufgenommen werden.**

## Bedienung und Konfiguration

Der Urlaubsmodus wird ausschließlich manuell eingeschaltet. Es gibt keine automatische
Aktivierung durch Anwesenheit. Bedienwege sind die Karte unter **Mehr**, die HA-Entity
`switch.lichtzentrale_urlaubsmodus` und der Administrator-Dienst
`lichtzentrale.set_vacation` mit `enabled` und optional `until`.

`until` ist ein Datum `JJJJ-MM-TT` einschließlich dieses Tages in der HA-Zeitzone.
Weglassen erhält das bisherige Enddatum; `null` entfernt es. Konfiguration und Enddatum
lassen sich gemeinsam speichern, ohne den Modus einzuschalten. Zustand und Einstellungen
liegen additiv unter `vacation` im bestehenden Store, ohne Versionswechsel oder Migration.
Alte Sammlungen und unbekannte Zusatzfelder werden erhalten.

Räume und Zonen mit freigegebenen Lampen sind frei wählbar. Pro Ziel:

- Wohnraum: 45–150 Minuten, zuerst im Abendabschnitt.
- Durchgang: 2–12 Minuten, danach.
- Schlafraum: 10–40 Minuten, spät.
- Gewicht 0–100; 0 nimmt das Ziel aus Planung und Probelauf.
- Einschaltart: eigene Szene, feste Helligkeit oder letzter Zustand.

Der globale Höchstwert gleichzeitiger Räume beträgt standardmäßig 3 und ist von 1 bis
20 einstellbar. Überlappende Zonen übernehmen nicht nochmals bereits eingeschaltete
Lampen. Die Simulation schaltet nur zu Beginn ausgeschaltete, ausdrücklich freigegebene
Lampen; bereits eingeschaltete Lampen werden nicht übernommen oder bei Ende ausgeschaltet.

## Planung

- Abend standardmäßig ab Sonnenuntergang −15 Minuten, Ende täglich zufällig zwischen
  22:30 und 23:30. Alle Grenzen unterstützen Uhrzeit oder Sonnenereignis mit Versatz.
- Optionaler Morgen standardmäßig 06:30–07:30, zunächst ausgeschaltet. Ein bis zwei Räume
  mit insgesamt 10–30 Minuten, nur bei Dunkelheit bis zum nächsten Sonnenaufgang.
  Wohnraumbesuche werden für diesen ausdrücklich kurzen Abschnitt verkürzt.
- Der Planer ist mit festem Seed reproduzierbar; die Laufzeit erzeugt neue Tagespläne.
  UTC-Zeitpunkte und die HA-Zeitzone berücksichtigen Mitternacht und Zeitumstellungen.
  Bei sehr weit gefassten, sich überschneidenden benutzerdefinierten Fenstern bleiben
  Raumobergrenze und Doppelbelegungsschutz wirksam.
- Nach Neustart wird der laufende Abschnitt ab jetzt neu geplant, nichts nachgeholt.
  Laufende Einträge über Mitternacht bleiben bis zu ihrem Ende berücksichtigt.
- „Plan heute“ zeigt Zeitspannen, ausgenommene Räume und nächste Schaltung. Die Oberfläche
  aktualisiert Laufzeitstatus, ohne ungespeicherte Konfiguration zu überschreiben.
- Optionales Lernen liest echte Aus→An-Wechsel aus den letzten 14 Recorder-Tagen.
  Mindestens drei unterschiedliche Tage müssen einen Zeitcluster stützen. Typische
  Zeiten werden innerhalb der gültigen Planungsgrenzen um bis zu ±20 Minuten verschoben.
  Fehlender Recorder, Datenmangel oder Datenbankfehler führen zum Zufallsplan. Es werden
  keine privaten Verlaufsdaten exportiert oder dauerhaft dupliziert.

## Zusammenarbeit, Sicherheit und Grenzen

Während Urlaubsmodus oder Probelauf pausieren Bewegungsautomatik, Grundhelligkeit,
alle Lichtzentrale-Zeitpläne und Taster-Ambiente. Die gespeicherten Aktivierungseinstellungen
der normalen Regeln werden nicht umgeschrieben. Alte Timer, Lernvorgänge und automatische
Dynamik werden begrenzt; Fortsetzen wartet auf neue gültige Auslöser statt verpasste
Schaltungen oder eine alte Lux-Schwelle nachzuholen.

Taster funktionieren normal. Ein Tastendruck nimmt betroffene Räume und überlappende
Simulationszonen für den restlichen Abschnitt heraus, auch zwischen zwei geplanten
Besuchen. Handbedienung hat Vorrang. Fremde Serviceaufrufe, Ein/Aus-Wechsel und
Nutzerattributänderungen lösen den Besitz; reine kontextlose Attribut-Rückmeldungen
werden entsprechend den bestehenden K1/K2-Regeln nicht als Handbedienung behandelt.

Aufräumen prüft weiterhin Freigabe, tatsächliche Zugehörigkeit und Besitz. Eine entzogene
Freigabe wird niemals zugunsten eines Ausschaltbefehls übergangen. Fehlgeschlagenes Aus
bleibt als noch eigener Auftrag erkennbar und kann durch erneutes Beenden wiederholt
werden. Die Simulation nutzt die bestehenden Lichtwege, Effekte und den gemeinsamen
Befehlsbegrenzer. Initialer Zustandsvergleich und fortlaufende Effektprüfung sind getrennt,
damit eigene Farbe-/Stoppbefehle den anschließenden Effekt nicht fälschlich verhindern.

Besitz nach Neustart wird nur mit unverändertem Live-Kontext und unveränderter physischer
Zuordnung wieder übernommen, nicht aus gleicher Helligkeit/Farbe geraten. Lässt sich
Besitz nicht mehr beweisen, bleibt die Lampe unangetastet. Das kann bei einem vollständigen
HA-Neustart eine früher simulierte Lampe eingeschaltet lassen; Sicherheit vor dem
Ausschalten inzwischen fremd bedienter Lampen hat Vorrang. Persistierte alte Dynamik wird
bei aktivem Urlaubsmodus nicht automatisch wiederbelebt. Simulationsdynamik selbst ist
nicht persistent.

Eine ausgewählte Szene verwendet deren bestehende Effekte und Start-Skript. Dessen
Inhalt liegt weiterhin beim Nutzer. Lichtänderungen durch ein solches Skript gelten als
fremde Bedienung. Optional gewählte benannte `notify`-Dienste erhalten nur einen allgemeinen
Ein-/Aus-Hinweis. `notify.send_message` ohne erforderliche Zielauswahl wird nicht angeboten.
Externe Home-Assistant-Automationen werden nicht deaktiviert oder umgeschrieben.

## Probelauf

**Probelauf 5 min** verlangt eine bewusste Bestätigung und gespeicherte, positive
gewichtete Ziele. Er ist während eines normalen Urlaubsmodus oder eines anderen
Probelaufs gesperrt, verwendet ausschließlich diese Auswahl und ist jederzeit beendbar.
Die komprimierten Besuche laufen nacheinander; die Raumobergrenze bleibt damit gewahrt.
Nach fünf Minuten endet der Test. Er wird nach Neustart nicht neu gestartet.

Die native Smoke-Prüfung startet einen tatsächlichen isolierten Test, prüft seine
Fünf-Minuten-Frist und beendet ihn ausdrücklich. Sie wartet nicht fünf reale Minuten.
Der Ablauf bis zur automatischen Frist ist in den Zeittests abgedeckt. Ein inaktiv
gespeichertes Enddatum beendet keinen Probelauf. Beenden sperrt weitere Befehle
bereits vor dem Warten auf einen laufenden Auftrag; physisch schon gesendete Befehle
lassen sich nicht zurücknehmen. Wird das Beenden abgebrochen oder kann nicht gespeichert
werden, bleiben neue Simulationsbefehle gesperrt. Ein sichtbarer Fehler bittet um
erneutes Ausschalten; eine erfolgreich bestätigte Wiederholung löst die Sperre.

## Automatisierte Prüfung

```sh
.venv-test/bin/python -m pytest -q
.venv-test/bin/ruff check custom_components tests scripts
.venv-target/bin/python scripts/smoke_target.py
.venv-target/bin/python scripts/smoke_stage5c_review.py
.venv-target/bin/python scripts/smoke_stage5d.py
.venv-target/bin/python scripts/smoke_stage5e.py
.venv-target/bin/python scripts/smoke_stage6.py
npm run typecheck
npm run lint
npm test -- --maxWorkers=2
npm run build
git diff --check
```

Reguläre pytest-Fixtures verwenden HA **2026.10.4**, native Smoke-Skripte tatsächlich
**2026.11.0**, ohne alte Fixtures oder Patches interner HA-Symbole. Der neue Smoke nutzt
reale HA-Services, Zustandsereignisse, Store und Astral-Berechnungen, aber nur synthetische
Geräte. Die CI-Konfiguration enthält alle fünf nativen Smoke-Skripte.

Gezielt abgedeckt: Seed, Dauergrenzen, Höchstzahl, dunkler/heller Morgen, Enddatum,
Neustart, Pause/Fortsetzen, Tasterausnahme einschließlich Abschnittslücken, nur eigene
Lampen aus, Freigabeentzug, Handbedienung, fehlgeschlagenes Aufräumen, Recorder mit/ohne
Daten, API-Administratorrechte, HA-Schalter, Store-Speicherfehler und Unload/Reload.
Zusätzliche Abschlussregressionen prüfen dynamische Szenen mit gemischten Lampen und
Lichtschaltern, inaktive Enddaten, Probelauf über Mitternacht sowie sofortige
Abbruchsperre und sichtbare Wiederholbarkeit nach abgebrochenem/fehlgeschlagenem Stoppen.

## Nachgewiesener Stand

- Python: **1.415 Tests bestanden** (HA-Fixtures 2026.10.4).
- Frontend: **249 Tests in 18 Dateien bestanden** mit zwei Vitest-Workern.
- TypeScript-Typprüfung, ESLint und Ruff: bestanden.
- Alle fünf nativen Smoke-Skripte auf **Home Assistant 2026.11.0**: bestanden.
  Stufe 5d prüft zusätzlich 5.100 Helligkeits-/Untergrenzen-Kombinationen; K1/K2 prüft
  kontextlose Rückmeldungen nach mehr als zehn realen Sekunden.
- Produktionsbuild erfolgreich; nur die drei bekannten Webpack-Größenhinweise.
- Produktives Frontend: SHA-256
  `2e24cf71e5392a6a373c1c5f2d0edec36cd05215ca6ecee04ccd24ce267ef969`.
- Browser: Chrome **157.0.8103.38**, sechs Originalaufnahmen mit **390 × 844 px**.
  Keine Seiten-/Konsolenfehler, kein horizontaler Überlauf.
- Zwei Produktionsbuilds sind bytegleich; Git-Diff-Prüfung ohne Formatfehler.
- Das ausgelieferte Bundle wird mit `git bundle verify` sowie Import und
  Commit-/Tree-Vergleich in einem separaten Checkout geprüft.
Keine externe GitHub-CI, hassfest-/HACS-Prüfung oder Live-Abnahme wird ausgelöst.

## Browseransichten

Originale und Messprotokoll liegen unter `docs/screenshots/stufe6/`.
`scripts/qa_stage6_capture.cjs` prüft das echte produktive React-Panel mit dem synthetischen
Transport `scripts/qa_stage6_fixture.js`: Karte, Räume, Zeitfenster, Plan und Probelauf,
Speichern/Fehler/Wiederholen, Enddatum, Navigation und horizontalen Überlauf. Es besteht
keine Verbindung zum echten HA-System. Keine Ansichten wurden nachgezeichnet.

- [Urlaubsmodus](screenshots/stufe6/01-urlaubsmodus-390.png)
- [Raumauswahl](screenshots/stufe6/02-raumauswahl-390.png)
- [Abendfenster](screenshots/stufe6/03-abendfenster-390.png)
- [Morgen und Optionen](screenshots/stufe6/04-morgen-optionen-390.png)
- [Plan heute](screenshots/stufe6/05-plan-heute-390.png)
- [Probelauf](screenshots/stufe6/06-probelauf-390.png)
- [Messprotokoll mit SHA-256 je Original](screenshots/stufe6/qa-report.json)

Bestanden sind Auswahl und Werteänderung, Uhrzeit/Sonne, fehlerhaftes Speichern mit
Erhalt der Eingaben und anschließendem Wiederholen, Serverbestätigung, Enddatum,
Ein-/Ausschalten, ausdrückliches Bestätigen/Abbrechen/Beenden des Probelaufs und
Schutz vor dem Verwerfen ungespeicherter Eingaben. Die regelmäßige Statusaktualisierung
mit Erhalt lokaler Änderungen ist zusätzlich in den Frontendtests abgedeckt.

## Bundle übernehmen

In einem sauberen Checkout, ohne fremde Änderungen zu überschreiben:

```sh
git fetch origin main
git bundle verify /Pfad/ha-lichtzentrale-stufe-6-0.6.0.bundle
git fetch /Pfad/ha-lichtzentrale-stufe-6-0.6.0.bundle stufe-6-urlaub
git switch -c stufe-6-review FETCH_HEAD
```

Bei vorhandenem Reviewbranch neue Commits zuerst vergleichen und regulär integrieren.
Kein erzwungenes Zurücksetzen. Das Bundle benötigt die oben angegebene Main-Basis.
Nach Lieferung endet die Arbeit bis zur nächsten Freigabe.
