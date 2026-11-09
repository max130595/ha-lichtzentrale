# Stufe 5b: Wo finde ich meine bisherigen Funktionen?

**Entwurf zur Freigabe, Teil 1.** Die [Handy-Vorschau](vorschau-5b/index.html) arbeitet nur mit
Beispielen im Arbeitsspeicher. Sie ist kein Home-Assistant-Panel und steuert keine Geräte.
Die bestehende Integration, ihr Bundle und alle gespeicherten Daten bleiben unverändert.

## Fünf Reiter, ein gemeinsamer Ablauf

- **Zuhause:** Räume und Zonen auf einen Blick, direkt schalten und dimmen. Ein Tipp auf den
  Namen öffnet Szenen und Lampen. Ein reiner Lichtschalter bekommt keinen Helligkeitsregler.
- **Szenen:** Eigene Szenen und Farbpaletten. Eine Farbe wählen, dann Raum oder Zone.
- **Automationen:** Verständliche Sätze statt technischer Regeln. Neu anlegen mit **Wann → Wo → Was**.
- **Taster:** Ein Bild des Geräts, darauf die Taste wählen und ihre Aufgabe festlegen.
- **Mehr:** Lampenfreigaben, seltene Einstellungen, Protokoll und Hinweise zur Vorschau.

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
| Snapshot speichern | Zuhause → Raum/Zone → Szene speichern | Aktuellen Zustand sichern; fehlende Lampen ausdrücklich melden |
| Gespeicherte Szenen starten | Szenen oder Raum-/Zonendetails | Snapshot, Palette, Hue; Favoriten, Namen und Reihenfolge |
| Szenen umbenennen, favorisieren, sortieren, löschen | Szenen → Bearbeiten | Bestehende IDs und Verweise; Löschbestätigung |
| Hue-Szene importieren | Szenen → Mehr Optionen → Von Hue übernehmen | Nur verifizierte Ziele; keine Hue-Bilder oder mitgelieferten Hue-Namen |
| Farbpaletten nach Kategorie | Szenen → Farbpaletten | Eigene Namen, Farben und erzeugte Farbverläufe |
| Palette direkt anwenden / als Szene speichern | Szenen → Palette wählen | Zielauswahl, Helligkeit, optional Dynamik |
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
| Jetzt testen / nächste Ausführung | Direkt in der Automationenliste | In Phase 2 echte Aktion mit Bedingungen; in dieser Vorschau ausschließlich Simulation |
| Bewegungsautomatik | Raum → Mehr Optionen → Bewegung | Sensoren, Fenster, Aktionen, Lux, Nachlauf, Vorabdunkeln, manuelle Pause |
| Grundhelligkeit | Raum → Mehr Optionen → Grundhelligkeit | Stufen, Lux-Ziel, Hysterese, Mindestzeit, Eigenlicht-Lernen, Besitz und manuelle Pause |
| Grundhelligkeit abschalten / Licht anlassen | Grundhelligkeit → Mehr Optionen | Bestehende ausdrückliche Auswahl, keine unbeabsichtigte Übernahme |
| Lampenfreigaben | Mehr → Lampen freigeben | Bisherige ausdrückliche Freigabe und ausgeschlossene Geräte |
| Fehlende Geräte / Teilfehler / erneutes Laden | Beim betroffenen Element und im Protokoll | Keine vorgetäuschte Erfolgsmeldung; Anzeigenamen statt Entity-ID |

Die Vorschau zeigt die Platzierung dieser erweiterten Einstellungen. Eine tatsächliche
Sensorberechnung, Importfunktion oder Gerätevalidierung ist damit noch nicht umgesetzt.

## Neu in Stufe 5b

| Funktion | Vorgesehener Ablauf |
|---|---|
| Zonen | Zuhause → Zone hinzufügen → Lampen aus mehreren Räumen wählen; Mehrfachmitgliedschaft erlaubt |
| Mehrere Ziele | Räume, Zonen und Einzellampen in derselben Auswahl; überall verständliche Namen |
| Mehrere Aktionen pro Automation | In „Was“ weitere Aktion samt Zielauswahl hinzufügen |
| Nachtlicht | Eine normale Szene je Raum/Zone als Nachtlicht markieren und frei einstellen |
| Zurück zur Automatik | Letzten heutigen Automatikstand wiederherstellen; ohne Stand nur Protokollhinweis |
| Nachtlicht ⇄ Automatik | Aus Nachtlicht zurück zur Automatik, sonst Nachtlicht starten |
| Volle Helligkeit | 100 % und neutrales Weiß für geeignete Lampen; keine Helligkeits-/Farbwerte für Switches |
| Zigbee2MQTT-Taster | Taste anlernen: Event-Quelle, Ereignistyp und aktuelle Tasten-/Drehrichtungsattribute gemeinsam zuordnen |

## Grenzen zwischen Vorschau und Umsetzung

- **Jetzt:** Alle Aktionen verändern nur synthetische Demodaten. Neuladen oder „Vorschau
  zurücksetzen“ setzt sie zurück. Keine Browser-Persistenz, keine Netzwerkanfragen an HA.
- **Erst nach Freigabe:** Serverseitige Zonen, Multiaktionen und Nachtlicht-Zuordnung ergänzen
  das bestehende Modell. Alte Szenen, Zeitpläne, Bewegungs-/Grundhelligkeitsregeln und Taster
  dürfen weder still gelöscht noch ungefragt umgedeutet werden.
- **Automatikstand in Phase 2:** Pro Raum/Zone gilt die letzte heute von einer Automation
  ausgeführte Aktion, auch „aus“ oder Nachtlicht. Der Stand überlebt einen Neustart und wird
  um lokales Mitternacht zurückgesetzt. Manuelle Bedienung überschreibt ihn nicht.
  Die Vorschau macht die Rückkehr sichtbar; sie simuliert keine vollständige HA-Zeitplanung.
- **Zigbee2MQTT in Phase 2:** Tatsächliche Ereignisattribute werden zur Laufzeit gelernt.
  Ein generischer Ereignistyp alleine reicht nicht für mehrere Tasten. Attribute im Demoablauf
  sind nur Beispieldaten und kein festgelegter Adapter. Vorhandene Hue-Belegungen bleiben gültig.
- **Migrationstest später:** Ein bestehender Store muss vor/nach Migration verglichen werden,
  einschließlich unbekannter Zusatzfelder und alter Ein-Aktions-Zeitpläne. Phase 1 schreibt
  keinen Store und kann deshalb keinen erfolgreichen Migrationstest behaupten.
- Bestehende externe Home-Assistant-Automationen werden nicht abgeschaltet. Das übernimmt
  Claude erst nach erfolgreicher produktiver Abnahme.
- Stufe 6/7, Urlaubsmodus, Sicherung und erweiterte Switch-Freigaben gehören nicht zu diesem Entwurf.

## Freigabeentscheidung

Bitte zuerst die Bedienung in der Vorschau beurteilen: Ist die Raum-/Zonenübersicht verständlich?
Ist die Automation mit −15 Minuten ohne Anleitung anlegbar? Lässt sich der Dimmer unmittelbar
belegen und Nachtlicht ⇄ Automatik nachvollziehen? Danach kann Teil 2 gesondert freigegeben werden.
