"""Pydantic-Datenmodelle: Fundstellen, Ansichtsbereiche, Beobachtungen, Mengen, Kosten, Projektstand."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ViewType = Literal["grundriss", "ansicht", "schnitt", "plankopf", "legende", "sonstiges"]
Facade = Literal["nord", "sued", "ost", "west"]
Side = Literal["oben", "unten", "links", "rechts"]

FACADE_LABEL = {"nord": "Nord", "sued": "Süd", "ost": "Ost", "west": "West"}

# Kontrollierte Bezüge für Höhenkoten
LevelRef = Literal[
    "ok_bekleidung",
    "uk_bekleidung",
    "ok_attika",
    "ok_dach",
    "ok_bodenplatte",
    "uk_bodenplatte",
    "ok_fertigfussboden",
    "ok_rohdecke",
    "traufe",
    "first",
    "gelaende",
    "sonstige",
]

LEVEL_LABEL = {
    "ok_bekleidung": "OK Bekleidung",
    "uk_bekleidung": "UK Bekleidung",
    "ok_attika": "OK Attika",
    "ok_dach": "OK Dach",
    "ok_bodenplatte": "OK Bodenplatte",
    "uk_bodenplatte": "UK Bodenplatte",
    "ok_fertigfussboden": "OK Fertigfußboden",
    "ok_rohdecke": "OK Rohdecke",
    "traufe": "Traufe",
    "first": "First",
    "gelaende": "Gelände",
    "sonstige": "sonstige Kote",
}


class BBox(BaseModel):
    """Rechteck in PDF-Punkten, bezogen auf die *unrotierte* Seite (wie PyMuPDF es speichert)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    def contains_point(self, x: float, y: float, tol: float = 0.0) -> bool:
        return self.x0 - tol <= x <= self.x1 + tol and self.y0 - tol <= y <= self.y1 + tol

    def intersects(self, other: "BBox") -> bool:
        return not (other.x1 < self.x0 or other.x0 > self.x1 or other.y1 < self.y0 or other.y0 > self.y1)

    @classmethod
    def of(cls, r) -> "BBox":
        return cls(x0=float(r[0]), y0=float(r[1]), x1=float(r[2]), y1=float(r[3]))


class Evidence(BaseModel):
    """Planfundstelle: Datei, Seite, Ansichtsbereich, Originaltext/Symbol und Markierungsrechteck."""

    id: str
    doc_id: str
    file_name: str
    page: int  # 0-basiert
    view_id: str | None = None
    view_title: str = ""
    text: str = ""
    bbox: BBox
    source: Literal["pdf_text", "ki_bild", "vektor", "manuell"] = "pdf_text"
    note: str = ""


class Measure(BaseModel):
    """Eine gelesene Zahl samt Originalschreibweise, Normalisierung und Fundstelle."""

    raw_text: str
    value: float | None = None  # normalisiert (m bzw. Grad)
    unit: str = "m"
    unit_explicit: bool = False
    evidence: Evidence | None = None


# --------------------------------------------------------------------------------------
# Beobachtungen je Ansichtsbereich (gemeinsames Ausgabeformat aller Erkennungsverfahren)
# --------------------------------------------------------------------------------------


class DimChain(BaseModel):
    """Maßkette entlang einer Gebäudeseite in einer Zeichnung."""

    direction: Literal["horizontal", "vertikal"]
    side: Side | None = None  # Lage der Kette relativ zum Gebäude in der Zeichnung
    role: Literal["gesamtmass", "kette"] = "kette"
    refers_to: Literal["gebaeude_aussen", "oeffnungen", "hoehen", "sonstiges"] = "gebaeude_aussen"
    segments: list[Measure] = Field(default_factory=list)
    # Lage der Segmente relativ zum Gebäudeumriss (0..1 entlang der Richtung), falls bekannt
    spans: list[tuple[float, float]] | None = None


class LevelObs(BaseModel):
    measure: Measure
    refs: list[LevelRef]
    label_raw: str = ""


class OpeningObs(BaseModel):
    label: str | None = None  # z. B. "F01" (Typkürzel, kann mehrfach vorkommen)
    kind: Literal["fenster", "tuer", "fenstertuer", "unbekannt"] = "fenster"
    facade: Facade | None = None
    # Lage entlang der Fassade als Anteil (0..1) in der *Zeichnung* von links nach rechts
    # bzw. (Grundriss) bezogen auf die Gebäudekante. Nur zur Zuordnung, nie zur Mengenbildung.
    pos_in_view: tuple[float, float] | None = None
    width: Measure | None = None
    height: Measure | None = None
    sill: Measure | None = None  # Brüstungshöhe (keine Fensterhöhe!)
    symbol: Evidence | None = None


