# Stufe 5b: Wo finde ich meine bisherigen Funktionen?

**Teil 1 freigegeben; Teil 2 im Draft zur technischen Abnahme.** Die [Handy-Vorschau](vorschau-5b/index.html) arbeitet nur mit
Beispielen im Arbeitsspeicher. Sie ist kein Home-Assistant-Panel und steuert keine Geräte.
Die produktive Umsetzung nutzt dieselbe Zuordnung; bestehende gespeicherte Daten werden
additiv ergänzt. Geräte werden ausschließlich über die Home-Assistant-Integration gesteuert.

## Fünf Reiter, ein gemeinsamer Ablauf

- **Zuhause:** Zonen vor Räumen, kompakte Kacheln mit Name, Schalter und Helligkeit. Ein Tipp auf den
  Namen öffnet Szenen und Lampen. Ein reiner Lichtschalter bekommt keinen Helligkeitsregler.
- **Farben:** Farbpaletten auswählen, dann Raum oder Zone. Eigene Szenen entstehen direkt im Ziel.
- **Automationen:** Verständliche Sätze statt technischer Regeln. Neu anlegen mit **Wann → Wo → Was**.
- **Taster:** Ein Bild des Geräts, darauf die Taste wählen und ihre Aufgabe festlegen.
- **Mehr:** Lampenfreigaben und seltene Einstellungen. Protokollhinweise erscheinen zusätzlich in Home Assistant.

Der bisherige eigene Reiter „Raum“ wird zur Detailansicht von „Zuhause“. So muss niemand einen
Raum auswählen und danach erst den richtigen Reiter suchen. Ein Zurück-Knopf führt zur Liste.
Formulare und aufklappbare „Mehr Optionen“ bleiben innerhalb dieser zweiten Ebene.

## Bestehende Funktionen

| Bisher | Neuer Platz | Was erhalten bleiben muss |
|---|---|---|
| Räume-Übersicht | Zuhause | Bereiche, Anzeigenamen, Verfügbarkeit, zuletzt gestartete Szene |
| Raum an/aus | Direkt auf der Raumkachel und in den Details | Freigaben und bisherige Wiederherstellung; keine unerwünschten Deckenlichter einschalten |
| Raumhelligkeit | Schieberegler auf Kachel und in Details | Nur dimmbare Lampen; Schalter niemals dimmen |
| Einzellampen schalten, Farbe, Weißton | Zuhause → Raum/Zone → Lampen | Geräteeigene Fähigkeiten und Temperaturgrenzen |
| Snapshot speichern | Zuhause → Raum/Zone → + Neue Szene | Aktuellen Zustand sichern; fehlende Lampen ausdrücklich melden |
| Gespeicherte Szenen starten | Raum-/Zonendetails | Snapshot, Palette, Hue; Favoriten, Namen und Reihenfolge |
| Szenen umbenennen, favorisieren, sortieren, löschen | Raum-/Zonendetails → Szene bearbeiten | Bestehende IDs und Verweise; Löschbestätigung |
| Hue-Szene importieren | Raumdetails → Mehr Optionen → Hue-Szene importieren | Nur verifizierte Ziele; keine Hue-Bilder oder mitgelieferten Hue-Namen |
| Farbpaletten nach Kategorie | Farben → Farbpaletten | Eigene Namen, Farben und erzeugte Farbverläufe |
| Palette direkt anwenden / als Szene speichern | Farben → Palette wählen | Zielauswahl, Helligkeit, optional Dynamik |
| Dynamische Szene starten | Szene → Mehr Optionen | Intervall und Übergang; ausgeschaltete Lampen bleiben aus |
| Lokale und Hue-Dynamik stoppen | Raum-/Zonendetails → Dynamik stoppen | Eingeschaltete Ziele einfrieren, ohne andere Lampen einzuschalten |
| Räumliche Farbverteilung / Welle | Szene → Mehr Optionen | Zufall, beide Achsen, Höhe und Welle |
| Lampenpositionen im 3×3-Raster und Höhe | Zuhause → Raum → Mehr Optionen → Lampen anordnen | Bestehende Positionen, mehrere Lampen pro Feld |
| Natürliches Licht zuordnen / an / aus | Raum → Mehr Optionen | Nur sichtbar, wenn Adaptive Lighting tatsächlich vorhanden ist |
| Verhalten beim Einschalten | Raum → Mehr Optionen | Letzter Zustand, Szene oder optional natürliches Licht |
| Szenenzyklus am Taster | Raum → Mehr Optionen | Reihenfolge und Neustart des Zyklus nach zehn Minuten |
| Tastenbelegungen und Einzellampenauswahl | Taster → Taste | Bestehende Hue-/Shelly-Belegungen und Mehrfachziele |
| Kurz/lang/halten/drehen, doppelt/dreifach | Taster → Taste; seltene Ereignisse unter Mehr Optionen | Bekannte Ereignisse verständlich benennen; unbekannte nicht ausblenden |
| Hue-Doppelklickzeit | Taster → Mehr Optionen | Erkennung nur für entsprechend belegte Tasten |
| Zeitpläne schalten, bearbeiten, löschen | Automationen | Alte Pläne erscheinen als Satz, behalten ihre Daten und ihren Aktivierungszustand |
| Uhrzeit, Sonnenauf/-untergang und Versatz | Automationen → Wann | Astronomische Sonnenzeiten und freie Versatzwerte |
| Lux als Auslöser, Mindestdauer | Automationen → Wann → Mehr Optionen | Ereignisabhängiger Auslöser bleibt erhalten |
| Wochentage | Automationen → Wann | Alle vorausgewählt bei neuer Regel; alte Auswahl unverändert |
| Personen, Lichtzustand, Zeitfenster, Übergang | Automationen → Mehr Optionen | Einschließlich Mitternacht, offenen Grenzen und bisherigen Sicherheitsregeln |
| Jetzt testen / nächste Ausführung | Direkt in der Automationenliste | Produktiv echte Aktion mit Bedingungen; in der separaten Vorschau ausschließlich Simulation |
| Bewegungsautomatik | Raum → Mehr Optionen → Bewegung | Sensoren, Fenster, Aktionen, Lux, Nachlauf, Vorabdunkeln, manuelle Pause |
| Grundhelligkeit | Raum → Mehr Optionen → Grundhelligkeit | Stufen, Lux-Ziel, Hysterese, Mindestzeit, Eigenlicht-Lernen, Besitz und manuelle Pause |
| Grundhelligkeit abschalten / Licht anlassen | Grundhelligkeit → Mehr Optionen | Bestehende ausdrückliche Auswahl, keine unbeabsichtigte Übernahme |
| Lampenfreigaben | Mehr → Lampen freigeben | Bisherige ausdrückliche Freigabe und ausgeschlossene Geräte |
| Fehlende Geräte / Teilfehler / erneutes Laden | Beim betroffenen Element und im Protokoll | Keine vorgetäuschte Erfolgsmeldung; Anzeigenamen statt Entity-ID |

