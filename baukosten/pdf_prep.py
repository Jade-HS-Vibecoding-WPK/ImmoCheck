"""PDF-Aufbereitung: Text samt Positionen, Vektorgeometrie, Ansichtsbereiche, Plankopf,
Vorschauen, hochaufgelöste Ausschnitte und Markierungen.

Koordinaten: Alle ``BBox``-Werte im Modell sind *Anzeige-Koordinaten* der Seite
(PDF-Punkte, Ursprung oben links, Seitendrehung /Rotate bereits angewendet) – also
genau das, was Nutzer und Bildmodell sehen. PyMuPDF liefert Text und Zeichnungen in
unrotierten Koordinaten; sie werden hier mit ``page.rotation_matrix`` umgerechnet.
Für gerenderte Ausschnitte rechnen ``px_to_page`` / ``page_to_px`` zwischen Bildpixeln
(Ausschnitt + Zoom) und Seitenkoordinaten um.
"""
from __future__ import annotations

import hashlib
import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from .models import BBox, DocumentInfo, PageInfo, ViewRegion

MAX_PX = 1568  # lange Kante je Bild für das Bildmodell


# ----------------------------------------------------------------------------------------
# Grundelemente
# ----------------------------------------------------------------------------------------


@dataclass
class Span:
    id: str
    text: str
    bbox: BBox
    dir: str  # "h" (waagrecht lesbar) oder "v" (um 90° gedreht)
    size: float


@dataclass
class Seg:
    x0: float
    y0: float
    x1: float
    y1: float
    width: float
    dashed: bool = False

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    @property
    def is_h(self) -> bool:
        return abs(self.y1 - self.y0) < 0.5 and abs(self.x1 - self.x0) > 0.5

    @property
    def is_v(self) -> bool:
        return abs(self.x1 - self.x0) < 0.5 and abs(self.y1 - self.y0) > 0.5


@dataclass
class RectShape:
    bbox: BBox
    width: float
    filled: bool


@dataclass
class PageGeometry:
    spans: list[Span] = field(default_factory=list)
    segs: list[Seg] = field(default_factory=list)
    rects: list[RectShape] = field(default_factory=list)
    width: float = 0
    height: float = 0

    def in_region(self, r: BBox, tol: float = 0.5) -> "PageGeometry":
        def inside(b: BBox) -> bool:
            return b.x0 >= r.x0 - tol and b.x1 <= r.x1 + tol and b.y0 >= r.y0 - tol and b.y1 <= r.y1 + tol

        return PageGeometry(
            spans=[s for s in self.spans if r.contains_point(s.bbox.cx, s.bbox.cy)],
            segs=[s for s in self.segs if inside(BBox(x0=min(s.x0, s.x1), y0=min(s.y0, s.y1),
                                                      x1=max(s.x0, s.x1), y1=max(s.y0, s.y1)))],
            rects=[q for q in self.rects if inside(q.bbox)],
            width=self.width,
            height=self.height,
        )


def _tr_rect(r, m) -> BBox:
    rr = pymupdf.Rect(r) * m
    rr.normalize()
    return BBox.of(rr)