class ComponentObs(BaseModel):
    component: Literal[
        "bodenplatte", "dach", "bekleidung", "aussenwand", "fenster", "tuer", "sockel", "sonstiges"
    ]
    description: str = ""
    material: str = ""
    flush_with_outline: bool | None = None  # bündig/deckungsgleich mit Außenkontur belegt
    overhang: Measure | None = None
    roof_form: Literal["flachdach", "satteldach", "pultdach", "sonstiges"] | None = None
    pitch: Measure | None = None
    facades: list[Facade] = Field(default_factory=list)  # z. B. Bekleidung auf diesen Seiten
    all_around: bool = False  # "umlaufend"
    from_level: LevelRef | None = None
    to_level: LevelRef | None = None
    evidence: Evidence | None = None


class AreaObs(BaseModel):
    """Beschriftete Flächen-/Rauminhaltsangabe im Plan (z. B. „BGF = 96,00 m²“). NUF/NRF/Wohnfläche
    werden nur notiert und nie als BGF verwendet."""

    kind: Literal["bgf", "bri", "nuf", "nrf", "wohnflaeche", "sonstige"]
    measure: Measure
    label_raw: str = ""


class PriceNote(BaseModel):
    text: str
    evidence: Evidence | None = None


class ViewResult(BaseModel):
    """Beobachtungen eines Ansichtsbereichs. Enthält keine Mengen."""

    view_id: str
    engine: str
    view_type: ViewType
    title: str = ""
    storey: str | None = None
    facade: Facade | None = None
    left_dir: Facade | None = None  # Himmelsrichtung am linken Zeichnungsrand (Ansicht/Schnitt)
    outline: BBox | None = None
    rectangular: bool | None = None
    chains: list[DimChain] = Field(default_factory=list)
    levels: list[LevelObs] = Field(default_factory=list)
    openings: list[OpeningObs] = Field(default_factory=list)
    components: list[ComponentObs] = Field(default_factory=list)
    price_notes: list[PriceNote] = Field(default_factory=list)
    area_statements: list[AreaObs] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Dokumente und Ansichtsbereiche
# --------------------------------------------------------------------------------------


class ViewRegion(BaseModel):
    id: str
    doc_id: str
    page: int
    bbox: BBox
    view_type: ViewType = "sonstiges"
    title: str = ""
    storey: str | None = None
    facade: Facade | None = None
    left_dir: Facade | None = None
    scale: str | None = None
    confidence: float = 0.5
    user_corrected: bool = False
    include: bool = True


class PageInfo(BaseModel):
    index: int
    width: float
    height: float
    rotation: int = 0
    plan_number: str | None = None
    plan_stand: str | None = None  # Revisionsstand, z. B. "Index a · 10.11.2026"
    plan_title: str | None = None
    project_name: str | None = None
    views: list[ViewRegion] = Field(default_factory=list)


class DocumentInfo(BaseModel):
    id: str  # Inhalts-Hash (kurz)
    sha256: str
    file_name: str
    stored_path: str
    uploaded_at: datetime = Field(default_factory=datetime.now)
    pages: list[PageInfo] = Field(default_factory=list)
    duplicate_names: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Zusammengeführtes Gebäudemodell
# --------------------------------------------------------------------------------------


class Candidate(BaseModel):
    value: float
    raw_text: str
    evidence: list[Evidence] = Field(default_factory=list)
    origin: str = ""  # z. B. "Gesamtmaß", "Summe Maßkette", "Ansicht", "manuell"


class Value(BaseModel):
    """Ein zusammengeführtes Einzelmaß mit allen Belegen."""

    key: str
    label: str
    unit: str = "m"
    candidates: list[Candidate] = Field(default_factory=list)
    chosen: float | None = None
    status: Literal["ok", "widerspruch", "fehlt", "manuell"] = "fehlt"
    question: str | None = None

    @property
    def value(self) -> float | None:
        return self.chosen if self.status in ("ok", "manuell") else None

    @property
    def evidence(self) -> list[Evidence]:
        out: list[Evidence] = []
        for c in self.candidates:
            out.extend(c.evidence)
        return out


class Opening(BaseModel):
    id: str  # stabil: Fassade + Reihenfolge, z. B. "sued-1"
    label: str | None
    kind: Literal["fenster", "tuer", "fenstertuer", "unbekannt"]
    facade: Facade | None
    pos: tuple[float, float] | None  # Anteil entlang der Fassade (kanonisch: ab West bzw. ab Süd)
    width: Value
    height: Value
    sill: Value
    occurrences: list[Evidence] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)  # Ansichtstitel

    @property
    def area(self) -> float | None:
        if self.width.value is None or self.height.value is None:
            return None
        return self.width.value * self.height.value


