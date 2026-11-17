# Baukostentool

Pläne (PDF) hochladen → auswerten → BKI-Orientierung KG 300+400 (BGF/BRI) und bepreiste Bauteile nach DIN 276, jede Zahl mit Fundstelle.

## Start (Mac und Windows)
- **Mac:** Doppelklick auf `start.command` (beim ersten Mal Rechtsklick → Öffnen).
- **Windows:** Doppelklick auf `start.bat`.

Beim ersten Start wird alles automatisch eingerichtet (Python 3.9+ nötig). Danach öffnet sich das Tool im Browser unter http://localhost:8501. Das Fenster offen lassen, Schließen beendet das Tool.

## Lokale KI (ohne API-Schlüssel, Pläne verlassen den Rechner nicht)
Einmalig einrichten (ca. 6 GB Platz, 16 GB RAM genügen):
1. Ollama von https://ollama.com/download laden und installieren (App starten, sie läuft dann im Hintergrund).
2. Im Terminal das Bildmodell laden: `ollama pull qwen2.5vl:7b`
3. Tool starten. In der Seitenleiste steht „Lokale KI bereit“, unter ② ist „Lokale KI (Ollama)“ vorausgewählt.

Anderes Modell: `OLLAMA_MODEL=...` in `.env` (siehe `.env.example`). Die Auswertung dauert je Zeichnung einige Minuten.
Optional zusätzlich: Anthropic-API mit `ANTHROPIC_API_KEY` in `.env`.

## Tests
    .venv/bin/python -m pytest tests
Testpläne: `plaene/`, erzeugt mit `scripts/testplaene.py`. Demo-Daten: `scripts/demo_erzeugen.py`.

## Status
- Getestet: Rechenlogik mit allen Sollwerten (46.212 €, 48.612 €, 39.192 €, Widerspruch, BKI), echter Upload über die App mit lokaler Erkennung.
- Lokale KI: Ablauf mit Ersatz-Server getestet (Schema, Rückprojektion, Fehlerpfad). Mit echtem Modell noch nicht, Ollama war hier nicht installiert.
- Nicht getestet: Anthropic-API, eigener unbekannter Plansatz.
