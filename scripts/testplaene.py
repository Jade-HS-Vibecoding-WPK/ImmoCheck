"""Erzeugt den künstlichen, gezeichneten Testplansatz (Grundriss, Ansichten, Schnitt) als PDF.

Das ist ein Testbau für die Entwicklung, kein Aufmaß eines echten Gebäudes. Die Pläne enthalten
nur Zeichnung, Maßketten, Höhenkoten und Beschriftungen, keine Mengentabelle und keine Eurobeträge.
Die erwarteten Mengen stehen nirgends in der Erkennungslogik, sie ergeben sich nur aus der Zeichnung.

Aufruf:
    python scripts/testplaene.py                         # Standardsatz in plaene/
    python scripts/testplaene.py --hoehe 3,50 --index b --out plaene/Testbau_Index-b.pdf
    python scripts/testplaene.py --kote-sued +3,10 --out plaene/Testbau_Widerspruch.pdf
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pymupdf

S = 340.2 / 12.0  # Punkte je Meter (M 1:100 auf A3)
BLACK = (0, 0, 0)
GREY = (0.45, 0.45, 0.45)
WOOD = (0.55, 0.35, 0.15)
PAGE = (1191, 842)  # A3 quer in pt
FONT = "helv"


def de(x: float, sign: bool = False) -> str:
    s = f"{abs(x):.2f}".replace(".", ",")
    if not sign:
        return s
    if abs(x) < 1e-9:
        return "±0,00"
    return ("+" if x > 0 else "-") + s


@dataclass
class Params:
    hoehe: float = 3.00          # OK Attika / OK Bekleidung über ±0,00
    platte: float = 0.25         # Dicke Bodenplatte (UK = -platte)
    index: str = "a"
    datum: str = "10.11.2026"
    kote_sued: str | None = None  # abweichende Beschriftung der Oberkante in Ansicht Süd (Widerspruchstest)

    @property
    def dach_ok(self) -> float:
        return round(self.hoehe - 0.20, 2)

    @property
    def stand(self) -> str:
        return f"Index {self.index} vom {self.datum}"


class Sheet:
    def __init__(self, doc: pymupdf.Document, p: Params, inhalt: str, nr: str):
        self.page = doc.new_page(width=PAGE[0], height=PAGE[1])
        self.p = p
        self._frame(inhalt, nr)

    # ---- Grundelemente ---------------------------------------------------------------
    def line(self, a, b, w=0.3, color=BLACK, dashes=None):
        sh = self.page.new_shape()
        sh.draw_line(a, b)
        sh.finish(width=w, color=color, dashes=dashes)
        sh.commit()

    def rect(self, r, w=0.6, color=BLACK, fill=None):
        sh = self.page.new_shape()
        sh.draw_rect(pymupdf.Rect(*r))
        sh.finish(width=w, color=color, fill=fill)
        sh.commit()

    def text(self, x, y, s, size=6.5, rotate=0):
        self.page.insert_text((x, y), s, fontsize=size, fontname=FONT, rotate=rotate, color=BLACK)

    def width(self, s, size=6.5):
        return pymupdf.get_text_length(s, fontname=FONT, fontsize=size)

    def _frame(self, inhalt: str, nr: str):
        self.rect((20, 20, 1171, 822), w=0.8)
        self.rect((871, 672, 1171, 822), w=0.6)
        for y in (695, 714, 733, 752, 771, 790, 809):
            self.line((871, y), (1171, y), w=0.25, color=GREY)
        rows = [("Projekt:", "Testbau WPK (künstlicher Testbau)"), ("Bauherr:", "· Übungsprojekt ·"),
                ("Planinhalt:", inhalt), ("Plan-Nr.:", nr), ("Maßstab:", "1:100"), ("Format:", "A3"),
                ("Planstand:", self.p.stand)]
        for i, (k, v) in enumerate(rows):
            y = 690 + 19 * i
            self.text(877, y, k, size=7)
            self.text(941, y, v, size=7.5)

    # ---- Bemaßung ----------------------------------------------------------------------
    def _tick(self, x, y):
        self.line((x - 2.2, y + 2.2), (x + 2.2, y - 2.2), w=0.6)

    def hchain(self, x0: float, y: float, meters: list[float], ext_to: float):
        """Waagrechte Maßkette ab x0 (Punkte) mit Einzelmaßen in m. ext_to = y, bis zu dem die Hilfslinien laufen."""
        xs = [x0]
        for m in meters:
            xs.append(xs[-1] + m * S)
        self.line((xs[0] - 4, y), (xs[-1] + 4, y), w=0.35)
        for x in xs:
            self._tick(x, y)
            y_far = y - 3 if ext_to < y else y + 3
            self.line((x, y_far), (x, ext_to), w=0.2, color=GREY)
        for a, b, m in zip(xs, xs[1:], meters):
            s = de(m)
            self.text((a + b) / 2 - self.width(s) / 2, y - 2.0, s)

    def vchain(self, x: float, y0: float, meters: list[float], ext_to: float):
        """Senkrechte Maßkette ab y0 nach unten. Text gedreht (von unten lesbar), links der Maßlinie."""
        ys = [y0]
        for m in meters:
            ys.append(ys[-1] + m * S)
        self.line((x, ys[0] - 4), (x, ys[-1] + 4), w=0.35)
        for y in ys:
            self._tick(x, y)
            x_far = x + 3 if ext_to > x else x - 3
            self.line((x_far, y), (ext_to, y), w=0.2, color=GREY)
        for a, b, m in zip(ys, ys[1:], meters):
            s = de(m)
            self.text(x - 2.0, (a + b) / 2 + self.width(s) / 2, s, rotate=90)

    def kote(self, x: float, y: float, value: str, label: str, text_left: bool):
        sh = self.page.new_shape()
        sh.draw_polyline([(x, y), (x - 3.5, y - 5), (x + 3.5, y - 5), (x, y)])
        sh.finish(width=0.3, color=BLACK, fill=BLACK, closePath=True)
        sh.commit()
        self.line((x - 12, y), (x + 12, y), w=0.3)
        if text_left:
            self.text(x - 6 - self.width(value), y - 6, value)
            self.text(x - 6 - self.width(label, 6), y + 7.5, label, size=6)
        else:
            self.text(x + 6, y - 6, value)
            self.text(x + 6, y + 7.5, label, size=6)


# ----------------------------------------------------------------------------------------
# Testgebäude: 12,00 × 8,00 m, sechs Fenster 1,50 × 1,20 (BRH 0,90), eine Tür 1,00 × 2,10
# ----------------------------------------------------------------------------------------
LX, LY = 12.0, 8.0
SUED = [("F01", 1.50), ("F01", 5.25), ("F02", 9.00)]   # Abstand ab Westecke
NORD = [("F03", 2.00), ("F04", 8.50)]                  # Abstand ab Westecke
WEST = [("T01", 3.50, 1.00)]                           # Abstand ab Nordecke
OST = [("F05", 3.25)]                                  # Abstand ab Nordecke
FB, FH, BRH = 1.50, 1.20, 0.90
TB, TH = 1.00, 2.10


def _chain(total: float, starts: list[float], w: float) -> list[float]:
    out, pos = [], 0.0
    for s in sorted(starts):
        out += [round(s - pos, 2), w]
        pos = s + w
    out.append(round(total - pos, 2))
    return out


def grundriss(doc, p: Params):
    sh = Sheet(doc, p, "Grundriss EG", "TB-101")
    x0, y0 = 330.0, 230.0
    x1, y1 = x0 + LX * S, y0 + LY * S
    t = 0.30 * S
    sh.rect((x0, y0, x1, y1), w=1.4)
    sh.rect((x0 + t, y0 + t, x1 - t, y1 - t), w=0.9)

    def window_h(xa, ya, yb, label, label_y):
        xb = xa + FB * S
        sh.rect((xa, ya, xb, yb), w=0, color=None, fill=(1, 1, 1))
        sh.line((xa, ya), (xa, yb), w=0.6)
        sh.line((xb, ya), (xb, yb), w=0.6)
        sh.line((xa, ya + t * 0.4), (xb, ya + t * 0.4), w=0.3)
        sh.line((xa, ya + t * 0.6), (xb, ya + t * 0.6), w=0.3)
        sh.text((xa + xb) / 2 - sh.width(label, 7) / 2, label_y, label, size=7)
        sh.text((xa + xb) / 2 - sh.width(f"BRH {de(BRH)}", 5.5) / 2, label_y + 7.5, f"BRH {de(BRH)}", size=5.5)

    for lab, a in SUED:
        window_h(x0 + a * S, y1 - t, y1, lab, y1 - t - 10)
    for lab, a in NORD:
        window_h(x0 + a * S, y0, y0 + t, lab, y0 + t + 16)
    # Ost: Fenster in senkrechter Wand
    for lab, a in OST:
        ya, yb = y0 + a * S, y0 + (a + FB) * S
        sh.rect((x1 - t, ya, x1, yb), w=0, color=None, fill=(1, 1, 1))
        sh.line((x1 - t, ya), (x1, ya), w=0.6)
        sh.line((x1 - t, yb), (x1, yb), w=0.6)
        sh.line((x1 - t * 0.6, ya), (x1 - t * 0.6, yb), w=0.3)
        sh.line((x1 - t * 0.4, ya), (x1 - t * 0.4, yb), w=0.3)
        sh.text(x1 - t - 32, (ya + yb) / 2 - 2, lab, size=7)
        sh.text(x1 - t - 38, (ya + yb) / 2 + 6, f"BRH {de(BRH)}", size=5.5)
    # West: Außentür mit Aufschlag
    for lab, a, w in WEST:
        ya, yb = y0 + a * S, y0 + (a + w) * S
        sh.rect((x0, ya, x0 + t, yb), w=0, color=None, fill=(1, 1, 1))
        sh.line((x0, ya), (x0 + t, ya), w=0.6)
        sh.line((x0, yb), (x0 + t, yb), w=0.6)
        shp = sh.page.new_shape()
        r = w * S
        shp.draw_line((x0 + t, ya), (x0 + t + r, ya))
        shp.draw_bezier((x0 + t + r, ya), (x0 + t + r, ya + 0.55 * r), (x0 + t + 0.55 * r, yb), (x0 + t, yb))
        shp.finish(width=0.3, color=GREY)
        shp.commit()
        sh.text(x0 + t + 20, (ya + yb) / 2 + 2, lab, size=7)
    # Maßketten
    sh.hchain(x0, y1 + 28, _chain(LX, [a for _, a in SUED], FB), y1 + 2)
    sh.hchain(x0, y1 + 52, [LX], y1 + 30)
    sh.hchain(x0, y0 - 26, _chain(LX, [a for _, a in NORD], FB), y0 - 2)
    sh.hchain(x0, y0 - 50, [LX], y0 - 28)
    sh.vchain(x0 - 28, y0, _chain(LY, [a for _, a, _w in WEST], TB), x0 - 2)
    sh.vchain(x0 - 52, y0, [LY], x0 - 30)
    sh.vchain(x1 + 34, y0, _chain(LY, [a for _, a in OST], FB), x1 + 2)
    sh.vchain(x1 + 58, y0, [LY], x1 + 36)
    # Schnittlinie A-A (durch F02/F04)
    xs = x0 + 9.40 * S
    sh.line((xs, y0 - 70), (xs, y1 + 70), w=0.6, dashes="[6 2 1 2] 0")
    sh.line((xs, y0 - 70), (xs - 14, y0 - 70), w=0.9)
    sh.line((xs, y1 + 70), (xs - 14, y1 + 70), w=0.9)
    sh.text(xs + 4, y0 - 66, "A", size=9)
    sh.text(xs + 4, y1 + 74, "A", size=9)
    # Raum, Nordpfeil, Titel
    sh.text((x0 + x1) / 2 - sh.width("Mehrzweckraum", 8) / 2, (y0 + y1) / 2 - 3, "Mehrzweckraum", size=8)
    nrf = (LX - 0.6) * (LY - 0.6) - 0.0
    s_nrf = f"NRF {de(nrf)} m²"
    sh.text((x0 + x1) / 2 - sh.width(s_nrf) / 2, (y0 + y1) / 2 + 8, s_nrf)
    nx, ny = x1 + 110, y0 - 50
    shp = sh.page.new_shape()
    shp.draw_polyline([(nx, ny), (nx - 6, ny + 24), (nx, ny + 18), (nx + 6, ny + 24), (nx, ny)])
    shp.finish(width=0.4, color=BLACK, fill=BLACK, closePath=True)
    shp.draw_circle((nx, ny + 14), 15)
    shp.finish(width=0.4, color=BLACK)
    shp.commit()
    sh.text(nx - 3, ny - 6, "N", size=9)
    sh.text(x0, y1 + 92, "Grundriss EG", size=13)
    sh.text(x0 + 100, y1 + 92, "M 1:100", size=8)
    sh.text(x0, y1 + 106, "Außenwand Holzrahmenbau d = 30 cm, Fassade siehe Ansichten.")


def _elevation(sh: Sheet, p: Params, x0: float, base: float, length: float, openings: list[tuple[str, float, float, float, float]],
               title: str, kote_top: str | None = None):
    """openings: (Kennung, Abstand links, Breite, UK über ±0, Höhe)."""
    h = p.hoehe
    x1, top = x0 + length * S, base - h * S
    sh.line((x0 - 30, base), (x1 + 30, base), w=0.9)
    sh.rect((x0, top, x1, base), w=1.2)
    x = x0 + 6
    while x < x1 - 2:
        sh.line((x, top + 2), (x, base - 2), w=0.15, color=WOOD)
        x += 6
    for lab, a, w, uk, oh in openings:
        xa, xb = x0 + a * S, x0 + (a + w) * S
        ya, yb = base - (uk + oh) * S, base - uk * S
        sh.rect((xa, ya, xb, yb), w=0.8, fill=(1, 1, 1))
        if lab.startswith("F"):
            sh.line(((xa + xb) / 2, ya), ((xa + xb) / 2, yb), w=0.3)
        sh.text((xa + xb) / 2 - sh.width(lab, 7) / 2, ya + 10, lab, size=7)
    # waagrechte Ketten
    starts = sorted((a for _, a, _, _, _ in openings))
    widths = {a: w for _, a, w, _, _ in openings}
    chain, pos = [], 0.0
    for a in starts:
        chain += [round(a - pos, 2), widths[a]]
        pos = a + widths[a]
    chain.append(round(length - pos, 2))
    sh.hchain(x0, base + 24, chain, base + 2)
    sh.hchain(x0, base + 46, [length], base + 26)
    # senkrechte Kette (an der ersten Öffnung ausgerichtet)
    _, _, _, uk, oh = openings[0]
    v = [round(h - uk - oh, 2), oh] + ([uk] if uk > 0 else [])
    sh.vchain(x1 + 30, top, v, x1 + 2)
    # Koten
    sh.kote(x0 - 16, top, kote_top or de(h, sign=True), "OK Attika / OK Bekleidung", text_left=True)
    sh.kote(x0 - 16, base, de(0, sign=True), "OK Bodenplatte / UK Bekleidung", text_left=True)
    note = "Holzbekleidung Lärche, Boden-Deckel-Schalung, umlaufend"
    sh.text((x0 + x1) / 2 - sh.width(note) / 2, base + 64, note)
    sh.text(x0, base + 82, title, size=12)
    sh.text(x0 + sh.width(title, 12) + 4, base + 82, "M 1:100", size=8)


def ansichten_sued_nord(doc, p: Params):
    sh = Sheet(doc, p, "Ansichten Süd und Nord", "TB-201")
    _elevation(sh, p, 250, 270, LX, [(l, a, FB, BRH, FH) for l, a in SUED], "Ansicht Süd", kote_top=p.kote_sued)
    # Nord: Blick von Norden, links = Ost -> Abstände von der Ostecke
    _elevation(sh, p, 250, 620, LX, [(l, LX - a - FB, FB, BRH, FH) for l, a in NORD], "Ansicht Nord")


def ansichten_west_ost(doc, p: Params):
    sh = Sheet(doc, p, "Ansichten West und Ost", "TB-202")
    # West: Blick von Westen, links = Nord
    _elevation(sh, p, 250, 270, LY, [(l, a, w, 0.0, TH) for l, a, w in WEST], "Ansicht West")
    # Ost: Blick von Osten, links = Süd
    _elevation(sh, p, 250, 620, LY, [(l, LY - a - FB, FB, BRH, FH) for l, a in OST], "Ansicht Ost")


def schnitt(doc, p: Params):
    sh = Sheet(doc, p, "Schnitt A-A", "TB-301")
    h, dok = p.hoehe, p.dach_ok
    x0, base = 330.0, 400.0
    x1 = x0 + LY * S
    t = 0.30 * S
    top = base - h * S
    uk = base + p.platte * S
    win_top, win_bot = base - (BRH + FH) * S, base - BRH * S
    sh.line((x0 - 40, base + 1.4), (x0, base + 1.4), w=0.6)
    sh.line((x1, base + 1.4), (x1 + 40, base + 1.4), w=0.6)
    sh.rect((x0, base, x1, uk), w=1.0, fill=(0.8, 0.8, 0.8))
    for xa in (x0, x1 - t):
        sh.rect((xa, win_bot, xa + t, base), w=1.0, fill=(0.6, 0.6, 0.6))
        sh.rect((xa, top, xa + t, win_top), w=1.0, fill=(0.6, 0.6, 0.6))
        sh.rect((xa, win_top, xa + t, win_bot), w=0.6)
        sh.line((xa + t / 2, win_top), (xa + t / 2, win_bot), w=0.3)
    y_dach = base - dok * S
    sh.rect((x0 + t, y_dach + 0.10 * S, x1 - t, y_dach + 0.30 * S), w=0.8, fill=(0.75, 0.75, 0.75))
    sh.rect((x0 + t, y_dach, x1 - t, y_dach + 0.10 * S), w=0.5)
    sh.line((x0 - 1.5, base), (x0 - 1.5, top), w=0.5, color=WOOD)
    sh.line((x1 + 1.5, base), (x1 + 1.5, top), w=0.5, color=WOOD)
    sh.text(x0 + t + 8, (win_top + win_bot) / 2 + 2, "F02", size=7)
    sh.text(x1 - t - 20, (win_top + win_bot) / 2 + 2, "F04", size=7)
    # Koten rechts
    ka, kb = x1 + 70, x1 + 190
    for y, xk in ((top, ka), (y_dach, kb), (base, ka), (uk, kb)):
        sh.line((x1 + 2, y), (xk - 14, y), w=0.15, color=GREY)
    sh.kote(ka, top, de(h, sign=True), "OK Attika / OK Bekleidung", text_left=False)
    sh.kote(kb, y_dach, de(dok, sign=True), "OK Dachbelag", text_left=False)
    sh.kote(ka, base, de(0, sign=True), "OK Bodenplatte / UK Bekleidung", text_left=False)
    sh.kote(kb, uk, de(-p.platte, sign=True), "UK Bodenplatte", text_left=False)
    # Maßketten
    sh.vchain(x0 - 26, top, [round(h - BRH - FH, 2), FH, BRH], x0 - 2)
    sh.vchain(x0 - 50, top, [h], x0 - 28)
    sh.hchain(x0, uk + 26, [0.30, round(LY - 0.60, 2), 0.30], uk + 2)
    sh.hchain(x0, uk + 48, [LY], uk + 28)
    # Beschriftungen
    sh.text(370, top - 29, "Flachdach: Abdichtung, Wärmedämmung, Kiesschüttung - ohne Dachüberstand")
    sh.text(370, top - 19, "Außenwand: Holzrahmenbau, Holzbekleidung Lärche bis OK Attika")
    sh.text(370, (win_top + win_bot) / 2, f"LRH {de(dok - 0.30)}")
    sh.text(370, uk + 64, "Bodenplatte Stahlbeton d = 25 cm, bündig mit Außenkante Außenwand (umlaufend)")
    sh.text(x0, uk + 81, "Schnitt A-A", size=12)
    sh.text(x0 + 75, uk + 81, "M 1:100   Blick nach Westen", size=8)
    sh.text(x0 - 10, top - 40, "Süd", size=6.5)
    sh.text(x1 - 10, top - 40, "Nord", size=6.5)


def build(p: Params) -> bytes:
    doc = pymupdf.open()
    doc.set_metadata({"title": f"Testbau WPK – Plansatz Index {p.index}", "creator": "scripts/testplaene.py"})
    grundriss(doc, p)
    ansichten_sued_nord(doc, p)
    ansichten_west_ost(doc, p)
    schnitt(doc, p)
    return doc.tobytes(garbage=3, deflate=True)


def _num(s: str) -> float:
    return float(s.replace(",", ".").replace("+", ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hoehe", default="3,00", help="OK Bekleidung / OK Attika in m (Standard 3,00)")
    ap.add_argument("--index", default="a", help="Planstand-Index (Standard a)")
    ap.add_argument("--datum", default="10.11.2026")
    ap.add_argument("--kote-sued", help="abweichende Kote der Oberkante in Ansicht Süd, z. B. +3,10 (Widerspruchstest)")
    ap.add_argument("--out", type=Path, help="Zieldatei")
    a = ap.parse_args()
    p = Params(hoehe=_num(a.hoehe), index=a.index, datum=a.datum, kote_sued=a.kote_sued)
    out = a.out or Path(__file__).resolve().parents[1] / "plaene" / f"Testbau_Plansatz_Index-{p.index}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build(p))
    print(f"geschrieben: {out}  (OK Bekleidung {de(p.hoehe, sign=True)}, {p.stand})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