class Issue(BaseModel):
    key: str
    kind: Literal["frage", "widerspruch", "revision", "hinweis", "pruefen"]
    text: str
    value_key: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class BuildingModel(BaseModel):
    length_x: Value  # West–Ost
    length_y: Value  # Nord–Süd
    rectangular: bool | None = None
    levels: dict[str, Value] = Field(default_factory=dict)
    openings: list[Opening] = Field(default_factory=list)
    components: dict[str, list[ComponentObs]] = Field(default_factory=dict)
    clad_facades: dict[str, list[Evidence]] = Field(default_factory=dict)
    roof_form: str | None = None
    roof_pitch: Value | None = None
    issues: list[Issue] = Field(default_factory=list)
    active_stand: str | None = None
    stands: list[str] = Field(default_factory=list)
    used_views: list[str] = Field(default_factory=list)
    price_notes: list[PriceNote] = Field(default_factory=list)
    storeys: list[str] = Field(default_factory=list)
    area_statements: list[AreaObs] = Field(default_factory=list)
    bgf: Value | None = None
    bri: Value | None = None
    bgf_calc: CalcInfo | None = None
    bri_calc: CalcInfo | None = None


# --------------------------------------------------------------------------------------
# Mengen, Katalog, Kosten
# --------------------------------------------------------------------------------------


class QuantityInput(BaseModel):
    name: str
    value: float | None
    unit: str
    value_key: str | None = None
    raw_text: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class CalcInfo(BaseModel):
    """Rechenweg einer Gebäudemenge (BGF/BRI) aus Planmaßen."""

    value: float | None = None
    formula: str = ""
    inputs: list[QuantityInput] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Quantity(BaseModel):
    key: str
    bauteil: str  # Anzeige, z. B. "Bodenplatte"
    bauteiltyp: str  # Katalog-Schlüssel, z. B. "bodenplatte"
    ausfuehrung: str = ""  # aus Plan gelesene Ausführung/Material
    kg_hint: str = ""
    values: dict[str, float | None] = Field(default_factory=dict)  # Einheit -> Menge (ungerundet)
    primary_unit: str = "m²"
    formula: str = ""
    inputs: list[QuantityInput] = Field(default_factory=list)
    status: Literal["ok", "pruefen", "offen"] = "ok"
    reasons: list[str] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)


class CatalogEntry(BaseModel):
    id: str
    bauteiltyp: str
    ausfuehrung: str = ""
    kg: str
    leistung: str = ""
    einheit: str
    bezugsgroesse: str = ""
    preis: float
    herkunft: str = ""
    beleg: str = ""
    preisstand: str = ""
    brutto_netto: Literal["brutto", "netto"] = "brutto"
    region: str = ""
    umfasst: str = ""  # Schichten/Leistungen, die der Kennwert vollständig abdeckt (;-getrennt)
    kennwert_art: Literal["bauteil", "gebaeude"] = "bauteil"
    aktiv: bool = True


class CostPosition(BaseModel):
    key: str
    kg: str
    bauteil: str
    quantity: Quantity
    unit: str | None = None
    menge: float | None = None
    entry: CatalogEntry | None = None
    combo: list[CatalogEntry] = Field(default_factory=list)  # bei Kombination mehrerer Kennwerte
    alternatives: list[CatalogEntry] = Field(default_factory=list)
    betrag: float | None = None
    status: Literal["bepreist", "offen", "pruefen", "auswahl"] = "offen"
    reasons: list[str] = Field(default_factory=list)


class CostResult(BaseModel):
    positions: list[CostPosition]
    total: float
    total_label: str
    preisbasis: str
    preisstand: str
    open_count: int
    priced_count: int
    orientation: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Projektstand
# --------------------------------------------------------------------------------------


class Override(BaseModel):
    """Korrektur durch den Nutzer. Der ursprüngliche Beleg bleibt verknüpft."""

    value_key: str
    value: float | None = None
    chosen_evidence_id: str | None = None
    note: str = ""
    original_evidence: list[Evidence] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class ViewRun(BaseModel):
    view_id: str
    engine: str
    cache_key: str
    status: Literal["ok", "fehler", "ausstehend"] = "ausstehend"
    error: str = ""
    finished_at: datetime | None = None


class ProjectState(BaseModel):
    name: str
    building_type: str = ""
    slug: str
    demo: bool = False
    engine: str = "lokal"
    documents: list[DocumentInfo] = Field(default_factory=list)
    runs: dict[str, ViewRun] = Field(default_factory=dict)
    overrides: dict[str, Override] = Field(default_factory=dict)
    price_choices: dict[str, str] = Field(default_factory=dict)  # Positions-Key -> Katalog-ID
    active_stand: str | None = None
    catalog_file: str = "katalog.csv"
    # Bauwerksorientierung (BKI Gebäude Neubau 2026)
    building_category: str | None = None  # vom Nutzer festgelegt; sonst gilt der Vorschlag
    location: str = ""
    regionalfaktor: dict | None = None  # {"region", "faktor", "quelle"} – nur mit Beleg
    netto: bool = False
    kennwert_snapshot: dict[str, dict] = Field(default_factory=dict)  # "Kategorie|BGF" -> verwendeter Kennwert
    created_at: datetime = Field(default_factory=datetime.now)


BuildingModel.model_rebuild()