def page_geometry(page: pymupdf.Page) -> PageGeometry:
    m = page.rotation_matrix
    geo = PageGeometry(width=page.rect.width, height=page.rect.height)
    n = 0
    d = page.get_text("dict")
    origin = pymupdf.Point(0, 0) * m
    for block in d["blocks"]:
        for ln in block.get("lines", []):
            dx, dy = ln["dir"]
            # Leserichtung in Anzeige-Koordinaten
            v = pymupdf.Point(dx, dy) * m - origin
            ddx, ddy = v.x, v.y
            direction = "h" if abs(ddx) >= abs(ddy) else "v"
            for sp in ln["spans"]:
                t = sp["text"].strip()
                if not t:
                    continue
                geo.spans.append(Span(f"t{n}", t, _tr_rect(sp["bbox"], m), direction, sp["size"]))
                n += 1
    for dr in page.get_drawings():
        w = dr.get("width") or 0.0
        filled = dr.get("fill") is not None
        dashed = bool(dr.get("dashes")) and dr.get("dashes") not in ("[] 0", "[] 0.0")
        # Rechteck aus geschlossenem Linienzug (3–4 Linien, achsparallel) rekonstruieren
        its = dr["items"]
        if 3 <= len(its) <= 4 and all(it[0] == "l" for it in its):
            pts = [pymupdf.Point(p) * m for it in its for p in (it[1], it[2])]
            xs = sorted({round(p.x, 1) for p in pts})
            ys = sorted({round(p.y, 1) for p in pts})
            closed = len(its) == 4 or dr.get("closePath")
            if closed and len(xs) == 2 and len(ys) == 2 and xs[1] - xs[0] > 0.5 and ys[1] - ys[0] > 0.5:
                geo.rects.append(RectShape(BBox(x0=xs[0], y0=ys[0], x1=xs[1], y1=ys[1]), w, filled))
        for it in dr["items"]:
            if it[0] == "l":
                p1, p2 = pymupdf.Point(it[1]) * m, pymupdf.Point(it[2]) * m
                geo.segs.append(Seg(p1.x, p1.y, p2.x, p2.y, w, dashed))
            elif it[0] == "re":
                b = _tr_rect(it[1], m)
                if b.w > 0.5 and b.h > 0.5 and (dr.get("color") is not None or filled):
                    geo.rects.append(RectShape(b, w, filled))
                if dr.get("color") is not None:
                    for (a, c) in (((b.x0, b.y0), (b.x1, b.y0)), ((b.x1, b.y0), (b.x1, b.y1)),
                                   ((b.x1, b.y1), (b.x0, b.y1)), ((b.x0, b.y1), (b.x0, b.y0))):
                        geo.segs.append(Seg(a[0], a[1], c[0], c[1], w))
            elif it[0] == "qu":
                b = _tr_rect(it[1].rect, m)
                geo.rects.append(RectShape(b, w, filled))
    return geo


# ----------------------------------------------------------------------------------------
# Dokumente
# ----------------------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_document(plans_dir: Path, data: bytes, file_name: str, existing: list[DocumentInfo]) -> tuple[DocumentInfo, bool]:
    """Speichert die PDF inhaltsadressiert. Gibt (Dokument, neu?) zurück.

    Gleicher Inhalt (auch unter anderem Dateinamen) wird nicht erneut aufgenommen –
    so verdoppeln sich Mengen beim wiederholten Hochladen nicht.
    """
    sha = sha256_bytes(data)
    for d in existing:
        if d.sha256 == sha:
            if file_name != d.file_name and file_name not in d.duplicate_names:
                d.duplicate_names.append(file_name)
            return d, False
    plans_dir.mkdir(parents=True, exist_ok=True)
    doc_id = sha[:12]
    path = plans_dir / f"{doc_id}.pdf"
    path.write_bytes(data)
    pdf = pymupdf.open(path)
    if pdf.needs_pass:
        raise ValueError(f"{file_name}: PDF ist kennwortgeschützt.")
    info = DocumentInfo(id=doc_id, sha256=sha, file_name=file_name, stored_path=str(path))
    info.pages = analyze_layout(pdf, doc_id)
    return info, True


# ----------------------------------------------------------------------------------------
# Layout: Plankopf und Ansichtsbereiche
# ----------------------------------------------------------------------------------------

_TITLE_PATTERNS = [
    ("ansicht", re.compile(r"\bansicht\s+(nord|süd|sued|ost|west|n|s|o|w)\b|\b(nord|süd|ost|west)ansicht\b", re.I)),
    ("schnitt", re.compile(r"\bschnitt\b\s*([a-z0-9]+\s*[-–—]\s*[a-z0-9]+|[a-z0-9]+)?", re.I)),
    ("grundriss", re.compile(r"\bgrundriss\b|\b(erd|ober|unter|dach|keller)geschoss\b", re.I)),
]
_FACADE_WORDS = {"nord": "nord", "n": "nord", "süd": "sued", "sued": "sued", "s": "sued",
                 "ost": "ost", "o": "ost", "west": "west", "w": "west"}
