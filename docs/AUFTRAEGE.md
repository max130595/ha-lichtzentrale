# Offene Aufträge (Reihenfolge verbindlich)

Diese Datei pflegt Claude. ChatGPT/Codex arbeitet immer nur **eine** Stufe ab, genau dann, wenn
der Nutzer sie startet („Starte Stufe X aus docs/AUFTRAEGE.md“). Ablauf je Stufe: `git pull` auf
`main`, neuer Branch wie angegeben, umsetzen, `docs/BAUPLAN.md` ergänzen, Tests, Draft-PR öffnen,
**aufhören** bis Claude freigibt (siehe AGENTS.md). Für alle Stufen gilt: keine Kinderzimmer und kein
Bad oben in Tests oder Beispielen, Schalter (`switch`) werden nie gedimmt.

| Stufe | Branch | Status |
|---|---|---|
| 4a Zeitfenster-Bedingung | `stufe-4a-zeitfenster` | erledigt (PR #9, getestet 08.11.) |
| 5 Grundhelligkeit | `stufe-5-grundhelligkeit` | offen |
| 6 Anwesenheitssimulation | `stufe-6-urlaub` | offen |
| 7 Sicherung, „Alles aus“, Öffnung für andere | `stufe-7-sicherung` | offen |

---

## Stufe 5 – Grundhelligkeit

- Pro Raum: Lux-Sensor (wählbar, device_class illuminance, Einheit lx), Zielhelligkeit in lx,
  Hysterese in lx, Mindestzeit zwischen zwei Stufenwechseln (Standard 3 Minuten).
- Geordnete Stufen pro Raum; jede Stufe ist eine Lampen-/Schalterauswahl mit Helligkeit.
  Zu dunkel → nächste Stufe dazu; zu hell → Stufen in umgekehrter Reihenfolge aus.
  Schalter (Deckenlichter) sind typischerweise die letzte Stufe.
- Eigenlicht herausrechnen: Beim Zuschalten einer Stufe den Lux-Anstieg messen und pro Stufe als
  gleitenden Mittelwert speichern; beim Abschalten berücksichtigen, damit nichts pendelt.
- Lampen übernehmen den Weißton von Adaptive Lighting, falls dem Raum zugeordnet.
- Bedingungen: Zeitfenster (Uhrzeit/Sonnenstand wie in 4a), optional nur bei Anwesenheit
  (person-Entities).
- Handbedienung (Taster, Szene, App) pausiert die Regelung bis zum nächsten Zeitfenster-Beginn
  oder bis „Raum aus“.
- Oberfläche: Ein/Aus pro Raum, Anzeige aktuelle Lux, Ziel, aktive Stufe, gelernte Anteile.

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
