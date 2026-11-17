"""Lokale, regelbasierte Auswertung von PDF-Textebene und Vektorzeichnung (ohne KI).

Grenzen (bewusst): funktioniert nur bei digital erzeugten PDFs, in denen Maßzahlen als
Text vorliegen und Maßlinien als Vektorlinien mit Maßbegrenzern (Schrägstrich/Hilfslinie)
gezeichnet sind. Keine Bilderkennung, keine Scans. Es werden nur *Beobachtungen* erzeugt;
die Zuordnung „welches Maß gehört zu welcher Öffnung“ erfolgt rein geometrisch über
deckungsgleiche Maßbegrenzer bzw. die Lage der Beschriftung.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import (AreaObs, BBox, ComponentObs, DimChain, DocumentInfo, Evidence, LevelObs, Measure, OpeningObs,
                      PriceNote, ViewRegion, ViewResult)
from ..pdf_prep import PageGeometry, Seg, Span
from ..units import looks_like_kote, looks_like_measure, parse_measure, parse_quantity
from . import vocab

ENGINE = "lokal"
ENGINE_VERSION = "lokal-2"


@dataclass
class DimSeg:
    span: Span
    a: float  # Anfang entlang der Maßlinie (x bei horizontal, y bei vertikal)
    b: float
    line_pos: float  # y (horizontal) bzw. x (vertikal) der Maßlinie
    direction: str  # "horizontal" | "vertikal"
    chain_key: tuple


class _Ctx:
    def __init__(self, doc: DocumentInfo, view: ViewRegion):
        self.doc = doc
        self.view = view

    def ev(self, span: Span | None, bbox: BBox | None = None, text: str | None = None, source="pdf_text", note="") -> Evidence:
        b = bbox or span.bbox
        sid = span.id if span else f"g{int(b.x0)}_{int(b.y0)}"
        return Evidence(id=f"{self.view.id}:{sid}", doc_id=self.doc.id, file_name=self.doc.file_name,
                        page=self.view.page, view_id=self.view.id, view_title=self.view.title,
                        text=text if text is not None else (span.text if span else ""), bbox=b, source=source, note=note)

    def measure(self, span: Span, raw: str | None = None) -> Measure:
        raw = raw if raw is not None else span.text
        pm = parse_measure(raw)
        return Measure(raw_text=span.text, value=pm.value_m, unit=pm.unit, unit_explicit=pm.unit_explicit,
                       evidence=self.ev(span))


# ----------------------------------------------------------------------------------------
# Geometrie-Hilfen
# ----------------------------------------------------------------------------------------


def _outline(geo: PageGeometry, view_type: str) -> BBox | None:
    cands = [r for r in geo.rects if r.bbox.w > 30 and r.bbox.h > 15]
    if view_type == "schnitt":
        filled = [r.bbox for r in geo.rects if r.filled and (r.bbox.w > 3 or r.bbox.h > 3)]
        if filled:
            b = filled[0]
            for f in filled[1:]:
                b = BBox(x0=min(b.x0, f.x0), y0=min(b.y0, f.y0), x1=max(b.x1, f.x1), y1=max(b.y1, f.y1))
            return b
    stroked = [r for r in cands if not r.filled or r.width > 0]
    if stroked:
        best = max(stroked, key=lambda r: (r.bbox.w * r.bbox.h, r.width))
        return best.bbox
    thick = [s for s in geo.segs if s.width >= 0.9 and s.length > 20]
    if thick:
        xs = [v for s in thick for v in (s.x0, s.x1)]
        ys = [v for s in thick for v in (s.y0, s.y1)]
        return BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))
    return None


def _ticks_on_line(seg: Seg, geo: PageGeometry, horizontal: bool) -> list[float]:
    """Positionen der Maßbegrenzer auf einer Maßlinie: kurze Querstriche und Hilfslinien."""
    pos = []
    lo, hi = (min(seg.x0, seg.x1), max(seg.x0, seg.x1)) if horizontal else (min(seg.y0, seg.y1), max(seg.y0, seg.y1))
    lp = seg.y0 if horizontal else seg.x0
    for s in geo.segs:
        if s is seg or s.dashed:
            continue
        long_ = s.length >= 12
        if long_:
            # Hilfslinie: muss an der Maßlinie enden (nicht nur kreuzen, z. B. Schnittlinie, Achse)
            d0 = abs((s.y0 if horizontal else s.x0) - lp)
            d1 = abs((s.y1 if horizontal else s.x1) - lp)
            if min(d0, d1) > 5:
                continue
        if horizontal:
            if s.is_h:
                continue
            ymin, ymax = min(s.y0, s.y1), max(s.y0, s.y1)
            if ymin - 4 <= lp <= ymax + 4:
                x = (s.x0 + s.x1) / 2 if not s.is_v else s.x0
                if lo - 0.5 <= x <= hi + 0.5 and (s.length < 12 or s.is_v):
                    pos.append(round(x, 2))
        else:
            if s.is_v:
                continue
            xmin, xmax = min(s.x0, s.x1), max(s.x0, s.x1)
            if xmin - 4 <= lp <= xmax + 4:
                y = (s.y0 + s.y1) / 2 if not s.is_h else s.y0
                if lo - 0.5 <= y <= hi + 0.5 and (s.length < 12 or s.is_h):
                    pos.append(round(y, 2))
    pos = sorted(pos)
    merged: list[float] = []
    for p in pos:
        if not merged or p - merged[-1] > 1.0:
            merged.append(p)
    return merged


def _dim_segments(geo: PageGeometry, spans: list[Span]) -> list[DimSeg]:
    hsegs = [s for s in geo.segs if s.is_h and s.length > 8]
    vsegs = [s for s in geo.segs if s.is_v and s.length > 8]
    out: list[DimSeg] = []
    tick_cache: dict[int, list[float]] = {}
    for sp in spans:
        if not looks_like_measure(sp.text) or looks_like_kote(sp.text):
            continue
        b = sp.bbox
        if sp.dir == "h":
            cands = [s for s in hsegs if b.y1 - 2 <= s.y0 <= b.y1 + 6 and min(s.x0, s.x1) <= b.cx <= max(s.x0, s.x1)]
            if not cands:
                continue
            line = min(cands, key=lambda s: abs(s.y0 - b.y1))
            key = id(line)
            if key not in tick_cache:
                tick_cache[key] = _ticks_on_line(line, geo, True)
            ticks = tick_cache[key]
            left = [t for t in ticks if t < b.cx]
            right = [t for t in ticks if t > b.cx]
            if not left or not right:
                continue
            out.append(DimSeg(sp, max(left), min(right), line.y0, "horizontal", ("h", round(line.y0, 1), round(min(line.x0, line.x1)))))
        else:
            cands = [s for s in vsegs if b.x1 - 2 <= s.x0 <= b.x1 + 6 and min(s.y0, s.y1) <= b.cy <= max(s.y0, s.y1)]
            if not cands:
                continue
            line = min(cands, key=lambda s: abs(s.x0 - b.x1))
            key = id(line)
            if key not in tick_cache:
                tick_cache[key] = _ticks_on_line(line, geo, False)
            ticks = tick_cache[key]
            up = [t for t in ticks if t < b.cy]
            down = [t for t in ticks if t > b.cy]
            if not up or not down:
                continue
            out.append(DimSeg(sp, max(up), min(down), line.x0, "vertikal", ("v", round(line.x0, 1), round(min(line.y0, line.y1)))))
    return out


def _near(a: BBox, b: BBox) -> float:
    dx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    dy = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    return (dx * dx + dy * dy) ** 0.5


# ----------------------------------------------------------------------------------------
# Hauptfunktion
# ----------------------------------------------------------------------------------------


def analyze_view(doc: DocumentInfo, view: ViewRegion, geo_page: PageGeometry) -> ViewResult:
    ctx = _Ctx(doc, view)
    geo = geo_page.in_region(view.bbox)
    res = ViewResult(view_id=view.id, engine=ENGINE, view_type=view.view_type, title=view.title,
                     storey=view.storey, facade=view.facade, left_dir=view.left_dir)
    _area_statements(ctx, res, geo_page.in_region(view.bbox).spans)
    if view.view_type not in ("grundriss", "ansicht", "schnitt"):
        res.notes.append("Bereich ist keiner Zeichnungsart zugeordnet – nicht ausgewertet.")
        return res
    outline = _outline(geo, view.view_type)
    res.outline = outline
    res.rectangular = True if outline is not None and view.view_type == "grundriss" else None
    if outline is None:
        res.notes.append("Gebäudeumriss nicht erkannt.")
        return res

    spans = geo.spans
    dims = _dim_segments(geo, spans)

    # --- Maßketten ---------------------------------------------------------------------
    chains: dict[tuple, list[DimSeg]] = {}
    for d in dims:
        chains.setdefault(d.chain_key, []).append(d)
    chain_objs: list[tuple[DimChain, list[DimSeg]]] = []
    for key, segs in chains.items():
        segs.sort(key=lambda d: d.a)
        horiz = segs[0].direction == "horizontal"
        lo, hi = (outline.x0, outline.x1) if horiz else (outline.y0, outline.y1)
        length = hi - lo
        lp = segs[0].line_pos
        if horiz:
            side = "oben" if lp < outline.y0 else "unten" if lp > outline.y1 else None
        else:
            side = "links" if lp < outline.x0 else "rechts" if lp > outline.x1 else None
        full = abs(segs[0].a - lo) < 0.02 * length + 1.5 and abs(segs[-1].b - hi) < 0.02 * length + 1.5
        if view.view_type == "grundriss" or horiz:
            refers = "gebaeude_aussen" if full else "sonstiges"
        else:
            refers = "hoehen"
        role = "gesamtmass" if len(segs) == 1 and full else "kette"
        ch = DimChain(direction=segs[0].direction, side=side, role=role, refers_to=refers,
                      segments=[ctx.measure(d.span) for d in segs],
                      spans=[((d.a - lo) / length, (d.b - lo) / length) for d in segs])
        chain_objs.append((ch, segs))
        res.chains.append(ch)

    # --- Höhenkoten ----------------------------------------------------------------------
    label_spans = [s for s in spans if vocab.LEVEL_HINT_RE.search(s.text) and not looks_like_kote(s.text)]
    for s in spans:
        if not looks_like_kote(s.text):
            continue
        near = sorted(label_spans, key=lambda l: _near(l.bbox, s.bbox))
        label = near[0] if near and _near(near[0].bbox, s.bbox) < 25 else None
        refs = vocab.level_refs(label.text) if label else ["sonstige"]
        m = ctx.measure(s)
        if label is not None and m.evidence is not None:
            m.evidence.note = label.text
        res.levels.append(LevelObs(measure=m, refs=refs, label_raw=label.text if label else ""))

    # --- Öffnungen ----------------------------------------------------------------------
    sill_spans = [s for s in spans if vocab.SILL_RE.match(s.text)]
    for s in spans:
        if not vocab.OPENING_LABEL_RE.match(s.text):
            continue
        op = OpeningObs(label=s.text.replace(" ", "").upper(), kind=vocab.opening_kind(s.text), symbol=ctx.ev(s))
        if view.view_type == "grundriss":
            _opening_in_plan(ctx, op, s, outline, chain_objs, sill_spans)
        else:
            _opening_in_elevation(ctx, op, s, outline, geo, dims, view)
        res.openings.append(op)

    # --- Bauteile, Material, Planpreise ---------------------------------------------------
    for s in spans:
        txt = s.text
        if vocab.PRICE_RE.search(txt):
            res.price_notes.append(PriceNote(text=txt, evidence=ctx.ev(s)))
        if re.match(r"^\s*(ok|uk)\b", txt, re.I):
            continue  # Kotenbezeichnung, keine Bauteilangabe
        for comp, rx in vocab.COMPONENT_PATTERNS.items():
            if not rx.search(txt):
                continue
            c = ComponentObs(component=comp, description=txt, material=txt, evidence=ctx.ev(s))
            c.flush_with_outline = True if vocab.FLUSH_RE.search(txt) else None
            mo = vocab.OVERHANG_RE.search(txt)
            if mo and not re.search(r"ohne|kein", txt, re.I):
                pm = parse_measure(mo.group(2))
                c.overhang = Measure(raw_text=mo.group(2), value=pm.value_m, unit=pm.unit, evidence=ctx.ev(s))
                c.flush_with_outline = False
            mp = vocab.PITCH_RE.search(txt)
            if mp:
                c.pitch = Measure(raw_text=mp.group(0), value=float(mp.group(1).replace(",", ".")), unit="grad",
                                  evidence=ctx.ev(s))
            for form, frx in vocab.ROOF_FORM_RE.items():
                if frx.search(txt):
                    c.roof_form = form
            c.all_around = bool(vocab.ALL_AROUND_RE.search(txt))
            if comp == "bekleidung":
                if view.view_type == "ansicht" and view.facade:
                    c.facades = [view.facade]
                mt = re.search(r"bis\s+(ok\s+\w+|oberkante\s+\w+)", txt, re.I)
                if mt:
                    refs = vocab.level_refs(mt.group(1))
                    c.to_level = refs[0] if refs and refs[0] != "sonstige" else None
            res.components.append(c)

    if view.view_type == "grundriss" and not any(s.text.strip() == "N" for s in spans):
        res.notes.append("Nordpfeil nicht erkannt – Annahme: Norden oben. Bitte prüfen.")
    return res


def _opening_in_plan(ctx: _Ctx, op: OpeningObs, s: Span, outline: BBox, chain_objs, sill_spans: list[Span]):
    # Nächstgelegene Gebäudekante -> Fassade (Annahme Norden oben)
    d = {"nord": abs(s.bbox.cy - outline.y0), "sued": abs(s.bbox.cy - outline.y1),
         "west": abs(s.bbox.cx - outline.x0), "ost": abs(s.bbox.cx - outline.x1)}
    facade = min(d, key=d.get)
    op.facade = facade
    side = {"nord": "oben", "sued": "unten", "west": "links", "ost": "rechts"}[facade]
    horiz = facade in ("nord", "sued")
    coord = s.bbox.cx if horiz else s.bbox.cy
    best = None
    for ch, segs in chain_objs:
        if ch.side != side or ch.role != "kette" or len(segs) < 2:
            continue
        for m, dseg in zip(ch.segments, segs):
            if dseg.a <= coord <= dseg.b:
                if best is None or abs(dseg.line_pos - (outline.y0 if side == "oben" else outline.y1 if side == "unten" else outline.x0 if side == "links" else outline.x1)) < best[2]:
                    lo, hi = (outline.x0, outline.x1) if horiz else (outline.y0, outline.y1)
                    edge = outline.y0 if side == "oben" else outline.y1 if side == "unten" else outline.x0 if side == "links" else outline.x1
                    best = (m, ((dseg.a - lo) / (hi - lo), (dseg.b - lo) / (hi - lo)), abs(dseg.line_pos - edge))
    if best:
        op.width = best[0]
        op.pos_in_view = best[1]
    sills = sorted((t for t in sill_spans if _near(t.bbox, s.bbox) < 14), key=lambda t: _near(t.bbox, s.bbox))
    if sills:
        mm = vocab.SILL_RE.match(sills[0].text)
        pm = parse_measure(mm.group(1))
        op.sill = Measure(raw_text=sills[0].text, value=pm.value_m, unit=pm.unit, evidence=ctx.ev(sills[0]))


def _opening_in_elevation(ctx: _Ctx, op: OpeningObs, s: Span, outline: BBox, geo: PageGeometry, dims: list[DimSeg], view: ViewRegion):
    inner = [r.bbox for r in geo.rects if not r.filled or r.width > 0]
    inner = [b for b in inner if b.w < outline.w * 0.9 and b.h < outline.h * 0.98 and b.w > 5 and b.h > 5]
    containing = [b for b in inner if b.contains_point(s.bbox.cx, s.bbox.cy)]
    if containing:
        r = min(containing, key=lambda b: b.w * b.h)
    else:
        near = sorted(inner, key=lambda b: _near(b, s.bbox))
        r = near[0] if near and _near(near[0], s.bbox) < 20 else None
    if r is None:
        return
    op.symbol = ctx.ev(s, bbox=BBox(x0=min(r.x0, s.bbox.x0), y0=min(r.y0, s.bbox.y0), x1=max(r.x1, s.bbox.x1), y1=max(r.y1, s.bbox.y1)),
                       text=s.text, note="Öffnungssymbol mit Beschriftung")
    tol = 1.6
    for d in dims:
        if (view.view_type == "ansicht" and d.direction == "horizontal" and abs(d.a - r.x0) < tol
                and abs(d.b - r.x1) < tol and op.width is None):
            op.width = ctx.measure(d.span)
        if d.direction == "vertikal":
            if abs(d.a - r.y0) < tol and abs(d.b - r.y1) < tol and op.height is None:
                op.height = ctx.measure(d.span)
            elif abs(d.a - r.y1) < tol and abs(d.b - outline.y1) < tol and r.y1 < outline.y1 - tol and op.sill is None:
                op.sill = ctx.measure(d.span)  # Brüstung: Unterkante Öffnung bis ±0,00 – keine Fensterhöhe
    rel = ((r.x0 - outline.x0) / outline.w, (r.x1 - outline.x0) / outline.w)
    if view.view_type == "ansicht":
        op.facade = view.facade
        op.pos_in_view = rel
    else:  # Schnitt: Öffnung in linker oder rechter Außenwand
        if view.left_dir:
            opposite = {"nord": "sued", "sued": "nord", "ost": "west", "west": "ost"}
            op.facade = view.left_dir if r.cx < outline.cx else opposite[view.left_dir]
        op.pos_in_view = None


def _area_statements(ctx: _Ctx, res: ViewResult, spans: list[Span]) -> None:
    """Beschriftete BGF-/BRI-Angaben (auch NUF/NRF/Wohnfläche, die nie als BGF gelten)."""
    for s in spans:
        m = vocab.AREA_LABEL_RE.match(s.text)
        if not m:
            continue
        val, unit = parse_quantity(s.text[m.end():])
        src = s
        if val is None:  # Wert rechts daneben auf gleicher Zeile
            right = sorted((o for o in spans if o is not s and abs(o.bbox.cy - s.bbox.cy) < 3 and o.bbox.x0 >= s.bbox.x1 - 1),
                           key=lambda o: o.bbox.x0)
            if right:
                val, unit = parse_quantity(right[0].text)
                src = right[0]
        if val is None:
            continue
        kind = vocab.area_kind(m.group(1))
        if (kind == "bgf" and unit == "m³") or (kind == "bri" and unit == "m²"):
            res.notes.append(f"Angabe „{s.text}“: Einheit passt nicht zur Bezeichnung – nicht verwendet.")
            continue
        ev = ctx.ev(src, bbox=BBox(x0=min(s.bbox.x0, src.bbox.x0), y0=min(s.bbox.y0, src.bbox.y0),
                                  x1=max(s.bbox.x1, src.bbox.x1), y1=max(s.bbox.y1, src.bbox.y1)),
                    text=s.text if src is s else f"{s.text} {src.text}")
        res.area_statements.append(AreaObs(kind=kind, label_raw=s.text,
                                           measure=Measure(raw_text=src.text, value=val, unit=unit or "", evidence=ev)))
