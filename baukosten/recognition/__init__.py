"""Erkennung: liefert ausschließlich Beobachtungen (``ViewResult``) mit Fundstellen, keine Mengen.

Verfahren:
- ``ki``     Bildmodell von Anthropic (Ausschnitte + PDF-Text, strukturierte Ausgabe, Schema-Validierung)
- ``lokal``  regelbasierte Auswertung von PDF-Textebene und Vektorzeichnung (ohne KI, nur digitale PDFs)
- ``demo``   gespeichertes Erkennungsergebnis (ausdrücklich markierter Demomodus)
"""
