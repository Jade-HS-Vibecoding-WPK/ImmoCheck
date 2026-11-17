# Baukostentool aus Architekturplänen · Bauauftrag für Claude Code

## Auftrag

Implementiere eine lokal startbare, deutschsprachige Web-App für meinen Architektur-Wahlpflichtkurs. Als Architekt möchte ich Grundrisse, Ansichten und Schnitte aus Archicad als PDF hochladen, auf **„Pläne auswerten“** klicken und eine nach DIN-276-Kostengruppen gegliederte Kostenaufstellung erhalten. Die App soll selbst die Pläne lesen, Maße und Bauteile zusammenführen, Mengen berechnen und passende hinterlegte Kostenkennwerte anwenden. Die erste Auswertung liefert eine kennwertbasierte Orientierung für das Bauwerk (KG 300+400) aus BGF und, wenn herleitbar, BRI. Parallel kann sie planbelegte Einzelbauteile bewerten. Mein Gemeindehaus in Bersenbrück ist ein möglicher Praxisfall. Projektname und Gebäudetyp bleiben frei.

Der Hauptweg beginnt mit einem echten Datei-Upload. Eine manuell auszufüllende Mengentabelle oder ein Variantenvergleich würde den Kern verfehlen. Baue einen funktionierenden Durchlauf, teste ihn und dokumentiere den Start. Wenn das Repository leer ist, lege die Anwendung an. Arbeite die unten beschriebenen Schritte selbständig ab.

## Was ich als Nutzer sehe

1. **Plansatz hochladen.** Mehrere PDFs oder eine mehrseitige PDF ablegen. Miniaturen zeigen Grundriss, Schnitt und Ansichten mit Planbezeichnung, Geschoss, Orientierung und Planstand, soweit vorhanden. Bei mehreren Zeichnungen auf einem Blatt führe getrennte Ansichtsbereiche. Unklare Zuordnungen sind korrigierbar.
2. **Pläne auswerten.** Ein Klick startet die Analyse. Wenn eindeutige Unterlagen und Kennwerte vorliegen, erscheint unmittelbar die Kostenaufstellung. Die App schlägt Zuordnungen selbst vor. Bei einer Lücke fragt sie gezielt, etwa „Welche Höhe hat das Fenster F03?“. Bereits verwertbare Ergebnisse bleiben sichtbar.
3. **Ergebnis prüfen.** Oben stehen die Bauwerksorientierung mit Bandbreite und Quelle sowie die verwendete Gebäudekategorie. Die BGF- und BRI-Ergebnisse sind einzeln beschriftet. Darunter stehen die bepreisten Teilkosten nach KG und Bauteil mit der Zahl offener Positionen. Ein Klick auf **„Im Plan zeigen“** öffnet die markierte Fundstelle. Bei einer aus mehreren Zeichnungen berechneten Menge kann ich jeden verwendeten Beleg öffnen. Eine Korrektur rechnet alle betroffenen Mengen und Beträge neu.
4. **Ausgeben.** Einen kompakten Bericht über die Druckansicht als PDF speichern und die Positionen als CSV exportieren. Projekt, Planstand, erfasste Leistungen, Preisstand und offene Punkte sollen auch ohne geöffnete App verständlich sein.

## Welche Informationen die App gewinnt

| Quelle | Gesuchte Angaben | Verwendung |
|---|---|---|
| Grundriss | Bemaßte Gebäude- und Bauteilkonturen, Außenmaße, Wandabschnitte, Fenster- und Türpositionen, IDs, Geschosse, Materialhinweise | Grundflächen und Längen, Lage und Zahl der Öffnungen, Bezug zu den anderen Plänen |
| Ansicht | Fassadenseite, Öffnungsgrößen, Giebel, Materialwechsel und Grenzen der Bekleidung | Öffnungs- und Bekleidungsflächen je Fassadenseite |
| Schnitt | Höhenkoten, Traufe und First, Dachneigung, Überstände, Aufbau und Ausdehnung von Bodenplatte und Dach | Höhen aus Kotendifferenzen, geneigte Dachflächen, Zuordnung der tatsächlichen Bauteile |
| Legenden und Bauteilangaben | Material, Typ, Abmessungen und beschriebener Leistungsumfang | Auswahl eines fachlich passenden Kostenkennwerts |
| BKI Gebäude Neubau 2026 | Gebäudekategorie, Von-/Mittel-/Bis-Kennwerte, BGF und BRI als getrennte Bezugsgrößen | Kostenspanne für KG 300+400 aus der zum Plansatz passenden Gebäudekategorie |
| Eigener Preiskatalog oder eindeutig beschriftete Kostenangabe im Plan | Bauteil, Bezugsgröße, Preis, Quelle und Preisbasis | Eurobetrag. Bei einem Planpreis müssen Betrag und Leistung eindeutig zusammengehören. |

**Kern für den 4–5-Tage-Kurs:** Ein klar bemaßter, eingeschossiger Neubau mit digital erzeugten, gut lesbaren PDF-Plänen. Ermittle zuerst die belegbare BGF und bei ausreichend definierten Außenmaßen auch den BRI. Ermittle außerdem Bodenplattenfläche, Außenwandöffnungen, äußere Bekleidungsfläche und eine einfache Dachfläche, soweit die jeweiligen Bauteile im Plansatz belegt sind. Mindestens eine Menge muss Informationen aus zwei verschiedenen Zeichnungen verbinden. Ein regelmäßiges Flachdach ist der erste Abnahmefall. Einfaches Satteldach, Scans und komplexere Geschosse sind Erweiterungen nach bestandenem Kern. Bei einem anderen Gebäude darf die App belegte Positionen ausgeben und anspruchsvollere Geometrien zur Prüfung markieren.