_LEFT_FOR_ANSICHT = {"sued": "west", "nord": "ost", "west": "nord", "ost": "sued"}
_LEFT_FOR_VIEWDIR = {"nord": "west", "sued": "ost", "ost": "nord", "west": "sued"}
_STOREY_RE = re.compile(r"\b(UG|KG|EG|OG|[1-9]\.\s?OG|DG)\b")
_SCALE_RE = re.compile(r"\b(?:M\s*)?1\s*:\s*(\d{1,4})\b")
_VIEWDIR_RE = re.compile(r"blick(?:richtung)?\s*(?:nach\s*)?(norden|süden|osten|westen|nord|süd|ost|west)", re.I)
_TB_KEYS = ("planstand", "plan-nr", "plannr", "maßstab", "massstab", "projekt", "planinhalt", "index", "gezeichnet")


def classify_title(texts: list[str]) -> dict:
    """Bestimmt Zeichnungsart, Fassade, Geschoss, Maßstab aus den Texten eines Bereichs."""
    out: dict = {"view_type": "sonstiges", "title": "", "facade": None, "storey": None,
                 "scale": None, "left_dir": None, "confidence": 0.3}
    joined = " | ".join(texts)
    for vt, rx in _TITLE_PATTERNS:
        for t in texts:
            mm = rx.search(t)
            if mm:
                out["view_type"] = vt
                out["title"] = t
                out["confidence"] = 0.9
                if vt == "ansicht":
                    word = (mm.group(1) or mm.group(2) or "").lower()
                    out["facade"] = _FACADE_WORDS.get(word)
                    out["left_dir"] = _LEFT_FOR_ANSICHT.get(out["facade"])
                break
        if out["view_type"] != "sonstiges":
            break
    mm = _VIEWDIR_RE.search(joined)
    if mm and out["view_type"] == "schnitt":
        w = mm.group(1).lower().replace("en", "") if mm.group(1).lower().endswith("en") else mm.group(1).lower()
        w = {"nord": "nord", "süd": "sued", "ost": "ost", "west": "west"}.get(w, None)
        out["left_dir"] = _LEFT_FOR_VIEWDIR.get(w) if w else None
    mm = _STOREY_RE.search(out["title"] or "")
    if mm:
        out["storey"] = mm.group(1)
    elif out["view_type"] == "grundriss" and re.search(r"erdgeschoss", joined, re.I):
        out["storey"] = "EG"
    mm = _SCALE_RE.search(joined)
    if mm:
        out["scale"] = f"1:{mm.group(1)}"
    return out


def _union(a: BBox, b: BBox) -> BBox:
    return BBox(x0=min(a.x0, b.x0), y0=min(a.y0, b.y0), x1=max(a.x1, b.x1), y1=max(a.y1, b.y1))


def _cluster(boxes: list[BBox], gap: float) -> list[list[int]]:
    """Gruppiert Rechtecke, deren Abstand kleiner als ``gap`` ist (Union-Find mit Sweep)."""
    n = len(boxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(n), key=lambda i: boxes[i].x0)
    active: list[int] = []
    for i in order:
        b = boxes[i]
        active = [j for j in active if boxes[j].x1 + gap >= b.x0]
        for j in active:
            c = boxes[j]
            if c.y0 - gap <= b.y1 and b.y0 - gap <= c.y1:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
        active.append(i)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _seg_box(s: Seg) -> BBox:
    return BBox(x0=min(s.x0, s.x1), y0=min(s.y0, s.y1), x1=max(s.x0, s.x1), y1=max(s.y0, s.y1))


