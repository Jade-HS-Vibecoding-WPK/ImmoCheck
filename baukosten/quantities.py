"""Mengenermittlung in Python mit nachvollziehbaren Formeln und Beleg-IDs.

Nur geschriebene Maße und eindeutige Regelgeometrien. Eine Menge entsteht nie aus einem
Markierungsrechteck. Fehlende oder widersprüchliche Eingangswerte führen zu
„offen“ bzw. „prüfen“ – nie zu geschätzten Werten.
"""
from __future__ import annotations

import math

from .models import FACADE_LABEL, BuildingModel, Opening, Quantity, QuantityInput, Value
from .units import format_de

FACADES = ["nord", "ost", "sued", "west"]


def _inp(name: str, v: Value | None, unit: str = "m") -> QuantityInput:
    if v is None:
        return QuantityInput(name=name, value=None, unit=unit)
    raw = " / ".join(sorted({c.raw_text for c in v.candidates})) if v.candidates else ""
    return QuantityInput(name=name, value=v.value, unit=v.unit or unit, value_key=v.key, raw_text=raw, evidence=v.evidence)


def _f(x: float | None, d: int = 2) -> str:
    return format_de(x, d)


def _status_of(*values: Value | None) -> tuple[str, list[str]]:
    reasons, status = [], "ok"
    for v in values:
        if v is None:
            continue
        if v.status == "widerspruch":
            status = "pruefen"
            reasons.append(f"Widerspruch: {v.label} – bitte Fundstelle wählen")
        elif v.status == "fehlt":
            if status != "pruefen":
                status = "offen"
            reasons.append(f"fehlt: {v.label}")
    return status, reasons


def _opening_inputs(ops: list[Opening]) -> list[QuantityInput]:
    out = []
    for o in ops:
        out.append(_inp(f"Breite {o.label or o.id} ({o.id})", o.width))
        out.append(_inp(f"Höhe {o.label or o.id} ({o.id})", o.height))
    return out


def opening_formula(ops: list[Opening]) -> str:
    if not ops:
        return "–"
    if any(o.area is None for o in ops):
        return "unvollständig"
    dims = {(round(o.width.value, 4), round(o.height.value, 4)) for o in ops}
    total = sum(o.area for o in ops)
    if len(dims) == 1:
        w, h = dims.pop()
        return f"{len(ops)} × {_f(w)} m × {_f(h)} m = {_f(total)} m²"
    parts = " + ".join(f"{_f(o.width.value)} × {_f(o.height.value)}" for o in ops)
    return f"{parts} = {_f(total)} m²"