## So muss die Auswertung arbeiten

**A · PDF lesen und lesbare Ausschnitte erzeugen.** Text samt Positionen direkt aus dem PDF gewinnen. Für jede Seite eine Vorschau erzeugen und dicht bemaßte Zeichnungen bei Bedarf zusätzlich in höherer Auflösung ausschneiden. Die Bilder zusammen mit relevantem PDF-Text an ein bildfähiges Modell geben. Pro Fundstelle Datei, Seite, Ansichtsbereich, Text oder Symbol und Markierungsrechteck speichern. Beim Zurückprojizieren der Markierung Ausschnitt, Auflösung und Seitendrehung berücksichtigen. Prüfe auch ein A1-Blatt mit mehreren Zeichnungen, wenn ein solches Testblatt vorliegt.

**B · Die KI liefert Beobachtungen.** Extrahiere beispielsweise „Grundriss EG: Außenmaß West–Ost 12,00 m“, „Schnitt A–A: Oberkante Bekleidung +3,00 m“ oder „Ansicht Süd: Öffnung F03 mit Breite und Höhe“. Fordere strukturierte Daten an und validiere sie mit einem Schema. Speichere Originalschreibweise, normalisierten Wert, Einheit, Bauteilbezug und Fundstelle. Bei unleserlichen Werten bleibt das Zahlenfeld leer. Ordne Maße der richtigen Maßkette zu. Eine Maßkette und ihr Gesamtmaß sind zwei Belege für dieselbe Länge. Maßangaben wie 1,50 m, 150 cm und 1.500 mm müssen einheitlich verarbeitet werden. Eine Brüstungshöhe ist keine Fensterhöhe.

**C · Quellen zusammenführen.** Ein Fenster kann im Grundriss, im Schnitt und in der Ansicht auftauchen. Speichere pro gebauter Öffnung einen Datensatz mit mehreren Belegen. Gleiche Geschoss, Fassadenseite und Lage bzw. Achse ab. Ein mehrfach verwendetes Typkürzel wie „F01“ kann mehrere Fenster bezeichnen. Mehrere gleichartige Fenster müssen als getrennte Vorkommen erhalten bleiben. Stimmen zwei Werte für dasselbe Maß nicht überein, zeige beide Fundstellen zur Auswahl. Bei widersprüchlichen Revisionsständen lasse den aktiven Stand festlegen. Wiederholtes Hochladen derselben Datei darf die Mengen nicht verdoppeln.

**D · Geometrie in Python berechnen.** Verwende nachvollziehbare Formeln und die zugehörigen Beleg-IDs. Eine gezeichnete Kontur darf nur metrisch vermessen werden, wenn der zugehörige Zeichnungsbereich kalibriert ist. Gedruckte Maßzahlen haben Vorrang. Ist die grafische Messung nötig, nutze eine eindeutig zugeordnete Referenzstrecke mit bekanntem Maß und eine unabhängige Kontrollstrecke, sofern vorhanden. Bei nur einem Referenzmaß bleibt die Messung prüfpflichtig. Unterschiedliche Maßstäbe auf einem Blatt getrennt behandeln. Aus dem Markierungsrechteck der KI allein darf keine Menge entstehen. Für den ersten Durchlauf genügen geschriebene Maße und eindeutige Regelgeometrien.

| Bauteil | Rechenregel und Anwendungsgrenze |
|---|---|
| Bodenplatte | Belegte Plattenkontur bzw. Plattenmaße verwenden. Nur bei im Plan nachgewiesener Deckungsgleichheit gilt Gebäudegrundfläche = Plattenfläche. |
| Fassadenbekleidung | Je belegtem Bekleidungsabschnitt Fläche ermitteln. Bei rechteckigen, vollständig bekleideten Fassaden gilt Länge × bekleidete Höhe abzüglich zugehöriger Öffnungen. Giebel, Sockel, Laibungen und Materialwechsel nur gemäß nachgewiesenem Umfang und Bezugsgröße ansetzen. |
| Fenster und Außentüren | Öffnungsmaße oder Stückzahl passend zum Kennwert. Bei rechteckiger Öffnung ist die Fläche Breite × Höhe. Öffnungsfläche und Glasfläche bleiben eigene Bezugsgrößen. |
| Dach | Tatsächliche belegte Dachgrenzen verwenden. Beim ebenen Testdach ohne Überstand entspricht die Dachfläche seiner horizontalen Projektion. Beim späteren geneigten Dach jede einfache Dachfläche mit horizontaler Projektionsfläche / cos(Neigung) bzw. mit belegter Schräglänge berechnen. |
| Weitere Positionen | Andere Bauteile dürfen mit belastbaren Mengen ergänzt werden. TGA, Gründungsausführung oder Materialqualität ohne Beleg erscheinen als offene Grundlagen. |

