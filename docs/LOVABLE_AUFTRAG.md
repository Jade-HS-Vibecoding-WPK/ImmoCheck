# Auftrag für Lovable: Kaufklar

Referenz: `docs/index.html` in diesem Repository ist eine voll funktionierende Einzeldatei (HTML, CSS, JavaScript) mit der gesamten Oberfläche und allen Berechnungen. Baue die App in React, TypeScript und Tailwind **genau so nach**: gleiche Rechenwege, gleiche Texte, gleiches Design. Lies die Datei zuerst vollständig. Ersetze nur die Teile, die in der Einzeldatei provisorisch sind (siehe „Was zu ersetzen ist“).

## Ziel
Web-App für Immobilien-Käufer. Man legt Objekte an (Kaufangebote oder Bestand), bekommt pro Objekt ein Urteil (Kaufen, Nur mit Verhandlung, Nicht kaufen) mit Begründung, rechnet Sanierung, Stresstest und Ertrag, vergleicht Objekte und überblickt den Bestand im Portfolio. Alles auf Deutsch.

## Was zu ersetzen ist
1. **Konten:** In der Einzeldatei gibt es lokale Konten im Browser (Passwort als Hash in localStorage). Ersetze das durch echte Anmeldung mit E-Mail und Passwort über Supabase Auth: Registrieren, Anmelden, Abmelden, Passwort ändern, Passwort vergessen (E-Mail-Link), Konto löschen. Passwort mindestens 8 Zeichen.
2. **Daten:** Statt localStorage Supabase-Datenbank. Jeder Nutzer sieht nur seine eigenen Daten (Row Level Security auf `user_id = auth.uid()`).
3. **Export und Import** der Objekte als JSON (gibt es in der Einzeldatei unter „Konto“) beibehalten.

## Datenmodell (Supabase)
- `objects`: `id uuid`, `user_id uuid`, `name text`, `status text` (angebot oder bestand), `data jsonb` (alle Eingabefelder, siehe unten), `checklist jsonb`, `renovation jsonb`, `created_at`, `updated_at`
- `comparisons`: `id`, `user_id`, `object_id`, `overrides jsonb` (Werte, die nur im Vergleich geändert wurden), `position int`
- Berechnete Werte werden nicht gespeichert, sondern immer aus `data` berechnet.

### Eingabefelder (`data`)
Angebot: `name`, `stat`, `kp` (Kaufpreis), `wf` (Wohnfläche), `mist` (Ist-Miete €/m² Monat), `ek` (Eigenkapital), `zi` (Zins %), `ti` (Tilgung %), `san` (Sanierung €).
Objektdaten: `typ`, `adr`, `ort`, `bj`, `we` (Wohneinheiten), `mj`, `zim`, `gesch`, `gf` (Grundstück m²), `hz`, `ekl`, `zst`, `kel`, `stp`.
Miete und Kosten: `lee` (Leerstand und Mietausfall %), `verw` (€ pro Einheit und Jahr), `ihr` (Instandhaltung €/m² und Jahr), `hg` (Hausgeld nicht umlagefähig €/Monat, nur bei Eigentumswohnung), `vgl` (Vergleichspreis €/m²).
Kauf: `bl` (Bundesland), `grest`, `not`, `mak` (je %).
Finanzierung: `zb` (Zinsbindung Jahre), `dis` (Disagio %), `geb` (Gebühr %).
Prognose und Ziele: `hd` (Haltedauer), `ms` (Mietsteigerung % p. a.), `ws` (Wertentwicklung % p. a.), `zr` (Ziel-Nettorendite), `zirr` (Ziel-Eigenkapitalrendite).
Sonderfälle (jeweils mit Schalter, Felder erst bei „ja“ sichtbar): Erbbaurecht `erb`, `ebz`, `ebl`, `eba`. Ertragswert `ewon`, `bw`, `lz`, `rnd`. Steuerwirkung `steu`, `st`, `gs`, `afa`.
Bestand (nur bei Status Bestand): `kj` (Kaufjahr), `mw` (Marktwert), `zbj` (Zinsbindung bis Jahr).
Standardwerte: `lee 5`, `verw 300`, `ihr 12`, `not 2`, `mak 3,57`, `zi 3,8`, `ti 2`, `zb 10`, `hd 10`, `ms 1,5`, `ws 1`, `zr 4`, `zirr 6`, `eba 1,5`, `lz 3`, `rnd 50`, `st 30`, `gs 80`, `afa 2`, `we 1`. Die Grunderwerbsteuer wird aus dem Bundesland vorbelegt (BW 5, BY 3,5, BE 6, BB 6,5, HB 5, HH 5,5, HE 6, MV 6, NI 5, NW 6,5, RP 5, SL 6,5, SN 5,5, ST 5, SH 6,5, TH 5) und bleibt änderbar. Zahlen im deutschen Format eingeben und anzeigen (Komma als Dezimalzeichen, Punkt als Tausender).

