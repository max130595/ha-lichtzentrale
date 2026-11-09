# Stufe 5b: Vorschau prüfen, Umsetzung getrennt freigeben

## Umfang dieses Draft-PRs

Teil 1 ist eine eigenständige Handy-Vorschau unter `docs/vorschau-5b/index.html`.
Alle Daten sind erfunden und bleiben nur im Arbeitsspeicher der Seite. Die Vorschau
verbindet sich weder mit Home Assistant noch mit Geräten. Produktiver Quellcode,
Frontend-Bundle, Integrationsversion und gespeicherte Nutzerdaten bleiben unverändert.

`index.html` herunterladen und in einem Browser öffnen. Kein Build und kein Konto nötig.
Die Datei funktioniert auch offline. Auf einem breiten Bildschirm kann die Prüfbreite mit `?width=320`, `?width=390` oder
`?width=430` am Ende der Adresse gewählt werden. Auf dem Handy passt sie sich dem Bildschirm an.
Neuladen oder „Vorschau zurücksetzen“ stellt die Ausgangsbeispiele wieder her.

## Teil 1: Bedienung zur Freigabe

1. **Alle Reiter:** Zuhause, Szenen, Automationen, Taster und Mehr öffnen. Die Reiterleiste
   bleibt unten erreichbar. Keine waagerechte Scrollleiste bei 320, 390 und 430 Pixeln.
   Raumdetails haben den Raumnamen als Überschrift. Die Beispieldaten und Grenzen der
   Vorschau sind erkennbar; keine echten Entity-IDs oder privaten Wohnungsdaten erscheinen.
2. **Zonen:** Eine neue Zone aus Leselicht und Pendelleuchte anlegen. Beide gehören weiterhin
   zu ihren Räumen und dürfen zusätzlich in einer anderen Zone liegen. In Zuhause direkt
   schalten/dimmen, Details öffnen und eine Szene starten. Reine Schalter nicht dimmen.
3. **Sonnenuntergang:** Automationen → Neue Automation → Sonnenuntergang → −15 → Weiter →
   Zone Wohnbereich → Weiter → Szene Abend → speichern. Satz in der Übersicht prüfen.
   Alle Wochentage sind anfangs ausgewählt. Freien Versatz, Sonnenaufgang und Uhrzeit prüfen.
4. **Mehrere Aktionen:** Einen Plan für 22:30 Uhr anlegen: Wohnbereich aus, Flur Nachtlicht.
   „Jetzt testen“ muss beide Demoaktionen ausführen. Die Liste zeigt einen verständlichen
   Satz, Ein/Aus und den ausdrücklich simulierten Hinweis zur nächsten Ausführung.
5. **Nachtlicht:** Im Wohnbereich zunächst den Abend-Plan mit „Jetzt testen“ ausführen.
   Nachtlicht aktivieren und erneut „Nachtlicht ⇄ Automatik“ drücken: Abend kehrt zurück.
   Manuelles Schalten ersetzt den gespeicherten Demo-Automatikstand nicht. Nachtlichtname
   und Helligkeit ändern. Ohne heutigen Stand bleibt „Zurück zur Automatik“ wirkungslos
   und schreibt einen Hinweis ins Protokoll. Den Tageswechsel in Mehr simulieren.
6. **Dimmer:** Taster → Hue Dimmer → Vorlage verwenden, Ziel Wohnbereich wählen. An = volle
   Helligkeit mit neutralem Weiß, Hue = Nachtlicht ⇄ Automatik, Hoch/Runter = dimmen,
   Aus = ausschalten. Tasten in der Zeichnung antippen, Kurz/Lang/Drehen und Ziele ändern.
   Andere Gerätezeichnungen öffnen. Ein Raum, eine Zone und einzelne Lampen sind wählbar.
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

Nach `npm ci` im Projektstamm: `node --test docs/vorschau-5b/preview.test.cjs`.
Die Tests laden ausschließlich die eigene HTML-Datei in einer isolierten DOM-Umgebung.
Sie prüfen die Kernabläufe, ausgeschlossene Schalter sowie die Abwesenheit von Netzwerk-
und Browser-Persistenzzugriffen. Sie ersetzen keine Prüfung mit Home Assistant.

Vorhandene Frontend-Regression: `npm run typecheck`, `npm run lint`, `npm test`.
Der genaue ausgeführte Stand und die manuellen Handyprüfungen stehen im PR.

## Teil 2: Erst nach ausdrücklicher Freigabe

Diese Punkte sind **offen**, nicht durch eine klickbare Vorschau nachgewiesen:

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
  Ausführungsreihenfolge, nächste Ausführung, deaktivierte Pläne und Fehlerfälle testen.
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

**Haltepunkt:** Nach Öffnen des Draft-PRs endet die Arbeit an Teil 1. Keine produktive
Umsetzung, Nachbesserung am Branch oder CI-Überwachung bis zur vereinbarten Rückmeldung.