**E · Preise zuordnen und summieren.** Ein kleiner lokaler Katalog lässt sich einmal per CSV importieren oder in der App pflegen. Felder: Bauteiltyp, beschriebene Ausführung, KG, Leistung, Einheit, Bezugsgröße, gewählter Preis, Herkunft, Seite bzw. Beleg, Preisstand, brutto/netto und Regionalbezug. Bauteilpreise stammen aus passenden Einzelbelegen. Der fotografierte Gebäudeband stellt hierfür die gesonderte Bauwerksorientierung bereit. Wähle automatisch, wenn Typ, Ausführung, Einheit und Leistungsumfang eindeutig passen. Bei mehreren geeigneten Treffern zeige eine kurze Auswahl. Deckt ein kompletter Aufbau mehrere Schichten ab, verhindere deren doppelte Bepreisung. Die App zeigt die Gebäudeorientierung aus dem mitgelieferten BKI-Katalog in einem eigenen Ergebnisblock.

Eurobetrag = ermittelte Menge × zugeordneter Preis. Mit ungerundeten Mengen rechnen, den Positionsbetrag auf Cent runden und die gerundeten Positionen einmal summieren. Einheitliche Preisbasis verwenden. Fehlende Preise, Mengen oder ungeklärte Widersprüche sind **offen**. Für die einzeln bepreisten Positionen heißt das Ergebnis etwa **„Bepreiste Teilkosten · KG 300“**. Zeige die berücksichtigten und die offenen Leistungen. Berechne keine Gesamtprojektkosten aus einem lückenhaften Plansatz. Die mitgelieferten fiktiven Preise sind ausschließlich für das Demoprojekt. Ein echter Upload verwendet den ausgewählten Projektkatalog und weist fehlende Werte aus.

## Gebäudeorientierung mit dem vorhandenen BKI-Band

**Verfügbare Quelle.** BKI *Baukosten Gebäude Neubau 2026 – Statistische Kostenkennwerte*. Die sechs fotografierten Übersichten zeigen Bauwerkskosten für **KG 300 + 400 zusammen**. Die goldenen Balken beziehen sich auf m² Brutto-Grundfläche (BGF), die blauen auf m³ Brutto-Rauminhalt (BRI). Linker Rand, roter Strich und rechter Rand stehen für Von-, Mittel- und Bis-Wert. **Preisbasis aller sechs Seiten: 1. Quartal 2026, Bundesdurchschnitt Deutschland, brutto einschließlich 19 % MwSt.** Die Streuung beschreibt die Vergleichsobjekte. Sie ist keine Kostengarantie und keine statistische Aussage zur Genauigkeit der Planerkennung.

**Vom Plan zum Gebäudewert.** Lies eine eindeutig bezeichnete BGF-/BRI-Berechnung mit passendem Planstand bevorzugt als Beleg. Alternativ summiere für einfache geschlossene Neubauten die aus den Grundrissen belegten Bruttoflächen der relevanten Ebenen. Ermittle den BRI aus den Außenkonturen und den zugehörigen vertikalen Begrenzungen im Schnitt. Keller, Rücksprünge, Dachräume und Lufträume bei der Zuordnung einzeln prüfen. Sind die nötigen Maße offen, zeige nur den belegbaren Rechenweg. Wohnfläche, NUF, Dachfläche, Bodenplattenfläche und bekleidete Fassadenhöhe haben jeweils andere Bezugsgrenzen. Prüfe Bezeichnung und Geometrie, bevor eine Menge als BGF oder BRI in die Rechnung eingeht.

**Gebäudekategorie.** Leite einen Vorschlag aus Projektbezeichnung, Nutzung, Bauweise und erkennbaren Merkmalen ab. Die Zuordnung bleibt editierbar. Je nach Kategorie sind Standard, Unterkellerung, Wohneinheiten, Mischnutzung oder Hallenanteil entscheidend. Das Buch führt z. B. bei Mehrfamilienhäusern sowohl „bis zu 6 WE“ als auch „6 bis 19 WE“ auf. Bei genau sechs Einheiten eine Auswahl anbieten. Bei Holzbauweise prüfen, ob sie für die konkrete Gebäudeart als eigene Vergleichskategorie ausgewiesen ist. Bauteile aus Holz allein bestimmen die Bauweise des Gebäudes nicht. Für den Entwurf am Klosterareal ist „Gemeindezentren – Holzbauweise“ ein Vorschlag für den **Neubau des Gemeindehauses**. Die bestehende Scheune, Wohnbauten und Freianlagen haben eigene Projektumfänge.

| Rechnung | Darstellung in der App |
|---|---|
| BGF × jeweiliger Kennwert in €/m² BGF | Bauwerksorientierung KG 300+400 mit Von-, Mittel- und Bis-Wert, Preisstand und beiden Belegen für Menge und Kennwert |
| BRI × jeweiliger Kennwert in €/m³ BRI | Eigenständige Vergleichsrechnung für denselben Bauwerksumfang. In einem hohen Gemeindesaal kann sie anders ausfallen. |
| Bauteilmenge × preislich und fachlich passender Bauteilkennwert | Bepreiste Teilkosten der tatsächlich erfassten Leistungen. Fehlende Einzelpreise bleiben offen. |

