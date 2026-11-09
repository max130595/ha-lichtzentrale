# Offene Aufträge (Reihenfolge verbindlich)

Diese Datei pflegt Claude. ChatGPT/Codex arbeitet immer nur **eine** Stufe ab, genau dann, wenn
der Nutzer sie startet („Starte Stufe X aus docs/AUFTRAEGE.md“). Ablauf je Stufe: `git pull` auf
`main`, neuer Branch wie angegeben, umsetzen, `docs/BAUPLAN.md` ergänzen, Tests, Draft-PR öffnen,
**aufhören** bis Claude freigibt (siehe AGENTS.md). Für alle Stufen gilt: keine Kinderzimmer und kein
Bad oben in Tests oder Beispielen, Schalter (`switch`) werden nie gedimmt.

| Stufe | Branch | Status |
|---|---|---|
| 4a Zeitfenster-Bedingung | `stufe-4a-zeitfenster` | erledigt (PR #9, getestet 08.11.) |
| 5 Grundhelligkeit | `stufe-5-grundhelligkeit` | erledigt (PR #10, #11) |
| 5b Einfache Bedienung wie die Hue-App | `stufe-5b-einfach` | erledigt (PR #12, am echten System getestet 09.11.) |
| 5c Stimmungen, eigene Paletten, Helligkeit pro Lampe | `stufe-5c-paletten` | zusammengeführt (PR #13, Review-Korrekturen K1/K2), Abnahme am echten System läuft |
| 5d Dimmen schaltet nie aus | `stufe-5d-dimmgrenze` | erledigt (PR #14, 0.5.1) |
| 5e Hue-Effekte, Ambiente-zuerst-Taster, Szene startet Skript | `stufe-5e-effekte` | offen – **als Nächstes** |
| 6 Anwesenheitssimulation | `stufe-6-urlaub` | offen |
| 7 Sicherung, „Alles aus“, Öffnung für andere | `stufe-7-sicherung` | offen |

---

## Stufe 5b – Einfache Bedienung wie die Hue-App

**Ziel:** Der Nutzer stellt Räume, Zonen, Automationen und Taster selbst ein, ohne Hilfe, so
leicht wie in der Hue-App. Die Technik aus Stufe 1–5 bleibt, die Oberfläche wird neu gedacht.
Die Lichtzentrale ersetzt danach die Hue-App vollständig, auch für Lampen ohne Hue-Bridge
(Zigbee2MQTT).

**Zwei Teile, getrennt freigegeben:**

1. **Vorschau zuerst.** Eine klickbare Vorschau oder Screenshots mit synthetischen Daten für alle
   Reiter, Handy-Format. Dazu eine Seite, die zeigt, welche bisherigen Funktionen wohin wandern.
   Draft-PR öffnen und **aufhören**. Weiter geht es erst nach Freigabe durch den Nutzer.
2. **Umsetzung** nach Freigabe, mit Testplan `STUFE_5B_TESTPLAN.md`.

### Grundsätze für die Oberfläche

- Alles auf Deutsch, in einfachen Worten. **Keine Entity-IDs sichtbar**, nur Anzeigenamen.
- Höchstens zwei Ebenen tief. Was selten gebraucht wird (Lux-Schwelle, Personen, Zeitfenster,
  Übergangszeit, Bewegung, Grundhelligkeit), liegt eingeklappt unter „Mehr Optionen“.
- Jede Automation und jede Tastenbelegung wird in der Übersicht als **ein Satz** angezeigt,
  z. B. „15 Min. vor Sonnenuntergang · Wohnbereich · Szene Abend“.
- Große Kacheln und Schieberegler, bedienbar mit dem Daumen.

### Startseite: Räume und Zonen

- Kachel je Raum **und je Zone**, darauf direkt Ein/Aus und ein Helligkeitsregler (wie Hue).
  Tippen öffnet die Detailseite mit Szenen und Einzellampen.
- **Zonen (neu):** frei zusammengestellte Lampengruppen über Räume hinweg, z. B. eine Zone
  „Wohnbereich“ aus Lampen von drei Räumen. Eine Lampe darf in mehreren Zonen sein. Zonen sind
  überall wählbar, wo ein Raum wählbar ist (Szenen, Automationen, Taster).

### Automationen

- Neue Automation in drei Schritten:
  1. **Wann:** Sonnenuntergang oder Sonnenaufgang (astronomisch, wie bisher `sun`) mit Versatz
     als Auswahlknöpfe −30, −20, −15, −10, 0, +10, +15, +20, +30 Min. und freier Eingabe; oder eine
     Uhrzeit. Darunter die Wochentage (Standard: alle).
  2. **Wo:** Räume, Zonen oder einzelne Lampen auswählen, auch mehrere.
  3. **Was:** Szene, Nachtlicht, ausschalten oder eine Helligkeit.
- Beliebig viele Automationen, auch mehrere zum Sonnenuntergang für verschiedene Gruppen.
- **Mehrere Aktionen pro Automation** (z. B. eine Zone aus und gleichzeitig ein Raum auf Nachtlicht).
- Ein- und Ausschalten direkt in der Liste. Daneben stehen „Jetzt testen“ und die nächste Ausführung
  (wie Stufe 4).
- Beispiel für Testplan und Vorschau (synthetisch): „15 Min. vor Sonnenuntergang: Zone
  Wohnbereich → Szene Abend“ und „22:30 Uhr: Zone Wohnbereich aus, Raum Flur → Nachtlicht“.

### Nachtlicht und „Zurück zur Automatik“ (neu)

- **Nachtlicht** ist pro Raum oder Zone eine normale, frei einstellbare Szene mit Kennzeichnung
  „Nachtlicht“.
- **Automatik-Szene:** Für jeden Raum und jede Zone merkt sich die Lichtzentrale, welche Szene
  die zuletzt ausgeführte Automation heute gesetzt hat. Hat danach eine Automation dieses Ziel
  ausgeschaltet oder aufs Nachtlicht gesetzt, gilt das Nachtlicht bzw. „aus“ als Automatik-Stand.
  Um Mitternacht wird alles zurückgesetzt. Der Stand überlebt einen Neustart.
- **Neue Aktion „Zurück zur Automatik“:** setzt Raum oder Zone wieder auf den Automatik-Stand.
  Gibt es keinen, passiert nichts, und es erscheint ein Hinweis im Protokoll.
- **Neue Aktion „Nachtlicht ⇄ Automatik“:** Ist das Nachtlicht gerade aktiv, geht es zurück zur
  Automatik-Szene, sonst wird das Nachtlicht eingeschaltet. Taster und Automationen können sie
  beide nutzen.
- **Neue Aktion „Volle Helligkeit“:** schaltet Raum oder Zone auf 100 % mit neutralem Weiß.

### Taster

- Pro Gerät eine einfache Zeichnung des Schalters mit seinen Tasten (Hue Dimmer, Tap Dial,
  Wandschalter-Modul, Shelly). Antippen einer Taste öffnet „Kurz drücken / Lang drücken /
  Drehen“ mit einer Auswahlliste in Klartext.
- Vorlage für den Hue Dimmer (synthetisch im Test): An = Volle Helligkeit, Hue-Taste =
  Nachtlicht ⇄ Automatik, Hoch/Runter = dimmen, Aus = ausschalten. Das Ziel ist frei wählbar
  (ein Raum, eine Zone oder Lampen).
- **Vorbereitung Zigbee2MQTT:** Taster, die über Zigbee2MQTT als `event`-Entity kommen, werden
  genauso angeboten. Deren Ereignisnamen (z. B. `on_press_release`, `button_1_press_release`,
  `dial_rotate_right_step`) werden in Klartext übersetzt. Unbekannte Ereignisse erscheinen mit
  ihrem Rohnamen, statt zu fehlen.
- **Wichtig (am echten System festgestellt, Zigbee2MQTT 2.14 mit `experimental_event_entities`):**
  Ein Gerät liefert **eine** Event-Entity mit allgemeinen Typen (`press`, `press_release`,
  `hold`, `hold_release`, `dial_rotate`, `brightness_step`). Welche Taste bzw. welche
  Drehrichtung gemeint ist, steht nur in den Ereignis-Attributen (z. B. Taste, Richtung,
  Geschwindigkeit). Eine Belegung muss deshalb aus Event-Entity **plus** Ereignistyp **plus**
  diesen Attributen bestehen. Die Attributnamen werden zur Laufzeit aus dem tatsächlichen Ereignis
  gelesen, nicht fest einprogrammiert. Vorhandene Hue-Belegungen bleiben gültig.
- Bis das fertig ist, laufen auf dem echten System umgezogene Zigbee2MQTT-Taster über einzelne
  Home-Assistant-Automationen. Nach Stufe 5b übernimmt die Lichtzentrale sie, und die
  Automationen werden abgeschaltet (das macht Claude).

### Bestehendes bleibt erhalten

- Alle gespeicherten Szenen, Paletten, Taster, Zeitpläne, Bewegungs- und Grundhelligkeitsregeln
  laufen unverändert weiter. Store-Migration nur ergänzend, nichts wird stillschweigend
  gelöscht. Vorhandene Pläne erscheinen in der neuen Liste als Satz.
- Lampen werden über ihre Entity-ID angesprochen, egal ob Hue-Bridge oder Zigbee2MQTT. Bei einem
  Umzug mit gleicher Entity-ID funktioniert alles weiter.

**Fertig wenn:** In der Vorschau (synthetisch) kann ein Nutzer ohne Anleitung eine
Sonnenuntergangs-Automation mit −15 Min. für eine Zone anlegen, einen Hue Dimmer wie oben belegen
und „Nachtlicht ⇄ Automatik“ auslösen, und alle bisherigen Daten bleiben erhalten.

## Stufe 5c – Stimmungen, eigene Paletten, Helligkeit pro Lampe

**Termin:** Muss am Folgetag bis 15:00 auf dem echten System laufen (eine Sonnenuntergangs-Automation
startet dort täglich eine Zonen-Szene). Deshalb **keine getrennte Vorschau-Phase**: direkt umsetzen,
Draft-PR mit Screenshots (Handy 390 px) der neuen Bildschirme; Claude macht Code-Review und Sichtprüfung.

**Anlass (Test am echten System, 09.11.):** Eine dynamische Herbstszene für eine Zone mit elf Lampen
ließ sich nicht schön einstellen:
- In den eingebauten Paletten fehlt ein sattes Orange; die Töne wirkten auf dem Raum schmutzig.
  Der Raum hat schwarze, Eichen- und Birkenholzflächen, olivgrüne und dunkelgraue Wände.
- Alle Lampen liefen mit derselben Helligkeit: Deckenspots direkt über dem Sofa blendeten, ein Flur
  im offenen Treppenhaus war zu hell, andere Lampen zu dunkel.
- Eigene Farben und Feinabstimmung pro Lampe fehlten; man konnte nicht live am Raum einstellen.

Ziel: Bedienung und Ergebnis wie in der Hue-App – fertige Stimmungen antippen, eigene Szenen live
am echten Raum einstellen, pro Lampe Helligkeit und Verhalten festlegen.

### 1. Mitgelieferte Stimmungen (Galerie wie in der Hue-App)
- Mindestens **20 eingebaute Paletten** in Kategorien **Herbst, Winter, Weihnachten, Frühling,
  Sommer, Party, Entspannen, Romantik**. Je 3–5 Farben, eine passende Grundhelligkeit und ein
  vorausgewähltes Tempo (siehe 4.).
- **Eigene Namen und eigene Farben**, keine Namen, Farben oder Bilder aus der Hue-App (AGENTS.md).
- Farben passend zu warmen Wohnräumen mit Holz- und Grüntönen. Keine schmutzigen Rosa-/Lilatöne in
  Herbst/Romantik. Party darf kräftig und schnell sein.
- Darunter **„Herbstglut“** (Herbst): Bernstein `#FF9A2E`, sattes Orange `#FF6A13`, Kupfer `#D9541E`,
  Goldgelb `#FFC247`, gedämpftes Weinrot `#9E2A2B`.
- Die bisherigen 12 Paletten bleiben mit gleichen IDs erhalten (Szenen verweisen darauf).
- Galerie nach Kategorien, Vorschau als Verlauf. Antippen → Ziel (Raum/Zone) wählen → sofort
  anwenden; „Als Szene speichern“ öffnet den Szenen-Editor (3.) mit dieser Palette.

### 2. Eigene Paletten
- **Farben → + Neue Palette**: Name, Kategorie, 2–6 Farben per Farbwähler, Live-Vorschau als Verlauf.
  Bearbeiten, duplizieren („Eigene Variante aus eingebauter Palette“), löschen.
- **Live-Probe** auf ein Ziel während der Bearbeitung; „Abbrechen“ stellt den vorherigen Zustand der
  Lampen wieder her.
- Serverseitig im Store, Migration nur ergänzend. Eigene Paletten sind überall wählbar wie eingebaute.
- Löschen einer Palette, die von Szenen benutzt wird: verweigern und die Szenen nennen.

### 3. Szenen-Editor mit Einstellungen pro Lampe (Kern dieser Stufe)
- Neue und **bestehende** Szenen bearbeiten (Name, Palette/Momentaufnahme, Tempo, Lampen).
- Für **jede Lampe** des Ziels eine Zeile mit:
  - **Helligkeit**: „wie Szene“ oder fest 1–100 %. Bestehende Szenen bleiben „wie Szene“.
  - **Verhalten**: „Farbwechsel“ (Standard) · „feste Farbe“ (Palettenfarbe, Farbwähler oder Weißton) ·
    **„Mondlicht nach Mondphase“** (siehe 5.) · „in dieser Szene aus“.
- **Gesamthelligkeit** der Szene als eigener Regler; feste Lampenwerte bleiben fest, „wie Szene“ folgt.
- **Live**: Jede Änderung wirkt sofort auf die echte Lampe (wie Hue), entprellt. „Speichern“ übernimmt,
  „Abbrechen“ stellt den Zustand vor dem Öffnen wieder her.
- Lampen nur mit Ein/Aus (auch `switch_as_x`-Lichter) zeigen „An / Aus“ statt „0 %“.
- Gilt gleichermaßen für Räume und Zonen; eine Lampe in mehreren Zonen hat pro Szene eigene Werte.

### 4. Dynamik verständlich und stabil
- Tempo als Auswahl statt Sekunden: **Sehr langsam** (≈180 s/60 s Übergang), **Langsam** (≈90/40),
  **Mittel** (≈30/15), **Schnell** (≈8/3, Party). Sekunden nur unter „Mehr Optionen“.
- **Welle**: Reihenfolge der Lampen als **sortierbare Liste** („Welle läuft von … nach …“) statt
  3×3-Raster. Das bisherige Raster bleibt unter „Mehr Optionen“.
- Optional **„sanft lebendig“**: Helligkeit jeder Farbwechsel-Lampe schwankt langsam um ±10 % ihres Werts.
- Jeder Takt hält Helligkeit, feste Farben und „aus“ pro Lampe exakt ein.
- **Zigbee schonen**: Befehle eines Takts zeitlich verteilen; global höchstens ~5 Lichtbefehle pro
  Sekunde; bei Engpass Takt verlängern statt Befehle zu stauen. Im Protokoll vermerken.
- **Nach Neustart von Home Assistant** laufen aktive dynamische Szenen weiter (bis „aus“, eine andere
  Szene oder eine Automation sie ablöst).
- **Handbedienung einer einzelnen Lampe** während der Dynamik: nur diese Lampe verlässt den Farbwechsel
  bis zum nächsten Szenenstart; die übrigen laufen weiter.

### 4a. Jahreszeiten-Szene
- Pro Raum/Zone eine **„Szene nach Jahreszeit“**: je eine Szene für Frühling, Sommer, Herbst, Winter,
  optional Weihnachten (Zeitraum frei wählbar, Standard 1.–26. Dezember). Jahreszeitengrenzen
  einstellbar (Standard meteorologisch: 1. März/Juni/September/Dezember).
- Wählbar überall, wo eine Szene wählbar ist (Automationen, Taster, Kachel). Beim Auslösen wird die
  Szene der aktuellen Jahreszeit gestartet; fehlt eine, wird die nächstliegende genommen, mit Hinweis.
- Beispiele am echten System: Zone Wohnbereich abends nach Jahreszeit; Ambiente-Lichtstreifen im
  Schlafzimmer nach Jahreszeit mit Schwerpunkt Kategorie **Romantik**.
- Kategorie Romantik in 1. mit mindestens 4 Stimmungen (sinnlich, gedimmt, warm, auch tiefe Rot-,
  Bernstein- und dezente Violetttöne für Lichtstreifen), alle eher dunkel und ruhig.

### 5. Akzent „Mondlicht nach Mondphase“
- Pro Lampe wählbar (3.). Berechnet die beleuchtete Mondfläche lokal (synodischer Monat, ohne Cloud
  und ohne zusätzliche Integration).
- Einstellbar: Helligkeit bei Neumond und bei Vollmond (Standard 10 % / 80 %), Farbe bei Neumond und
  bei Vollmond (Standard kühles Blauweiß → helles Kaltweiß), fließend dazwischen. Optional „bei
  Vollmond langsam atmen“.
- Aktualisierung alle 30 Minuten während die Szene läuft. Anzeige in der Szene: „Mond heute: 37 %“.

### 6. Startseite und schnelle Bedienung
- Auf jeder Raum-/Zonenkachel die **Lieblingsszenen als Chips** (antippen = starten), wie in Hue.
- Kachel zeigt laufende Szene und ob sie dynamisch ist; Antippen der Szene stoppt/startet die Dynamik.

### 6a. Taster: Einschalten mit fester Helligkeit
- Für „Lampen ein/aus“ (`toggle_lights`, `turn_on_lights`) und „Raum ein/aus“ optional
  **„beim Einschalten“**: letzter Zustand (wie bisher) · feste Helligkeit 1–100 % · eine Szene ·
  **nach Tageszeit** (Liste von Zeitfenstern mit Uhrzeit oder Sonnenstand → Helligkeit/Weißton bzw.
  Szene, z. B. tagsüber 100 % neutral, abends 30 % warm, nachts 5 %).
  Beispiele am echten System: Esstisch-Lampen per Tap Dial Taste 1 an = immer 100 %, aus = aus;
  Deckenlicht per Wandschalter-Modul an = Helligkeit nach Tageszeit.
- Im Taster-Editor als Auswahl unter der Aktion; bestehende Belegungen bleiben „letzter Zustand“.

### 7. Umbenennen und Ersetzen von Lampen überstehen
- Beim echten System wurden Lampen umbenannt und von der Hue-Bridge zu Zigbee2MQTT umgezogen; dabei
  gingen u. a. Positionen verloren.
- Auf `entity_registry_updated` mit `old_entity_id` reagieren und **alle** Verweise im Store
  mitziehen: Freigaben, Zonen, Szenen (inkl. Werte pro Lampe), Positionen, Taster, Zeitpläne,
  Bewegung, Grundhelligkeit, Automatik-Stand.
- Unter „Mehr“: **„Lampe ersetzen“** – alle Verweise von Lampe A auf Lampe B übertragen (mit Vorschau
  der betroffenen Einträge).

### 8. Robustheit, am echten System beobachtet
- Hue-Farblampen über Zigbee2MQTT melden nach dem Anlernen `color_mode: unknown` und `brightness: null`,
  bis einmal Farbe oder Weißton gesetzt wurde. Solche Lampen nicht als „0 %“/„aus“ werten und beim
  ersten Befehl immer Farbe bzw. Weißton mitsenden.
- Farben so umsetzen, dass Farblampen gesättigt leuchten (xy im Gamut der Lampe begrenzen). Lampen nur
  mit Weißton erhalten den nächstliegenden bzw. wärmsten Weißton, nie eine Fehlermeldung.

### Abnahme
Synthetisch in Tests (keine echten Entity-IDs). Fertig, wenn:
1. Mindestens 20 Stimmungen inkl. „Herbstglut“ in Kategorien erscheinen und mit einem Tipp starten.
2. Eine eigene Palette angelegt, live probiert, gespeichert und in einer Szene benutzt werden kann.
3. In einer dynamischen Zonen-Szene zwei Lampen dauerhaft dunkler, eine Lampe mit fester Farbe und eine
   Lampe mit „Mondlicht“ laufen, während die übrigen die Farben wechseln – über mindestens drei Takte.
4. Eine aktive dynamische Szene einen Neustart übersteht.
5. Das Umbenennen einer Lampen-Entity alle Verweise mitzieht.
6. Bestehende Szenen, Zeitpläne, Taster und Zonen unverändert weiterlaufen.
Nach dem Draft-PR stoppen.

## Stufe 5d – Dimmen schaltet nie aus

Kleiner Nachtrag aus der Abnahme von 5c am 09.11. Problem: Wer mit einem Taster oder Drehring
herunterdimmt, schaltet die Lampe am Ende ganz aus. Grund ist `brightness_step_pct: -10`, denn bei
0 schaltet Home Assistant aus. Danach kann man sie nicht wieder hochdimmen, weil Hochdimmen
absichtlich nur eingeschaltete Lampen anfasst.

1. **Dunkler dimmen schaltet nie aus.** Gilt für alle Dimmwege: `dim_down` für Raum, Zone und
   ausgewählte Lampen, Taster, Drehring, Halten, Grundhelligkeit und Bewegung, falls sie relativ
   dimmen. Unterschreitet ein Schritt die Untergrenze, wird jede Lampe genau auf die Untergrenze
   gesetzt (absoluter Wert statt relativem Schritt). Eine Lampe, die schon an der Grenze ist,
   bekommt keinen Befehl.
2. **Untergrenze:** 1 % (Helligkeit 3 von 255). Global unter Einstellungen einstellbar von 1 bis 20 %.
   Gespeichert im Store mit Standardwert, ohne Migration. Für reine An/Aus-Lichter gibt es keine
   Dimmbefehle.
3. **Ausschalten bleibt unverändert:** Toggle- und Aus-Tasten, Zeitpläne und Szenen mit „aus“
   schalten weiter aus.
4. **Hochdimmen bleibt wie bisher:** Es wirkt nur auf eingeschaltete Lampen und schaltet nichts ein.
5. **Tests:** Eine Lampe bei 5 % plus `dim_down` ergibt Helligkeit 3, kein `turn_off`. Eine Lampe bei
   Helligkeit 3 plus `dim_down` ergibt keinen Befehl. Eine Lampe bei 50 % plus `dim_down` ergibt den
   normalen Schritt. Gemischte Auswahl mit einer Lampe an der Grenze und einer darüber. Halten mit
   Wiederholung. Ungültige Einstellwerte. Bestehende Dimm-Tests bleiben grün.
6. Hue-Effekte → verschoben nach Stufe 5e.
7. Lieferung als Git-Bundle auf `stufe-5d-dimmgrenze` mit Basis aktuelles `main`, Version 0.5.1,
   Screenshot der Einstellung bei 390 px. Keine Vorschauphase.

## Stufe 5e – Hue-Effekte, „Ambiente zuerst“ am Taster, Szene startet Skript

Basis: aktuelles `main` (0.5.1). Branch `stufe-5e-effekte`, Version 0.5.2. Drei Teile, eine Lieferung.

### A · Hue-Effekte in Szenen

Lampen, die `effect_list` melden, zum Beispiel ein Hue-Lichtband
   über Zigbee2MQTT mit sparkle, candle, fireplace, glisten, enchant oder cosmos, können im Szenen-Editor
   pro Lampe zusätzlich einen Effekt bekommen. Es zählen nur Werte aus der aktuellen `effect_list` der Lampe.
   Anzeige auf Deutsch: Funkeln, Kerze, Kamin, Glitzern, Verzaubern, Kosmos usw.
   Ausführung: zuerst Farbe und Helligkeit, nach etwa 2 s ein eigener `light.turn_on` mit `effect`.
   Beides im selben Befehl ging am echten System nicht, der Effekt startete nicht.
   Beim Wechsel auf eine Szene ohne Effekt oder beim Ausschalten wird vorher `stop_hue_effect` gesendet,
   falls die Lampe den Wert kennt, sonst `none`. Eine Lampe mit Effekt nimmt nicht am Farbwechsel teil
   (wie „feste Farbe“). Gilt für Momentaufnahme- und Palettenszenen, also auch für Jahreszeiten-Szenen.
   Die Live-Probe zeigt den Effekt. Tests: Effekt nicht in der Liste → abgelehnt; Ablauf Farbe → Effekt;
   Stopp beim Szenenwechsel; reine An/Aus-Lampen ohne Effekt.
   Vorlage am echten System: Schlafzimmer-Band, Ruby xy 0.55/0.25, Helligkeit 140, Funkeln.

Weitere Vorlage am echten System: Bad-Spiegellampen (Hue Filament, nur Helligkeit) mit Kerze, warm glühend.

### B · Taster-Option „Ambiente zuerst“

Allgemein für alle Taster mit `toggle_lights` und `toggle_room`. Eingesetzt wird die Option vorerst nur im Bad.

1. Neue optionale Einstellung an der Belegung: `ambient_first = {scene_id, window}`.
   - `scene_id` ist eine Szene des Raums oder der Zone, zu der die Belegung gehört. Jahreszeiten-Szenen sind erlaubt.
   - `window` ist ein Zeitfenster im bekannten Format mit Uhrzeit oder Sonne plus Versatz.
     Beispiel Bad: Sonnenuntergang −15 bis 22:30.
2. Ablauf innerhalb des Fensters:
   - Alle Ziellampen der Taste sind aus → die Ambiente-Szene startet für den ganzen Raum, mit Dynamik.
   - Die Ambiente-Szene läuft gerade → der Druck stoppt die Dynamik und schaltet die Ziellampen der Taste
     nach ihrem normalen Einschaltverhalten (`on_behavior`, z. B. 100 % oder nach Tageszeit).
     Die übrigen Lampen des Raums gehen dabei aus.
     „Läuft gerade“ heißt: Das ist `last_scene_id` des Raums, die Dynamik ist aktiv bzw. die Szenenlampen sind an,
     und es gab keine Handbedienung danach.
   - Sonst, also die Ziellampen sind an und keine Ambiente-Szene läuft → aus.
3. Außerhalb des Fensters ist alles wie bisher: Einschalten nach `on_behavior`, nochmal drücken heißt aus.
4. Die Bedienung zeigt die Option im Tasterdialog als „Zur Ambiente-Zeit zuerst Szene“ mit Szenenwahl und Zeitfenster.
5. Tests:
   - die drei Zustände innerhalb des Fensters
   - außerhalb des Fensters
   - Fenster über Mitternacht
   - gelöschte Szene: Fallback auf das normale Verhalten mit Protokollhinweis
   - entzogene Freigabe
   - Handbedienung beendet „läuft gerade“
6. Einrichtung bei Max im Bad (macht Claude nach der Installation):
   - Schalter Decke: Ambiente „Bad Herbstglut“, danach Decke nach Tageszeit (100 % / 20 % / Nachtlicht)
   - Schalter Spiegel: Ambiente „Bad Herbstglut“, danach Spiegel 100 %

### C · Szene startet zusätzlich ein Home-Assistant-Skript

1. Optionales Feld an jeder Szene: `start_script`, eine `script.*`-Entity. Wird beim Start der Szene
   nach den Lichtbefehlen mit `script.turn_on` ausgeführt.
   Gilt für Kachel, Taster, Zeitplan und Jahreszeiten-Auflösung.
   Nicht bei Live-Probe und nicht beim Fortsetzen nach einem Neustart.
2. Nur Skripte, die in Home Assistant existieren. Ein Fehler im Skript lässt die Szene trotzdem laufen,
   mit Protokollhinweis.
3. Zweck: Musik zur Stimmung, z. B. eine Spotify-Playlist über Music Assistant. Den Ablauf baut Claude
   als HA-Skript. Die Lichtzentrale selbst bekommt keine Spotify-Logik.
4. Tests:
   - Skript läuft genau einmal pro Szenenstart
   - nicht bei Fortsetzen und nicht bei Live-Probe
   - fehlendes oder ungültiges Skript wird beim Speichern abgelehnt
   - Fehler im Skript blockiert das Licht nicht

Lieferung als Git-Bundle mit Tests und Screenshots bei 390 px: Effekt-Feld, Tasterdialog „Ambiente zuerst“, Skript-Feld der Szene. Keine Vorschauphase.

## Stufe 6 – Anwesenheitssimulation

- Schalter „Urlaubsmodus“ in der Oberfläche und als Service.
- Pro ausgewähltem Raum abends zwischen wählbaren Grenzen (Uhrzeit/Sonnenstand) zufällige Ein-
  und Ausschaltzeiten mit Mindest- und Höchstdauer, plausible Abfolge (Wohnraum lang, Flur/Bad
  kurz).
- Optional „aus dem Verlauf lernen“: typische Schaltzeiten der letzten 14 Tage aus dem Recorder,
  zufällig um ±20 Minuten verschoben.
- Bewegungsautomatik und Grundhelligkeit sind im Urlaubsmodus pausiert.

## Stufe 7 – Sicherung, „Alles aus“, Öffnung für andere

- Export aller Lichtzentrale-Daten (Szenen, Paletten, Positionen, Taster, Bewegungsregeln,
  Zeitpläne, Grundhelligkeit, Urlaubsmodus) als JSON über die Oberfläche; Import mit Vorschau und
  Bestätigung; ungültige oder fehlende Entities melden, nicht stillschweigend übernehmen.
- Automatische tägliche Sicherung der letzten 7 Stände unter `<config>/lichtzentrale_backups/`.
- Service `lichtzentrale.all_off`: alle freigegebenen Lampen und Schalter aus, dynamische Szenen
  stoppen, optional Raumauswahl. Kein automatisches Auslösen.
- **Beliebige Schalter freigeben:** Jede `switch`-Entity (nicht nur Shelly mit „Licht“ im Namen)
  lässt sich in der Freigabe ausdrücklich als Licht markieren. Die bisherige Shelly-Erkennung
  bleibt als Vorschlag erhalten. Die Vorgabe in AGENTS.md („nur die in HAUS.md genannten switch-Deckenlichter“)
  entsprechend auf „ausdrücklich als Licht freigegebene switch-Entities“ anpassen.
- README: Hinweis „Privates Projekt, ohne Support und ohne Gewähr“; Installationsanleitung über
  HACS als benutzerdefiniertes Repository; Liste der Voraussetzungen (HA-Version, optional
  Adaptive Lighting, optional Hue Bridge für Hue-Szenen).
