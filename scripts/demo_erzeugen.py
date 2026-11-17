"""Legt das gespeicherte Erkennungsergebnis für den Demomodus an (data/demo/erkennung_demo.json).

Grundlage ist der künstliche Testplansatz (Index a). Das Ergebnis wird einmal mit der lokalen
PDF-Text-/Vektorauswertung erzeugt und gespeichert. Im Demomodus liest die App nur diese Datei,
es läuft keine Erkennung. Für eigene Pläne gilt der Demomodus nicht.

Aufruf:  python scripts/demo_erzeugen.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from baukosten.project import DEMO_DIR, Project, demo_key  # noqa: E402

PLAN = ROOT / "plaene" / "Testbau_Plansatz_Index-a.pdf"


def main() -> int:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        p = Project.create("demo-erzeugen", base=Path(tmp))
        d, _ = p.add_file(PLAN.name, PLAN.read_bytes())
        stats = p.analyze("lokal")
        results = {}
        for doc, _pg, v in p.iter_views(analyzable_only=True):
            run = p.state.runs[v.id]
            res = p.cached(run.cache_key)
            if res is not None:
                results[demo_key(doc, v)] = json.loads(res.model_dump_json())
    shutil.copy(PLAN, DEMO_DIR / PLAN.name)
    out = {"plan_file": PLAN.name, "erzeugt": datetime.now().isoformat(timespec="seconds"),
           "verfahren": "lokal (einmalig gespeichert)", "results": results}
    (DEMO_DIR / "erkennung_demo.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(results)} Zeichnungen gespeichert ({stats}) → {DEMO_DIR / 'erkennung_demo.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
