"""Baukostentool: Kostenaufstellung nach DIN 276 aus Architekturplänen (PDF).

Vier Bereiche:
- ``pdf_prep``      PDF-Aufbereitung (Text mit Positionen, Vorschauen, Ansichtsbereiche, Ausschnitte)
- ``recognition``   Erkennung (liefert ausschließlich Beobachtungen mit Fundstellen)
- ``merge`` / ``quantities`` / ``costs``  Mengen- und Kostenlogik
- ``app.py``        Oberfläche (Streamlit)
"""

__version__ = "0.1.0"