def find_title_block(geo: PageGeometry) -> BBox | None:
    keys = [s for s in geo.spans if any(s.text.lower().startswith(k) for k in _TB_KEYS)]
    if len(keys) < 2:
        return None
    area = geo.width * geo.height
    best: BBox | None = None
    for r in geo.rects:
        b = r.bbox
        if b.w * b.h > 0.35 * area:
            continue
        hits = sum(1 for s in keys if b.contains_point(s.bbox.cx, s.bbox.cy))
        if hits >= 2 and (best is None or b.w * b.h > best.w * best.h):
            best = b
    if best is None:
        best = keys[0].bbox
        for s in keys[1:]:
            best = _union(best, s.bbox)
        best = BBox(x0=best.x0 - 5, y0=best.y0 - 5, x1=best.x1 + 120, y1=best.y1 + 5)
    return best


def parse_title_block(geo: PageGeometry, tb: BBox | None) -> dict:
    spans = [s for s in geo.spans if tb is None or tb.contains_point(s.bbox.cx, s.bbox.cy)]
    out: dict = {"plan_stand": None, "plan_number": None, "plan_title": None, "project_name": None}
    keymap = {"planstand": "plan_stand", "stand": "plan_stand", "revision": "plan_stand", "index": "plan_stand",
              "plan-nr": "plan_number", "plannr": "plan_number", "plannummer": "plan_number",
              "planinhalt": "plan_title", "projekt": "project_name", "bauvorhaben": "project_name"}
    for s in spans:
        low = s.text.lower()
        for k, field_ in keymap.items():
            if low.startswith(k) and out[field_] is None:
                rest = s.text.split(":", 1)[1].strip() if ":" in s.text else ""
                if not rest:
                    # Wert rechts daneben auf gleicher Zeile
                    cands = [o for o in spans if o is not s and abs(o.bbox.cy - s.bbox.cy) < 3 and o.bbox.x0 > s.bbox.x1 - 1]
                    cands.sort(key=lambda o: o.bbox.x0)
                    rest = cands[0].text if cands else ""
                if k == "index" and not rest:
                    rest = s.text
                if rest:
                    out[field_] = rest
    if out["plan_stand"] is None:
        for s in geo.spans:
            mm = re.search(r"\b(Index|Rev\.?|Revision)\s*([A-Za-z0-9]{1,3})\b.*", s.text)
            if mm:
                out["plan_stand"] = mm.group(0)
                break
    return out


