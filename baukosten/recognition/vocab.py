"""Gemeinsames Fachvokabular für Koten, Öffnungen und Bauteile."""
from __future__ import annotations

import re

LEVEL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ok_bekleidung", re.compile(r"\b(ok|oberkante)\s*(fassaden)?(bekleidung|verkleidung|schalung|fassade)", re.I)),
    ("uk_bekleidung", re.compile(r"\b(uk|unterkante)\s*(fassaden)?(bekleidung|verkleidung|schalung|fassade)", re.I)),
    ("ok_attika", re.compile(r"\b(ok|oberkante)\s*attika", re.I)),
    ("ok_dach", re.compile(r"\b(ok|oberkante)\s*(dachbelag|dachhaut|dach\b|dachabdichtung|kies)", re.I)),
    ("ok_bodenplatte", re.compile(r"\b(ok|oberkante)\s*(bodenplatte|rohboden|rfb|rohfu(ß|ss)boden|sohle)", re.I)),
    ("uk_bodenplatte", re.compile(r"\b(uk|unterkante)\s*(bodenplatte|sohle|sohlplatte)", re.I)),
    ("ok_fertigfussboden", re.compile(r"\b(ok\s*ff(b)?|okff|ok\s*fertigfu(ß|ss)boden|fertigfu(ß|ss)boden)\b", re.I)),
    ("ok_rohdecke", re.compile(r"\b(ok|oberkante)\s*(roh)?decke", re.I)),
    ("traufe", re.compile(r"\btraufe\b", re.I)),
    ("first", re.compile(r"\bfirst\b", re.I)),
    ("gelaende", re.compile(r"\bgel(ä|ae)nde\b", re.I)),
]

LEVEL_HINT_RE = re.compile(r"\b(ok|uk|oberkante|unterkante|okff|ffb|rfb|attika|first|traufe|gelände)\b", re.I)


def level_refs(text: str) -> list[str]:
    refs = [ref for ref, rx in LEVEL_PATTERNS if rx.search(text)]
    return refs or (["sonstige"] if text.strip() else [])


OPENING_LABEL_RE = re.compile(r"^(?:Pos\.?\s*)?(FT|TF|FE|F|T|TÜ|AT|HT)\s?-?\s?(\d{1,3}[a-z]?)$", re.I)


def opening_kind(label: str) -> str:
    u = label.upper().replace(" ", "")
    if u.startswith(("FT", "TF")):
        return "fenstertuer"
    if u.startswith(("T", "AT", "HT")):
        return "tuer"
    if u.startswith("F"):
        return "fenster"
    return "unbekannt"


SILL_RE = re.compile(r"^(?:BRH|BR|Brüstung(?:shöhe)?)\s*[:=]?\s*(.+)$", re.I)

COMPONENT_PATTERNS = {
    "bodenplatte": re.compile(r"bodenplatte|sohlplatte|fundamentplatte|bodenplatte", re.I),
    "dach": re.compile(r"flachdach|satteldach|pultdach|walmdach|\bdach\s*:|dachaufbau", re.I),
    "bekleidung": re.compile(r"bekleidung|verkleidung|schalung|fassadenbekleidung", re.I),
}
FLUSH_RE = re.compile(r"bündig|deckungsgleich|ohne\s+(dach)?überstand|kein(en)?\s+(dach)?überstand", re.I)
OVERHANG_RE = re.compile(r"(dach)?überstand\s*[:=]?\s*(\d+(?:[.,]\d+)?\s*(?:m|cm|mm)?)", re.I)
PITCH_RE = re.compile(r"(?:dn|dachneigung|neigung)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*°", re.I)
ALL_AROUND_RE = re.compile(r"umlaufend|allseitig|ringsum", re.I)
ROOF_FORM_RE = {"flachdach": re.compile(r"flachdach", re.I), "satteldach": re.compile(r"satteldach", re.I),
                "pultdach": re.compile(r"pultdach", re.I)}
PRICE_RE = re.compile(r"€|\bEUR\b|\beuro\b", re.I)

AREA_LABEL_RE = re.compile(r"^\s*(BGF|BRI|NUF|NRF|WFL|Wohnfl(?:ä|ae)che|Brutto-?Grundfl(?:ä|ae)che|Brutto-?Rauminhalt)\b", re.I)


def area_kind(label: str) -> str:
    l = label.lower()
    if l.startswith(("bgf", "brutto-grund", "bruttogrund")):
        return "bgf"
    if l.startswith(("bri", "brutto-raum", "bruttoraum")):
        return "bri"
    if l.startswith("nuf"):
        return "nuf"
    if l.startswith("nrf"):
        return "nrf"
    if l.startswith(("wfl", "wohnfl")):
        return "wohnflaeche"
    return "sonstige"
