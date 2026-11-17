"""Kompakter Bericht (HTML-Druckansicht und PDF) sowie CSV-Export der Positionen."""
from __future__ import annotations

import csv
import html
import io
from datetime import datetime

import pymupdf

from . import bki
from .models import Evidence
from .project import ENGINES, Evaluation, Project
from .units import format_de, format_eur, parse_quantity

STATUS_DE = {"bepreist": "bepreist", "offen": "offen", "pruefen": "prüfen", "auswahl": "Kennwert wählen"}


def _ev_txt(e: Evidence) -> str:
    return f"{e.file_name} S.{e.page + 1} · {e.view_title} · „{e.text}“"


def _uniq_ev(evs: list[Evidence], limit: int = 6) -> list[Evidence]:
    seen, out = set(), []
    for e in evs:
        if e.id in seen:
            continue
        seen.add(e.id)
        out.append(e)
    return out[:limit]


def engine_label(p: Project, ev: Evaluation) -> str:
    names = []
    for e in sorted(ev.engines_used):
        if p.state.demo and e.startswith("demo"):
            continue
        names.append(ENGINES.get(e, e))
    if p.state.demo:
        names.insert(0, "DEMOMODUS – gespeichertes Erkennungsergebnis, keine Live-Erkennung")
    return "; ".join(dict.fromkeys(names)) or "noch keine Auswertung"


def open_points(ev: Evaluation) -> list[str]:
    pts = []
    for pos in ev.cost.positions:
        if pos.status != "bepreist":
            pts.append(f"{pos.bauteil} (KG {pos.kg}): {STATUS_DE[pos.status]} – {'; '.join(dict.fromkeys(pos.reasons)) or 'offen'}")
    for i in ev.model.issues:
        if i.kind in ("frage", "widerspruch", "revision"):
            pts.append(i.text)
    for v, err in ev.failed_views:
        pts.append(f"Erkennung fehlgeschlagen: {v.title} – {err[:160]}")
    for v in ev.pending_views:
        pts.append(f"Noch nicht ausgewertet: {v.title}")
    return list(dict.fromkeys(pts))


def build_html(p: Project, ev: Evaluation, for_pdf: bool = False) -> str:
    st, c, m = p.state, ev.cost, ev.model
    e = html.escape
    plans = []
    for d in st.documents:
        stands = sorted({pg.plan_stand or "–" for pg in d.pages})
        nums = ", ".join(sorted({pg.plan_number for pg in d.pages if pg.plan_number})) or "–"
        plans.append(f"<tr><td>{e(d.file_name)}</td><td>{len(d.pages)}</td><td>{e(nums)}</td><td>{e(', '.join(stands))}</td></tr>")
    rows = []
    for pos in sorted(c.positions, key=lambda x: (x.kg, x.bauteil)):
        price = f"{format_de(pos.entry.preis)} €/{pos.unit}" if pos.entry else "–"
        src = e(f"{pos.entry.id} · {pos.entry.herkunft} {pos.entry.beleg}".strip()) if pos.entry else "–"
        rows.append(
            f"<tr class='{pos.status}'><td>{e(pos.kg)}</td><td>{e(pos.bauteil)}</td>"
            f"<td class='r'>{format_de(pos.menge)}</td><td>{e(pos.unit or '')}</td><td class='r'>{price}</td>"
            f"<td class='r'><b>{format_eur(pos.betrag) if pos.status == 'bepreist' else 'offen'}</b></td>"
            f"<td>{e(STATUS_DE[pos.status])}</td><td class='s'>{src}</td></tr>")
    deriv = []
    for pos in c.positions:
        q = pos.quantity
        lines = [f"<p class='h'><b>{e(pos.bauteil)}</b> (KG {e(pos.kg)}) – {e(STATUS_DE[pos.status])}</p>"]
        if pos.entry:
            lines.append(f"<p>Preisquelle: {e(pos.entry.leistung)} · {format_de(pos.entry.preis)} €/{e(pos.entry.einheit)} · "
                         f"{e(pos.entry.herkunft)} {e(pos.entry.beleg)} · {e(pos.entry.preisstand)} · {e(pos.entry.brutto_netto)}</p>")
        lines.append(f"<p>Menge und Formel: {e(q.formula or '–')}</p>")
        items = []
        for inp in q.inputs:
            evs = _uniq_ev(inp.evidence, 4)
            val = f"{format_de(inp.value)} {inp.unit}" if inp.value is not None else (inp.raw_text or "–")
            fund = "; ".join(e(_ev_txt(x)) for x in evs) or "keine Fundstelle"
            items.append(f"<li>{e(inp.name)}: {e(val)} – {fund}</li>")
        if items:
            lines.append("<ul>" + "".join(items[:14]) + (f"<li>… {len(items) - 14} weitere Einzelmaße</li>" if len(items) > 14 else "") + "</ul>")
        for dline in q.details[:10]:
            lines.append(f"<p class='s'>{e(dline)}</p>")
        deriv.append("".join(lines))
    corrections = []
    for ov in st.overrides.values():
        orig = "; ".join(e(_ev_txt(x)) for x in ov.original_evidence[:3]) or "–"
        what = f"Fundstelle {ov.chosen_evidence_id}" if ov.chosen_evidence_id else f"{format_de(ov.value)}"
        corrections.append(f"<li>{e(ov.value_key)}: {e(what)} {e(ov.note)} (ursprünglicher Beleg: {orig})</li>")
    ops = "".join(f"<li>{e(t)}</li>" for t in open_points(ev)) or "<li>keine</li>"
    hints = "".join(f"<li>{e(i.text)}</li>" for i in m.issues if i.kind in ("hinweis", "pruefen")) or "<li>keine</li>"
    orient_html = orientation_html(p, ev)
    demo_note = ("<p class='warn'>DEMOMODUS: gespeichertes Erkennungsergebnis, keine Live-Planauswertung.</p>" if st.demo else "")
    fict = any("FIKTIV" in (pos.entry.herkunft if pos.entry else "").upper() for pos in c.positions)
    fict_note = "<p class='warn'>Hinweis: Es werden fiktive Testpreise verwendet (nur Demoprojekt/Abnahmetest).</p>" if fict else ""
    css = """
    body{font-family:Helvetica,Arial,sans-serif;font-size:9.5pt;color:#111;margin:0}
    h1{font-size:15pt;margin:0 0 4pt 0} h2{font-size:11pt;margin:12pt 0 4pt 0;border-bottom:1px solid #999}
    table{border-collapse:collapse;width:100%} td,th{border:1px solid #bbb;padding:2pt 4pt;vertical-align:top}
    th{background:#eee;text-align:left} .r{text-align:right} .s{font-size:8pt;color:#444}
    .big{font-size:14pt;font-weight:bold} .warn{color:#a00000;font-weight:bold} p{margin:2pt 0} .h{margin-top:6pt}
    ul{margin:2pt 0 2pt 14pt;padding:0} li{margin:1pt 0}
    @media print{ .noprint{display:none} body{margin:12mm} }"""
    printbtn = "" if for_pdf else "<p class='noprint'><button onclick='window.print()'>Drucken / als PDF speichern</button></p>"
    return f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>Kostenbericht {e(st.name)}</title>
