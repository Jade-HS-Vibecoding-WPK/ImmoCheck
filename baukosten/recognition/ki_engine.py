"""KI-Erkennung mit einem bildfähigen Claude-Modell (offizielles Anthropic-Python-SDK).

Ablauf je Ansichtsbereich:
1. Übersichtsbild (+ bei dichter Bemaßung Kacheln in höherer Auflösung) rendern.
2. PDF-Textebene des Bereichs mit IDs und Pixelpositionen beilegen.
3. Strukturierte Antwort (Pydantic-Schema ``KIErgebnis``) anfordern und validieren.
4. Text-IDs bzw. Pixelrechtecke auf Seitenkoordinaten zurückprojizieren
   (Ausschnitt, Zoom und Seitendrehung werden berücksichtigt) und Maße in Python normalisieren.

Die KI liefert ausschließlich Beobachtungen. Mengen rechnet sie nicht.
Konfiguration auf dem Server: ANTHROPIC_API_KEY, ANTHROPIC_MODEL (Standard: claude-opus-5-5).
"""
from __future__ import annotations

import base64
import os
from typing import Literal

import pymupdf
from pydantic import BaseModel, Field

from ..models import (AreaObs, BBox, ComponentObs, DimChain, DocumentInfo, Evidence, Facade, LevelObs, LevelRef, Measure,
                      OpeningObs, PriceNote, ViewRegion, ViewResult)
from ..pdf_prep import PageGeometry, RenderInfo, page_to_px, plan_images, px_to_page
from ..units import parse_measure, parse_quantity

ENGINE = "ki"
PROMPT_VERSION = "ki-4"
DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_MODELS = {"claude-opus-5-5", "claude-fable-5-2", "claude-fable-5-1", "claude-opus-5", "claude-sonnet-5-5"}


def configured_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "").strip() or DEFAULT_MODEL


def configured_effort() -> str:
    return os.environ.get("ANTHROPIC_EFFORT", "").strip() or "high"


def api_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip() or os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip())


# ----------------------------------------------------------------------------------------
# Antwortschema (alle Felder Pflicht, ggf. null) – wird von der API erzwungen und lokal validiert
# ----------------------------------------------------------------------------------------


class KIWert(BaseModel):
    text_id: str | None = Field(description="ID des PDF-Textes (z. B. 't12'), wenn die Zahl als PDF-Text gelistet ist, sonst null")
    original: str = Field(description="Originalschreibweise exakt wie im Plan, z. B. '1,50', '150', '+3,00'. Leer, wenn unleserlich.")
    bild: int | None = Field(description="Nummer des Bildes, auf das sich 'box' bezieht (1 = Übersicht)")
    box: list[float] | None = Field(description="[x0, y0, x1, y1] in Pixeln im angegebenen Bild, nur wenn kein text_id vorhanden")


class KIKette(BaseModel):
    richtung: Literal["horizontal", "vertikal"]
    lage: Literal["oben", "unten", "links", "rechts", "innen"]
    art: Literal["gesamtmass", "kette"] = Field(description="gesamtmass = ein einzelnes Maß über die ganze Gebäudeseite")
    bezug: Literal["gebaeude_aussen", "oeffnungen", "hoehen", "sonstiges"] = Field(
        description="gebaeude_aussen: Kette läuft von Außenkante zu Außenkante des Gebäudes")
    werte: list[KIWert] = Field(description="Einzelmaße der Kette in Reihenfolge (links->rechts bzw. oben->unten)")


class KIKote(BaseModel):
    wert: KIWert
    bezeichnung: str = Field(description="Beschriftung der Kote im Original, z. B. 'OK Attika / OK Bekleidung'")
    bezug: list[LevelRef]