**Eine Summe pro Rechenweg.** Beide Gebäudeansätze repräsentieren dasselbe Bauwerk. Sie werden weder addiert noch automatisch gemittelt. Die belegten Bauteilkosten werden daneben gezeigt. Eine prozentuale Budgetabweichung ist nur zwischen Werten mit vergleichbarem Leistungsumfang und Preisstand sinnvoll. Eine Aufteilung in KG 300 und KG 400 bzw. deren Untergruppen erfordert passende Tabellenwerte. Allein aus dem gemeinsamen Diagrammbalken lässt sie sich nicht gewinnen. Grundstück, Außenanlagen, Baunebenkosten und andere Leistungen außerhalb KG 300+400 gehören nicht zu diesem Kennwert.

**Region und Steuer.** Ohne belegten Regionalfaktor lautet die Ausgabe „Bundesdurchschnitt“. Bei Wahl von Bersenbrück ist die Zeile **Landkreis Osnabrück** der Ausgabe 2026 maßgeblich. Ein belegter Faktor wird auf den Bundeskennwert genau einmal angewendet und mit Quelle gespeichert. Eine Nettoansicht derselben Bruttopreise ergibt sich durch Division durch 1,19. Stelle den ursprünglichen Preisstand weiterhin dar. Eine Indexfortschreibung braucht gesondert belegte Eingabewerte.

**Gebäudedaten einlesen.** Verwende den CSV-Block im Anhang als sofort verfügbaren lokalen Startkatalog. Er enthält alle 87 grafisch dargestellten Kategorien. Die Werte sind am **lokalen Achsenraster auf Höhe der jeweiligen Zeile** aus Balken und Mittelstrich abgelesen. Sie wurden auf **100 €/m² BGF** bzw. **25 €/m³ BRI** gerundet. Zeige bei der Verwendung „ca. · aus BKI-Übersicht grafisch abgelesen“. So lässt sich auch mit einem echten Plan eine erste Größenordnung liefern. In der Anzeige die daraus errechneten Gebäudebeträge sinnvoll runden, etwa auf Tausend Euro. Bewahre die ungerundeten Rechenergebnisse für Tests und den Abgleich mit späteren Eingaben auf.

Speichere je Wert Kategorie, Bezugsgröße, KG-Umfang, Von/Mittel/Bis, Ausgabe, Übersichtsseite, Beginn des Detailkapitels, Kostenstand, Regionalbezug, Steuerbasis und Erfassungsart. Unterscheide `grafisch_gerundet` und `tabellarisch_belegt`. Ist später eine gedruckte Zahlentabelle eingepflegt, erhält sie für die gleiche Kategorie, Bezugsgröße und Preisbasis Vorrang. Bereits gespeicherte Projekte behalten ihren verwendeten Kennwert samt Herkunft, bis der Nutzer eine Aktualisierung übernimmt. Ein leeres Von-/Bis-Feld bedeutet „im Foto nicht auflösbar“. Es ist kein Nullpreis.

## Welche Buchseiten die Auswertung belegen

| Foto | Inhalt und Verwendung |
|---|---|
| IMG_0469 | Titel und Ausgabe. Die Illustration auf dem Einband zeigt beispielhaft 1.460 €/m² BGF und 405 €/m³ BRI. Die Zuordnung zu einer Gebäudeart ist dort nicht ausgewiesen. Die Titelillustration bleibt außerhalb des Katalogs. |
| IMG_0470 | Inhaltsverzeichnis und Erläuterungen. Musterseiten ab S. 56 für Bauwerkskennwerte, S. 58 für KG der 1. und 2. Ebene, S. 60 für KG 700, S. 62 für STLB-Anteile, S. 64 für Flächen und Rauminhalte nach DIN 277, S. 66 für Objektübersichten und S. 68 für die Standardeinordnung. Weitere Hinweise ab S. 70 und 74. Außerdem Kapitel zu Verwaltung, Forschung und Lehre. |
| IMG_0471 | Detailkapitel zu Gesundheit, Schulen, Kindergärten, Sportbauten sowie Ein- und Zweifamilienhäusern und Doppel-/Reihenendhäusern. Standard, Holzbau, Passivhausstandard und Unterkellerung stehen je nach Typ als eigene Kategorien im Verzeichnis. |
| IMG_0472 | Reihen- und Mehrfamilienhäuser nach Standard und WE, Wohnhäuser nach Mischnutzung, Seniorenwohnen, Beherbergung, Gastronomie, Produktion und Handel. Die Startseiten sind in den Datenzeilen hinterlegt. |
| IMG_0473 | Lager, Garagen, Bereitschaftsdienste sowie Kultur und Religion. Gemeindezentren: Standardeinordnung ab S. 1072, einfache Ausführung ab 1076, mittlere ab 1082, hohe ab 1096, Holzbauweise ab **1108**. Sakralbauten beginnen ab 1118. Kapitel 8 „Bauwerke für technische Zwecke“ hat auf diesen Diagrammseiten keine eigene Datenzeile. BKI-NHK ab S. 1137 bilden einen separaten Buchteil. Regionalfaktoren Deutschland ab **1144**, Österreich/Europa ab 1148. |
| IMG_0474 · S. 152 / IMG_0477 · S. 156 | Gleiche 28 Kategorien. Büro, Forschung, Gesundheit, Schulen, Kitas, Sport sowie Ein- und Zweifamilienhäuser mit bzw. ohne Keller. Erstes Foto BGF, zweites BRI. |
| IMG_0475 · S. 153 / IMG_0478 · S. 157 | Gleiche 30 Kategorien. Weitere Wohngebäude, Mischnutzung, Seniorenwohnen und Beherbergung. Erstes Foto BGF, zweites BRI. |
| IMG_0476 · S. 154 / IMG_0479 · S. 158 | Gleiche 29 Kategorien. Gewerbe, Lager, Garagen, Bereitschaftsdienste, Kultur und religiöse Bauten einschließlich aller vier Gemeindezentrum-Kategorien. Erstes Foto BGF, zweites BRI. |

