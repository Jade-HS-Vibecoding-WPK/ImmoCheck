"""Baukostentool · Oberfläche (Streamlit).

Start:  ./start.command   oder   .venv/bin/streamlit run app.py
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_env() -> None:
    """Liest KEY=WERT aus .env (falls vorhanden), ohne gesetzte Umgebungsvariablen zu überschreiben."""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from baukosten import bki, costs, report  # noqa: E402
from baukosten.models import FACADE_LABEL, BBox, CatalogEntry, Evidence, Value  # noqa: E402
from baukosten.pdf_prep import render_marked, render_thumbnail  # noqa: E402
from baukosten.project import DATA, ENGINES, PROJECTS_DIR, Evaluation, Project, create_demo_project  # noqa: E402
from baukosten.recognition import ki_engine  # noqa: E402
from baukosten.units import format_de, format_eur  # noqa: E402

st.set_page_config(page_title="Baukostentool", page_icon="🏗️", layout="wide")

TESTKATALOG = DATA / "katalog" / "testkatalog.csv"
STEPS = ["① Pläne", "② Auswerten", "③ Ergebnis", "④ Preiskatalog", "⑤ Ausgabe"]
VIEW_TYPES = {"grundriss": "Grundriss", "ansicht": "Ansicht", "schnitt": "Schnitt", "plankopf": "Plankopf",
              "legende": "Legende", "sonstiges": "sonstiges"}
STATUS_ICON = {"bepreist": "✅", "offen": "⚪", "pruefen": "⚠️", "auswahl": "🔶"}
VALUE_STATUS = {"ok": "belegt", "widerspruch": "Widerspruch", "fehlt": "fehlt", "manuell": "korrigiert"}

st.markdown("""<style>
.block-container{padding-top:1.6rem}
.kpi{border:1px solid rgba(128,128,128,.35);border-radius:8px;padding:.7rem .9rem;margin-bottom:.4rem}
.kpi .l{font-size:.8rem;opacity:.75}.kpi .v{font-size:1.45rem;font-weight:600}.kpi .s{font-size:.78rem;opacity:.7}
.demo{background:#fff4e5;color:#7a4a00;border:1px solid #f0c27a;border-radius:6px;padding:.5rem .8rem;font-weight:600}
</style>""", unsafe_allow_html=True)


# =========================================================================================
# Projekt laden / anlegen
# =========================================================================================
def current_project() -> Project | None:
    slug = st.session_state.get("project")
    if not slug:
        return None
    path = PROJECTS_DIR / slug
    if not (path / "project.json").exists():
        st.session_state.pop("project", None)
        return None
    return Project.load(path)


def open_project(p: Project, step: str = STEPS[0]) -> None:
    st.session_state["project"] = p.path.name
    st.session_state["_goto"] = step
    st.rerun()


def sidebar() -> Project | None:
    sb = st.sidebar
    sb.title("🏗️ Baukostentool")
    sb.caption("DIN 276 · BKI Gebäude Neubau 2026 · aus Plan-PDFs")
    projects = Project.list_all()
    names = {p.name: Project.load(p).state.name for p in projects}
    if "project" not in st.session_state and st.query_params.get("p"):
        st.session_state["project"] = st.query_params["p"]  # Projekt bleibt nach Neuladen der Seite offen
    cur = st.session_state.get("project")
    if cur and st.query_params.get("p") != cur:
        st.query_params["p"] = cur
    options = ["–"] + [p.name for p in projects]
    idx = options.index(cur) if cur in options else 0
    sel = sb.selectbox("Projekt", options, index=idx, format_func=lambda s: "– Projekt wählen –" if s == "–" else names.get(s, s))
    if sel != "–" and sel != cur:
        st.session_state["project"] = sel
        st.rerun()

    with sb.expander("Neues Projekt", expanded=not projects):
        with st.form("neu", clear_on_submit=True):
            name = st.text_input("Projektname", placeholder="z. B. Gemeindehaus Klosterareal")
            typ = st.text_input("Gebäudetyp / Nutzung", placeholder="z. B. Gemeindehaus, Kita, MFH 8 WE")
            ort = st.text_input("Standort (optional)", placeholder="z. B. Bersenbrück")
            kat = st.radio("Bauteil-Preiskatalog", ["leer (eigene Preise später)", "eigene CSV hochladen"], horizontal=False)
            up = st.file_uploader("Katalog-CSV", type=["csv"], label_visibility="collapsed")
            if st.form_submit_button("Projekt anlegen", type="primary") and name.strip():
                p = Project.create(name.strip(), typ.strip())
                p.state.location = ort.strip()
                p.save()
                if kat.startswith("eigene") and up is not None:
                    p.save_catalog(costs.read_catalog_csv(up.getvalue()))
                open_project(p)
    if sb.button("Demoprojekt öffnen (Testbau, ohne KI)", width="stretch"):
        demo = next((Project.load(x) for x in projects if Project.load(x).state.demo), None)
        open_project(demo or create_demo_project(), STEPS[2])

    p = current_project()
    if p is not None:
        with sb.expander("Projekt sichern / laden"):
            st.download_button("Projekt als ZIP sichern", p.export_zip(), file_name=f"{p.state.slug}.zip",
                               mime="application/zip", width="stretch")
        sb.divider()
        default = st.session_state.pop("_goto", None)
        if default is not None:
            st.session_state["step"] = default
        if "step" not in st.session_state and st.query_params.get("s") in STEPS:
            st.session_state["step"] = st.query_params["s"]
        sb.radio("Schritt", STEPS, key="step")
        st.query_params["s"] = st.session_state["step"]
    with sb.expander("Projekt-ZIP importieren"):
        z = st.file_uploader("ZIP", type=["zip"], key="zipimp", label_visibility="collapsed")
        if z is not None and st.button("Importieren"):
            open_project(Project.import_zip(z.getvalue()))
    sb.divider()
    if ki_engine.api_available():
        sb.success(f"KI-Erkennung bereit · Modell {ki_engine.configured_model()}", icon="🔑")
    else:
        sb.info("Kein ANTHROPIC_API_KEY gesetzt: lokale Auswertung digitaler PDFs und Demomodus verfügbar.", icon="ℹ️")
    return p


# =========================================================================================
# Hilfen
# =========================================================================================
def kpi(label: str, value: str, sub: str = "") -> None:
    st.markdown(f"<div class='kpi'><div class='l'>{label}</div><div class='v'>{value}</div><div class='s'>{sub}</div></div>",
                unsafe_allow_html=True)


def uniq(evs: list[Evidence], limit: int = 12) -> list[Evidence]:
    seen, out = set(), []
    for e in evs:
        if e.id not in seen and e.bbox is not None:
            seen.add(e.id)
            out.append(e)
    return out[:limit]


@st.dialog("Fundstelle im Plan", width="large")
def show_evidence(p_slug: str, ev_json: list[str], title: str) -> None:
    p = Project.load(PROJECTS_DIR / p_slug)
    evs = [Evidence.model_validate_json(j) for j in ev_json]
    st.caption(title)
    groups: dict[tuple, list[Evidence]] = {}
    for e in evs:
        groups.setdefault((e.doc_id, e.page, e.view_id), []).append(e)
    for (doc_id, page, view_id), items in groups.items():
        try:
            d = p.doc(doc_id)
        except StopIteration:
            st.warning("Plan nicht mehr im Projekt.")
            continue
        view = next((v for pg in d.pages if pg.index == page for v in pg.views if v.id == view_id), None)
        clip = view.bbox if view else BBox(x0=min(e.bbox.x0 for e in items) - 120, y0=min(e.bbox.y0 for e in items) - 120,
                                           x1=max(e.bbox.x1 for e in items) + 120, y1=max(e.bbox.y1 for e in items) + 120)
        png = render_marked(p.pdf(d), page, clip, [(e.bbox, "") for e in items])
        st.markdown(f"**{d.file_name}** · Seite {page + 1} · {items[0].view_title}")
        st.caption(" · ".join(f"„{e.text}“" + (f" ({e.note})" if e.note else "") for e in items))
        st.image(png, width=1200)


def evidence_button(p: Project, evs: list[Evidence], title: str, key: str, label: str = "Im Plan zeigen") -> None:
    evs = uniq(evs, 40)
    if not evs:
        st.caption("keine Fundstelle")
        return
    if st.button(f"🔍 {label} ({len(evs)})" if len(evs) > 1 else f"🔍 {label}", key=key):
        show_evidence(p.path.name, [e.model_dump_json() for e in evs], title)


def all_values(m) -> dict[str, Value]:
    out = {"len:x": m.length_x, "len:y": m.length_y}
    out.update({v.key: v for v in m.levels.values()})
    for o in m.openings:
        for v in (o.width, o.height, o.sill):
            out[v.key] = v
    for v in (m.roof_pitch, m.bgf, m.bri):
        if v is not None:
            out[v.key] = v
    return out


def parse_num(s: str) -> float | None:
    s = (s or "").strip().replace(" ", "")
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
    except ValueError:
        return None


# =========================================================================================
# ① Pläne
# =========================================================================================
def step_plans(p: Project) -> None:
    st.header("① Plansatz hochladen")
    st.caption("Grundrisse, Ansichten und Schnitte als PDF (mehrere Dateien oder eine mehrseitige PDF). "
               "Dieselbe Datei ein zweites Mal hochzuladen zählt nichts doppelt.")
    files = st.file_uploader("Plan-PDFs", type=["pdf"], accept_multiple_files=True, key=f"up_{st.session_state.get('upn', 0)}")
    if files:
        msgs = []
        for f in files:
            try:
                d, new = p.add_file(f.name, f.getvalue())
                msgs.append(("success" if new else "info",
                             f"{f.name}: {'hochgeladen' if new else 'bereits im Projekt (gleicher Inhalt) – nicht doppelt gezählt'}, "
                             f"{len(d.pages)} Seite(n)"))
            except Exception as exc:  # noqa: BLE001
                msgs.append(("error", f"{f.name}: konnte nicht gelesen werden ({exc})"))
        st.session_state["upload_msgs"] = msgs
        st.session_state["upn"] = st.session_state.get("upn", 0) + 1
        st.rerun()
    for kind, m in st.session_state.pop("upload_msgs", []):
        getattr(st, kind)(m)

    if not p.state.documents:
        st.info("Noch keine Pläne im Projekt. Zum Ausprobieren liegen Testpläne im Ordner „plaene/“.")
        return
    for d in p.state.documents:
        with st.expander(f"📄 {d.file_name} · {len(d.pages)} Seite(n)", expanded=len(p.state.documents) <= 2):
            pdf = p.pdf(d)
            for pg in d.pages:
                c1, c2 = st.columns([2, 3])
                with c1:
                    st.image(render_thumbnail(pdf, pg.index, pg.views, max_px=900), width="stretch")
                with c2:
                    st.markdown(f"**Seite {pg.index + 1}** · {pg.plan_title or '–'} · Plan-Nr. {pg.plan_number or '–'}")
                    stand = st.text_input("Planstand", pg.plan_stand or "", key=f"st_{d.id}_{pg.index}")
                    if stand != (pg.plan_stand or ""):
                        p.update_page(d.id, pg.index, plan_stand=stand or None)
                        st.rerun()
                    rows = [{"id": v.id, "Auswerten": v.include, "Art": VIEW_TYPES.get(v.view_type, v.view_type),
                             "Titel": v.title, "Geschoss": v.storey or "", "Fassade": FACADE_LABEL.get(v.facade or "", ""),
                             "Maßstab": v.scale or ""} for v in pg.views]
                    df = pd.DataFrame(rows)
                    edited = st.data_editor(
                        df, hide_index=True, key=f"views_{d.id}_{pg.index}", width="stretch",
                        column_config={"id": None,
                                       "Art": st.column_config.SelectboxColumn(options=list(VIEW_TYPES.values())),
                                       "Fassade": st.column_config.SelectboxColumn(options=["", *FACADE_LABEL.values()])},
                        disabled=["Maßstab"])
                    inv_vt = {v: k for k, v in VIEW_TYPES.items()}
                    inv_f = {v: k for k, v in FACADE_LABEL.items()}
                    changed = False
                    for old, new in zip(rows, edited.to_dict("records")):
                        upd = {}
                        if new["Auswerten"] != old["Auswerten"]:
                            upd["include"] = bool(new["Auswerten"])
                        if new["Art"] != old["Art"]:
                            upd["view_type"] = inv_vt.get(new["Art"], "sonstiges")
                        if new["Titel"] != old["Titel"]:
                            upd["title"] = new["Titel"]
                        if new["Geschoss"] != old["Geschoss"]:
                            upd["storey"] = new["Geschoss"] or None
                        if new["Fassade"] != old["Fassade"]:
                            upd["facade"] = inv_f.get(new["Fassade"])
                        if upd:
                            p.update_view(old["id"], **upd)
                            changed = True
                    if changed:
                        st.rerun()
            if st.button("Plan aus dem Projekt entfernen", key=f"rm_{d.id}"):
                p.remove_document(d.id)
                st.rerun()
    st.caption("Farbige Rahmen: erkannte Zeichnungsbereiche. Falsche Zuordnungen in der Tabelle korrigieren – "
               "geänderte Bereiche werden bei der nächsten Auswertung neu gelesen.")
    if st.button("Weiter zu ② Auswerten →", type="primary"):
        st.session_state["_goto"] = STEPS[1]
        st.rerun()


# =========================================================================================
# ② Auswerten
# =========================================================================================
def step_analyze(p: Project) -> None:
    st.header("② Pläne auswerten")
    views = list(p.iter_views(analyzable_only=True))
    if not views:
        st.warning("Keine auswertbaren Zeichnungen (Grundriss, Ansicht, Schnitt). Bitte zuerst Pläne hochladen bzw. Zuordnung prüfen.")
        return
    if p.state.demo:
        engines = ["demo"]
        st.markdown("<div class='demo'>DEMOMODUS – gespeichertes Erkennungsergebnis, keine Live-Planauswertung.</div>",
                    unsafe_allow_html=True)
    else:
        engines = (["ki"] if ki_engine.api_available() else []) + ["lokal"]
    cur = p.state.engine if p.state.engine in engines else engines[0]
    engine = st.radio("Erkennungsverfahren", engines, index=engines.index(cur), format_func=lambda e: ENGINES[e])
    if not ki_engine.api_available() and not p.state.demo:
        st.info("KI-Erkennung nicht verfügbar: Für Scans, Fotos und fremde Planlayouts ANTHROPIC_API_KEY in der Datei .env "
                "eintragen (siehe README). Die lokale Auswertung liest nur digitale PDFs mit Text- und Vektorebene.")
    ok = True
    if engine == "ki":
        st.warning(f"Datenübertragung: Beim Start werden die Planausschnitte von {len(views)} Zeichnung(en) als Bilder samt "
                   f"PDF-Text an Anthropic übertragen (Modell {ki_engine.configured_model()}). Der BKI- und der Preiskatalog "
                   "bleiben lokal.", icon="📤")
        ok = st.checkbox("Einverstanden – Planausschnitte an Anthropic übertragen")
    force = st.checkbox("Erkennung erzwingen (Cache ignorieren)", value=False,
                        help="Normalerweise wird jede Zeichnung nur einmal gelesen. Korrekturen und Neuberechnungen lösen keinen neuen Modellaufruf aus.")
    if st.button("🔎 Pläne auswerten", type="primary", disabled=not ok):
        bar = st.progress(0.0, text="Starte …")

        def prog(n, total, label):
            bar.progress((n - 1) / max(total, 1), text=f"{n}/{total} · {label}")

        stats = p.analyze(engine, progress=prog, force=force)
        bar.progress(1.0, text="fertig")
        st.session_state["analyze_stats"] = stats
        if stats["fehler"] == 0:
            st.session_state["_goto"] = STEPS[2]
        st.rerun()
    stats = st.session_state.pop("analyze_stats", None)
    if stats:
        st.success(f"Auswertung: {stats['neu']} neu gelesen, {stats['cache']} aus Cache, {stats['fehler']} Fehler.")

    st.subheader("Stand je Zeichnung")
    rows = []
    for d, pg, v in views:
        r = p.state.runs.get(v.id)
        rows.append({"Datei": d.file_name, "Seite": pg.index + 1, "Zeichnung": v.title, "Art": VIEW_TYPES[v.view_type],
                     "Planstand": pg.plan_stand or "–", "Verfahren": ENGINES.get(r.engine, r.engine) if r else "–",
                     "Status": {"ok": "✅ gelesen", "fehler": "❌ Fehler"}.get(r.status, "⏳ offen") if r else "⏳ offen"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    failed = [(v, p.state.runs[v.id].error) for _, _, v in views if v.id in p.state.runs and p.state.runs[v.id].status == "fehler"]
    for v, err in failed:
        c1, c2 = st.columns([4, 1])
        c1.error(f"{v.title}: {err}")
        if c2.button("Nur diesen Schritt wiederholen", key=f"retry_{v.id}", disabled=not ok):
            st.session_state["analyze_stats"] = p.analyze(engine, view_ids=[v.id], force=True)
            st.rerun()


# =========================================================================================
# ③ Ergebnis
# =========================================================================================
def orientation_block(p: Project, ev: Evaluation) -> None:
    st.subheader("Bauwerkskosten KG 300+400 · BKI-Orientierung")
    cats = bki.categories()
    sug = ev.suggestion
    c1, c2, c3 = st.columns([3, 1.2, 1.2])
    with c1:
        labels = ["– Vorschlag übernehmen –"] + cats
        cur = p.state.building_category
        sel = st.selectbox("Gebäudekategorie", labels, index=labels.index(cur) if cur in labels else 0,
                           help="Vorschlag aus Projektname, Nutzung und Planbeschriftung. Bitte prüfen und festlegen.")
        new = None if sel == labels[0] else sel
        if new != cur:
            p.set_category(new)
            st.rerun()
        if ev.kategorie:
            st.caption(f"Verwendet: **{ev.kategorie}** ({ev.kategorie_quelle})"
                       + (" · " + "; ".join(sug.begruendung) if sug and ev.kategorie_quelle == "Vorschlag" and sug.begruendung else ""))
        else:
            st.warning("Keine Kategorie erkennbar – bitte auswählen.")
        if sug and len(sug.optionen) > 1 and not p.state.building_category:
            st.info("Mehrere passende Kategorien: " + "; ".join(sug.optionen))
    with c2:
        netto = st.toggle("Netto anzeigen", value=p.state.netto, help="Netto = brutto / 1,19. BKI-Werte sind brutto.")
        if netto != p.state.netto:
            p.state.netto = netto
            p.save()
            st.rerun()
    with c3:
        with st.popover("Regionalfaktor"):
            rf = p.state.regionalfaktor or {}
            reg = st.text_input("Region", rf.get("region", "Landkreis Osnabrück" if "bersenbr" in p.state.location.lower() else ""))
            fak = st.text_input("Faktor (aus BKI, ab S. 1144)", format_de(rf["faktor"], 3) if rf else "")
            qu = st.text_input("Beleg / Quelle", rf.get("quelle", ""))
            if st.button("Übernehmen"):
                f = parse_num(fak)
                if reg and f and qu.strip():
                    p.set_region(reg, f, qu)
                    st.rerun()
                st.error("Region, Faktor und Beleg sind Pflicht – ohne Beleg gilt der Bundesdurchschnitt.")
            if rf and st.button("Faktor entfernen"):
                p.set_region(None)
                st.rerun()
    if ev.region_hint:
        st.info(ev.region_hint)
    o = ev.orientation
    if o is None or not o.lines:
        for h in (o.hinweise if o else []):
            st.caption(h)
        return
    cols = st.columns(len(o.lines))
    for col, ln in zip(cols, o.lines):
        k = ln.kennwert
        calc = ev.model.bgf_calc if ln.bezugsgroesse == "BGF" else ev.model.bri_calc
        val = ev.model.bgf if ln.bezugsgroesse == "BGF" else ev.model.bri
        with col:
            mv = format_de(ln.menge, 2, ln.mengeneinheit) if ln.menge is not None else "offen"
            kpi(f"über {ln.bezugsgroesse} · {mv}", bki.fmt_eur_k(ln.mittel) if ln.mittel is not None else "offen",
                f"Spanne {bki.fmt_eur_k(ln.von)} – {bki.fmt_eur_k(ln.bis)}")
            st.markdown(f"Kennwert {k.einheit}: von **{format_de(k.von, 0)}** · mittel **{format_de(k.mittel, 0)}** · "
                        f"bis **{format_de(k.bis, 0)}**")
            st.caption(k.quelle + (f" · {bki.HINWEIS_GRAFISCH}" if k.erfassungsart == "grafisch_gerundet" else " · Tabellenwert"))
            if calc and calc.formula:
                st.caption(f"Rechenweg: {calc.formula}")
            for n in (calc.notes if calc else []):
                st.caption(n)
            if ln.hinweis:
                st.warning(ln.hinweis)
            if val is not None:
                key_evs = [e for i in (calc.inputs if calc else []) for e in uniq(i.evidence, 3)]
                evidence_button(p, key_evs or val.evidence, f"Belege {ln.bezugsgroesse} (je Eingangswert die ersten Fundstellen)",
                                key=f"ev_{ln.bezugsgroesse}")
    st.caption(f"{o.region} · {o.steuer} · Kostenstand {o.kostenstand} · " + " ".join(o.hinweise[:1]))
    with st.expander("Hinweise zur Orientierung, Tabellenwerte"):
        for h in o.hinweise:
            st.markdown(f"- {h}")
        for upd in ev.kennwert_updates or []:
            st.warning(f"Neuer Kennwert verfügbar ({upd.bezugsgroesse}, {upd.erfassungsart}): "
                       f"{format_de(upd.von, 0)} / {format_de(upd.mittel, 0)} / {format_de(upd.bis, 0)} {upd.einheit}")
            if st.button(f"Aktualisierung {upd.bezugsgroesse} übernehmen", key=f"acc_{upd.bezugsgroesse}"):
                p.accept_kennwert_update(ev.kategorie, upd.bezugsgroesse)
                st.rerun()
        if ev.kategorie:
            st.markdown("**Gedruckten Tabellenwert erfassen** (ersetzt die grafische Näherung für genau diese Bezugsgröße)")
            with st.form("tab"):
                a, b, c, d_, e_ = st.columns(5)
                bez = a.selectbox("Bezug", ["BGF", "BRI"])
                von, mit, bis = b.text_input("von"), c.text_input("mittel"), d_.text_input("bis")
                seite = e_.text_input("Buchseite", "1108" if "Gemeindezentren" in ev.kategorie else "")
                if st.form_submit_button("Tabellenwert speichern") and parse_num(mit):
                    bki.add_table_value(bki.BKIKennwert(kategorie=ev.kategorie, bezugsgroesse=bez, einheit=bki.EINHEIT[bez],
                                                        von=parse_num(von), mittel=parse_num(mit), bis=parse_num(bis),
                                                        uebersichtsseite=int(seite) if seite.isdigit() else None,
                                                        beleg=f"S. {seite}" if seite else ""))
                    st.rerun()


def cost_block(p: Project, ev: Evaluation) -> None:
    c = ev.cost
    st.subheader(c.total_label)
    a, b, d = st.columns(3)
    with a:
        kpi(c.total_label, format_eur(c.total), f"{c.preisbasis} · Preisstand {c.preisstand}")
    with b:
        kpi("Bepreiste Positionen", str(c.priced_count), "Menge × passender Bauteilkennwert")
    with d:
        kpi("Offene Positionen", str(c.open_count), "fehlender Preis, Menge oder Widerspruch")
    st.caption("Diese Summe umfasst nur die einzeln belegten Bauteile. Sie wird nicht zur BKI-Orientierung addiert.")
    if any("FIKTIV" in (pos.entry.herkunft if pos.entry else "").upper() for pos in c.positions):
        st.warning("Es werden fiktive Testpreise verwendet (nur für Demoprojekt und Abnahmetest).")
    for w in c.warnings:
        st.warning(w)
    rows = [{"": STATUS_ICON[pos.status], "KG": pos.kg, "Bauteil": pos.bauteil,
             "Menge": format_de(pos.menge) if pos.menge is not None else "–", "Einheit": pos.unit or "",
             "Preis": f"{format_de(pos.entry.preis)} €" if pos.entry else "–",
             "Betrag": format_eur(pos.betrag) if pos.status == "bepreist" else report.STATUS_DE[pos.status]}
            for pos in sorted(c.positions, key=lambda x: (x.kg, x.bauteil))]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    for pos in sorted(c.positions, key=lambda x: (x.kg, x.bauteil)):
        q = pos.quantity
        with st.expander(f"{STATUS_ICON[pos.status]} KG {pos.kg} · {pos.bauteil} · "
                         f"{format_eur(pos.betrag) if pos.status == 'bepreist' else report.STATUS_DE[pos.status]}"):
            if pos.reasons:
                st.warning(" · ".join(dict.fromkeys(pos.reasons)))
            st.markdown(f"**Menge und Formel:** {q.formula or '–'}")
            if q.ausfuehrung:
                st.caption(f"Ausführung laut Plan: {q.ausfuehrung}")
            for dl in q.details[:8]:
                st.caption(dl)
            for i, inp in enumerate(q.inputs):
                cc1, cc2 = st.columns([4, 1])
                val = f"{format_de(inp.value)} {inp.unit}" if inp.value is not None else (inp.raw_text or "–")
                cc1.markdown(f"- {inp.name}: **{val}**")
                with cc2:
                    evidence_button(p, inp.evidence, f"{pos.bauteil} · {inp.name}", key=f"evq_{pos.key}_{i}", label="Beleg")
            evidence_button(p, [e for inp in q.inputs for e in inp.evidence], f"Alle Belege · {pos.bauteil}",
                            key=f"evall_{pos.key}", label="Alle Belege im Plan")
            if pos.alternatives:
                opts = {e.id: f"{e.id} · {e.leistung or e.ausfuehrung} · {format_de(e.preis)} €/{e.einheit} ({e.herkunft})"
                        for e in pos.alternatives}
                chosen = [e.id for e in (pos.combo or ([pos.entry] if pos.entry else []))]
                sel = st.multiselect("Kennwert(e)", list(opts), default=[x for x in chosen if x in opts],
                                     format_func=opts.get, key=f"price_{pos.key}",
                                     help="Bei mehreren passenden Kennwerten auswählen. Kombinierte Aufbauten werden nicht doppelt bepreist.")
                if sorted(sel) != sorted(chosen):
                    p.set_price_choice(pos.key, sel)
                    st.rerun()
            elif pos.entry is None:
                st.caption("Kein passender Kennwert im Projektkatalog → unter ④ Preiskatalog ergänzen.")


def questions_block(p: Project, ev: Evaluation) -> None:
    m = ev.model
    vals = all_values(m)
    # Brüstungshöhen fließen in keine Menge ein: fehlende Werte sind keine Rückfrage, Widersprüche schon
    open_vals = [v for v in vals.values()
                 if v.status == "widerspruch" or (v.status == "fehlt" and v.question and not v.key.endswith(":bruestung"))]
    if len(m.stands) > 1:
        st.markdown("**Planstand**")
        opts = ["neuester (automatisch)"] + m.stands
        cur = p.state.active_stand
        sel = st.selectbox("Aktiver Planstand", opts, index=opts.index(cur) if cur in opts else 0)
        new = None if sel == opts[0] else sel
        if new != cur:
            p.set_active_stand(new)
            st.rerun()
        st.caption(f"Gerechnet wird mit: {m.active_stand}")
    if not open_vals and not p.state.overrides:
        st.success("Keine offenen Rückfragen.")
    for v in open_vals:
        with st.container(border=True):
            if v.status == "widerspruch":
                st.markdown(f"⚠️ **{v.question}**")
                for n, cnd in enumerate(v.candidates):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.markdown(f"{format_de(cnd.value)} {v.unit} · „{cnd.raw_text}“ · {cnd.origin}")
                    with c2:
                        evidence_button(p, cnd.evidence, f"{v.label} = {format_de(cnd.value)}", key=f"evc_{v.key}_{n}", label="Beleg")
                    if c3.button("Diesen Wert verwenden", key=f"use_{v.key}_{n}") and cnd.evidence:
                        chosen = cnd.evidence[0].id
                        p.set_override(v.key, chosen_evidence_id=chosen, note="Auswahl in der App", original_evidence=v.evidence)
                        # Dieselbe Kote kann mehrere Bezüge tragen (z. B. „OK Attika / OK Bekleidung“): mit auswählen
                        for other in vals.values():
                            if other.key != v.key and other.key.startswith("level:") and other.status == "widerspruch":
                                same = next((e.id for c in other.candidates for e in c.evidence
                                             if e.bbox == cnd.evidence[0].bbox and e.page == cnd.evidence[0].page
                                             and e.doc_id == cnd.evidence[0].doc_id), None)
                                if same:
                                    p.set_override(other.key, chosen_evidence_id=same, note="gleiche Kote wie " + v.label,
                                                   original_evidence=other.evidence)
                        st.rerun()
            else:
                st.markdown(f"❓ **{v.question or v.label + ' fehlt'}**")
                c1, c2 = st.columns([3, 1])
                txt = c1.text_input(f"{v.label} in {v.unit}", key=f"fill_{v.key}", placeholder="z. B. 1,20")
                if c2.button("Übernehmen", key=f"fillb_{v.key}") and parse_num(txt) is not None:
                    p.set_override(v.key, value=parse_num(txt), note="Eingabe in der App")
                    st.rerun()
    for i in m.issues:
        if i.kind in ("revision", "hinweis", "pruefen") and not (i.value_key and i.value_key in {v.key for v in open_vals}):
            st.caption(f"• {i.text}")
    for v, err in ev.failed_views:
        st.error(f"Erkennung fehlgeschlagen: {v.title} – {err[:200]} (unter ② gezielt wiederholen)")
    for v in ev.pending_views:
        st.caption(f"⏳ Noch nicht ausgewertet: {v.title}")
    if p.state.overrides:
        st.markdown("**Korrekturen**")
        for k, ov in list(p.state.overrides.items()):
            c1, c2 = st.columns([4, 1])
            what = f"Beleg {ov.chosen_evidence_id}" if ov.chosen_evidence_id else format_de(ov.value)
            c1.caption(f"{vals[k].label if k in vals else k}: {what} · {ov.note}")
            if c2.button("Zurücknehmen", key=f"undo_{k}"):
                p.clear_override(k)
                st.rerun()


def values_block(p: Project, ev: Evaluation) -> None:
    vals = all_values(ev.model)
    keys = [k for k in vals if not k.startswith("opening:")]
    rows = []
    for k in keys:
        v = vals[k]
        rows.append({"Wert": v.label, "Ergebnis": f"{format_de(v.value)} {v.unit}" if v.value is not None else "–",
                     "Status": VALUE_STATUS[v.status], "Belege": sum(len(c.evidence) for c in v.candidates),
                     "Herkunft": "; ".join(c.origin for c in v.candidates)[:120]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    ops = ev.model.openings
    if ops:
        st.markdown(f"**Öffnungen ({len(ops)})** – je gebaute Öffnung ein Datensatz mit allen Belegen")
        orow = [{"ID": o.id, "Kennung": o.label or "–", "Art": o.kind, "Fassade": FACADE_LABEL.get(o.facade or "", "–"),
                 "Breite": format_de(o.width.value), "Höhe": format_de(o.height.value), "BRH": format_de(o.sill.value),
                 "Fläche m²": format_de(o.area), "Zeichnungen": ", ".join(dict.fromkeys(o.sources))} for o in ops]
        st.dataframe(pd.DataFrame(orow), hide_index=True, width="stretch")
    with st.form("korr"):
        st.markdown("**Einzelmaß korrigieren** (der ursprüngliche Beleg bleibt verknüpft, alle Mengen werden neu berechnet)")
        allk = list(vals)
        c1, c2, c3 = st.columns([3, 1, 2])
        k = c1.selectbox("Wert", allk, format_func=lambda x: f"{vals[x].label} ({x})")
        num = c2.text_input("neuer Wert (m)")
        note = c3.text_input("Begründung", placeholder="z. B. laut Werkplan")
        if st.form_submit_button("Korrigieren") and parse_num(num) is not None:
            p.set_override(k, value=parse_num(num), note=note or "Korrektur in der App", original_evidence=vals[k].evidence)
            st.rerun()


def step_result(p: Project) -> None:
    st.header("③ Ergebnis prüfen")
    ev = p.evaluate()
    if p.state.demo:
        st.markdown("<div class='demo'>DEMOMODUS – gespeichertes Erkennungsergebnis des künstlichen Testbaus, fiktive Testpreise. "
                    "Keine Live-Planauswertung.</div>", unsafe_allow_html=True)
    if not ev.engines_used:
        st.info("Noch keine Auswertung. Bitte unter ② „Pläne auswerten“ starten.")
        return
    st.caption(f"Erkennung: {report.engine_label(p, ev)} · Planstand: {ev.model.active_stand or '–'}")
    orientation_block(p, ev)
    st.divider()
    cost_block(p, ev)
    st.divider()
    n_open = len([x for x in report.open_points(ev)])
    t1, t2 = st.tabs([f"Rückfragen & offene Punkte ({n_open})", "Einzelmaße & Öffnungen"])
    with t1:
        questions_block(p, ev)
    with t2:
        values_block(p, ev)


# =========================================================================================
# ④ Preiskatalog
# =========================================================================================
def step_catalog(p: Project) -> None:
    st.header("④ Bauteil-Preiskatalog (Projekt)")
    st.caption("Bauteilpreise aus passenden Einzelbelegen (Angebot, Bürokennwerte, BKI Bauelemente). Ein Preis wird automatisch "
               "zugeordnet, wenn Bauteiltyp, Einheit und Ausführung eindeutig passen. Der Katalog wird lokal verarbeitet.")
    entries = p.catalog()
    df = pd.DataFrame([e.model_dump() for e in entries], columns=costs.CSV_FIELDS)
    edited = st.data_editor(
        df, num_rows="dynamic", hide_index=True, width="stretch", key="cat",
        column_config={
            "bauteiltyp": st.column_config.SelectboxColumn(options=list(costs.BAUTEILTYPEN), required=True),
            "einheit": st.column_config.SelectboxColumn(options=["m²", "Stk", "m³", "m", "m² BGF"], required=True),
            "brutto_netto": st.column_config.SelectboxColumn(options=["brutto", "netto"]),
            "kennwert_art": st.column_config.SelectboxColumn(options=["bauteil", "gebaeude"]),
            "preis": st.column_config.NumberColumn(format="%.2f €", min_value=0.0),
            "aktiv": st.column_config.CheckboxColumn()})
    c1, c2, c3 = st.columns(3)
    if c1.button("Katalog speichern", type="primary"):
        out, errs = [], []
        for n, r in enumerate(edited.to_dict("records"), 1):
            if not r.get("bauteiltyp") or r.get("preis") in (None, "") or pd.isna(r.get("preis")):
                continue
            r = {k: ("" if (v is None or (isinstance(v, float) and pd.isna(v))) else v) for k, v in r.items()}
            r["id"] = r["id"] or f"K{n:02d}"
            r["aktiv"] = bool(r["aktiv"]) if r["aktiv"] != "" else True
            r["kennwert_art"] = r["kennwert_art"] or "bauteil"
            r["brutto_netto"] = r["brutto_netto"] or "brutto"
            r["kg"] = str(r["kg"] or "")
            try:
                out.append(CatalogEntry(**r))
            except Exception as exc:  # noqa: BLE001
                errs.append(f"Zeile {n}: {exc}")
        p.save_catalog(out)
        for e in errs:
            st.error(e)
        st.success(f"{len(out)} Kennwerte gespeichert.")
    c2.download_button("Als CSV exportieren", costs.catalog_to_csv(entries).encode("utf-8-sig"), "katalog.csv", "text/csv")
    with c3.popover("CSV importieren"):
        up = st.file_uploader("Katalog-CSV (Semikolon, UTF-8)", type=["csv"], key="catimp")
        if up is not None and st.button("Ersetzen"):
            p.save_catalog(costs.read_catalog_csv(up.getvalue()))
            st.rerun()
        if st.button("Fiktiven Testkatalog laden (nur Testbau!)"):
            p.save_catalog(costs.load_catalog(TESTKATALOG))
            st.rerun()
    st.caption("Spalten: " + ", ".join(costs.CSV_FIELDS) + ". „umfasst“: Schichten mit Komma, verhindert doppelte Bepreisung.")


# =========================================================================================
# ⑤ Ausgabe
# =========================================================================================
def step_output(p: Project) -> None:
    st.header("⑤ Bericht und CSV")
    ev = p.evaluate()
    c1, c2, c3 = st.columns(3)
    c1.download_button("📄 Bericht als PDF", report.build_pdf(p, ev), f"Kostenbericht_{p.state.slug}.pdf", "application/pdf",
                       type="primary", width="stretch")
    c2.download_button("📊 Positionen als CSV", report.build_csv(p, ev), f"Positionen_{p.state.slug}.csv", "text/csv",
                       width="stretch")
    c3.download_button("🖨️ Druckansicht (HTML)", report.build_html(p, ev).encode("utf-8"), f"Kostenbericht_{p.state.slug}.html",
                       "text/html", width="stretch")
    st.caption("Vorschau der Druckansicht:")
    components.html(report.build_html(p, ev), height=900, scrolling=True)


# =========================================================================================
def main() -> None:
    p = sidebar()
    if p is None:
        st.header("Baukosten aus Architekturplänen")
        st.markdown(
            "1. **Plansatz hochladen** – Grundriss, Ansichten, Schnitt als PDF (z. B. aus Archicad)\n"
            "2. **Pläne auswerten** – die App liest Maße, Koten und Öffnungen und führt sie zusammen\n"
            "3. **Ergebnis prüfen** – BKI-Bauwerkskosten KG 300+400 über BGF und BRI, bepreiste Bauteile nach DIN 276, "
            "jede Zahl mit Fundstelle im Plan\n"
            "4. **Ausgeben** – Bericht als PDF, Positionen als CSV")
        st.info("Links ein neues Projekt anlegen oder das Demoprojekt öffnen.")
        return
    st.title(p.state.name)
    st.caption(f"{p.state.building_type or 'Gebäudetyp offen'}" + (f" · {p.state.location}" if p.state.location else "")
               + f" · {len(p.state.documents)} Plan-Datei(en)")
    step = st.session_state.get("step", STEPS[0])
    {STEPS[0]: step_plans, STEPS[1]: step_analyze, STEPS[2]: step_result, STEPS[3]: step_catalog,
     STEPS[4]: step_output}[step](p)


main()