<style>{css}</style></head><body>
{printbtn}
<h1>Kostenbericht · {e(st.name)}</h1>
<p>Gebäudetyp: {e(st.building_type or '–')} · Stand des Berichts: {datetime.now():%d.%m.%Y %H:%M}</p>
<p>Erkennung: {e(engine_label(p, ev))}</p>
<p>Aktiver Planstand: {e(m.active_stand or '–')}{' (verfügbar: ' + e(', '.join(m.stands)) + ')' if len(m.stands) > 1 else ''}</p>
{demo_note}{fict_note}
{orient_html}
<h2>Bepreiste Teilkosten (planbelegte Einzelbauteile)</h2>
<p class="big">{e(c.total_label)}: {format_eur(c.total)}</p>
<p>Preisbasis: {e(c.preisbasis)} · Preisstand: {e(c.preisstand)} · bepreist: {c.priced_count} · offen/prüfen: {c.open_count}</p>
<p class="s">Summe der auf Cent gerundeten Positionen. Es werden keine Gesamtprojektkosten aus einem lückenhaften Plansatz berechnet;
nicht belegte Leistungen (z. B. TGA, Gründungsausführung) sind nicht enthalten.</p>
<h2>Erfasste Leistungen nach DIN 276</h2>
<table><tr><th>KG</th><th>Bauteil</th><th>Menge</th><th>Einh.</th><th>Einheitspreis</th><th>Betrag</th><th>Status</th><th>Kennwert</th></tr>
{''.join(rows)}</table>
<h2>Offene Punkte</h2><ul>{ops}</ul>
<h2>Herleitung (Preisquelle → Menge/Formel → Einzelmaße → Planfundstellen)</h2>
{''.join(deriv)}
<h2>Korrekturen</h2><ul>{''.join(corrections) or '<li>keine</li>'}</ul>
<h2>Hinweise</h2><ul>{hints}</ul>
<h2>Plansatz</h2>
<table><tr><th>Datei</th><th>Seiten</th><th>Plan-Nr.</th><th>Planstand</th></tr>{''.join(plans)}</table>
</body></html>"""


def orientation_html(p: Project, ev: Evaluation) -> str:
    e = html.escape
    o = ev.orientation
    if o is None:
        return ""
    head = (f"<h2>Bauwerksorientierung · Bauwerkskosten KG 300+400</h2>"
            f"<p>Gebäudekategorie: <b>{e(ev.kategorie or 'nicht gewählt')}</b>"
            f"{' (' + e(ev.kategorie_quelle) + ')' if ev.kategorie_quelle else ''}</p>")
    if not o.lines:
        return head + f"<p>{e(' '.join(o.hinweise))}</p>"
    rows = []
    for l in o.lines:
        k = l.kennwert
        calc = ev.model.bgf_calc if l.bezugsgroesse == "BGF" else ev.model.bri_calc
        val = ev.model.bgf if l.bezugsgroesse == "BGF" else ev.model.bri
        approx = k.erfassungsart == "grafisch_gerundet"
        src = (f"Diagramm S. {k.uebersichtsseite}" if approx else f"Tabelle S. {k.uebersichtsseite} {k.beleg}") + \
              (f", Detailkapitel ab S. {k.detailseite_ab}" if k.detailseite_ab else "")
        evs = sorted(val.evidence if val else [], key=lambda x: -(parse_quantity(x.text)[0] or 0))
        fund = "; ".join(e(_ev_txt(x)) for x in _uniq_ev(evs, 4))
        kw = " / ".join("–" if x is None else format_de(x, 0) for x in (k.von, k.mittel, k.bis))
        rows.append(
            f"<tr><td><b>{e(l.label)}</b></td><td>{format_de(l.menge)} {l.mengeneinheit}</td><td>{kw} {e(k.einheit)}</td>"
            f"<td class='r'>{bki.fmt_eur_k(l.von)}</td><td class='r'><b>{bki.fmt_eur_k(l.mittel)}</b></td><td class='r'>{bki.fmt_eur_k(l.bis)}</td>"
            f"<td class='s'>{e(src)}<br>{'Näherungswert – ' + e(bki.HINWEIS_GRAFISCH) if approx else 'tabellarisch belegt'}</td></tr>"
            f"<tr><td colspan='7' class='s'>Menge: {e(calc.formula if calc and calc.formula else (val.candidates[0].origin if val and val.candidates else 'offen'))}"
            f" {e(' '.join(calc.notes) if calc else '')} · Belege: {fund or '–'}{' · ' + e(l.hinweis) if l.hinweis else ''}</td></tr>")
    rf = o.regionalfaktor
    return head + ("<table><tr><th>Rechenweg</th><th>Menge</th><th>Kennwert von/mittel/bis</th><th>Von</th><th>Mittel</th><th>Bis</th>"
                   "<th>Quelle</th></tr>" + "".join(rows) + "</table>"
                   f"<p class='s'>Preisstand {e(o.kostenstand)} · {e(o.region)}"
                   f"{' (Faktor ' + format_de(rf.faktor, 3) + ', ' + e(rf.quelle) + ')' if rf else ''} · {e(o.steuer)}. "
                   f"Beträge auf Tausend Euro gerundet. {e(' '.join(o.hinweise))}</p>")


def build_pdf(p: Project, ev: Evaluation) -> bytes:
    """PDF direkt aus dem HTML-Bericht (PyMuPDF Story), A4 hoch."""
    src = build_html(p, ev, for_pdf=True)
    story = pymupdf.Story(html=src)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (40, 40, -40, -40)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()


def build_csv(p: Project, ev: Evaluation) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Projekt", p.state.name, "Planstand", ev.model.active_stand or "", "Erkennung", engine_label(p, ev)])
    w.writerow(["KG", "Bauteil", "Menge", "Einheit", "Einheitspreis €", "Betrag €", "Status", "Preisbasis", "Preisstand",
                "Kennwert-ID", "Kennwert-Herkunft", "Formel", "Fundstellen", "Offene Gründe"])
    for pos in sorted(ev.cost.positions, key=lambda x: (x.kg, x.bauteil)):
        q = pos.quantity
        evs = _uniq_ev([x for inp in q.inputs for x in inp.evidence], 12)
        w.writerow([pos.kg, pos.bauteil, format_de(pos.menge, 3) if pos.menge is not None else "", pos.unit or "",
                    format_de(pos.entry.preis) if pos.entry else "",
                    format_de(pos.betrag) if pos.status == "bepreist" else "", STATUS_DE[pos.status],
                    pos.entry.brutto_netto if pos.entry else "", pos.entry.preisstand if pos.entry else "",
                    pos.entry.id if pos.entry else "", pos.entry.herkunft if pos.entry else "", q.formula,
                    " | ".join(_ev_txt(x) for x in evs), "; ".join(dict.fromkeys(pos.reasons))])
    w.writerow([])
    o = ev.orientation
    if o is not None and o.lines:
        w.writerow(["Bauwerksorientierung KG 300+400 (nicht addiert, nicht gemittelt)", ev.kategorie or "", o.region, o.steuer, o.kostenstand])
        w.writerow(["Rechenweg", "Menge", "Einheit", "Kennwert von", "Kennwert mittel", "Kennwert bis", "Kennwert-Einheit",
                    "Betrag von €", "Betrag mittel €", "Betrag bis €", "Quelle", "Erfassungsart"])
        for l in o.lines:
            k = l.kennwert
            f = lambda x, d=2: "" if x is None else format_de(x, d)  # noqa: E731
            w.writerow([l.label, f(l.menge), l.mengeneinheit, f(k.von, 0), f(k.mittel, 0), f(k.bis, 0), k.einheit,
                        f(l.von), f(l.mittel), f(l.bis), k.quelle, k.erfassungsart])
        w.writerow([])
    w.writerow(["", ev.cost.total_label, "", "", "", format_de(ev.cost.total), f"{ev.cost.priced_count} bepreist / {ev.cost.open_count} offen"])
    return buf.getvalue().encode("utf-8-sig")