Für den nächsten Präzisionsschritt beim Gemeindehaus genügen ein Foto der **Zahlentabelle ab S. 1108** mit Tabellenkopf und Fußnote sowie bei gewünschter Ortsanpassung die Zeile für den **Landkreis Osnabrück** ab S. 1144. Die zugehörige Tabelle der 1. und 2. KG-Ebene ist zusätzlich für eine Aufgliederung hilfreich. Für bauteilspezifische Einheitspreise kommen getrennte Belege wie Angebote, projektspezifische Bürokennwerte oder der BKI-Band *Bauelemente Neubau* infrage.

## Minimaler technischer Aufbau

Für ein neues Repository verwende **Python, Streamlit, PyMuPDF, Pydantic und das offizielle Anthropic-Python-SDK**. Speichere den Projektstand und die zugehörigen Pläne lokal. Bei einem schon geeigneten Projekt passe dich dessen Stack an. Claude Code baut die App. Die laufende App verwendet für die automatische visuelle Erkennung einen separat konfigurierten Modellzugang. Im Python-Aufbau kommen API-Schlüssel und bildfähiges Modell aus ANTHROPIC_API_KEY und ANTHROPIC_MODEL auf dem Server. Dokumentiere die Einrichtung und mache vor dem Start der Analyse sichtbar, dass die ausgewählten Planausschnitte an Anthropic übertragen werden. Den BKI-Preiskatalog verarbeitet die App lokal.

Halte den Code in vier überschaubaren Bereichen: PDF-Aufbereitung, Erkennung, Mengen-/Kostenlogik und Oberfläche. Die Erkennung gibt Beobachtungen zurück. Die Rechenlogik akzeptiert nur definierte Operationen und strukturierte Zahlen. Speichere für jede Ergebnisposition die Kette **Preisquelle → Menge und Formel → Einzelmaße → Planfundstellen**. Korrigierte Rohmaße bleiben mit ihrem ursprünglichen Beleg verknüpft. Nutze einen Cache pro Dokumentinhalt, Ansicht und Analysekonfiguration, damit das Neuberechnen eines Betrags keinen neuen Modellaufruf auslöst. Bei API-Fehlern kann genau der betroffene Schritt erneut ausgeführt werden.

Ohne Schlüssel soll ein ausdrücklich markierter Demomodus mit gespeichertem Erkennungsergebnis die Rechen- und Bedienlogik demonstrieren. Bei einem eigenen Upload muss die App den verfügbaren Funktionsumfang ehrlich zeigen. Als „Live-Planauswertung getestet“ gilt nur ein Durchlauf über den echten Upload und die echte Erkennung. Eine vorgefüllte Demo allein erfüllt die Abnahme nicht.

## Abnahmetest mit überprüfbaren Sollwerten

Erzeuge für die Entwicklung ein kleines **gezeichnetes** PDF-Planset aus Grundriss, Ansichten und Schnitt. Das ist ein künstlicher Testbau und kein Aufmaß meines Gemeindehauses. Zeichne Außenmaßketten, Öffnungen, Höhenkoten, Orientierung, Achsen sowie die Bauteilbeschriftungen. Platziere die benötigten Angaben auf fachlich passenden Blättern. Der Grundriss liefert Außenlängen und Positionen, die Ansichten liefern Öffnungshöhen und den Bekleidungsumfang, der Schnitt die bekleidete Höhe und die Dach-/Plattenabgrenzung. Der Plansatz enthält keine fertige Mengentabelle und keine Eurobeträge.

**Testgeometrie.** Rechteck 12,00 × 8,00 m, durchgehende äußere Holzbekleidung von ±0,00 bis +3,00 m, sechs Fensteröffnungen je 1,50 × 1,20 m und eine Außentüröffnung 1,00 × 2,10 m. Bodenplatte und ebenes Dach sind deckungsgleich mit der Außenkontur, ohne Überstand. Im Test werden Laibungen und Anschlüsse nicht gesondert erfasst. Ein Fenster ist in mehreren Zeichnungen zu sehen, zwei Öffnungen verwenden das gleiche Typkürzel. Die fünf **fiktiven Bruttopreise** liegen als separater Testkatalog vor.

| Position | Aus dem Plansatz herzuleitende Menge | Testpreis | Erwarteter Betrag |
|---|---:|---:|---:|
| KG 322 · Bodenplatte | 12 × 8 = 96,00 m² Plattenfläche | 180 €/m² | 17.280 € |
| KG 334 · sechs Fenster | 6 × 1,50 × 1,20 = 10,80 m² Öffnungsfläche | 650 €/m² | 7.020 € |
| KG 334 · Außentür | 1 Stück | 900 €/Stück | 900 € |
| KG 335 · äußere Bekleidung | 2 × (12 + 8) × 3 − 10,80 − 2,10 = 107,10 m² | 120 €/m² | 12.852 € |
| KG 363 · Dachbelag | 12 × 8 = 96,00 m² Dachfläche | 85 €/m² | 8.160 € |
| **Bepreiste Teilkosten** | **5 Positionen** | | **46.212 €** |