## Rechenlogik (Referenz `model()` in `docs/index.html`)
- Nebenkostensatz `nk = (grest + not + mak) / 100`. Gesamtinvestition `ges = kp * (1 + nk) + san`.
- Jahresmiete `jm = wf * mist * 12`. Leerstand und Ausfall `jm * lee / 100`.
- Kosten `= verw * we + ihr * wf + hg * 12 + Erbbauzins`. Reinertrag `rein = jm - Leerstand - Kosten`.
- Nettorendite `rein / ges`. Bruttorendite `jm / ges`. Faktor `ges / jm`.
- Darlehen `dar = max(0, ges - ek)`. Kapitaldienst `kd = dar * (zi + ti) / 100`. Cashflow pro Monat `(rein - kd) / 12`.
- Zinsdeckung `rein / (dar * zi / 100)`. Kapitaldienstdeckung `rein / kd`.
- Eigenkapitalrendite (IRR): Jahr 0 `-min(ek, ges)`. Jahr y: `(jm - Leerstand) * (1 + ms)^(y-1) - (Kosten - Erbbau) - Erbbau * (1 + eba)^(y-1) - kd`. Restschuld `bal = bal * (1 + zi) - kd`. Im letzten Jahr plus Erlös `Wert * (1 - 0,02) - Restschuld` mit `Wert = (kp + san) * (1 + ws)^hd`, bei Erbbaurecht mal `max(0, (Restlaufzeit - hd) / Restlaufzeit)`. IRR per Intervallhalbierung.
- Höchstpreis für die Zielrendite: `(rein / zr - san) / (1 + nk)`.
- Effektivzins: Rate `dar * (zi + ti) / 1200` pro Monat über `zb * 12` Monate, Auszahlung `dar * (1 - (dis + geb) / 100)`, Restschuld am Ende, IRR der Monatsflüsse, `(1 + r)^12 - 1`.
- Ertragswert (nur bei Schalter): `Bodenwert = bw * gf` (bei Erbbau 0), `Gebäudeertrag = rein - Bodenwert * lz`, `Vervielfältiger = (1 - (1 + lz)^-rnd) / lz`, `Ertragswert = Gebäudeertrag * Vervielfältiger + Bodenwert`.
- Steuer (nur bei Schalter): AfA-Basis `kp * (1 + nk) * gs / 100 + san`, AfA `Basis * afa / 100`, zu versteuern `jm - Leerstand - Kosten - Zinsen Jahr 1 - AfA`, Steuer `* st / 100`.
- Stresstest: sechs Szenarien (Basis, Zins +1, Zins +2, Miete -10 %, Leerstand +5 Punkte, alles zusammen) mit Nettorendite, Cashflow, IRR. Kipppunkte (Cashflow gleich null) für Zins, Miete, Kaufpreis und Leerstand per Intervallhalbierung.
- Sanierung: Position `Menge * Preis` (bei Einheit „pauschal“ nur Preis). Summe, plus Unvorhergesehenes % (10), plus Baunebenkosten % (15) auf die Summe inkl. Unvorhergesehenes, minus Förderung. Der Knopf „In die Kaufberechnung übernehmen“ setzt `san`. Keine Preise vorgeben, nur Mengen und Einheiten von Vorlagen (Dach, Fassade, Fenster, Heizung, Bad usw.).
- Portfolio (nur Status Bestand): Restschuld heute = Darlehensverlauf über `aktuelles Jahr - kj` Jahre. Wert `= mw` oder `kp + san`. Nettovermögen `Wert - Restschuld`. Beleihung `Restschuld / Wert`. Summen, gewichtete Nettorendite `Σ rein / Σ ges`, Warnungen bei negativem Cashflow, Beleihung über 80 %, Zinsbindung endet in höchstens zwei Jahren, Cashflow negativ bei Zins plus 2 %.
- Urteil: Kriterien Nettorendite gleich oder über Ziel, Cashflow größer gleich null, IRR gleich oder über Ziel, Reinertrag deckt Zinsen (Zinsdeckung mindestens 1), optional Preis pro m² höchstens 105 % des Vergleichspreises. Alle erfüllt: Kaufen. Höchstens zwei verfehlt, mindestens eines erfüllt und Höchstpreis über 70 % des Kaufpreises: Nur mit Verhandlung. Sonst Nicht kaufen.
- Eingabeprüfung: Kaufpreis und Fläche größer 0, Miete und Eigenkapital nicht negativ, Prozentfelder (Leerstand, Zins, Tilgung, Steuern, Gebühren, Steuersatz, Gebäudeanteil, AfA) zwischen 0 und 100. Bei Fehlern „Bitte Eingaben prüfen“ mit Liste statt Zahlen.