Die Vorschau zeigt nur die Platzierung. Die produktive Oberfläche verwendet weiterhin die
bestehenden Sensorberechnungen, Importfunktionen und Gerätevalidierungen. Alte erweiterte
Zeitpläne behalten dafür ihren bisherigen Editor; neue Pläne nutzen den Assistenten.

## Neu in Stufe 5b

| Funktion | Vorgesehener Ablauf |
|---|---|
| Zonen | Zuhause → Zone hinzufügen → Lampen aus mehreren Räumen wählen; Mehrfachmitgliedschaft erlaubt |
| Mehrere Ziele | Erste Aktion übernimmt die Auswahl aus „Wo“; in „Was“ nur eine Zusammenfassung. Zusätzliche Aktionen wählen eigene Ziele |
| Mehrere Aktionen pro Automation | In „Was“ weitere Aktion samt Zielauswahl hinzufügen; streng nacheinander in angezeigter Reihenfolge, spätere Aktion gilt bei Überschneidung |
| Nachtlicht | Eine normale Szene je Raum/Zone als Nachtlicht markieren und frei einstellen |
| Zurück zur Automatik | Aktion für Taster und Automationen; letzten heutigen Automatikstand wiederherstellen; ohne Stand nur Protokollhinweis |
| Nachtlicht ⇄ Automatik | Aktion für Taster und Automationen; aus Nachtlicht zurück zur Automatik, sonst Nachtlicht starten |
| Volle Helligkeit | 100 % und neutrales Weiß für geeignete Lampen; keine Helligkeits-/Farbwerte für Switches |
| Zigbee2MQTT-Taster | Taste anlernen: Event-Quelle, Ereignistyp und aktuelle Tasten-/Drehrichtungsattribute gemeinsam zuordnen |

## Grenzen zwischen Vorschau und Umsetzung

- Die getrennte HTML-Vorschau verändert nur Demodaten im Arbeitsspeicher. Die produktive
  Integration speichert Zonen, Szenen, Taster und Automationen serverseitig.
- Der Automatikstand pro Raum/Zone gilt nur am lokalen Kalendertag und überlebt Neustarts
  innerhalb dieses Tages. Manuelle Bedienung überschreibt ihn nicht. Ohne Stand erfolgt
  keine Geräteaktion; ein Protokollhinweis erklärt die fehlende Rückkehr.
- Neue Automationen führen alle Aktionen streng nacheinander aus. Eine Szene gehört
  genau einem Raum oder einer Zone; für verschiedene Szenen mehrere Aktionen anlegen.
- Zigbee2MQTT-Attribute werden zur Laufzeit gelernt. Ein generischer Ereignistyp alleine
  reicht nicht für mehrere Tasten. Gerätezeichnungen/Vorlagen ersetzen nicht das tatsächliche
  Zuordnen der physischen Taste. Vorhandene Hue-Belegungen bleiben gültig.
- Alte gespeicherte Objekte und Zusatzfelder bleiben erhalten. Die automatisierten Prüfungen
  sowie noch offene Geräte- und Handy-Abnahmen stehen im [Testplan](STUFE_5B_TESTPLAN.md).
- Externe Home-Assistant-Automationen werden nicht abgeschaltet. Das übernimmt Claude erst
  nach erfolgreicher Abnahme. Stufe 6/7 gehören nicht zu dieser Umsetzung.

## Übergabe

Die Vorschau ist freigegeben. Teil 2 wird mit gebautem Bundle als Draft zur Prüfung
übergeben. Nach dieser Übergabe keine weiteren Änderungen oder CI-Überwachung, bis Claude
über den Nutzer die Arbeit wieder freigibt. Keine Live-Installation in diesem Auftrag.