**Pflichttests.**

- Gleichen Plansatz erneut hochladen. Die Summe bleibt bei 46.212 €.
- Im zweiten gezeichneten Plansatz die bekleidete Höhe auf 3,50 m ändern. Die neue Datei erhält einen anderen Dateinamen und darf über denselben Upload eingelesen werden. Das Ergebnis muss auf 127,10 m² Bekleidung und insgesamt 48.612 € steigen. Erwartete Testwerte dürfen nicht in der Erkennungslogik hinterlegt sein.
- Den Kennwert für Fenster entfernen. Die Fenster bleiben mit 10,80 m² in der Mengenliste. Die bepreiste Summe sinkt auf 39.192 €, die Fensterposition erscheint als offen und die Bekleidungsfläche bleibt korrekt.
- Zwei unterschiedliche Höhenkoten für dieselbe Oberkante im gleichen Planstand vorgeben. Die betroffene Bekleidung wird prüfpflichtig. Nach Auswahl der richtig belegten Kote aktualisieren sich Menge, Betrag und Bericht.
- Mindestens einen bislang unbekannten, vom Nutzer bereitgestellten Plansatz durch den normalen Upload schicken, sobald er verfügbar ist. Für drei Mengen die automatische Herleitung samt Fundstellen mit einer Handrechnung vergleichen. Abweichungen und ihre Ursache protokollieren. Wenn noch kein eigener Plan oder API-Zugang vorliegt, den Live-Test als ausstehend ausweisen.

**Abnahme der Gebäudeorientierung.** Separater Rechentest mit fiktiven, bereits geprüften Mengen von 100 m² BGF und 450 m³ BRI. Für „Gemeindezentren – Holzbauweise“ sind aus S. 154 ungefähr 2.700 / 3.500 / 4.400 €/m² und aus S. 158 ungefähr 625 / 775 / 1.025 €/m³ ablesbar. Bei Bundesdurchschnitt und Bruttopreisen erwartet der Test intern 270.000 / 350.000 / 440.000 € über BGF und 281.250 / 348.750 / 461.250 € über BRI. Beide Ausgaben tragen „ca.“. Beim Entfernen des BRI bleibt die BGF-Auswertung verfügbar. Die Bauteil-Demosumme von 46.212 € wird keiner der beiden Berechnungen zugeschlagen. Prüfe außerdem, dass ein fehlender Von-/Bis-Wert leer bleibt und dass ein später explizit übernommener Tabellenwert die grafische Näherung für genau die passende Bezugsgröße ersetzt.

## Reihenfolge für den WPK

| Zeitpunkt | Lieferfähiger Zwischenstand |
|---|---|
| Tag 1 | Upload, PDF-Vorschau und **erster echter Erkennungstest** für ein Maß aus dem Grundriss und eine Kote aus dem Schnitt. Vor anderen Oberflächenarbeiten prüfen, ob beide Fundstellen im richtigen Ausschnitt landen. |
| Tag 2 | Beobachtungen über die drei Planarten verbinden. BGF und belegbaren BRI aus den Plänen ermitteln, die BKI-Gebäudeorientierung anzeigen und die Fundstellen für die Mengen verknüpfen. |
| Tag 3 | Bauteilmengen herleiten, Doppelzählungen prüfen, passende Einzelpreise zuordnen und offene Grundlagen korrigierbar machen. Beide Rechenwege mit ihren Sollwerten prüfen. |
| Tag 4 | Praxisplansatz prüfen, PDF-Druckansicht und CSV fertigstellen, Startanleitung schreiben und Vorführung proben. |
| Tag 5, falls verfügbar | Die häufigste Schwachstelle aus dem Praxisversuch verbessern. Je nach Ergebnis z. B. mehrteilige Planlayouts, Satteldächer oder schlecht lesbare Maßketten bearbeiten. |

**Fertigstellung.** Liefere lauffähigen Quellcode, Abhängigkeiten, eine kurze README mit Startbefehl, das künstliche PDF-Planset, die aus dem Anhang erzeugte Datei bki_gebaeude_neubau_2026.csv und den getrennten Bauteil-Testkatalog. Führe Rechentests und, sofern Zugang vorhanden ist, die Live-Erkennung durch. Berichte separat, welche Ergebnisse automatisch aus echten Uploads gewonnen wurden, welche im Demomodus geprüft sind und welche Eingaben noch gebraucht werden.

## Technische und fachliche Referenzen