class KIOeffnung(BaseModel):
    kennung: str | None = Field(description="Kennung wie im Plan, z. B. 'F01'. Gleiche Kennungen können mehrfach vorkommen.")
    art: Literal["fenster", "tuer", "fenstertuer", "unbekannt"]
    fassade: Facade | None = Field(description="Himmelsrichtung der Außenwand, in der die Öffnung liegt")
    bild: int | None
    box: list[float] | None = Field(description="[x0,y0,x1,y1] Pixel des Öffnungssymbols im Bild")
    breite: KIWert | None = Field(description="Maß der Öffnungsbreite, nur wenn eindeutig dieser Öffnung zugeordnet")
    hoehe: KIWert | None = Field(description="Lichte Öffnungshöhe (Unterkante bis Oberkante Öffnung). NICHT die Brüstungshöhe.")
    bruestung: KIWert | None = Field(description="Brüstungshöhe (BRH), getrennt von der Öffnungshöhe")


class KIBauteil(BaseModel):
    bauteil: Literal["bodenplatte", "dach", "bekleidung", "aussenwand", "sockel", "sonstiges"]
    beschreibung: str = Field(description="Beschriftung/Leistungsbeschreibung im Original")
    material: str
    buendig_mit_aussenkontur: bool | None = Field(description="true nur wenn im Plan ausdrücklich bündig/deckungsgleich/ohne Überstand belegt")
    ueberstand: KIWert | None
    dachform: Literal["flachdach", "satteldach", "pultdach", "sonstiges"] | None
    neigung_grad: KIWert | None
    fassaden: list[Facade] = Field(description="Fassadenseiten, für die das Bauteil (z. B. Bekleidung) in dieser Zeichnung belegt ist")
    umlaufend: bool
    bis_kote: LevelRef | None
    quelle: KIWert | None = Field(description="Text-ID der Beschriftung")


class KIFlaechenangabe(BaseModel):
    art: Literal["bgf", "bri", "nuf", "nrf", "wohnflaeche", "sonstige"] = Field(
        description="Nur 'bgf'/'bri', wenn ausdrücklich als BGF/Brutto-Grundfläche bzw. BRI/Brutto-Rauminhalt bezeichnet")
    bezeichnung: str = Field(description="Beschriftung im Original, z. B. 'BGF = 96,00 m²'")
    wert: KIWert


class KIErgebnis(BaseModel):
    zeichnungsart: Literal["grundriss", "ansicht", "schnitt", "sonstiges"]
    titel: str
    geschoss: str | None
    fassade: Facade | None = Field(description="nur bei Ansichten: dargestellte Fassadenseite")
    links_himmelsrichtung: Facade | None = Field(description="Ansicht/Schnitt: Himmelsrichtung am linken Rand der Zeichnung")
    norden_oben: bool | None = Field(description="Grundriss: zeigt der Nordpfeil nach oben?")
    gebaeude_box: list[float] | None = Field(description="[x0,y0,x1,y1] Pixel der Gebäudeaußenkontur in Bild 1")
    grundriss_rechteckig: bool | None
    ketten: list[KIKette]
    koten: list[KIKote]
    oeffnungen: list[KIOeffnung]
    bauteile: list[KIBauteil]
    kostenangaben: list[KIWert]
    flaechenangaben: list[KIFlaechenangabe] = Field(description="Beschriftete Flächen-/Rauminhaltsangaben (BGF, BRI, NUF, NRF, Wohnfläche)")
    hinweise: list[str] = Field(description="Unklarheiten, unleserliche Stellen, Annahmen")


