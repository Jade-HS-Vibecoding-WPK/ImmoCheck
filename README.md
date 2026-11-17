# Baukostentool

Pläne (PDF) hochladen → auswerten → BKI-Orientierung KG 300+400 (BGF/BRI) und bepreiste Bauteile nach DIN 276, jede Zahl mit Fundstelle.

## Start
    ./start.command        # oder: .venv/bin/streamlit run app.py
Optional KI-Erkennung: `.env.example` nach `.env` kopieren und ANTHROPIC_API_KEY eintragen. Ohne Schlüssel: lokale Auswertung digitaler PDFs und Demomodus.

## Tests
    .venv/bin/python -m pytest tests
Testpläne: `plaene/`, erzeugt mit `scripts/testplaene.py`. Demo-Daten: `scripts/demo_erzeugen.py`.

## Status
- Getestet: Rechenlogik mit allen Sollwerten (46.212 €, 48.612 €, 39.192 €, Widerspruch, BKI), echter Upload über die App mit lokaler Erkennung.
- Nicht getestet: Live-KI-Erkennung (kein API-Schlüssel), eigener unbekannter Plansatz.