- [Anthropic · Analyse von PDF-Dokumenten](https://platform.claude.com/docs/en/build-with-claude/pdf-support)
- [Anthropic · Bilder und visuelle Erkennung](https://platform.claude.com/docs/en/build-with-claude/vision)
- [PyMuPDF · Vektorzeichnungen in PDF-Dateien](https://pymupdf.readthedocs.io/en/latest/recipes-drawing-and-graphics.html)
- [BKI · Verlagsinhaltsverzeichnis Gebäude Neubau 2026](https://bki-files.de/downloads/baukosten/2026/2026_T1_Inhalt.pdf)
- [BKI · Einordnung der Regionalfaktoren](https://bki.de/faq)
- [BKI · Beispiel für die Struktur der Bauelement-Kennwerte](https://bki-files.de/downloads/baukosten/2026/2026_T2_Muster.pdf)
- [BKI · Bildkommentar zu den Mengen und Bezugseinheiten](https://bki-files.de/downloads/bildkommentar/Leseprobe_BKI_Bildkommentar_DIN276_DIN277.pdf)

## Eingebetteter Startkatalog für Claude Code

Schreibe den folgenden UTF-8-CSV-Block unverändert als **bki_gebaeude_neubau_2026.csv** ins Projekt und lade ihn beim Start. Er enthält 87 Gebäudekategorien und je zwei kennwertbasierte Auswertungen. Für alle Zeilen gilt die oben beschriebene gemeinsame Preisbasis. Die Spalten bgf_* sind €/m² BGF, die Spalten bri_* sind €/m³ BRI. Detailseite bezeichnet den Kapitelbeginn zum Nachschlagen. diagrammseite_bgf und diagrammseite_bri bezeichnen die tatsächliche grafische Quelle. Leere Felder als fehlend einlesen. Die Fotos werden zur Laufzeit für diesen Katalog nicht benötigt.

```csv
gebaeudekategorie;detailseite_ab;diagrammseite_bgf;diagrammseite_bri;bgf_von;bgf_mittel;bgf_bis;bri_von;bri_mittel;bri_bis
Büro und Verwaltung – einfacher Standard;164;152;156;1500;1800;2200;450;550;700
Büro und Verwaltung – mittlerer Standard;170;152;156;2300;2900;3600;625;775;975
Büro und Verwaltung – hoher Standard;192;152;156;2800;3500;4600;775;950;1200
Büro und Verwaltung – Holzbauweise;206;152;156;2400;3400;4700;575;875;1175
Instituts- und Laborgebäude;216;152;156;3200;4400;5800;725;975;1275
Medizinische Einrichtungen;232;152;156;2500;3100;3900;675;825;975
Pflegeheime;246;152;156;2200;2800;3600;650;800;975
Erholungsgebäude;260;152;156;3400;4200;5200;725;1075;1425
Allgemeinbildende Schulen;268;152;156;2500;3000;3600;575;725;875
Schulen – Holzbauweise;286;152;156;2300;3100;3800;600;725;900
Berufliche Schulen;296;152;156;2300;2800;3700;550;725;925
Förder- und Sonderschulen;304;152;156;2400;2800;3500;575;700;875
Weiterbildungseinrichtungen;312;152;156;2800;3300;4300;625;800;975
Kindergarten ohne Keller – einfacher Standard;326;152;156;1800;2300;2800;500;600;725
Kindergarten ohne Keller – mittlerer Standard;334;152;156;2500;3000;3700;625;775;975
Kindergarten ohne Keller – hoher Standard;356;152;156;2600;3300;4000;650;800;975
Kindergarten ohne Keller – Holzbauweise;368;152;156;2700;3300;4200;650;800;1000
Kindergarten mit Keller;390;152;156;2600;3100;3600;700;800;975
Sport- und Mehrzweckhallen;400;152;156;2500;3000;3800;400;500;650
Sporthallen – Einfeldhallen;410;152;156;2500;3000;3600;400;475;650
Sporthallen – Dreifeldhallen;420;152;156;2000;2700;3400;275;375;500
Schwimmhallen;432;152;156;3500;4200;5000;675;800;1050
Ein- und Zweifamilienhäuser mit Keller – einfacher Standard;444;152;156;1300;1400;1500;500;525;550
Ein- und Zweifamilienhäuser mit Keller – mittlerer Standard;450;152;156;1800;2100;2400;575;650;750
Ein- und Zweifamilienhäuser mit Keller – hoher Standard;462;152;156;2100;2500;3300;650;800;1025
Ein- und Zweifamilienhäuser ohne Keller – einfacher Standard;484;152;156;1300;1500;1800;500;550;575
Ein- und Zweifamilienhäuser ohne Keller – mittlerer Standard;490;152;156;1900;2300;2800;575;700;825
Ein- und Zweifamilienhäuser ohne Keller – hoher Standard;510;152;156;2200;2700;3400;700;850;1050
Ein- und Zweifamilienhäuser – Passivhausstandard Massivbau;524;153;157;1900;2100;2500;575;675;750
Ein- und Zweifamilienhäuser – Passivhausstandard Holzbau;536;153;157;1900;2300;2700;625;750;850
Ein- und Zweifamilienhäuser in Holzbauweise – mit Keller;550;153;157;2000;2500;3200;650;775;1025
Ein- und Zweifamilienhäuser in Holzbauweise – ohne Keller;566;153;157;2100;2700;3800;675;850;1125
Doppel- und Reihenendhäuser – einfacher Standard;586;153;157;1100;1300;1400;425;475;550
Doppel- und Reihenendhäuser – mittlerer Standard;592;153;157;1600;1800;2000;525;625;700
Doppel- und Reihenendhäuser – hoher Standard;600;153;157;1800;2100;2500;625;700;850
Doppel- und Reihenendhäuser – Holzbauweise;608;153;157;1700;2100;3000;575;700;950
Reihenhäuser – einfacher Standard;620;153;157;;1200;;375;425;450
Reihenhäuser – mittlerer Standard;626;153;157;1500;1700;2000;500;550;700
Reihenhäuser – hoher Standard;634;153;157;1900;2200;2900;600;700;875
Mehrfamilienhäuser bis zu 6 WE – einfacher Standard;646;153;157;1200;1300;1500;400;500;550
Mehrfamilienhäuser bis zu 6 WE – mittlerer Standard;652;153;157;1600;1900;2400;575;650;775
Mehrfamilienhäuser bis zu 6 WE – hoher Standard;662;153;157;1900;2300;2900;625;800;1050
Mehrfamilienhäuser mit 6 bis 19 WE – einfacher Standard;680;153;157;1300;1500;1800;475;525;625
Mehrfamilienhäuser mit 6 bis 19 WE – mittlerer Standard;688;153;157;1500;1900;2300;500;625;775
Mehrfamilienhäuser mit 6 bis 19 WE – hoher Standard;706;153;157;1800;2200;2900;625;725;950
Mehrfamilienhäuser ab 20 WE – einfacher Standard;724;153;157;1300;1500;1600;450;500;525
Mehrfamilienhäuser ab 20 WE – mittlerer Standard;732;153;157;1700;1900;2100;550;625;725
Mehrfamilienhäuser ab 20 WE – hoher Standard;750;153;157;2000;2300;2700;625;750;875
Mehrfamilienhäuser – Passivhäuser;760;153;157;1600;2000;2400;550;625;700
Mehrfamilienhäuser – Holzbauweise;770;153;157;1800;2300;2800;575;725;900
Wohnhäuser bis 15 % Mischnutzung – einfacher Standard;786;153;157;1500;1600;1700;;525;
Wohnhäuser bis 15 % Mischnutzung – mittlerer Standard;792;153;157;1600;1900;2300;525;600;700
Wohnhäuser bis 15 % Mischnutzung – hoher Standard;802;153;157;2100;2500;3200;625;775;900
Wohnhäuser mit mehr als 15 % Mischnutzung;814;153;157;1900;2400;3000;600;725;900
Seniorenwohnungen – mittlerer Standard;832;153;157;1700;2200;3200;575;675;925
Seniorenwohnungen – hoher Standard;842;153;157;1600;2300;2700;575;700;775
Wohnheime und Internate;850;153;157;2100;2500;3100;625;775;950
Hotels;866;153;157;2400;2900;3500;750;900;1025
Gaststätten, Kantinen und Mensen;874;154;158;3100;4000;5200;700;925;1150
Industrielle Produktionsgebäude – Massivbauweise;888;154;158;1500;2000;2400;225;325;450
Industrielle Produktionsgebäude – überwiegend Skelettbauweise;896;154;158;1700;2300;3200;225;375;575
Betriebs- und Werkstätten – eingeschossig;906;154;158;1400;2200;3100;275;450;800
Betriebs- und Werkstätten – mehrgeschossig, geringer Hallenanteil;914;154;158;1700;2400;3800;375;525;775
Betriebs- und Werkstätten – mehrgeschossig, hoher Hallenanteil;924;154;158;1400;1900;2500;200;350;500
Geschäftshäuser mit Wohnungen;934;154;158;2000;2400;3400;575;700;850
Geschäftshäuser ohne Wohnungen;942;154;158;1800;2500;3300;550;725;875
Verbrauchermärkte;948;154;158;1600;1900;2500;275;325;400
Autohäuser;956;154;158;1900;2100;2300;425;450;575
Lagergebäude ohne Mischnutzung;962;154;158;800;1300;1900;125;225;350
Lagergebäude bis 25 % Mischnutzung;974;154;158;1000;1400;1800;125;200;325
Lagergebäude mit mehr als 25 % Mischnutzung;982;154;158;1500;1900;2300;200;350;475
Einzel- und Doppelgaragen;990;154;158;500;900;1200;200;350;450
Mehrfachgaragen;996;154;158;900;1500;2200;200;375;575
Hochgaragen;1002;154;158;700;900;1200;225;300;400
Fahrradparkhäuser;1008;154;158;1300;2500;3200;250;550;625
Carports;1014;154;158;700;1100;1600;250;375;550
Tiefgaragen;1020;154;158;1200;1500;1900;375;475;600
Feuerwehrhäuser;1026;154;158;2300;3000;3800;525;650;850
Öffentliche Bereitschaftsdienste;1044;154;158;1900;2500;3300;300;475;800
Bibliotheken, Museen und Ausstellungen;1052;154;158;2900;4100;6000;625;925;1250
Theater;1066;154;158;3400;4600;5800;750;875;1000
Gemeindezentren – einfacher Standard;1076;154;158;1800;2100;2500;375;500;550
Gemeindezentren – mittlerer Standard;1082;154;158;2500;3300;4400;650;775;950
Gemeindezentren – hoher Standard;1096;154;158;3100;3700;4200;650;825;975
Gemeindezentren – Holzbauweise;1108;154;158;2700;3500;4400;625;775;1025
Sakralbauten;1118;154;158;3300;4000;4500;650;750;925
Friedhofsgebäude;1124;154;158;2800;3900;5400;575;825;1175
```
