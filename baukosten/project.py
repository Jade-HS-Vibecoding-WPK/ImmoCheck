"""Projektstand, Pläne, Erkennungs-Cache und Auswertungs-Pipeline (ohne Oberfläche).

Speicherort: ``projekte/<slug>/`` mit ``project.json``, ``plans/`` (inhaltsadressiert),
``cache/`` (ein Erkennungsergebnis je Dokumentinhalt + Ansicht + Analysekonfiguration)
und ``katalog.csv`` (Projektkatalog, wird lokal verarbeitet).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import pymupdf

from . import bki, costs, merge, quantities
from .models import (BuildingModel, CatalogEntry, CostResult, DocumentInfo, Override, PageInfo, ProjectState, Quantity,
                     ViewRegion, ViewResult, ViewRun)
from .pdf_prep import page_geometry, store_document
from .recognition import ki_engine, local_engine

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROJECTS_DIR = Path(os.environ.get("BAUKOSTEN_PROJEKTE", ROOT / "projekte"))
DEMO_DIR = DATA / "demo"
ANALYZABLE = ("grundriss", "ansicht", "schnitt")

ENGINES = {
    "ki": "KI-Erkennung (Claude, Bild + PDF-Text)",
    "lokal": "Lokale PDF-Text-/Vektorauswertung (ohne KI, nur digitale PDFs)",
    "demo": "DEMO – gespeichertes Erkennungsergebnis",
}


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9äöüß]+", "-", name.lower()).strip("-")
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return s or "projekt"


@dataclass
class Evaluation:
    model: BuildingModel
    quantities: list[Quantity]
    cost: CostResult
    pending_views: list[ViewRegion]
    failed_views: list[tuple[ViewRegion, str]]
    engines_used: set[str]
    suggestion: bki.CategorySuggestion | None = None
    kategorie: str | None = None
    kategorie_quelle: str = ""  # "festgelegt" | "Vorschlag"
    orientation: bki.OrientationResult | None = None
    kennwert_updates: list[bki.BKIKennwert] | None = None
    region_hint: str = ""


class Project:
    def __init__(self, path: Path, state: ProjectState):
        self.path = path
        self.state = state

    # ---------------- Anlage / Laden -----------------------------------------------------
    @classmethod
    def create(cls, name: str, building_type: str = "", catalog_source: Path | None = None,
               base: Path | None = None, demo: bool = False) -> "Project":
        base = base or PROJECTS_DIR
        slug = slugify(name)
        path = base / slug
        n = 2
        while path.exists():
            path = base / f"{slug}-{n}"
            n += 1
        path.mkdir(parents=True)
        st = ProjectState(name=name, building_type=building_type, slug=path.name, demo=demo,
                          engine="demo" if demo else ("ki" if ki_engine.api_available() else "lokal"))
        p = cls(path, st)
        if catalog_source and catalog_source.exists():
            shutil.copy(catalog_source, p.catalog_path)
        else:
            costs.save_catalog(p.catalog_path, [])
        p.save()
        return p

    @classmethod
    def load(cls, path: Path) -> "Project":
        st = ProjectState.model_validate_json((path / "project.json").read_text(encoding="utf-8"))
        for d in st.documents:  # Pläne relativ zum Projektordner auflösen (verschiebbar, ZIP-Import)
            d.stored_path = str(path / "plans" / f"{d.id}.pdf")
        return cls(path, st)

    def export_zip(self) -> bytes:
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in self.path.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(self.path).as_posix())
        return buf.getvalue()

    @classmethod
    def import_zip(cls, data: bytes, base: Path | None = None) -> "Project":
        import io
        import zipfile

        base = base or PROJECTS_DIR
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if "project.json" not in names:
                raise ValueError("Keine Projektdatei (project.json) im ZIP.")
            st = ProjectState.model_validate_json(z.read("project.json"))
            path = base / st.slug
            n = 2
            while path.exists():
                path = base / f"{st.slug}-{n}"
                n += 1
            path.mkdir(parents=True)
            for name in names:
                target = (path / name).resolve()
                if not str(target).startswith(str(path.resolve())) or name.endswith("/"):
                    continue  # keine Pfade außerhalb des Projektordners
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
        st.slug = path.name
        p = cls(path, st)
        p.save()
        return cls.load(path)

    @staticmethod
    def list_all(base: Path | None = None) -> list[Path]:
        base = base or PROJECTS_DIR
        if not base.exists():
            return []
        return sorted([p for p in base.iterdir() if (p / "project.json").exists()], key=lambda p: p.name)

    def save(self) -> None:
        (self.path / "project.json").write_text(self.state.model_dump_json(indent=1), encoding="utf-8")

    @property
    def plans_dir(self) -> Path:
        return self.path / "plans"

    @property
    def cache_dir(self) -> Path:
        d = self.path / "cache"
        d.mkdir(exist_ok=True)
        return d

    @property
    def catalog_path(self) -> Path:
        return self.path / self.state.catalog_file

    # ---------------- Dokumente ----------------------------------------------------------
    def add_file(self, name: str, data: bytes) -> tuple[DocumentInfo, bool]:
        doc, new = store_document(self.plans_dir, data, name, self.state.documents)
        if new:
            self.state.documents.append(doc)
        self.save()
        return doc, new

    def remove_document(self, doc_id: str) -> None:
        self.state.documents = [d for d in self.state.documents if d.id != doc_id]
        for k in [k for k in self.state.runs if k.startswith(doc_id)]:
            del self.state.runs[k]
        self.save()

    def doc(self, doc_id: str) -> DocumentInfo:
        return next(d for d in self.state.documents if d.id == doc_id)

    def pdf(self, doc: DocumentInfo) -> pymupdf.Document:
        return pymupdf.open(doc.stored_path)

    def iter_views(self, analyzable_only: bool = False):
        for d in self.state.documents:
            for pg in d.pages:
                for v in pg.views:
                    if analyzable_only and (not v.include or v.view_type not in ANALYZABLE):
                        continue
                    yield d, pg, v

    def find_view(self, view_id: str) -> tuple[DocumentInfo, PageInfo, ViewRegion]:
        for d, pg, v in self.iter_views():
            if v.id == view_id:
                return d, pg, v
        raise KeyError(view_id)

    def update_view(self, view_id: str, **fields) -> None:
        _, _, v = self.find_view(view_id)
        for k, val in fields.items():
            setattr(v, k, val)
        if v.view_type == "ansicht" and "facade" in fields and "left_dir" not in fields:
            v.left_dir = {"sued": "west", "nord": "ost", "west": "nord", "ost": "sued"}.get(v.facade or "")
        v.user_corrected = True
        self.save()

    def update_page(self, doc_id: str, page: int, **fields) -> None:
        pg = self.doc(doc_id).pages[page]
        for k, val in fields.items():
            setattr(pg, k, val)
        self.save()

    # ---------------- Erkennung mit Cache ------------------------------------------------
    def engine_config(self, engine: str) -> str:
        if engine == "ki":
            return f"{ki_engine.PROMPT_VERSION}|{ki_engine.configured_model()}|{ki_engine.configured_effort()}"
        if engine == "lokal":
            return local_engine.ENGINE_VERSION
        return "demo-1"

    def cache_key(self, doc: DocumentInfo, v: ViewRegion, engine: str) -> str:
        b = v.bbox
        raw = "|".join([doc.sha256, str(v.page), f"{b.x0:.1f},{b.y0:.1f},{b.x1:.1f},{b.y1:.1f}", v.view_type,
                        v.facade or "", v.left_dir or "", v.title, engine, self.engine_config(engine)])
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _cache_file(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def cached(self, key: str) -> ViewResult | None:
        f = self._cache_file(key)
        if f.exists():
            return ViewResult.model_validate_json(json.loads(f.read_text(encoding="utf-8"))["result"])
        return None

    def analyze(self, engine: str | None = None, view_ids: list[str] | None = None, client=None,
                progress: Callable[[int, int, str], None] | None = None, force: bool = False) -> dict:
        """Wertet alle (oder die genannten) Ansichtsbereiche aus. Fehler betreffen nur den jeweiligen Schritt."""
        engine = engine or self.state.engine
        self.state.engine = engine
        todo = [(d, pg, v) for d, pg, v in self.iter_views(analyzable_only=True) if view_ids is None or v.id in view_ids]
        stats = {"neu": 0, "cache": 0, "fehler": 0}
        geo_cache: dict[tuple[str, int], object] = {}
        pdfs: dict[str, pymupdf.Document] = {}
        demo_store = load_demo_results() if engine == "demo" else {}
        for n, (d, pg, v) in enumerate(todo, 1):
            key = self.cache_key(d, v, engine)
            if progress:
                progress(n, len(todo), f"{d.file_name} · {v.title}")
            if not force and self.cached(key) is not None:
                self.state.runs[v.id] = ViewRun(view_id=v.id, engine=engine, cache_key=key, status="ok",
                                                finished_at=datetime.now())
                stats["cache"] += 1
                continue
            try:
                if engine == "demo":
                    res = demo_store.get(demo_key(d, v))
                    if res is None:
                        raise LookupError("Demomodus: für diesen Plan liegt kein gespeichertes Erkennungsergebnis vor. "
                                          "Für eigene Pläne bitte KI-Erkennung oder lokale Auswertung wählen.")
                    res = res.model_copy(deep=True)
                    res.view_id = v.id
                    res.engine = "demo (gespeichert)"
                    _rebind_evidence(res, d, v)
                else:
                    if d.id not in pdfs:
                        pdfs[d.id] = self.pdf(d)
                    gk = (d.id, v.page)
                    if gk not in geo_cache:
                        geo_cache[gk] = page_geometry(pdfs[d.id][v.page])
                    geo = geo_cache[gk]
                    if engine == "lokal":
                        res = local_engine.analyze_view(d, v, geo)
                    elif engine == "ki":
                        res = ki_engine.analyze_view(pdfs[d.id], d, v, geo, client=client)
                    else:
                        raise ValueError(f"unbekanntes Verfahren {engine}")
                self._cache_file(key).write_text(json.dumps({"engine": engine, "config": self.engine_config(engine),
                                                             "created": datetime.now().isoformat(),
                                                             "result": res.model_dump_json()}), encoding="utf-8")
                self.state.runs[v.id] = ViewRun(view_id=v.id, engine=engine, cache_key=key, status="ok",
                                                finished_at=datetime.now())
                stats["neu"] += 1
            except Exception as exc:  # noqa: BLE001 – Fehler gehört genau zu diesem Schritt
                msg = f"{type(exc).__name__}: {exc}"
                self.state.runs[v.id] = ViewRun(view_id=v.id, engine=engine, cache_key=key, status="fehler", error=msg[:800])
                stats["fehler"] += 1
                if os.environ.get("BAUKOSTEN_DEBUG"):
                    traceback.print_exc()
        self.save()
        return stats

    def failed_view_ids(self) -> list[str]:
        return [k for k, r in self.state.runs.items() if r.status == "fehler"]

    # ---------------- Auswertung ---------------------------------------------------------
    def view_inputs(self) -> tuple[list[merge.ViewInput], list[ViewRegion], list[tuple[ViewRegion, str]], set[str]]:
        inputs, pending, failed, engines = [], [], [], set()
        for d, pg, v in self.iter_views(analyzable_only=True):
            run = self.state.runs.get(v.id)
            if run is None:
                pending.append(v)
                continue
            if run.status == "fehler":
                failed.append((v, run.error))
                continue
            key = self.cache_key(d, v, run.engine)
            res = self.cached(key) if key == run.cache_key else None
            if res is None:
                pending.append(v)
                continue
            engines.add(run.engine)
            inputs.append(merge.ViewInput(view=v, result=res, page=pg, doc=d))
        return inputs, pending, failed, engines

    def catalog(self) -> list[CatalogEntry]:
        return costs.load_catalog(self.catalog_path)

    def save_catalog(self, entries: list[CatalogEntry]) -> None:
        costs.save_catalog(self.catalog_path, entries)

    def evaluate(self) -> Evaluation:
        inputs, pending, failed, engines = self.view_inputs()
        model = merge.build_model(inputs, self.state.overrides, self.state.active_stand)
        qs = quantities.compute_quantities(model)
        cost = costs.price_positions(qs, self.catalog(), self.state.price_choices)
        ev = Evaluation(model=model, quantities=qs, cost=cost, pending_views=pending, failed_views=failed,
                        engines_used=engines)
        # ---- Bauwerksorientierung KG 300+400 (getrennt von den Bauteilkosten) ----
        ev.suggestion = bki.suggest_category(self.state.name, self.state.building_type, self.plan_texts(), model.storeys)
        if self.state.building_category:
            ev.kategorie, ev.kategorie_quelle = self.state.building_category, "festgelegt"
        elif ev.suggestion.kategorie:
            ev.kategorie, ev.kategorie_quelle = ev.suggestion.kategorie, "Vorschlag"
        kennwerte, ev.kennwert_updates = self.orientation_kennwerte(ev.kategorie) if ev.kategorie else ({}, [])
        rf = bki.Regionalfaktor(**self.state.regionalfaktor) if self.state.regionalfaktor else None
        ev.orientation = bki.orientation(ev.kategorie, model.bgf.value if model.bgf else None,
                                         model.bri.value if model.bri else None, kennwerte, rf, self.state.netto)
        loc = f"{self.state.name} {self.state.location}".lower()
        if "bersenbrück" in loc and rf is None:
            ev.region_hint = ("Standort Bersenbrück: maßgeblich ist die Zeile „Landkreis Osnabrück“ der Regionalfaktoren "
                              f"(BKI 2026 ab S. {bki.REGIONALFAKTOR_SEITE}). Ohne eingetragenen, belegten Faktor gilt Bundesdurchschnitt.")
        return ev

    # ---------------- Bauwerksorientierung --------------------------------------------------
    _text_cache: dict[str, str] = {}

    def plan_texts(self) -> list[str]:
        out = []
        for d in self.state.documents:
            if d.sha256 not in Project._text_cache:
                try:
                    Project._text_cache[d.sha256] = " ".join(pg.get_text() for pg in self.pdf(d))
                except Exception:  # noqa: BLE001
                    Project._text_cache[d.sha256] = ""
            out.append(Project._text_cache[d.sha256])
            out.extend(pg.plan_title or "" for pg in d.pages)
        return out

    def orientation_kennwerte(self, kategorie: str) -> tuple[dict[str, bki.BKIKennwert], list[bki.BKIKennwert]]:
        """Verwendete Kennwerte bleiben im Projekt gespeichert (samt Herkunft), bis der Nutzer eine
        Aktualisierung übernimmt. Liefert (verwendete Kennwerte, verfügbare Aktualisierungen)."""
        cat = bki.load_catalog()
        used: dict[str, bki.BKIKennwert] = {}
        updates: list[bki.BKIKennwert] = []
        changed = False
        for bez in ("BGF", "BRI"):
            cur = cat.get((kategorie, bez))
            key = f"{kategorie}|{bez}"
            snap = self.state.kennwert_snapshot.get(key)
            if snap is not None:
                used[bez] = bki.BKIKennwert.model_validate(snap)
                if cur is not None and cur.model_dump() != used[bez].model_dump():
                    updates.append(cur)
            elif cur is not None:
                used[bez] = cur
                self.state.kennwert_snapshot[key] = cur.model_dump()
                changed = True
        if changed:
            self.save()
        return used, updates

    def accept_kennwert_update(self, kategorie: str, bezugsgroesse: str | None = None) -> None:
        cat = bki.load_catalog()
        for bez in ("BGF", "BRI"):
            if bezugsgroesse and bez != bezugsgroesse:
                continue
            cur = cat.get((kategorie, bez))
            if cur is not None:
                self.state.kennwert_snapshot[f"{kategorie}|{bez}"] = cur.model_dump()
        self.save()

    def set_category(self, kategorie: str | None) -> None:
        self.state.building_category = kategorie
        self.save()

    def set_region(self, region: str | None, faktor: float | None = None, quelle: str = "") -> None:
        if region and faktor and quelle.strip():
            self.state.regionalfaktor = {"region": region, "faktor": faktor, "quelle": quelle}
        else:
            self.state.regionalfaktor = None  # ohne Beleg kein Faktor
        self.save()

    # ---------------- Korrekturen ----------------------------------------------------------
    def set_override(self, value_key: str, value: float | None = None, chosen_evidence_id: str | None = None,
                     note: str = "", original_evidence=None) -> None:
        self.state.overrides[value_key] = Override(value_key=value_key, value=value, chosen_evidence_id=chosen_evidence_id,
                                                   note=note, original_evidence=original_evidence or [])
        self.save()

    def clear_override(self, value_key: str) -> None:
        self.state.overrides.pop(value_key, None)
        self.save()

    def set_price_choice(self, pos_key: str, entry_ids: list[str]) -> None:
        if entry_ids:
            self.state.price_choices[pos_key] = "+".join(entry_ids)
        else:
            self.state.price_choices.pop(pos_key, None)
        self.save()

    def set_active_stand(self, stand: str | None) -> None:
        self.state.active_stand = stand
        self.save()


# ----------------------------------------------------------------------------------------
# Demomodus: gespeichertes Erkennungsergebnis
# ----------------------------------------------------------------------------------------


def demo_key(d: DocumentInfo, v: ViewRegion) -> str:
    return f"{d.sha256}|{v.page}|{v.view_type}|{v.facade or ''}|{v.title}"


def load_demo_results() -> dict[str, ViewResult]:
    f = DEMO_DIR / "erkennung_demo.json"
    if not f.exists():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))
    return {k: ViewResult.model_validate(v) for k, v in data["results"].items()}


def _rebind_evidence(res: ViewResult, d: DocumentInfo, v: ViewRegion) -> None:
    """Fundstellen des gespeicherten Ergebnisses auf das aktuelle Dokument/den Bereich beziehen."""
    def fix(ev):
        if ev is None:
            return
        old_view = ev.view_id or ""
        ev.doc_id, ev.file_name, ev.page, ev.view_id, ev.view_title = d.id, d.file_name, v.page, v.id, v.title
        ev.id = ev.id.replace(old_view, v.id, 1) if old_view else ev.id
    for ch in res.chains:
        for m in ch.segments:
            fix(m.evidence)
    for lv in res.levels:
        fix(lv.measure.evidence)
    for o in res.openings:
        fix(o.symbol)
        for m in (o.width, o.height, o.sill):
            if m:
                fix(m.evidence)
    for c in res.components:
        fix(c.evidence)
        for m in (c.overhang, c.pitch):
            if m:
                fix(m.evidence)
    for pn in res.price_notes:
        fix(pn.evidence)


def create_demo_project(base: Path | None = None) -> Project:
    meta = json.loads((DEMO_DIR / "erkennung_demo.json").read_text(encoding="utf-8"))
    p = Project.create("DEMO Testbau WPK", "Gemeindehaus (künstlicher Testbau)", catalog_source=DATA / "katalog" / "testkatalog.csv",
                       base=base, demo=True)
    pdf_path = DEMO_DIR / meta["plan_file"]
    p.add_file(meta["plan_file"], pdf_path.read_bytes())
    p.analyze("demo")
    return p
