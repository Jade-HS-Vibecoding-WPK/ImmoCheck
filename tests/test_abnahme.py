"""Abnahmetests mit den Sollwerten aus dem Projektplan (Rechenlogik, Planerkennung lokal, BKI-Orientierung).

Die Pläne werden mit scripts/testplaene.py gezeichnet. Die erwarteten Werte stehen nur hier im Test,
nicht in der Erkennungs- oder Rechenlogik.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import testplaene  # noqa: E402
from baukosten import bki, costs, report  # noqa: E402
from baukosten.project import DATA, Project  # noqa: E402
from baukosten.units import parse_measure  # noqa: E402

TESTKATALOG = DATA / "katalog" / "testkatalog.csv"
PLAENE = ROOT / "plaene"


def _project(tmp_path: Path, name="Test", katalog=TESTKATALOG) -> Project:
    return Project.create(name, "Gemeindehaus (künstlicher Testbau)", catalog_source=katalog, base=tmp_path)


def _upload(p: Project, name: str, data: bytes):
    d, new = p.add_file(name, data)
    p.analyze("lokal")
    return d, new


def _pos(ev, bauteiltyp):
    return next(x for x in ev.cost.positions if x.quantity.bauteiltyp == bauteiltyp)


# ---------------------------------------------------------------------------------------
# Einheiten
# ---------------------------------------------------------------------------------------
def test_masseinheiten_einheitlich():
    assert parse_measure("1,50 m").value_m == pytest.approx(1.5)
    assert parse_measure("150 cm").value_m == pytest.approx(1.5)
    assert parse_measure("1.500 mm").value_m == pytest.approx(1.5)
    assert parse_measure("1,50").value_m == pytest.approx(1.5)  # Dezimalzahl ohne Einheit = m
    assert parse_measure("150").value_m is None  # ohne Einheit und ohne Komma: unsicher, bleibt leer
    assert parse_measure("±0,00").value_m == 0.0
    assert parse_measure("-0,25").value_m == pytest.approx(-0.25)


# ---------------------------------------------------------------------------------------
# Bauteilkosten aus dem gezeichneten Testplansatz
# ---------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def plan_a() -> bytes:
    return testplaene.build(testplaene.Params())


def test_testbau_46212(tmp_path, plan_a):
    p = _project(tmp_path)
    _upload(p, "Testbau_Index-a.pdf", plan_a)
    ev = p.evaluate()
    soll = {"bodenplatte": (96.00, 17280.00), "fenster": (10.80, 7020.00), "aussentuer": (1.0, 900.00),
            "fassadenbekleidung": (107.10, 12852.00), "dachbelag": (96.00, 8160.00)}
    for typ, (menge, betrag) in soll.items():
        pos = _pos(ev, typ)
        assert pos.status == "bepreist", (typ, pos.reasons)
        assert pos.menge == pytest.approx(menge)
        assert pos.betrag == pytest.approx(betrag)
    assert ev.cost.total == pytest.approx(46212.00)
    assert ev.cost.priced_count == 5 and ev.cost.open_count == 0
    # mindestens eine Menge verbindet zwei Zeichnungen (Bekleidung: Grundriss + Schnitt/Ansicht)
    clad = _pos(ev, "fassadenbekleidung").quantity
    views = {e.view_title for inp in clad.inputs for e in inp.evidence}
    assert any("Grundriss" in v for v in views) and any(("Schnitt" in v or "Ansicht" in v) for v in views)
    # sechs getrennte Fenster, obwohl F01 zweimal vorkommt
    fenster = [o for o in ev.model.openings if o.kind == "fenster"]
    assert len(fenster) == 6
    assert sum(1 for o in fenster if o.label == "F01") == 2


def test_gleicher_plansatz_erneut_hochgeladen(tmp_path, plan_a):
    p = _project(tmp_path)
    _upload(p, "Testbau_Index-a.pdf", plan_a)
    d, new = _upload(p, "Kopie mit anderem Namen.pdf", plan_a)
    assert new is False
    assert len(p.state.documents) == 1
    assert p.evaluate().cost.total == pytest.approx(46212.00)


def test_bekleidung_3_50_neue_datei(tmp_path, plan_a):
    p = _project(tmp_path)
    _upload(p, "Testbau_Index-a.pdf", plan_a)
    plan_b = testplaene.build(testplaene.Params(hoehe=3.50, index="b", datum="24.11.2026"))
    _upload(p, "Testbau_Index-b_Bekleidung-3,50.pdf", plan_b)
    ev = p.evaluate()
    assert ev.model.active_stand and "Index b" in ev.model.active_stand
    assert _pos(ev, "fassadenbekleidung").menge == pytest.approx(127.10)
    assert ev.cost.total == pytest.approx(48612.00)


def test_fensterkennwert_entfernt(tmp_path, plan_a):
    p = _project(tmp_path)
    _upload(p, "Testbau_Index-a.pdf", plan_a)
    p.save_catalog([e for e in p.catalog() if e.bauteiltyp != "fenster"])
    ev = p.evaluate()
    fenster = _pos(ev, "fenster")
    assert fenster.status == "offen"
    assert fenster.menge == pytest.approx(10.80)
    assert _pos(ev, "fassadenbekleidung").menge == pytest.approx(107.10)
    assert ev.cost.total == pytest.approx(39192.00)


def test_widerspruch_hoehenkote_und_auswahl(tmp_path):
    p = _project(tmp_path)
    plan = testplaene.build(testplaene.Params(kote_sued="+3,10"))
    _upload(p, "Testbau_Widerspruch.pdf", plan)
    ev = p.evaluate()
    v = ev.model.levels["ok_bekleidung"]
    assert v.status == "widerspruch"
    clad = _pos(ev, "fassadenbekleidung")
    assert clad.status == "pruefen" and clad.betrag is None
    assert any("OK Bekleidung" in t for t in report.open_points(ev))
    # Nutzer wählt die Kote aus dem Schnitt
    cand = next(c for c in v.candidates if c.value == pytest.approx(3.0))
    eid = next(e.id for e in cand.evidence if "Schnitt" in e.view_title)
    p.set_override("level:ok_bekleidung", chosen_evidence_id=eid, note="Schnitt gilt", original_evidence=v.evidence)
    p.set_override("level:ok_attika", chosen_evidence_id=eid.replace("ok_bekleidung", "ok_attika"), note="Schnitt gilt")
    ev2 = p.evaluate()
    assert _pos(ev2, "fassadenbekleidung").menge == pytest.approx(107.10)
    assert ev2.cost.total == pytest.approx(46212.00)
    html = report.build_html(p, ev2)
    assert "46.212,00" in html
    assert report.build_pdf(p, ev2)[:4] == b"%PDF"
    assert "46.212,00".encode() in report.build_csv(p, ev2)


def test_mitgelieferte_plaene(tmp_path):
    """Die mitgelieferten PDFs im Ordner plaene/ liefern dieselben Ergebnisse."""
    p = _project(tmp_path)
    _upload(p, "a.pdf", (PLAENE / "Testbau_Plansatz_Index-a.pdf").read_bytes())
    assert p.evaluate().cost.total == pytest.approx(46212.00)
    _upload(p, "b.pdf", (PLAENE / "Testbau_Plansatz_Index-b_Bekleidung-3,50.pdf").read_bytes())
    assert p.evaluate().cost.total == pytest.approx(48612.00)


def test_ohne_katalog_bleiben_positionen_offen(tmp_path, plan_a):
    p = _project(tmp_path, katalog=None)
    _upload(p, "a.pdf", plan_a)
    ev = p.evaluate()
    assert ev.cost.total == 0 and ev.cost.priced_count == 0
    assert _pos(ev, "fenster").menge == pytest.approx(10.80)


def test_bgf_bri_aus_plan(tmp_path, plan_a):
    p = _project(tmp_path)
    _upload(p, "a.pdf", plan_a)
    m = p.evaluate().model
    assert m.bgf.value == pytest.approx(96.0)
    assert m.bri.value == pytest.approx(96.0 * 3.05)


# ---------------------------------------------------------------------------------------
# Bauwerksorientierung BKI (KG 300+400)
# ---------------------------------------------------------------------------------------
KAT = "Gemeindezentren – Holzbauweise"


def _kw(kat=KAT, table_path=None):
    cat = bki.load_catalog(table_path=table_path) if table_path else bki.load_catalog(table_path=Path("/nonexistent.csv"))
    return {b: cat[(kat, b)] for b in ("BGF", "BRI") if (kat, b) in cat}


def test_orientierung_sollwerte():
    o = bki.orientation(KAT, 100.0, 450.0, _kw())
    bgf, bri = o.line("BGF"), o.line("BRI")
    assert (bgf.von, bgf.mittel, bgf.bis) == pytest.approx((270000, 350000, 440000))
    assert (bri.von, bri.mittel, bri.bis) == pytest.approx((281250, 348750, 461250))
    assert bgf.kennwert.uebersichtsseite == 154 and bri.kennwert.uebersichtsseite == 158
    assert bgf.kennwert.erfassungsart == "grafisch_gerundet"
    assert bki.fmt_eur_k(bgf.mittel).startswith("ca.")
    assert o.region == bki.REGION_BUND


def test_orientierung_ohne_bri():
    o = bki.orientation(KAT, 100.0, None, _kw())
    assert o.line("BGF").mittel == pytest.approx(350000)
    assert o.line("BRI").status == "offen" and o.line("BRI").mittel is None


def test_leerer_von_bis_bleibt_leer():
    k = _kw("Reihenhäuser – einfacher Standard")
    assert k["BGF"].von is None and k["BGF"].bis is None and k["BGF"].mittel == 1200
    line = bki.orientation("Reihenhäuser – einfacher Standard", 100.0, None, k).line("BGF")
    assert line.von is None and line.bis is None and line.mittel == pytest.approx(120000)
    assert bki.fmt_eur_k(line.von) == "–"


def test_tabellenwert_ersetzt_nur_passende_bezugsgroesse(tmp_path):
    tp = tmp_path / "tab.csv"
    bki.add_table_value(bki.BKIKennwert(kategorie=KAT, bezugsgroesse="BGF", einheit=bki.EINHEIT["BGF"],
                                        von=2810, mittel=3520, bis=4390, uebersichtsseite=1108, beleg="S. 1108"), path=tp)
    k = _kw(table_path=tp)
    assert k["BGF"].erfassungsart == "tabellarisch_belegt" and k["BGF"].mittel == 3520
    assert k["BRI"].erfassungsart == "grafisch_gerundet" and k["BRI"].mittel == 775


def test_netto_und_regionalfaktor_genau_einmal():
    rf = bki.Regionalfaktor(region="Landkreis Osnabrück", faktor=0.9, quelle="Testwert")
    o = bki.orientation(KAT, 100.0, None, _kw(), rf, netto=True)
    assert o.line("BGF").mittel == pytest.approx(350000 * 0.9 / 1.19)
    assert o.region == "Landkreis Osnabrück"


def test_bauteilsumme_nicht_in_orientierung(tmp_path, plan_a):
    p = _project(tmp_path)
    _upload(p, "a.pdf", plan_a)
    p.set_category(KAT)
    ev = p.evaluate()
    assert ev.cost.total == pytest.approx(46212.00)
    assert ev.orientation.line("BGF").mittel == pytest.approx(96 * 3500)
    assert ev.orientation.line("BRI").mittel == pytest.approx(96 * 3.05 * 775)


def test_kategorievorschlag_holzfassade_ist_keine_holzbauweise():
    s = bki.suggest_category("Gemeindehaus", "Gemeindehaus", ["Holzbekleidung Lärche, Boden-Deckel-Schalung"])
    assert s.kategorie == "Gemeindezentren – mittlerer Standard"
    tragwerk = bki.suggest_category("Gemeindehaus", "Gemeindehaus", ["Außenwand Holzrahmenbau d = 30 cm"])
    assert tragwerk.kategorie == "Gemeindezentren – Holzbauweise"


def test_genau_sechs_we_bietet_auswahl():
    s = bki.suggest_category("Wohnhaus", "MFH 6 WE", [])
    assert len([o for o in s.optionen if "Mehrfamilienhäuser" in o]) >= 2


# ---------------------------------------------------------------------------------------
# KI-Erkennung: Ablauf ohne Netz mit einer festen Modellantwort (prüft Schema, Rückprojektion, Fehlerpfad)
# ---------------------------------------------------------------------------------------
class _FakeMessages:
    def __init__(self, answer):
        self.answer = answer

    def parse(self, **kw):
        assert kw["output_format"].__name__ == "KIErgebnis"
        return SimpleNamespace(stop_reason="end_turn", parsed_output=self.answer)


def test_ki_pfad_mit_fester_antwort(tmp_path, plan_a):
    from baukosten.pdf_prep import page_geometry
    from baukosten.recognition import ki_engine as ki

    p = _project(tmp_path)
    d, _ = p.add_file("a.pdf", plan_a)
    doc, pg, view = next((dd, pp, vv) for dd, pp, vv in p.iter_views(True) if vv.view_type == "grundriss")
    pdf = p.pdf(doc)
    geo = page_geometry(pdf[view.page])
    content, infos, spans = ki.build_request(pdf, view, geo)
    tid = next(k for k, s in spans.items() if s.text == "12,00")
    ans = ki.KIErgebnis(zeichnungsart="grundriss", titel="Grundriss EG", geschoss="EG", fassade=None,
                        links_himmelsrichtung=None, norden_oben=True, gebaeude_box=None, grundriss_rechteckig=True,
                        ketten=[ki.KIKette(richtung="horizontal", lage="unten", art="gesamtmass", bezug="gebaeude_aussen",
                                           werte=[ki.KIWert(text_id=tid, original="12,00", bild=None, box=None)])],
                        koten=[], oeffnungen=[], bauteile=[], kostenangaben=[], flaechenangaben=[], hinweise=[])
    client = SimpleNamespace(messages=_FakeMessages(ans), beta=SimpleNamespace(messages=_FakeMessages(ans)))
    res = ki.analyze_view(pdf, doc, view, geo, client=client, model="test-modell")
    seg = res.chains[0].segments[0]
    assert seg.value == pytest.approx(12.0) and seg.evidence.source == "pdf_text"
    assert seg.evidence.bbox == spans[tid].bbox  # Fundstelle aus der PDF-Textebene
    # Fehler eines Schritts bleibt auf diesen Schritt beschränkt
    bad = SimpleNamespace(messages=SimpleNamespace(parse=lambda **k: SimpleNamespace(stop_reason="max_tokens", parsed_output=None)))
    bad.beta = bad
    stats = p.analyze("ki", view_ids=[view.id], client=bad)
    assert stats["fehler"] == 1 and p.state.runs[view.id].status == "fehler"