SYSTEM_PROMPT = """Du bist Bauzeichner/-in und liest Architekturpläne (deutsche Bemaßung) für eine Kostenermittlung nach DIN 276.
Du lieferst ausschließlich BEOBACHTUNGEN aus genau dieser Zeichnung – keine Mengen, keine Flächen, keine Preise, keine Annahmen.

Regeln:
- Übernimm Zahlen in Originalschreibweise ('1,50', '150', '+3,00', '±0,00'). Rechne nicht um. Unleserlich -> original = "".
- Wenn eine Zahl in der Liste 'PDF-Text' steht, gib ihre text_id an (bevorzugt). Nur sonst: Bildnummer und Pixelbox.
- Maßketten: ordne jedes Maß der richtigen Kette zu. Eine Kette mit Einzelmaßen und ihr Gesamtmaß sind getrennte Ketten
  (art 'kette' bzw. 'gesamtmass'); beide belegen dieselbe Gebäudelänge. 'gebaeude_aussen' nur, wenn die Kette von
  Außenkante zu Außenkante des Gebäudes läuft.
- Höhenkoten: Zahl mit Vorzeichen; Bezug aus der Beschriftung (z. B. 'OK Attika / OK Bekleidung' -> ok_attika und ok_bekleidung).
- Öffnungen: jede gebaute Öffnung einzeln aufführen, auch wenn das Typkürzel (z. B. F01) mehrfach vorkommt.
  Breite/Höhe nur angeben, wenn das Maß eindeutig zu dieser Öffnung gehört. Die Brüstungshöhe ist KEINE Fensterhöhe.
  Box = Lage des Öffnungssymbols (dient nur der Zuordnung zwischen Zeichnungen).
- Grundriss: Fassade einer Öffnung aus der Lage an der Außenwand und dem Nordpfeil bestimmen.
- Ansicht: links_himmelsrichtung angeben (z. B. Ansicht Süd: links = West).
- Bauteile: nur belegte Angaben (Beschriftung, Legende). buendig_mit_aussenkontur nur bei ausdrücklichem Nachweis.
- Kostenangaben (€-Beträge) im Plan nur auflisten, nie interpretieren.
- Flächenangaben: BGF/BRI nur, wenn ausdrücklich so beschriftet. NUF, NRF, Wohnfläche, Dachfläche usw. sind KEINE BGF.
- Unsicherheiten in 'hinweise' benennen."""


def _b64(png: bytes) -> str:
    return base64.standard_b64encode(png).decode("ascii")


def build_request(pdf: pymupdf.Document, view: ViewRegion, geo: PageGeometry) -> tuple[list[dict], list[RenderInfo], dict[str, object]]:
    region = geo.in_region(view.bbox)
    images = plan_images(pdf, view, region.spans)
    content: list[dict] = []
    infos: list[RenderInfo] = []
    for n, (png, info) in enumerate(images, 1):
        infos.append(info)
        content.append({"type": "text", "text": f"Bild {n}: {info.label} ({info.width_px}×{info.height_px} px)"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64(png)}})
    span_map = {s.id: s for s in region.spans}
    lines = []
    for s in region.spans[:600]:
        x0, y0, x1, y1 = page_to_px(infos[0], s.bbox)
        lines.append(f"{s.id} | {s.text!r} | Bild 1 px [{x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}] | {'waagrecht' if s.dir == 'h' else 'senkrecht'}")
    hint = (f"Vorläufige Einordnung durch Layoutanalyse: {view.view_type}, Titel '{view.title}'"
            f"{', Fassade ' + view.facade if view.facade else ''}{', Maßstab ' + view.scale if view.scale else ''}. "
            "Prüfe und korrigiere, falls falsch.")
    content.append({"type": "text", "text": hint + "\n\nPDF-Text dieses Bereichs (ID | Text | Lage | Richtung):\n" +
                    ("\n".join(lines) if lines else "(keine Textebene – nur Bild auswerten)") +
                    "\n\nLiefere die Beobachtungen dieser Zeichnung im vorgegebenen Schema."})
    return content, infos, span_map


class KIError(RuntimeError):
    """Fehler eines einzelnen Erkennungsschritts (kann gezielt wiederholt werden)."""


