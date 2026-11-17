"""Einheitliche Verarbeitung von Maßangaben (1,50 m = 150 cm = 1.500 mm).

Alle Längen werden intern in Metern geführt. Die Originalschreibweise bleibt
immer erhalten; ``parse_measure`` liefert zusätzlich, ob die Einheit sicher ist.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_UNIT_FACTORS = {"m": 1.0, "cm": 0.01, "mm": 0.001}

# Hochgestellte Ziffern (z. B. 1,01⁵ = 1,015 m in deutscher Bemaßung)
_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

_NUM_RE = re.compile(
    r"""^\s*
    (?P<sign>[+\-−–±]|\+/-)?\s*
    (?P<num>\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)
    (?P<sup>[⁰¹²³⁴⁵⁶⁷⁸⁹])?
    \s*(?P<unit>mm|cm|m)?\s*$""",
    re.VERBOSE,
)


@dataclass(frozen=True)
class ParsedMeasure:
    raw: str
    value_m: float | None  # normalisierter Wert in m (bzw. Zahl ohne Einheit)
    unit: str  # "m", "cm", "mm" oder "unbekannt"
    unit_explicit: bool
    signed: bool  # Höhenkote mit Vorzeichen (±0,00 / +3,00 / -0,25)

    @property
    def ok(self) -> bool:
        return self.value_m is not None


def _to_float(num: str, sup: str | None) -> tuple[float, int]:
    """Wandelt eine deutsch oder englisch geschriebene Zahl um. Liefert (Wert, Nachkommastellen)."""
    s = num.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        # 1.500 oder 1.500,5 -> Tausenderpunkt
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    decimals = len(s.split(".")[1]) if "." in s else 0
    if sup:
        s = s + sup.translate(_SUPERSCRIPT) if "." in s else s + "." + sup.translate(_SUPERSCRIPT)
        decimals += 1
    return float(s), decimals


def parse_measure(raw: str | None, default_unit: str = "m") -> ParsedMeasure:
    """Normalisiert eine Maßangabe.

    Regeln:
    - Explizite Einheit (m, cm, mm) gewinnt immer.
    - Ohne Einheit: Dezimalzahl mit Komma/Punkt (``1,50``) gilt als ``default_unit`` (Meter).
    - Ohne Einheit und ohne Nachkommastellen (``150``) ist die Einheit unsicher -> "unbekannt",
      der Wert bleibt leer und muss über die Maßkette oder vom Nutzer bestätigt werden.
    - Unleserliches bleibt leer (value_m = None).
    """
    if raw is None:
        return ParsedMeasure("", None, "unbekannt", False, False)
    text = raw.strip().translate(str.maketrans({" ": " ", " ": " "}))
    m = _NUM_RE.match(text)
    if not m:
        return ParsedMeasure(raw, None, "unbekannt", False, False)
    sign = m.group("sign")
    value, decimals = _to_float(m.group("num"), m.group("sup"))
    if sign in ("-", "−", "–"):
        value = -value
    unit = m.group("unit")
    if unit:
        return ParsedMeasure(raw, round(value * _UNIT_FACTORS[unit], 6), unit, True, bool(sign))
    if re.fullmatch(r"\d{1,3}(?:[.\s]\d{3})+", m.group("num")):
        # "1.500" ohne Einheit: Tausenderpunkt, Einheit unklar
        return ParsedMeasure(raw, None, "unbekannt", False, bool(sign))
    if decimals > 0:
        # Dezimalschreibweise ohne Einheit -> Standard-Einheit der Zeichnung (m)
        return ParsedMeasure(raw, round(value * _UNIT_FACTORS[default_unit], 6), default_unit, False, bool(sign))
    if value == 0:
        return ParsedMeasure(raw, 0.0, default_unit, False, bool(sign))
    return ParsedMeasure(raw, None, "unbekannt", False, bool(sign))


def format_de(value: float | None, decimals: int = 2, unit: str = "") -> str:
    """Deutsche Zahlendarstellung, z. B. 46.212,00."""
    if value is None:
        return "–"
    s = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {unit}".strip()


def format_eur(value: float | None) -> str:
    return "offen" if value is None else format_de(value, 2, "€")


def looks_like_measure(text: str) -> bool:
    return _NUM_RE.match(text.strip()) is not None


KOTE_RE = re.compile(r"^\s*(±|\+/-|[+\-−–])\s?\d+[.,]\d{2,3}\s*(m)?\s*$")


def looks_like_kote(text: str) -> bool:
    return KOTE_RE.match(text) is not None


_QTY_RE = re.compile(r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)\s*(m²|m2|qm|m³|m3|cbm)?", re.I)


def parse_quantity(raw: str | None) -> tuple[float | None, str | None]:
    """Flächen-/Rauminhaltsangabe lesen, z. B. „BGF = 96,00 m²“ -> (96.0, "m²"). Letzte Zahl im Text."""
    if not raw:
        return None, None
    hits = list(_QTY_RE.finditer(raw.replace("\u00a0", " ")))
    if not hits:
        return None, None
    m = hits[-1]
    num = m.group(1)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", num):
        num = num.replace(".", "").replace(",", ".")
    else:
        num = num.replace(",", ".")
    unit = (m.group(2) or "").lower()
    unit = "m²" if unit in ("m²", "m2", "qm") else "m³" if unit in ("m³", "m3", "cbm") else None
    return float(num), unit