## Seiten und Navigation (wie in der Einzeldatei)
- Anmeldeseite (Anmelden, Registrieren).
- Dashboard: Kennzahlen, Filter (Alle, Angebote, Im Bestand), Objektkarten mit Urteil und drei Zahlen, „In den Bestand“, „Zum Vergleich“, Löschen mit Zwei-Klick-Bestätigung (kein Browser-Dialog), Karte „Neues Objekt“.
- Portfolio.
- Objekte vergleichen: Objekte aus dem Dashboard auswählen, „Letzte 3 Objekte hinzufügen“, Eingaben direkt änderbar (nur für den Vergleich, gelb markiert, Zurücksetzen, als neues Objekt speichern), Ergebnisse mit Balken in einer Tabelle mit fester Spaltenbreite, nichts darf versetzt sein.
- Konto: Passwort ändern, Export, Import, Konto löschen.
- Pro Objekt: Kaufberechnung (Urteil, fünf Kennzahlen, Angebot, Objektdaten), Annahmen (fünf aufklappbare Gruppen plus Bestand), Sanierungsrechner, Analyse (weitere Kennzahlen, Ertragsrechnung, Zinsdeckung, Stresstest, Kaufpreis-Sensitivität, Grafik, Jahresverlauf), Checkliste (16 Prüfpunkte mit Status offen, geklärt, Problem und Notiz).
- Bericht als PDF per Druckansicht: Deckblatt mit Grunddaten und Urteil, Kennzahlen und Stresstest, Sanierung, Verlauf und Annahmen, offene Punkte.

## Design
Heller Grauton als Hintergrund, weiße Karten mit großen Rundungen, schwarze Hauptknöpfe, linke weiße Navigationskarte mit schwarzer aktiver Pille, dunkle Karte „Bericht erstellen“ unten links, erste Kennzahl-Karte schwarz. Schrift ohne Serifen. **Keine Emojis**, nur schlichte Linien-Icons. Positive Ergebnisse dick grün (`#17a34a`), negative dick rot (`#dc2626`). Hell- und Dunkelmodus. Auf dem Handy wird die Navigation zu einer schmalen, seitlich scrollbaren Leiste.
**Ausrichtung:** Alle Formularzeilen in einem Raster mit fester Beschriftungshöhe (zwei Zeilen) und gleich hohen Feldern. Keine Versätze, auch in Tabellen nicht.

## Qualitätsregeln
- Nie NaN, Infinity oder „undefined“ anzeigen. Ungültige Eingaben abfangen.
- Keine Browser-Dialoge (`alert`, `confirm`), stattdessen Meldungen und Zwei-Klick-Bestätigung.
- Hinweise zu Annahmen und „keine Anlage-, Rechts- oder Steuerberatung“ beibehalten.
- Nach dem Bau mit dem Beispielobjekt prüfen: Kaufpreis 330.000, Fläche 240, Miete 8,50, Eigenkapital 100.000, Zins 3,8, Tilgung 2, Einheiten 1. Erwartung: Gesamtinvestition 364.881 €, Nettorendite 5,50 %, Cashflow 393 € pro Monat, Eigenkapitalrendite 9,6 %, Zinsdeckung 1,99, Urteil Kaufen.

## Später (nicht jetzt bauen)
Objekt per Link oder Text anlegen (Inserat auslesen), Suchprofile mit E-Mail-Benachrichtigung, automatische Vorbewertung eingehender Inserate. Kein Massen-Crawling von Portalen wegen Nutzungsbedingungen und Rechtslage.