def detect_views(geo: PageGeometry, doc_id: str, page_no: int) -> tuple[list[ViewRegion], BBox | None]:
    area = geo.width * geo.height
    diag = math.hypot(geo.width, geo.height)
    gap = min(60.0, max(25.0, 0.025 * diag))
    tb = find_title_block(geo)

    def excluded(b: BBox) -> bool:
        if b.w * b.h > 0.5 * area or b.w > 0.8 * geo.width or b.h > 0.8 * geo.height:
            return True  # Blattrahmen
        if tb is not None and tb.contains_point(b.cx, b.cy, tol=2):
            return True
        return False

    boxes: list[BBox] = []
    kinds: list[str] = []
    for s in geo.segs:
        b = _seg_box(s)
        if not excluded(b):
            boxes.append(b)
            kinds.append("g")
    for r in geo.rects:
        if not excluded(r.bbox):
            boxes.append(r.bbox)
            kinds.append("g")
    for s in geo.spans:
        if not excluded(s.bbox):
            boxes.append(s.bbox)
            kinds.append("t")
    groups = _cluster(boxes, gap)
    regions: list[tuple[BBox, list[int]]] = []
    small: list[BBox] = []
    for g in groups:
        b = boxes[g[0]]
        for i in g[1:]:
            b = _union(b, boxes[i])
        if sum(1 for i in g if kinds[i] == "g") < 4 or b.w < 40 or b.h < 40:
            small.append(b)
            continue
        regions.append((b, g))
    # Kleine Gruppen (Nordpfeil, Einzeltexte) dem nächsten Bereich zuschlagen
    for sb in small:
        best, dist = None, 3 * gap
        for k, (rb, g) in enumerate(regions):
            dx = max(0.0, max(rb.x0, sb.x0) - min(rb.x1, sb.x1))
            dy = max(0.0, max(rb.y0, sb.y0) - min(rb.y1, sb.y1))
            dd = math.hypot(dx, dy)
            if dd < dist:
                best, dist = k, dd
        if best is not None:
            rb, g = regions[best]
            regions[best] = (_union(rb, sb), g)
    regions.sort(key=lambda t: (round(t[0].y0 / 50), t[0].x0))
    views: list[ViewRegion] = []
    for n, (b, _g) in enumerate(regions):
        pad = 6
        bb = BBox(x0=max(0, b.x0 - pad), y0=max(0, b.y0 - pad), x1=min(geo.width, b.x1 + pad), y1=min(geo.height, b.y1 + pad))
        texts = [s.text for s in sorted((s for s in geo.spans if bb.contains_point(s.bbox.cx, s.bbox.cy)),
                                        key=lambda s: -s.size)]
        c = classify_title(texts)
        views.append(ViewRegion(id=f"{doc_id}-p{page_no + 1}-v{n + 1}", doc_id=doc_id, page=page_no, bbox=bb,
                                view_type=c["view_type"], title=c["title"] or f"Bereich {n + 1}", storey=c["storey"],
                                facade=c["facade"], left_dir=c["left_dir"], scale=c["scale"],
                                confidence=c["confidence"], include=c["view_type"] != "sonstiges"))
    if tb is not None:
        views.append(ViewRegion(id=f"{doc_id}-p{page_no + 1}-pk", doc_id=doc_id, page=page_no, bbox=tb,
                                view_type="plankopf", title="Plankopf", include=False, confidence=0.9))
    return views, tb


def analyze_layout(pdf: pymupdf.Document, doc_id: str) -> list[PageInfo]:
    pages: list[PageInfo] = []
    for pno in range(len(pdf)):
        page = pdf[pno]
        geo = page_geometry(page)
        views, tb = detect_views(geo, doc_id, pno)
        meta = parse_title_block(geo, tb)
        pages.append(PageInfo(index=pno, width=page.rect.width, height=page.rect.height,
                              rotation=page.rotation, views=views, **meta))
    return pages


# ----------------------------------------------------------------------------------------
# Rendern, Ausschnitte, Rückprojektion
# ----------------------------------------------------------------------------------------


@dataclass
class RenderInfo:
    page: int
    clip: BBox  # Anzeige-Koordinaten
    zoom: float
    width_px: int
    height_px: int
    label: str = ""


def page_to_px(info: RenderInfo, b: BBox) -> tuple[float, float, float, float]:
    z = info.zoom
    return ((b.x0 - info.clip.x0) * z, (b.y0 - info.clip.y0) * z, (b.x1 - info.clip.x0) * z, (b.y1 - info.clip.y0) * z)


def px_to_page(info: RenderInfo, px: tuple[float, float, float, float] | list[float]) -> BBox:
    """Bildpixel eines gerenderten Ausschnitts -> Anzeige-Koordinaten der Seite."""
    x0, y0, x1, y1 = px
    z = info.zoom
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    return BBox(x0=info.clip.x0 + x0 / z, y0=info.clip.y0 + y0 / z, x1=info.clip.x0 + x1 / z, y1=info.clip.y0 + y1 / z)


def render(pdf: pymupdf.Document, page_no: int, clip: BBox | None = None, max_px: int = MAX_PX,
           zoom: float | None = None, label: str = "") -> tuple[bytes, RenderInfo]:
    page = pdf[page_no]
    c = clip or BBox.of(page.rect)
    if zoom is None:
        zoom = max_px / max(c.w, c.h)
    pm = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=pymupdf.Rect(c.as_tuple()), alpha=False)
    return pm.tobytes("png"), RenderInfo(page_no, c, zoom, pm.width, pm.height, label)


