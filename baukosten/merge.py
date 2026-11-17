"""Zusammenführen der Beobachtungen aller Zeichnungen zu einem Gebäudemodell.

- Revisionsstände: pro Zeichnung (Ansichtsart + Seite/Geschoss) gilt ein aktiver Planstand.
- Gleiche Länge aus Gesamtmaß und Summe der Maßkette = zwei Belege für dieselbe Länge.
- Öffnungen: ein Datensatz pro gebauter Öffnung mit allen Belegen; Abgleich über Fassade,
  Lage entlang der Fassade und Kennung. Gleiche Typkürzel bleiben getrennte Vorkommen.
- Abweichende Werte für dasselbe Maß -> Widerspruch mit allen Fundstellen zur Auswahl.
- Korrekturen (Overrides) bleiben mit dem ursprünglichen Beleg verknüpft.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import (FACADE_LABEL, LEVEL_LABEL, AreaObs, BuildingModel, CalcInfo, Candidate, ComponentObs, DocumentInfo,
                     Evidence, Issue, Measure, Opening, OpeningObs, Override, PageInfo, PriceNote, QuantityInput, Value,
                     ViewRegion, ViewResult)
from .units import format_de

TOL = 0.005  # m
OPPOSITE = {"nord": "sued", "sued": "nord", "ost": "west", "west": "ost"}
# Bezugsrichtung der kanonischen Lage: N/S-Fassaden ab West, W/O-Fassaden ab Süd
CANON_START = {"nord": "west", "sued": "west", "ost": "sued", "west": "sued"}


@dataclass
class ViewInput:
    view: ViewRegion
    result: ViewResult
    page: PageInfo
    doc: DocumentInfo


# ----------------------------------------------------------------------------------------
# Revisionsstände
# ----------------------------------------------------------------------------------------


def _stand_sort_key(s: str) -> tuple:
    date = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", s or "")
    d = (int(date.group(3)), int(date.group(2)), int(date.group(1))) if date else (0, 0, 0)
    idx = re.search(r"(?:index|rev\.?|revision)\s*([a-z0-9]+)", s or "", re.I)
    return (d, idx.group(1).lower() if idx else "")


def view_key(v: ViewRegion) -> str:
    if v.view_type == "ansicht":
        return f"ansicht:{v.facade or v.title.lower()}"
    if v.view_type == "grundriss":
        return f"grundriss:{v.storey or v.title.lower()}"
    if v.view_type == "schnitt":
        return f"schnitt:{re.sub(r'[^a-z0-9]', '', v.title.lower())}"
    return f"{v.view_type}:{v.id}"


def select_revisions(inputs: list[ViewInput], active_stand: str | None) -> tuple[list[ViewInput], list[Issue], list[str], str | None]:
    by_key: dict[str, dict[str, list[ViewInput]]] = {}
    for vi in inputs:
        by_key.setdefault(view_key(vi.view), {}).setdefault(vi.page.plan_stand or "", []).append(vi)
    all_stands = sorted({vi.page.plan_stand for vi in inputs if vi.page.plan_stand}, key=_stand_sort_key)
    conflicting = {k: d for k, d in by_key.items() if len([s for s in d if s]) > 1}
    issues: list[Issue] = []
    proposed = active_stand
    if conflicting and not proposed:
        proposed = all_stands[-1] if all_stands else None
    keep: list[ViewInput] = []
    for k, d in by_key.items():
        if k in conflicting:
            choice = proposed if proposed in d else sorted([s for s in d if s], key=_stand_sort_key)[-1]
            keep.extend(d[choice])
            keep.extend(d.get("", []))
        else:
            for lst in d.values():
                keep.extend(lst)
    if conflicting:
        ev = []
        for d in conflicting.values():
            for lst in d.values():
                for vi in lst:
                    ev.append(Evidence(id=f"{vi.view.id}:stand", doc_id=vi.doc.id, file_name=vi.doc.file_name,
                                       page=vi.view.page, view_id=vi.view.id, view_title=vi.view.title,
                                       text=vi.page.plan_stand or "ohne Planstand", bbox=vi.view.bbox, source="pdf_text"))
        how = "festgelegt" if active_stand else "Vorschlag (neuester Stand) – bitte bestätigen"
        issues.append(Issue(key="revision", kind="revision",
                            text=f"Widersprüchliche Revisionsstände für dieselben Zeichnungen: {', '.join(all_stands)}. "
                                 f"Aktiver Stand: {proposed} ({how}). Zeichnungen anderer Stände werden nicht verwendet.",
                            evidence=ev))
    return keep, issues, all_stands, proposed if conflicting else (all_stands[-1] if len(all_stands) == 1 else proposed)


# ----------------------------------------------------------------------------------------
# Werte mit mehreren Belegen
# ----------------------------------------------------------------------------------------


def _add(cands: list[Candidate], value: float | None, raw: str, evidence: list[Evidence], origin: str):
    if value is None:
        return
    for c in cands:
        if abs(c.value - value) <= TOL:
            ids = {e.id for e in c.evidence}
            c.evidence.extend(e for e in evidence if e.id not in ids)
            if origin not in c.origin:
                c.origin = f"{c.origin}; {origin}" if c.origin else origin
            return
    cands.append(Candidate(value=value, raw_text=raw, evidence=list(evidence), origin=origin))


def _finalize(v: Value, overrides: dict[str, Override], question: str | None = None) -> Value:
    ov = overrides.get(v.key)
    if ov is not None:
        if ov.chosen_evidence_id:
            for c in v.candidates:
                if any(e.id == ov.chosen_evidence_id for e in c.evidence):
                    v.chosen, v.status = c.value, "ok"
                    v.question = None
                    return v
        if ov.value is not None:
            v.chosen, v.status = ov.value, "manuell"
            if not any(c.origin.startswith("manuell") for c in v.candidates):
                v.candidates.append(Candidate(value=ov.value, raw_text=format_de(ov.value), origin=f"manuell: {ov.note}".strip(": "),
                                              evidence=list(ov.original_evidence)))
            return v
    if len(v.candidates) == 1:
        v.chosen, v.status = v.candidates[0].value, "ok"
    elif len(v.candidates) > 1:
        v.chosen, v.status = None, "widerspruch"
        opts = " oder ".join(f"{format_de(c.value)} {v.unit} ({c.origin})" for c in v.candidates)
        v.question = f"{v.label}: {opts}?"
    else:
        v.chosen, v.status = None, "fehlt"
        v.question = question
    return v


def _measure_ev(m: Measure | None) -> list[Evidence]:
    return [m.evidence] if m is not None and m.evidence is not None else []


# ----------------------------------------------------------------------------------------
# Öffnungen
# ----------------------------------------------------------------------------------------


def _canonical_pos(op: OpeningObs, vi: ViewInput) -> tuple[float, float] | None:
    if op.pos_in_view is None or op.facade is None:
        return None
    a, b = op.pos_in_view
    vt = vi.view.view_type
    if vt == "grundriss":
        # Annahme Norden oben: N/S von links (=West), W/O von oben (=Nord) -> ab Süd umkehren
        if op.facade in ("nord", "sued"):
            return (a, b)
        return (1 - b, 1 - a)
    if vt == "ansicht":
        left = vi.result.left_dir or vi.view.left_dir
        if left is None:
            return None
        return (a, b) if left == CANON_START[op.facade] else (1 - b, 1 - a)
    return None


def _overlap(p: tuple[float, float], q: tuple[float, float]) -> float:
    """Ähnlichkeit zweier Lagen entlang der Fassade (0..1).

    IoU der Intervalle; liegt die Mitte des einen Intervalls im anderen (z. B. KI-Box nur um die
    Beschriftung), gilt die Lage ebenfalls als übereinstimmend (Wert 0,6)."""
    inter = max(0.0, min(p[1], q[1]) - max(p[0], q[0]))
    union = max(p[1], q[1]) - min(p[0], q[0])
    iou = inter / union if union > 0 else 0.0
    cp, cq = (p[0] + p[1]) / 2, (q[0] + q[1]) / 2
    if q[0] <= cp <= q[1] or p[0] <= cq <= p[1]:
        iou = max(iou, 0.6)
    return iou


@dataclass
class _Occ:
    op: OpeningObs
    vi: ViewInput
    pos: tuple[float, float] | None


def merge_openings(inputs: list[ViewInput], overrides: dict[str, Override]) -> tuple[list[Opening], list[Issue]]:
    occs = [_Occ(op, vi, _canonical_pos(op, vi)) for vi in inputs for op in vi.result.openings]
    clusters: list[list[_Occ]] = []
    issues: list[Issue] = []
    # 1) Vorkommen mit Lage: Grundriss zuerst, dann Ansichten
    with_pos = sorted([o for o in occs if o.pos is not None], key=lambda o: 0 if o.vi.view.view_type == "grundriss" else 1)
    for o in with_pos:
        best, score = None, 0.0
        for cl in clusters:
            ref = cl[0]
            if ref.op.facade != o.op.facade:
                continue
            if o.op.label and ref.op.label and o.op.label != ref.op.label:
                continue
            ov = max(_overlap(o.pos, c.pos) for c in cl if c.pos)
            if ov > 0.5 and ov > score:
                best, score = cl, ov
        if best is None:
            clusters.append([o])
        else:
            best.append(o)
    # 2) Vorkommen ohne Lage (z. B. Schnitt): nur bei eindeutiger Kennung auf derselben Fassade
    for o in occs:
        if o.pos is not None:
            continue
        matches = [cl for cl in clusters if cl[0].op.label == o.op.label and (o.op.facade is None or cl[0].op.facade == o.op.facade)]
        if len(matches) == 1:
            matches[0].append(o)
        else:
            ev = [o.op.symbol] if o.op.symbol else []
            why = "mehrdeutig" if matches else "ohne Gegenstück im Grundriss/in den Ansichten"
            issues.append(Issue(key=f"opening-unassigned:{o.vi.view.id}:{o.op.label}", kind="hinweis",
                                text=f"Öffnung {o.op.label or '?'} in {o.vi.view.title}: Beleg {why} – nicht zugeordnet, "
                                     "keine eigene Menge gebildet.", evidence=ev))
    # 3) Datensätze bilden, stabile IDs je Fassade nach Lage
    out: list[Opening] = []
    by_facade: dict[str, list[list[_Occ]]] = {}
    for cl in clusters:
        by_facade.setdefault(cl[0].op.facade or "unbekannt", []).append(cl)
    for facade, cls in by_facade.items():
        cls.sort(key=lambda cl: min((c.pos[0] for c in cl if c.pos), default=9))
        for n, cl in enumerate(cls, 1):
            oid = f"{facade}-{n}"
            label = next((c.op.label for c in cl if c.op.label), None)
            kind = next((c.op.kind for c in cl if c.op.kind != "unbekannt"), "unbekannt")
            noun = {"fenster": "das Fenster", "tuer": "die Tür", "fenstertuer": "die Fenstertür"}.get(kind, "die Öffnung")
            where = f" ({FACADE_LABEL.get(facade, facade)}fassade)" if facade in FACADE_LABEL else ""
            w = Value(key=f"opening:{oid}:breite", label=f"Breite {label or oid}{where}")
            h = Value(key=f"opening:{oid}:hoehe", label=f"Höhe {label or oid}{where}")
            s = Value(key=f"opening:{oid}:bruestung", label=f"Brüstungshöhe {label or oid}{where}")
            occ_ev: list[Evidence] = []
            sources: list[str] = []
            for c in cl:
                t = c.vi.view.title
                sources.append(t)
                if c.op.symbol:
                    occ_ev.append(c.op.symbol)
                if c.op.width:
                    _add(w.candidates, c.op.width.value, c.op.width.raw_text, _measure_ev(c.op.width), t)
                if c.op.height:
                    _add(h.candidates, c.op.height.value, c.op.height.raw_text, _measure_ev(c.op.height), t)
                if c.op.sill:
                    _add(s.candidates, c.op.sill.value, c.op.sill.raw_text, _measure_ev(c.op.sill), t)
            pos = next((c.pos for c in cl if c.pos and c.vi.view.view_type == "grundriss"), None) or next((c.pos for c in cl if c.pos), None)
            out.append(Opening(id=oid, label=label, kind=kind, facade=facade if facade in FACADE_LABEL else None, pos=pos,
                               width=_finalize(w, overrides, f"Welche Breite hat {noun} {label or oid}{where}?"),
                               height=_finalize(h, overrides, f"Welche Höhe hat {noun} {label or oid}{where}?"),
                               sill=_finalize(s, overrides), occurrences=occ_ev, sources=sorted(set(sources))))
    return out, issues


# ----------------------------------------------------------------------------------------
# Gebäudemodell
# ----------------------------------------------------------------------------------------


def _schnitt_axis(vi: ViewInput) -> str | None:
    left = vi.result.left_dir or vi.view.left_dir
    if left in ("nord", "sued"):
        return "y"
    if left in ("ost", "west"):
        return "x"
    return None


def build_model(inputs: list[ViewInput], overrides: dict[str, Override], active_stand: str | None) -> BuildingModel:
    inputs, rev_issues, stands, active = select_revisions(inputs, active_stand)
    lx = Value(key="len:x", label="Außenmaß West–Ost")
    ly = Value(key="len:y", label="Außenmaß Nord–Süd")
    levels: dict[str, Value] = {}
    components: dict[str, list[ComponentObs]] = {}
    clad: dict[str, list[Evidence]] = {}
    issues: list[Issue] = list(rev_issues)
    price_notes: list[PriceNote] = []
    rect_votes: list[bool] = []
    area_obs: list[AreaObs] = []
    side_txt = {"oben": "oben", "unten": "unten", "links": "links", "rechts": "rechts", None: ""}

    for vi in inputs:
        r, v = vi.result, vi.view
        t = v.title
        for note in r.notes:
            issues.append(Issue(key=f"note:{v.id}:{note[:30]}", kind="hinweis", text=f"{t}: {note}",
                                evidence=[]))
        price_notes.extend(r.price_notes)
        area_obs.extend(r.area_statements)
        if v.view_type == "grundriss" and r.rectangular is not None:
            rect_votes.append(r.rectangular)
        # Außenmaße
        for ch in r.chains:
            if ch.refers_to != "gebaeude_aussen":
                continue
            if v.view_type == "grundriss":
                target = lx if ch.direction == "horizontal" else ly
            elif v.view_type == "ansicht" and ch.direction == "horizontal" and (r.facade or v.facade):
                target = lx if (r.facade or v.facade) in ("nord", "sued") else ly
            elif v.view_type == "schnitt" and ch.direction == "horizontal" and ch.role == "gesamtmass":
                ax = _schnitt_axis(vi)
                target = lx if ax == "x" else ly if ax == "y" else None
            else:
                target = None
            if target is None or not ch.segments:
                continue
            vals = [m.value for m in ch.segments]
            ev = [e for m in ch.segments for e in _measure_ev(m)]
            where = f"{t} {side_txt[ch.side]}".strip()
            if len(ch.segments) == 1:
                _add(target.candidates, vals[0], ch.segments[0].raw_text, ev, f"Gesamtmaß {where}")
            elif all(x is not None for x in vals):
                total = round(sum(vals), 6)
                _add(target.candidates, total, " + ".join(m.raw_text for m in ch.segments), ev, f"Summe Maßkette {where}")
            else:
                issues.append(Issue(key=f"chain-unreadable:{v.id}:{ch.side}", kind="hinweis",
                                    text=f"{t}: Maßkette {side_txt[ch.side]} enthält unlesbare Werte – nicht summiert.", evidence=ev))
        # Koten
        for lv in r.levels:
            for ref in lv.refs:
                if ref == "sonstige":
                    continue
                val = levels.setdefault(ref, Value(key=f"level:{ref}", label=LEVEL_LABEL.get(ref, ref)))
                _add(val.candidates, lv.measure.value, lv.measure.raw_text, _measure_ev(lv.measure), t)
        # Bauteile
        for c in r.components:
            components.setdefault(c.component, []).append(c)
            if c.component == "bekleidung":
                ev = [c.evidence] if c.evidence else []
                facs = list(c.facades)
                if c.all_around:
                    facs = ["nord", "sued", "ost", "west"]
                for f in facs:
                    clad.setdefault(f, []).extend(ev)

    model = BuildingModel(
        length_x=_finalize(lx, overrides, "Welches Außenmaß hat das Gebäude in West–Ost-Richtung?"),
        length_y=_finalize(ly, overrides, "Welches Außenmaß hat das Gebäude in Nord–Süd-Richtung?"),
        rectangular=(all(rect_votes) if rect_votes else None),
        levels={k: _finalize(v, overrides) for k, v in levels.items()},
        components=components, clad_facades=clad, stands=stands, active_stand=active,
        used_views=[vi.view.id for vi in inputs], price_notes=price_notes,
    )
    openings, op_issues = merge_openings(inputs, overrides)
    model.openings = openings
    issues.extend(op_issues)
    roofs = components.get("dach", [])
    forms = {c.roof_form for c in roofs if c.roof_form}
    model.roof_form = forms.pop() if len(forms) == 1 else ("widersprüchlich" if forms else None)
    pitch = Value(key="roof:pitch", label="Dachneigung", unit="°")
    for c in roofs:
        if c.pitch:
            _add(pitch.candidates, c.pitch.value, c.pitch.raw_text, _measure_ev(c.pitch), c.evidence.view_title if c.evidence else "")
    model.roof_pitch = _finalize(pitch, overrides) if pitch.candidates else None

    model.storeys = sorted({vi.view.storey or vi.view.title for vi in inputs if vi.view.view_type == "grundriss"})
    model.area_statements = area_obs
    _building_measures(model, overrides)

    # Fragen und Widersprüche als Issues
    for val in [model.length_x, model.length_y, *model.levels.values(), *[x for x in (model.bgf, model.bri) if x]] + \
               [x for o in model.openings for x in (o.width, o.height)]:
        if val.status == "widerspruch":
            issues.append(Issue(key=val.key, kind="widerspruch", text=val.question or val.label, value_key=val.key,
                                evidence=val.evidence))
        elif val.status == "fehlt" and val.question:
            issues.append(Issue(key=val.key, kind="frage", text=val.question, value_key=val.key, evidence=[]))
    for pn in price_notes:
        issues.append(Issue(key=f"price-note:{pn.evidence.id if pn.evidence else pn.text}", kind="hinweis",
                            text=f"Kostenangabe im Plan: „{pn.text}“ – wird nur verwendet, wenn Betrag und Leistung "
                                 "eindeutig zusammengehören (bitte im Katalog als Planpreis anlegen).",
                            evidence=[pn.evidence] if pn.evidence else []))
    model.issues = issues
    return model


# ----------------------------------------------------------------------------------------
# Gebäudemengen BGF und BRI (DIN 277) für die Bauwerksorientierung
# ----------------------------------------------------------------------------------------

def _fmt(x: float | None) -> str:
    return format_de(x)


def _qi(name: str, v: Value | None, unit: str = "m") -> QuantityInput:
    if v is None:
        return QuantityInput(name=name, value=None, unit=unit)
    raw = " / ".join(sorted({c.raw_text for c in v.candidates}))
    return QuantityInput(name=name, value=v.value, unit=unit, value_key=v.key, raw_text=raw, evidence=v.evidence)


def calc_bgf(m: BuildingModel) -> CalcInfo:
    """BGF einfacher geschlossener Neubauten: Summe der Bruttoflächen der Ebenen aus belegten Außenmaßen."""
    c = CalcInfo(inputs=[_qi("Außenmaß West–Ost", m.length_x), _qi("Außenmaß Nord–Süd", m.length_y)])
    lx, ly = m.length_x.value, m.length_y.value
    if lx is None or ly is None:
        c.notes.append("Außenmaße nicht vollständig belegt – BGF nicht berechenbar.")
        return c
    if m.rectangular is not True:
        c.notes.append("Rechteckige Außenkontur nicht belegt – BGF zur Prüfung (Rücksprünge einzeln erfassen).")
        return c
    if len(m.storeys) != 1:
        c.notes.append(f"{len(m.storeys)} Grundrissebenen ({', '.join(m.storeys) or '–'}): BGF je Ebene aus eigenem "
                       "Grundriss erforderlich – Keller, Dachräume und Lufträume einzeln prüfen.")
        return c
    st = m.storeys[0]
    if re.search(r"\b(UG|KG|DG)\b", st):
        c.notes.append(f"Einzige Ebene ist „{st}“ – Zuordnung prüfen.")
        return c
    c.value = lx * ly
    c.formula = f"BGF (1 Ebene: {st}, Außenmaße) = {_fmt(lx)} m × {_fmt(ly)} m = {_fmt(c.value)} m²"
    c.notes.append("Bruttofläche einer Ebene aus den äußeren Maßen der Baukonstruktion; weitere Ebenen sind im Plansatz nicht belegt.")
    return c


def calc_bri(m: BuildingModel, bgf_calc: CalcInfo) -> CalcInfo:
    """BRI aus Außenkontur × vertikaler Begrenzung im Schnitt (UK Bodenplatte bis OK Dachbelag)."""
    low, top = m.levels.get("uk_bodenplatte"), m.levels.get("ok_dach")
    c = CalcInfo(inputs=list(bgf_calc.inputs) + [_qi("Kote UK Bodenplatte (Unterfläche Bauwerkssohle)", low),
                                                  _qi("Kote OK Dachbelag (obere Begrenzung)", top)])
    if bgf_calc.value is None:
        c.notes.append("Grundfläche der Außenkontur nicht belegt – BRI nicht berechenbar.")
        return c
    if m.roof_form not in ("flachdach",):
        c.notes.append(f"Dachform „{m.roof_form or 'unbekannt'}“: Volumen des Dachraums einzeln prüfen – BRI nicht automatisch.")
        return c
    if low is None or low.value is None:
        c.notes.append("Untere Begrenzung (UK Bodenplatte) im Schnitt nicht belegt" + (" bzw. widersprüchlich" if low else "") + ".")
        return c
    if top is None or top.value is None:
        hint = " (nur OK Attika belegt – Attika/Brüstung ist keine Dachbegrenzung)" if "ok_attika" in m.levels else ""
        c.notes.append("Obere Begrenzung (OK Dachbelag) im Schnitt nicht belegt" + hint + ".")
        return c
    h = top.value - low.value
    if h <= 0:
        c.notes.append("Kotendifferenz nicht positiv – prüfen.")
        return c
    c.value = bgf_calc.value * h
    c.formula = (f"BRI = {_fmt(m.length_x.value)} m × {_fmt(m.length_y.value)} m × ({_fmt(top.value)} − ({_fmt(low.value)})) m "
                 f"= {_fmt(bgf_calc.value)} m² × {_fmt(h)} m = {_fmt(c.value)} m³")
    c.notes.append("Vertikale Begrenzung: UK Bodenplatte bis OK Dachbelag; Attika nicht eingerechnet – Bezugsgrenzen prüfen.")
    return c


def _building_measures(m: BuildingModel, overrides: dict[str, Override]) -> None:
    m.bgf_calc = calc_bgf(m)
    m.bri_calc = calc_bri(m, m.bgf_calc)
    for key, label, unit, calc in (("bgf", "BGF (Brutto-Grundfläche)", "m²", m.bgf_calc),
                                   ("bri", "BRI (Brutto-Rauminhalt)", "m³", m.bri_calc)):
        v = Value(key=key, label=label, unit=unit)
        # 1) eindeutig bezeichnete Angabe im Plan (aktiver Planstand) – bevorzugter Beleg
        for a in m.area_statements:
            if a.kind == key and a.measure.value is not None:
                _add(v.candidates, a.measure.value, a.measure.raw_text, _measure_ev(a.measure),
                     f"{key.upper()}-Angabe im Plan ({a.measure.evidence.view_title if a.measure.evidence else ''})")
        # 2) Rechenweg aus Planmaßen
        if calc.value is not None:
            ev = [e for i in calc.inputs for e in i.evidence]
            _add(v.candidates, calc.value, calc.formula, ev, "berechnet aus Planmaßen")
        setattr(m, key, _finalize(v, overrides, f"Welche {key.upper()} hat das Gebäude? (Rechenweg offen: "
                                                 f"{'; '.join(calc.notes) or 'Maße fehlen'})"))
