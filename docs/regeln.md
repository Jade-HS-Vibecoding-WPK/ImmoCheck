# Regeln und Formate (Nachschlagen bei Bedarf)

## Inhalt
1. BGF und BRI nach DIN 277: was die Skripte rechnen und was du selbst ablesen musst
2. Mengenregeln der Bauteile (DIN 276)
3. Format des Bauteil-Preiskatalogs
4. Grenzen der lokalen Planerkennung

## 1. BGF und BRI (DIN 277)
- **BGF** (Brutto-Grundfläche) ist die Summe der Grundflächen aller Grundrissebenen, gemessen an den äußeren
  Maßen der Baukonstruktion in Höhe des Fußbodens, einschließlich Putz und Bekleidung.
- **BRI** (Brutto-Rauminhalt) ist der Rauminhalt des Baukörpers, nach unten begrenzt durch die Unterfläche
  der Bauwerkssohle (UK Bodenplatte), nach oben durch die Dachhaut (OK Dachbelag).
- **Was das Skript automatisch kann:** ein Geschoss mit rechteckiger Außenkontur und Flachdach.
  Dann gilt BGF = Lx × Ly und BRI = BGF × (OK Dach − UK Bodenplatte). Steht im Plan eine eindeutig
  bezeichnete Angabe wie „BGF = 96,00 m²“, wird sie als weiterer Beleg geführt. Weichen Angabe und Rechnung
  voneinander ab, entsteht ein Widerspruch, den du dem Nutzer vorlegst.
- **Was du selbst ablesen musst:** mehrere Geschosse, Keller, Dachgeschoss, L- oder U-Formen, Rücksprünge,
  geneigte Dächer. Das Skript lässt den Wert in diesen Fällen bewusst offen.
  - Mehrere Geschosse: BGF = Summe je Ebene, jede Ebene aus ihrem eigenen Grundriss.
    Ein Luftraum zählt nicht, ein Kellergeschoss zählt mit.
  - Zusammengesetzte Grundrisse: in Rechtecke zerlegen und jedes Teilrechteck mit seinen Maßketten belegen.
  - Geneigtes Dach: BRI = Grundfläche × Traufhöhe + Dachkörper (Satteldach: ½ × Breite × (First − Traufe) × Länge),
    Höhen jeweils ab UK Bodenplatte.
  - Den Rechenweg legst du offen und lässt ihn bestätigen. Danach übergibst du die Werte mit
    `--setze bgf=… --setze bri=… --notiz "…"`.
- **Keine Ersatzwerte:** NUF, NRF, Wohnfläche und Raumflächen sind keine BGF. Fehlt ein Maß, frag nach,
  statt es zu schätzen.

## 2. Mengenregeln der Bauteile
| Bauteil (KG) | Menge | Voraussetzung |
|---|---|---|
| Bodenplatte (322) | Lx × Ly | Plan belegt „bündig/deckungsgleich mit Außenkontur“, sonst „prüfen“ |
| Fenster (334) | Σ Breite × Höhe, Rohbaumaß | Höhe ist die Fensterhöhe, nicht die Brüstungshöhe |
| Außentür (334) | Stück (zusätzlich m²) | |
| Äußere Bekleidung (335) | je bekleideter Fassade: Länge × (OK − UK Bekleidung) − Öffnungen | Koten aus Schnitt bzw. Ansicht, Fassaden belegt |
| Dachbelag (363) | Flachdach: Projektion; geneigt: Projektion / cos(Neigung) | Dachform belegt |

Dieselbe Öffnung in Grundriss, Ansicht und Schnitt wird nur einmal gezählt. Die Zuordnung läuft über die Fassade,
die Lage und das Typkürzel. Gleiche Typkürzel an verschiedenen Stellen bleiben getrennte Öffnungen.

## 3. Bauteil-Preiskatalog (CSV, Semikolon, UTF-8)
Spalten: `id;bauteiltyp;ausfuehrung;kg;leistung;einheit;bezugsgroesse;preis;herkunft;beleg;preisstand;brutto_netto;region;umfasst;kennwert_art;aktiv`
- `bauteiltyp`: `bodenplatte`, `fenster`, `aussentuer`, `fassadenbekleidung` oder `dachbelag`
- `einheit`: `m²`, `Stk`, `m³` oder `m`. `preis` mit Dezimalkomma, z. B. `650,00`.
- `brutto_netto`: `brutto` oder `netto`. Alle Positionen eines Katalogs brauchen dieselbe Basis, sonst prüft das Skript.
- `umfasst`: Schichten mit Komma getrennt, z. B. `abdichtung,daemmung,dachbelag`. Damit wird eine doppelte
  Bepreisung derselben Schicht erkannt.
- `aktiv`: `ja` oder `nein`.
Beispiel: `assets/` enthält keinen echten Katalog. Den Aufbau zeigt `data/katalog/testkatalog.csv` (fiktive Preise).
Will der Nutzer Preise nennen, z. B. „Fenster 650 €/m²“, legst du daraus eine CSV in diesem Format an und
übergibst sie mit `--katalog`.

## 4. Grenzen der lokalen Planerkennung
- Sie braucht PDFs mit Textebene und Vektorlinien, wie sie Archicad, Vectorworks oder Revit exportieren.
  Scans und Fotos liefern keine Werte. Dann liest du selbst (Abschnitt 1).
- Sie erkennt Zeichnungen am Titel („Grundriss EG“, „Ansicht Süd“, „Schnitt A-A“), Maßketten mit
  Maßhilfslinien, Höhenkoten mit Bezug („OK Dach“, „UK Bodenplatte“ …), Öffnungen mit Typkürzel (F01, T01)
  und Bauteilbeschriftungen. Unbeschriftete Koten bleiben ohne Bezug.
- Einen Planstand („Index a“, „Index b“) liest sie aus dem Plankopf. Bei mehreren Ständen wird der neueste
  vorgeschlagen. Mit `--stand` legst du einen anderen fest.