def compute_quantities(m: BuildingModel) -> list[Quantity]:
    out: list[Quantity] = []
    lx, ly = m.length_x, m.length_y
    base_status, base_reasons = _status_of(lx, ly)
    rect_reason = []
    if m.rectangular is not True:
        rect_reason = ["Rechteckige Grundrissform nicht belegt – Fläche zur Prüfung markiert"]

    # ---------------- Bodenplatte (KG 322) ----------------------------------------------
    plates = m.components.get("bodenplatte", [])
    q = Quantity(key="bodenplatte", bauteil="Bodenplatte", bauteiltyp="bodenplatte", kg_hint="322",
                 ausfuehrung="; ".join(sorted({c.material for c in plates if c.material}))[:160], primary_unit="m²",
                 inputs=[_inp("Außenmaß West–Ost", lx), _inp("Außenmaß Nord–Süd", ly)])
    flush_ev = [c.evidence for c in plates if c.flush_with_outline and c.evidence]
    overhang = [c for c in plates if c.flush_with_outline is False]
    if not plates:
        q.status, q.reasons = "offen", ["Bodenplatte im Plansatz nicht belegt"]
    elif overhang or not flush_ev:
        q.status = "pruefen"
        q.reasons = ["Deckungsgleichheit Bodenplatte/Außenkontur nicht nachgewiesen – Plattenmaße erforderlich"]
        if lx.value and ly.value:
            q.details.append(f"Gebäudegrundfläche (nur Hinweis): {_f(lx.value)} × {_f(ly.value)} = {_f(lx.value * ly.value)} m²")
    else:
        q.status, q.reasons = base_status, base_reasons + rect_reason
        if rect_reason and q.status == "ok":
            q.status = "pruefen"
        if q.status == "ok":
            area = lx.value * ly.value
            q.values = {"m²": area}
            q.formula = f"{_f(lx.value)} m × {_f(ly.value)} m = {_f(area)} m²"
        q.inputs.append(QuantityInput(name="Nachweis Deckungsgleichheit", value=None, unit="", raw_text=flush_ev[0].text,
                                      evidence=flush_ev))
        q.details.append("Plattenfläche = Gebäudegrundfläche, da Bodenplatte bündig mit Außenkontur belegt.")
    out.append(q)

    # ---------------- Fenster (KG 334) -----------------------------------------------------
    windows = [o for o in m.openings if o.kind in ("fenster", "fenstertuer")]
    doors = [o for o in m.openings if o.kind == "tuer"]
    for key, bauteil, typ, ops in (("fenster", "Fenster", "fenster", windows), ("aussentuer", "Außentüren", "aussentuer", doors)):
        q = Quantity(key=key, bauteil=bauteil, bauteiltyp=typ, kg_hint="334", primary_unit="m²" if typ == "fenster" else "Stk",
                     inputs=_opening_inputs(ops))
        if not ops:
            q.status, q.reasons = "offen", [f"{bauteil}: keine Öffnungen im Plansatz belegt"]
            out.append(q)
            continue
        st, rs = _status_of(*[x for o in ops for x in (o.width, o.height)])
        area = sum(o.area for o in ops) if all(o.area is not None for o in ops) else None
        q.values = {"Stk": float(len(ops)), "m²": area}
        q.status, q.reasons = st, rs
        q.formula = f"Öffnungsfläche: {opening_formula(ops)}; Anzahl: {len(ops)} Stk"
        q.details = [f"{o.label or '?'} [{o.id}] {FACADE_LABEL.get(o.facade or '', '?')}: "
                     f"{_f(o.width.value)} × {_f(o.height.value)} m"
                     f"{'' if o.sill.value is None else f', Brüstung {_f(o.sill.value)} m (nicht Teil der Höhe)'}"
                     f" – Belege: {', '.join(o.sources)}" for o in ops]
        q.details.append("Öffnungsfläche (Rohbaumaß) ≠ Glasfläche; Glasfläche wird nicht ermittelt.")
        out.append(q)

    # ---------------- Fassadenbekleidung (KG 335) -----------------------------------------
    clad = m.components.get("bekleidung", [])
    q = Quantity(key="bekleidung", bauteil="Äußere Bekleidung", bauteiltyp="fassadenbekleidung", kg_hint="335",
                 primary_unit="m²", ausfuehrung="; ".join(sorted({c.material for c in clad if c.material}))[:160])
    top = m.levels.get("ok_bekleidung")
    if top is None:
        to_refs = [c.to_level for c in clad if c.to_level]
        if to_refs and to_refs[0] in m.levels:
            top = m.levels[to_refs[0]]
            q.details.append(f"Oberkante Bekleidung aus Bauteilangabe „bis {top.label}“.")
    bottom = m.levels.get("uk_bekleidung")
    q.inputs = [_inp("Außenmaß West–Ost", lx), _inp("Außenmaß Nord–Süd", ly), _inp("Kote OK Bekleidung", top),
                _inp("Kote UK Bekleidung", bottom)]
    if not clad and not m.clad_facades:
        q.status, q.reasons = "offen", ["Fassadenbekleidung im Plansatz nicht belegt"]
        out.append(q)
    else:
        st, rs = _status_of(lx, ly, top, bottom)
        if top is None:
            st, rs = "offen", rs + ["Kote OK Bekleidung nicht belegt"]
        if bottom is None:
            st, rs = "offen", rs + ["Kote UK Bekleidung nicht belegt"]
        lines, total, missing_fac = [], 0.0, []
        op_status, op_reasons = _status_of(*[x for o in m.openings for x in (o.width, o.height)])
        if op_status != "ok":
            st = "pruefen" if "pruefen" in (st, op_status) else "offen"
            rs += [f"Öffnungsabzug: {r}" for r in op_reasons]
        if rect_reason:
            st = "pruefen" if st == "ok" else st
            rs += rect_reason
        h = None
        if top is not None and bottom is not None and top.value is not None and bottom.value is not None:
            h = top.value - bottom.value
        for f in FACADES:
            if f not in m.clad_facades:
                missing_fac.append(FACADE_LABEL[f])
                continue
            L = lx.value if f in ("nord", "sued") else ly.value
            ops = [o for o in m.openings if o.facade == f]
            a_ops = sum(o.area for o in ops) if all(o.area is not None for o in ops) else None
            if L is None or h is None or a_ops is None:
                lines.append(f"{FACADE_LABEL[f]}: unvollständig")
                continue
            a = L * h - a_ops
            total += a
            lines.append(f"{FACADE_LABEL[f]}: {_f(L)} × {_f(h)} − {_f(a_ops)} (Öffnungen {len(ops)}) = {_f(a)} m²")
            q.inputs.append(QuantityInput(name=f"Bekleidungsumfang {FACADE_LABEL[f]}", value=None, unit="",
                                          raw_text="belegt", evidence=m.clad_facades[f][:3]))
        if missing_fac:
            q.details.append(f"Keine Bekleidung belegt für: {', '.join(missing_fac)} – nicht angesetzt.")
            if len(missing_fac) == 4:
                st, rs = "offen", rs + ["Bekleidungsumfang nicht belegt"]
        q.status, q.reasons = st, rs
        q.inputs.extend(_opening_inputs(m.openings))
        if st == "ok":
            q.values = {"m²": total}
            if not missing_fac:
                a_all = sum(o.area for o in m.openings)
                q.formula = (f"2 × ({_f(lx.value)} + {_f(ly.value)}) m × ({_f(top.value)} − {_f(bottom.value)}) m "
                             f"− {_f(a_all)} m² Öffnungen = {_f(total)} m²")
            else:
                q.formula = " + ".join(lines)
        q.details = lines + q.details
        q.details.append("Laibungen, Anschlüsse und Sockel nicht gesondert erfasst (nur gemäß nachgewiesenem Umfang).")
        out.append(q)

    # ---------------- Dach (KG 363) -------------------------------------------------------
    roofs = m.components.get("dach", [])
    q = Quantity(key="dach", bauteil="Dachbelag", bauteiltyp="dachbelag", kg_hint="363", primary_unit="m²",
                 ausfuehrung="; ".join(sorted({c.material for c in roofs if c.material}))[:160],
                 inputs=[_inp("Außenmaß West–Ost", lx), _inp("Außenmaß Nord–Süd", ly)])
    flush = [c for c in roofs if c.flush_with_outline]
    overhangs = [c for c in roofs if c.overhang is not None and c.overhang.value]
    if not roofs:
        q.status, q.reasons = "offen", ["Dach im Plansatz nicht belegt"]
    elif m.roof_form == "flachdach":
        if flush and not overhangs:
            st, rs = _status_of(lx, ly)
            if rect_reason and st == "ok":
                st, rs = "pruefen", rs + rect_reason
            q.status, q.reasons = st, rs
            q.inputs.append(QuantityInput(name="Nachweis ohne Überstand", value=None, unit="", raw_text=flush[0].evidence.text if flush[0].evidence else "",
                                          evidence=[c.evidence for c in flush if c.evidence]))
            if st == "ok":
                a = lx.value * ly.value
                q.values = {"m²": a}
                q.formula = f"Flachdach ohne Überstand = horizontale Projektion: {_f(lx.value)} m × {_f(ly.value)} m = {_f(a)} m²"
        else:
            q.status = "pruefen"
            q.reasons = ["Dachgrenzen/Überstand nicht eindeutig belegt"]
    elif m.roof_form in ("satteldach", "pultdach") and m.roof_pitch is not None and m.roof_pitch.value is not None:
        st, rs = _status_of(lx, ly, m.roof_pitch)
        q.inputs.append(_inp("Dachneigung", m.roof_pitch, "°"))
        if overhangs:
            st, rs = "pruefen", rs + ["Dachüberstände vorhanden – Dachgrenzen bitte prüfen"]
        elif not flush:
            st, rs = "pruefen", rs + ["Dachgrenzen ohne Nachweis gleich Außenkontur angenommen"]
        q.status, q.reasons = st, rs
        if lx.value and ly.value:
            proj = lx.value * ly.value
            a = proj / math.cos(math.radians(m.roof_pitch.value))
            q.formula = f"{_f(lx.value)} × {_f(ly.value)} / cos({_f(m.roof_pitch.value, 1)}°) = {_f(a)} m²"
            if st == "ok":
                q.values = {"m²": a}
            else:
                q.details.append(f"Rechnerisch (zur Prüfung): {q.formula}")
    else:
        q.status, q.reasons = "pruefen", [f"Dachform „{m.roof_form or 'unbekannt'}“ – Geometrie zur Prüfung markiert"]
    out.append(q)
    return out