def plan_images(pdf: pymupdf.Document, view: ViewRegion, spans: list[Span], max_px: int = MAX_PX,
                min_text_px: float = 11.0) -> list[tuple[bytes, RenderInfo]]:
    """Übersichtsbild des Ansichtsbereichs plus – bei dichter Bemaßung – Kacheln in höherer Auflösung."""
    img, info = render(pdf, view.page, view.bbox, max_px=max_px, label="Übersicht")
    out = [(img, info)]
    heights = sorted(min(s.bbox.w, s.bbox.h) for s in spans if s.text and view.bbox.contains_point(s.bbox.cx, s.bbox.cy))
    if not heights:
        return out
    text_px = heights[len(heights) // 2] * info.zoom
    if text_px >= min_text_px:
        return out
    need_zoom = info.zoom * min_text_px / max(text_px, 0.1)
    tile_pt = max_px / need_zoom
    nx = max(1, math.ceil(view.bbox.w / (tile_pt * 0.9)))
    ny = max(1, math.ceil(view.bbox.h / (tile_pt * 0.9)))
    if nx * ny > 6:  # Begrenzung der Bildanzahl
        nx, ny = min(nx, 3), min(ny, 2)
    tw, th = view.bbox.w / nx, view.bbox.h / ny
    ov = 0.08
    for iy in range(ny):
        for ix in range(nx):
            c = BBox(x0=view.bbox.x0 + max(0, ix * tw - ov * tw), y0=view.bbox.y0 + max(0, iy * th - ov * th),
                     x1=min(view.bbox.x1, view.bbox.x0 + (ix + 1) * tw + ov * tw),
                     y1=min(view.bbox.y1, view.bbox.y0 + (iy + 1) * th + ov * th))
            out.append(render(pdf, view.page, c, max_px=max_px, label=f"Ausschnitt {iy + 1}/{ix + 1}"))
    return out


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def render_marked(pdf: pymupdf.Document, page_no: int, clip: BBox, marks: list[tuple[BBox, str]],
                  max_px: int = 1400, pad: float = 30.0, focus: BBox | None = None) -> bytes:
    """Rendert den Ausschnitt und markiert die Fundstellen (rot)."""
    page = pdf[page_no]
    pr = BBox.of(page.rect)
    c = BBox(x0=max(pr.x0, clip.x0 - pad), y0=max(pr.y0, clip.y0 - pad), x1=min(pr.x1, clip.x1 + pad), y1=min(pr.y1, clip.y1 + pad))
    img_bytes, info = render(pdf, page_no, c, max_px=max_px)
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    dr = ImageDraw.Draw(im)
    f = _font(max(12, int(info.width_px / 90)))
    for b, label in marks:
        x0, y0, x1, y1 = page_to_px(info, b)
        m = 4
        dr.rectangle([x0 - m, y0 - m, x1 + m, y1 + m], outline=(220, 0, 0), width=3)
        if label:
            dr.text((x0 - m, max(0, y0 - m - f.size - 4)), label, fill=(220, 0, 0), font=f)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def render_thumbnail(pdf: pymupdf.Document, page_no: int, views: list[ViewRegion], max_px: int = 900) -> bytes:
    img_bytes, info = render(pdf, page_no, None, max_px=max_px)
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    dr = ImageDraw.Draw(im)
    f = _font(13)
    colors = {"grundriss": (0, 102, 204), "ansicht": (0, 140, 70), "schnitt": (200, 90, 0),
              "plankopf": (120, 120, 120), "sonstiges": (160, 0, 160), "legende": (120, 120, 120)}
    for n, v in enumerate(views):
        x0, y0, x1, y1 = page_to_px(info, v.bbox)
        col = colors.get(v.view_type, (0, 0, 0))
        dr.rectangle([x0, y0, x1, y1], outline=col, width=2)
        dr.text((x0 + 3, y0 + 2), v.title[:40], fill=col, font=f)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()
