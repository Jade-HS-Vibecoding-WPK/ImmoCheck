# ImmoCheck

Wirtschaftlichkeitsprüfung für Immobilien als einzelne Webseite: Kaufangebote schnell bewerten und Bestandsobjekte verwalten. Läuft komplett im Browser, ohne Installation, ohne KI und ohne eigenen Server. Alle Eingaben bleiben im Browser des Nutzers.

**Live:** https://jade-hs-vibecoding-wpk.github.io/ImmoCheck/

## Starten
`docs/index.html` per Doppelklick im Browser öffnen (Mac und Windows) oder den Live-Link nutzen. Für Adressabfragen und Karten ist eine Internetverbindung nötig.

## Funktionen
**Kaufprüfung**
- **Dashboard** mit allen Objekten, Status Angebot oder Bestand, Filter
- **Kaufberechnung** pro Objekt: Nettorendite, Cashflow, Eigenkapitalrendite, Urteil mit Begründung
- **Annahmen** in eingeklappten Gruppen: Miete und Kosten, Kaufnebenkosten, Finanzierung mit Effektivzins, Prognose und Ziele, Sonderfälle (Erbbaurecht, Ertragswert, Steuerwirkung)
- **Analyse:** Ertragsrechnung, Zinsdeckung, Stresstest mit Kipppunkten, Kaufpreis-Sensitivität, Grafik und Jahresverlauf
- **Sanierungsrechner** mit eigenen Preisen, Zuschlägen und Übernahme in die Kaufberechnung
- **Checkliste** fürs Objekt und **Objektvergleich** aus den Dashboard-Objekten

**Daten zur Adresse** (automatisch nach Eingabe der Adresse)
- **Ortsübliche Miete** aus dem Zensus 2022 (Durchschnitt je Gitterzelle), Übernahme als Ist-Miete
- **Bodenrichtwert** und **Flurstücksfläche**, daraus der **Grundstückswert** (Niedersachsen und NRW)
- Objektdaten inkl. Sanierungsstand, Heizungsalter, Energiekennwert, Energieausweis und Erneuerungsjahren

**Bestandsverwaltung**
- **Portfolio** der Bestandsobjekte mit Restschuld, Nettovermögen und Zinsrisiko
- **Objektseite** mit Foto, Karte, Luftbild, Flurkarte, Flurstück, Gebäudegrundfläche und GRZ aus dem Kataster (Niedersachsen und NRW)
- **Dokumente** je Bestandsobjekt hochladen (Mietverträge, Abrechnungen, Versicherungen u. a.)

**Bericht** als PDF in DIN A4 mit Deckblatt, Foto, Lageseite mit Flurkarte und Luftbild, Kennzahlen, Annahmen und Checkliste (Drucken, als PDF sichern)

**Daten sichern:** Export und Import der Objekte als JSON, alles löschen.

## Datenquellen
| Daten | Quelle |
|---|---|
| Adresssuche | OpenStreetMap Nominatim |
| Karte | OpenStreetMap |
| Luftbild | Esri World Imagery |
| Miete | Zensus 2022 (Statistische Ämter des Bundes und der Länder), über einen ArcGIS-Dienst |
| Bodenrichtwerte | BORIS Niedersachsen (LGLN), BORIS NRW |
| Flurstücke, Gebäude, Flurkarte | ALKIS Niedersachsen (LGLN), ALKIS NRW (Geobasis NRW) |

Bundesweit gibt es keinen offenen Dienst für Bodenrichtwerte und Flurstücke. In anderen Bundesländern trägt man diese Werte selbst ein.

## Speicherung
Objekte liegen im `localStorage`, Dokumente und Fotos in der IndexedDB des Browsers, jeweils nur auf dem verwendeten Gerät. Dokumente und Fotos sind nicht im JSON-Export enthalten. Löschen der Websitedaten löscht auch sie.

## Veröffentlichen mit GitHub Pages
Einstellungen, Pages, Quelle `main`, Ordner `/docs`.

## Hinweis
Überschlagsrechnung vor Steuern. Standardwerte (Steuersätze, Zuschläge, Liegenschaftszins, Abschreibung) sind Annahmen und vor einer Entscheidung zu prüfen. Zensus-Mieten sind Durchschnitte, kein qualifizierter Mietspiegel. Die GRZ ist aus dem Kataster berechnet und ersetzt nicht den Bebauungsplan. Keine Anlage-, Rechts- oder Steuerberatung.
