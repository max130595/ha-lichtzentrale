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
| 5b Einfache Bedienung wie die Hue-App | `stufe-5b-einfach` | offen – **als Nächstes** |
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