def call_model(client, content: list[dict], model: str | None = None) -> KIErgebnis:
    model = model or configured_model()
    kwargs = dict(model=model, max_tokens=16000, system=SYSTEM_PROMPT,
                  messages=[{"role": "user", "content": content}], output_format=KIErgebnis,
                  thinking={"type": "adaptive"}, output_config={"effort": configured_effort()})
    if model in FALLBACK_MODELS:
        resp = client.beta.messages.parse(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    else:
        resp = client.messages.parse(**kwargs)
    if resp.stop_reason == "refusal":
        raise KIError(f"Anfrage vom Modell abgelehnt ({getattr(resp, 'stop_details', None)})")
    if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
        raise KIError(f"Keine vollständige strukturierte Antwort (stop_reason={resp.stop_reason}).")
    return KIErgebnis.model_validate(resp.parsed_output.model_dump())


# ----------------------------------------------------------------------------------------
# Rückprojektion und Umwandlung in Beobachtungen
# ----------------------------------------------------------------------------------------


class _Resolver:
    def __init__(self, doc: DocumentInfo, view: ViewRegion, infos: list[RenderInfo], spans: dict):
        self.doc, self.view, self.infos, self.spans = doc, view, infos, spans
        self.n = 0
        self.notes: list[str] = []

    def _info(self, bild: int | None) -> RenderInfo | None:
        if bild is None:
            return self.infos[0]
        if 1 <= bild <= len(self.infos):
            return self.infos[bild - 1]
        return None

    def ev_box(self, bild: int | None, box: list[float] | None, text: str, note: str = "") -> Evidence | None:
        info = self._info(bild)
        if info is None or not box or len(box) != 4:
            return None
        b = px_to_page(info, box)
        self.n += 1
        return Evidence(id=f"{self.view.id}:ki{self.n}", doc_id=self.doc.id, file_name=self.doc.file_name, page=self.view.page,
                        view_id=self.view.id, view_title=self.view.title, text=text, bbox=b, source="ki_bild", note=note)

    def measure(self, w: KIWert | None, default_unit: str = "m") -> Measure | None:
        if w is None:
            return None
        span = self.spans.get(w.text_id or "")
        if span is not None:
            raw = span.text
            if w.original and w.original.replace(" ", "") != raw.replace(" ", ""):
                self.notes.append(f"KI-Lesung '{w.original}' weicht von PDF-Text '{raw}' ab – PDF-Text verwendet.")
            ev = Evidence(id=f"{self.view.id}:{span.id}", doc_id=self.doc.id, file_name=self.doc.file_name, page=self.view.page,
                          view_id=self.view.id, view_title=self.view.title, text=raw, bbox=span.bbox, source="pdf_text")
        else:
            raw = w.original or ""
            ev = self.ev_box(w.bild, w.box, raw)
            if ev is None and raw:
                self.notes.append(f"Wert '{raw}' ohne Fundstelle geliefert – verworfen.")
                return None
        pm = parse_measure(raw, default_unit)
        return Measure(raw_text=raw, value=pm.value_m, unit=pm.unit, unit_explicit=pm.unit_explicit, evidence=ev)


def to_view_result(k: KIErgebnis, doc: DocumentInfo, view: ViewRegion, infos: list[RenderInfo], spans: dict, model: str) -> ViewResult:
    rs = _Resolver(doc, view, infos, spans)
    vt = view.view_type if view.user_corrected else (k.zeichnungsart if k.zeichnungsart != "sonstiges" else view.view_type)
    res = ViewResult(view_id=view.id, engine=f"{ENGINE}:{model}", view_type=vt, title=view.title or k.titel,
                     storey=view.storey or k.geschoss, facade=view.facade if view.user_corrected else (k.fassade or view.facade),
                     left_dir=view.left_dir if view.user_corrected else (k.links_himmelsrichtung or view.left_dir),
                     rectangular=k.grundriss_rechteckig)
    if k.zeichnungsart != view.view_type and k.zeichnungsart != "sonstiges":
        res.notes.append(f"KI ordnet den Bereich als „{k.zeichnungsart}“ ein (Layoutanalyse: „{view.view_type}“).")
    if vt == "grundriss" and k.norden_oben is False:
        res.notes.append("Nordpfeil zeigt nicht nach oben – Fassadenzuordnung der Öffnungen bitte prüfen.")
    outline = px_to_page(infos[0], k.gebaeude_box) if k.gebaeude_box and len(k.gebaeude_box) == 4 else None
    res.outline = outline
    for ch in k.ketten:
        segs = [m for m in (rs.measure(w) for w in ch.werte) if m is not None]
        res.chains.append(DimChain(direction=ch.richtung, side=None if ch.lage == "innen" else ch.lage,
                                   role=ch.art, refers_to=ch.bezug, segments=segs))
    for kt in k.koten:
        m = rs.measure(kt.wert)
        if m is not None:
            if m.evidence:
                m.evidence.note = kt.bezeichnung
            res.levels.append(LevelObs(measure=m, refs=kt.bezug or ["sonstige"], label_raw=kt.bezeichnung))
    for o in k.oeffnungen:
        sym = rs.ev_box(o.bild, o.box, o.kennung or "Öffnung", note="Öffnungssymbol (KI)")
        pos = None
        if sym is not None and outline is not None and outline.w > 0 and outline.h > 0:
            horizontal = vt == "ansicht" or (o.fassade in ("nord", "sued"))
            if horizontal:
                pos = ((sym.bbox.x0 - outline.x0) / outline.w, (sym.bbox.x1 - outline.x0) / outline.w)
            else:
                pos = ((sym.bbox.y0 - outline.y0) / outline.h, (sym.bbox.y1 - outline.y0) / outline.h)
            pos = (max(0.0, min(1.0, pos[0])), max(0.0, min(1.0, pos[1])))
        res.openings.append(OpeningObs(label=(o.kennung or "").replace(" ", "").upper() or None, kind=o.art,
                                       facade=o.fassade if vt != "ansicht" else (res.facade or o.fassade),
                                       pos_in_view=pos if vt in ("grundriss", "ansicht") else None,
                                       width=rs.measure(o.breite) if vt != "schnitt" else None,
                                       height=rs.measure(o.hoehe), sill=rs.measure(o.bruestung), symbol=sym))
    for b in k.bauteile:
        src = rs.measure(b.quelle) if b.quelle else None
        ev = src.evidence if src else None
        if ev is not None:
            ev.text = b.beschreibung or ev.text
        pitch = rs.measure(b.neigung_grad, default_unit="m")
        if pitch is not None and pitch.raw_text:
            try:
                pitch.value = float(pitch.raw_text.replace("°", "").replace(",", ".").strip())
                pitch.unit = "grad"
            except ValueError:
                pitch.value = None
        res.components.append(ComponentObs(
            component=b.bauteil if b.bauteil in ("bodenplatte", "dach", "bekleidung", "aussenwand", "sockel") else "sonstiges",
            description=b.beschreibung, material=b.material or b.beschreibung, flush_with_outline=b.buendig_mit_aussenkontur,
            overhang=rs.measure(b.ueberstand), roof_form=b.dachform, pitch=pitch, facades=list(b.fassaden),
            all_around=b.umlaufend, to_level=b.bis_kote, evidence=ev))
    for w in k.kostenangaben:
        m = rs.measure(w)
        res.price_notes.append(PriceNote(text=w.original, evidence=m.evidence if m else None))
    for fa in k.flaechenangaben:
        m = rs.measure(fa.wert)
        if m is None:
            continue
        val, unit = parse_quantity(m.raw_text or fa.bezeichnung)
        if val is None:
            val, unit = parse_quantity(fa.bezeichnung)
        m.value, m.unit = val, unit or ""
        res.area_statements.append(AreaObs(kind=fa.art, measure=m, label_raw=fa.bezeichnung))
    res.notes.extend(k.hinweise)
    res.notes.extend(rs.notes)
    return res


def analyze_view(pdf: pymupdf.Document, doc: DocumentInfo, view: ViewRegion, geo: PageGeometry, client=None,
                 model: str | None = None) -> ViewResult:
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    model = model or configured_model()
    content, infos, spans = build_request(pdf, view, geo)
    k = call_model(client, content, model)
    return to_view_result(k, doc, view, infos, spans, model)
