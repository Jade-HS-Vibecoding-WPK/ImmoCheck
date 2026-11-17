"""Baut docs/baukosten.html (Kostenrechner, eine Datei) und bettet den BKI-Katalog ein.  Aufruf: python scripts/rechner_bauen.py"""
import csv, json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
rows = []
for r in csv.DictReader((R / "data/katalog/bki_gebaeude_neubau_2026.csv").open(encoding="utf-8"), delimiter=";"):
    n = lambda k: int(r[k]) if r[k].strip() else None
    rows.append([r["gebaeudekategorie"], n("detailseite_ab"), n("diagrammseite_bgf"), n("diagrammseite_bri"),
                 n("bgf_von"), n("bgf_mittel"), n("bgf_bis"), n("bri_von"), n("bri_mittel"), n("bri_bis")])
tpl = (R / "scripts/rechner_vorlage.html").read_text(encoding="utf-8")
(R / "docs/baukosten.html").write_text(tpl.replace("/*BKI_DATA*/[]", json.dumps(rows, ensure_ascii=False)), encoding="utf-8")
print(len(rows), "Kategorien eingebettet -> docs/baukosten.html")
