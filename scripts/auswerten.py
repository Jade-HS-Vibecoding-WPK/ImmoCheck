"""Baukosten aus Plan-PDFs: Erkennung → BGF/BRI → BKI-Orientierung KG 300+400 → Bauteilmengen → Bericht.

Aufruf (Beispiele):
    python scripts/auswerten.py plan1.pdf plan2.pdf --out AUSGABE --name "Gemeindehaus" --typ "Gemeindehaus" --standort Bersenbrück
    python scripts/auswerten.py --out AUSGABE --setze bgf=100           # erneut rechnen mit Korrektur
    python scripts/auswerten.py --out AUSGABE --wahl level:ok_bekleidung=<Fundstellen-ID>
    python scripts/auswerten.py --out AUSGABE --kategorie "Gemeindezentren – Holzbauweise" --netto

Das Projekt wird in AUSGABE/projekt gespeichert. Ein erneuter Aufruf mit demselben --out nutzt den
Erkennungs-Cache und alle bisherigen Korrekturen (keine Doppelzählung bei erneutem Upload).

Ausgabe in AUSGABE:
    ergebnis.md      Zusammenfassung zum Vorlesen/Präsentieren
    ergebnis.json    alle Werte mit Belegen, Fragen, Widersprüchen (für Rückfragen und Korrekturen)
    bericht.pdf      Druckbericht · mengen.csv  CSV-Export
    fundstellen/     PNG-Ausschnitte mit rot markierten Fundstellen
    seiten/          Übersichtsbilder aller Planseiten (für die Sichtprüfung)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _ensure_deps() -> None:
    missing = []
    for mod, pkg in (("pymupdf", "pymupdf"), ("pydantic", "pydantic"), ("PIL", "pillow")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *missing])


_ensure_deps()

from baukosten import bki, report  # noqa: E402
from baukosten.models import BBox, Evidence, Value  # noqa: E402
from baukosten.pdf_prep import render_marked, render_thumbnail  # noqa: E402
from baukosten.project import DATA, Project  # noqa: E402
from baukosten.units import format_de, format_eur  # noqa: E402

TESTKATALOG = DATA / "katalog" / "testkatalog.csv"


def _num(s: str) -> float:
    return float(s.strip().replace(".", "").replace(",", ".") if "," in s else s.strip())


def _ev(e: Evidence) -> dict:
    return {"id": e.id, "datei": e.file_name, "seite": e.page + 1, "zeichnung": e.view_title, "text": e.text}


def _val(v: Value | None) -> dict | None:
    if v is None:
        return None
    return {
        "key": v.key, "bezeichnung": v.label, "einheit": v.unit, "wert": v.value, "status": v.status,
        "frage": v.question,
        "kandidaten": [{"wert": c.value, "originaltext": c.raw_text, "herkunft": c.origin,
                        "fundstellen": [_ev(e) for e in c.evidence[:6]]} for c in v.candidates],
    }


def _open_project(out: Path, a) -> Project:
    pdir = out / "projekt"
    if (pdir / "project.json").exists():
        p = Project.load(pdir)
    else:
        if not a.pdfs:
            sys.exit("Keine Plan-PDFs angegeben und kein bestehendes Projekt in --out gefunden.")
        out.mkdir(parents=True, exist_ok=True)
        katalog = TESTKATALOG if a.katalog == "test" else (Path(a.katalog) if a.katalog else None)
        p = Project.create("projekt", a.typ or "", catalog_source=katalog, base=out)
        if p.path != pdir:
            p.path.rename(pdir)
            p = Project.load(pdir)
        p.state.name = a.name or "Projekt"
    if a.name:
        p.state.name = a.name
    if a.typ:
        p.state.building_type = a.typ
    if a.standort:
        p.state.location = a.standort
    p.save()
    return p


def _apply_options(p: Project, a, model_before=None) -> list[str]:
    msgs = []
    if a.katalog:
        src = TESTKATALOG if a.katalog == "test" else Path(a.katalog)
        if not src.exists():
            sys.exit(f"Katalog nicht gefunden: {src}")
        p.catalog_path.write_bytes(src.read_bytes())
    if a.kategorie is not None:
        cats = bki.categories()
        if a.kategorie == "":
            p.set_category(None)
        elif a.kategorie in cats:
            p.set_category(a.kategorie)
        else:
            near = [c for c in cats if a.kategorie.lower() in c.lower()]
            if len(near) == 1:
                p.set_category(near[0])
            else:
                sys.exit(f"Kategorie „{a.kategorie}“ nicht eindeutig. Treffer: {near or 'keine'} "
                         "(Liste: python scripts/orientierung.py --liste)")
    if a.netto is not None:
        p.state.netto = a.netto
        p.save()
    if a.faktor is not None:
        if not (a.region and a.quelle):
            sys.exit("Regionalfaktor nur mit --region und --quelle (Beleg, z. B. „BKI 2026, S. 1144“).")
        p.set_region(a.region, a.faktor, a.quelle)
    if a.ohne_regionalfaktor:
        p.set_region(None)
    if a.stand is not None:
        p.set_active_stand(a.stand or None)
    for s in a.setze or []:
        key, _, val = s.partition("=")
        if val.strip().lower() in ("", "zurück", "zurueck", "reset"):
            p.clear_override(key.strip())
        else:
            p.set_override(key.strip(), value=_num(val), note=a.notiz or "Korrektur im Chat")
        msgs.append(f"Korrektur gesetzt: {s}")
    if a.wahl:
        ev = p.evaluate()
        allv = _all_values(ev.model)
        for w in a.wahl:
            key, _, eid = w.partition("=")
            v = allv.get(key.strip())
            if v is None:
                sys.exit(f"Unbekannter Wert „{key}“. Bekannte Schlüssel: {', '.join(sorted(allv))}")
            orig = [e for c in v.candidates for e in c.evidence]
            p.set_override(key.strip(), chosen_evidence_id=eid.strip(), note=a.notiz or "Auswahl im Chat", original_evidence=orig)
            msgs.append(f"Auswahl gesetzt: {w}")
    return msgs


def _all_values(m) -> dict[str, Value]:
    out = {"len:x": m.length_x, "len:y": m.length_y}
    out.update({v.key: v for v in m.levels.values()})
    for o in m.openings:
        for v in (o.width, o.height, o.sill):
            out[v.key] = v
    for v in (m.roof_pitch, m.bgf, m.bri):
        if v is not None:
            out[v.key] = v
    return out


def _mark(p: Project, folder: Path, name: str, evs: list[Evidence], label: str) -> str | None:
    evs = [e for e in evs if e.bbox is not None]
    if not evs:
        return None
    e0 = evs[0]
    d = p.doc(e0.doc_id)
    same = [e for e in evs if e.doc_id == e0.doc_id and e.page == e0.page]
    view = next((v for pg in d.pages if pg.index == e0.page for v in pg.views if v.id == e0.view_id), None) if e0.view_id else None
    clip = view.bbox if view else BBox(x0=min(e.bbox.x0 for e in same) - 120, y0=min(e.bbox.y0 for e in same) - 120,
                                       x1=max(e.bbox.x1 for e in same) + 120, y1=max(e.bbox.y1 for e in same) + 120)
    try:
        png = render_marked(p.pdf(d), e0.page, clip, [(e.bbox, label if i == 0 else "") for i, e in enumerate(same)])
    except Exception:  # noqa: BLE001
        return None
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / f"{name}.png"
    f.write_bytes(png)
    return str(f)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdfs", nargs="*", type=Path, help="Plan-PDFs (Grundriss, Ansichten, Schnitte)")
    ap.add_argument("--out", type=Path, required=True, help="Ausgabeordner (enthält auch das Projekt)")
    ap.add_argument("--name", help="Projektname")
    ap.add_argument("--typ", help="Gebäudeart/Nutzung, z. B. „Gemeindehaus“, „Kita“, „MFH 6 WE“")
    ap.add_argument("--standort", help="Ort (nur Hinweis; Regionalfaktor nur mit Beleg)")
    ap.add_argument("--katalog", help="Bauteil-Preiskatalog (CSV) oder „test“ für den fiktiven Testkatalog")
    ap.add_argument("--kategorie", help="BKI-Gebäudekategorie festlegen ('' = wieder Vorschlag)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--netto", dest="netto", action="store_true", default=None, help="Netto (= brutto / 1,19) anzeigen")
    g.add_argument("--brutto", dest="netto", action="store_false", help="Brutto anzeigen (Standard)")
    ap.add_argument("--region")
    ap.add_argument("--faktor", type=float, help="Regionalfaktor (nur mit --region und --quelle)")
    ap.add_argument("--quelle", help="Beleg für den Regionalfaktor")
    ap.add_argument("--ohne-regionalfaktor", action="store_true")
    ap.add_argument("--stand", help="aktiven Planstand festlegen, z. B. „Index a“ ('' = neuester)")
    ap.add_argument("--setze", action="append", metavar="SCHLÜSSEL=WERT", help="Wert korrigieren, z. B. bgf=100, len:x=12,50 (=zurück hebt auf)")
    ap.add_argument("--wahl", action="append", metavar="SCHLÜSSEL=FUNDSTELLEN-ID", help="bei Widerspruch einen Beleg wählen")
    ap.add_argument("--notiz", help="Begründung zur Korrektur (erscheint im Bericht)")
    a = ap.parse_args()

    out: Path = a.out
    p = _open_project(out, a)
    msgs = []
    for f in a.pdfs:
        d, new = p.add_file(f.name, f.read_bytes())
        msgs.append(f"{f.name}: {'hochgeladen' if new else 'bereits im Projekt (gleicher Inhalt) – nicht doppelt gezählt'}"
                    f", {len(d.pages)} Seite(n)")
    stats = p.analyze("lokal")
    msgs += _apply_options(p, a)
    ev = p.evaluate()
    m, c, o = ev.model, ev.cost, ev.orientation

    # ---------------- Bilder --------------------------------------------------------------
    seiten = []
    for d in p.state.documents:
        pdf = p.pdf(d)
        for pg in d.pages:
            f = out / "seiten" / f"{Path(d.file_name).stem}_S{pg.index + 1}.png"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(render_thumbnail(pdf, pg.index, pg.views, max_px=1600))
            seiten.append(str(f))
    fund = {}
    allv = _all_values(m)
    for key in ("len:x", "len:y", "bgf", "bri", *[k for k in allv if k.startswith("level:")]):
        v = allv.get(key)
        if v is None:
            continue
        evs = [e for cand in v.candidates for e in cand.evidence]
        f = _mark(p, out / "fundstellen", key.replace(":", "_"), evs, v.label)
        if f:
            fund[key] = f

    # ---------------- Dateien -------------------------------------------------------------
    (out / "bericht.pdf").write_bytes(report.build_pdf(p, ev))
    (out / "mengen.csv").write_bytes(report.build_csv(p, ev))

    views = []
    for d, pg, v in p.iter_views():
        run = p.state.runs.get(v.id)
        views.append({"datei": d.file_name, "seite": pg.index + 1, "titel": v.title, "art": v.view_type,
                      "planstand": pg.plan_stand, "status": run.status if run else "nicht ausgewertet",
                      "fehler": run.error if run and run.error else None})
    lines = []
    for ln in (o.lines if o else []):
        k = ln.kennwert
        lines.append({
            "bezug": ln.bezugsgroesse, "menge": ln.menge, "mengeneinheit": ln.mengeneinheit,
            "kennwert": {"von": k.von, "mittel": k.mittel, "bis": k.bis, "einheit": k.einheit,
                         "buchseite": k.uebersichtsseite, "detailseiten_ab": k.detailseite_ab,
                         "erfassung": k.erfassungsart, "quelle": k.quelle},
            "kosten": {"von": ln.von, "mittel": ln.mittel, "bis": ln.bis},
            "anzeige": {"von": bki.fmt_eur_k(ln.von), "mittel": bki.fmt_eur_k(ln.mittel), "bis": bki.fmt_eur_k(ln.bis)},
            "status": ln.status, "hinweis": ln.hinweis,
        })
    data = {
        "meldungen": msgs, "erkennung": stats, "zeichnungen": views,
        "gebaeudekategorie": {"gewaehlt": ev.kategorie, "quelle": ev.kategorie_quelle,
                              "vorschlag": ev.suggestion.kategorie if ev.suggestion else None,
                              "optionen": ev.suggestion.optionen if ev.suggestion else [],
                              "begruendung": ev.suggestion.begruendung if ev.suggestion else []},
        "bgf": _val(m.bgf), "bri": _val(m.bri),
        "rechenweg": {"bgf": m.bgf_calc.model_dump() if m.bgf_calc else None,
                      "bri": m.bri_calc.model_dump() if m.bri_calc else None},
        "orientierung": {"zeilen": lines, "region": o.region if o else None,
                         "regionalfaktor": o.regionalfaktor.model_dump() if o and o.regionalfaktor else None,
                         "steuer": o.steuer if o else None, "kostenstand": o.kostenstand if o else None,
                         "hinweise": o.hinweise if o else [], "regionshinweis": ev.region_hint},
        "werte": {k: _val(v) for k, v in allv.items()},
        "bauteilkosten": {
            "bezeichnung": c.total_label, "summe": c.total, "preisbasis": c.preisbasis,
            "bepreist": c.priced_count, "offen": c.open_count,
            "positionen": [{"key": pos.key, "kg": pos.kg, "bauteil": pos.bauteil, "menge": pos.menge, "einheit": pos.unit,
                            "preis": pos.entry.preis if pos.entry else None,
                            "kennwert": f"{pos.entry.id} · {pos.entry.herkunft}" if pos.entry else None,
                            "betrag": pos.betrag, "status": pos.status, "gruende": list(dict.fromkeys(pos.reasons)),
                            "formel": pos.quantity.formula} for pos in c.positions],
        },
        "planstaende": {"aktiv": m.active_stand, "alle": m.stands},
        "offene_punkte": report.open_points(ev),
        "korrekturen": {k: {"wert": ov.value, "beleg": ov.chosen_evidence_id, "notiz": ov.note} for k, ov in p.state.overrides.items()},
        "dateien": {"bericht": str(out / "bericht.pdf"), "csv": str(out / "mengen.csv"), "fundstellen": fund, "seiten": seiten},
    }
    (out / "ergebnis.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    # ---------------- Zusammenfassung -----------------------------------------------------
    L = [f"# Baukosten – {p.state.name}", ""]
    L += [f"- {s}" for s in msgs]
    L.append(f"- Erkennung (lokale PDF-Text-/Vektorauswertung): {stats['neu']} neu, {stats['cache']} aus Cache, {stats['fehler']} Fehler")
    L += ["", "## Bauwerkskosten KG 300+400 (BKI-Orientierung)", ""]
    kat = ev.kategorie or "– (bitte wählen)"
    L.append(f"Gebäudekategorie: **{kat}** ({ev.kategorie_quelle or 'offen'})")
    if ev.suggestion and len(ev.suggestion.optionen) > 1:
        L.append("Weitere passende Kategorien: " + "; ".join(x for x in ev.suggestion.optionen if x != ev.kategorie))
    if o:
        L.append(f"Region: {o.region}" + (f" · Faktor {format_de(o.regionalfaktor.faktor, 3)} ({o.regionalfaktor.quelle})" if o.regionalfaktor else "")
                 + f" · {o.steuer} · Kostenstand {o.kostenstand}")
    if ev.region_hint:
        L.append(f"> {ev.region_hint}")
    for ln in (o.lines if o else []):
        k = ln.kennwert
        mv = format_de(ln.menge, 2, ln.mengeneinheit) if ln.menge is not None else "offen"
        L += ["", f"### Über {ln.bezugsgroesse}: {mv}",
              f"| | Von | Mittel | Bis |", "|---|---|---|---|",
              f"| Kennwert ({k.einheit}) | {format_de(k.von, 0)} | {format_de(k.mittel, 0)} | {format_de(k.bis, 0)} |",
              f"| Kosten | {bki.fmt_eur_k(ln.von)} | **{bki.fmt_eur_k(ln.mittel)}** | {bki.fmt_eur_k(ln.bis)} |",
              f"Quelle: {k.quelle}" + (f" · {bki.HINWEIS_GRAFISCH}" if k.erfassungsart == "grafisch_gerundet" else "")]
        if ln.hinweis:
            L.append(f"Hinweis: {ln.hinweis}")
    for key, calc in (("BGF", m.bgf_calc), ("BRI", m.bri_calc)):
        v = m.bgf if key == "BGF" else m.bri
        if v is not None:
            L.append(f"\n{key}: {format_de(v.value, 2, v.unit) if v.value is not None else 'offen'} · Status {v.status}"
                     + (f" · Rechenweg: {calc.formula}" if calc and calc.formula else "")
                     + ("" if not calc or not calc.notes else " · " + "; ".join(calc.notes)))
    L += [""] + [f"- {h}" for h in (o.hinweise if o else [])]
    L += ["", f"## {c.total_label}", "",
          "| KG | Bauteil | Menge | Einheit | Preis | Betrag | Status |", "|---|---|---|---|---|---|---|"]
    for pos in sorted(c.positions, key=lambda x: (x.kg, x.bauteil)):
        L.append(f"| {pos.kg} | {pos.bauteil} | {format_de(pos.menge)} | {pos.unit or ''} | "
                 f"{format_de(pos.entry.preis) + ' €' if pos.entry else '–'} | "
                 f"{format_eur(pos.betrag) if pos.status == 'bepreist' else 'offen'} | {report.STATUS_DE[pos.status]} |")
    L.append(f"\n**Summe {c.total_label}: {format_eur(c.total)}** ({c.preisbasis}; {c.priced_count} bepreist, {c.open_count} offen)"
             " – nicht zur BKI-Orientierung addieren.")
    if not p.catalog():
        L.append("Kein Bauteil-Preiskatalog hinterlegt → Bauteilpositionen offen (Mengen trotzdem ermittelt).")
    pts = report.open_points(ev)
    if pts:
        L += ["", "## Offene Punkte / Rückfragen", ""] + [f"- {x}" for x in pts]
    L += ["", "## Dateien", f"- Bericht: {out / 'bericht.pdf'}", f"- CSV: {out / 'mengen.csv'}"]
    L += [f"- Fundstelle {k}: {f}" for k, f in fund.items()]
    (out / "ergebnis.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
