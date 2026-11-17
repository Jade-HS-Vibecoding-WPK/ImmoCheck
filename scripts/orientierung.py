"""BKI-Orientierung KG 300+400 direkt aus BGF/BRI – für Werte, die nicht per Planerkennung kamen
(z. B. von Claude im Planbild abgelesen, vom Nutzer genannt, oder die Gegenprobe).

    python scripts/orientierung.py --liste [SUCHWORT]
    python scripts/orientierung.py --kategorie "Gemeindezentren – Holzbauweise" --bgf 100
    python scripts/orientierung.py --kategorie Kindergärten --bgf 480 --bri 1750 --netto
    python scripts/orientierung.py --vorschlag --typ "Gemeindehaus" --text "Holzrahmenbau, 2 Geschosse"
    ... --region "Landkreis Osnabrück" --faktor 1.02 --quelle "BKI 2026, S. 1144"   (nur mit Beleg!)
Ausgabe: Markdown-Tabelle; mit --json zusätzlich maschinenlesbar.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from baukosten import bki
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pydantic"])
    from baukosten import bki
from baukosten.units import format_de  # noqa: E402


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip()
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--liste", nargs="?", const="", help="Kategorien auflisten (optional gefiltert)")
    ap.add_argument("--vorschlag", action="store_true", help="Kategorie aus --typ/--text vorschlagen")
    ap.add_argument("--typ", default="")
    ap.add_argument("--text", default="", help="Planbeschriftung/Beschreibung für den Vorschlag")
    ap.add_argument("--kategorie")
    ap.add_argument("--bgf", help="m² BGF")
    ap.add_argument("--bri", help="m³ BRI")
    ap.add_argument("--netto", action="store_true")
    ap.add_argument("--region")
    ap.add_argument("--faktor", type=float)
    ap.add_argument("--quelle")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cats = bki.categories()

    if a.liste is not None:
        cat = bki.load_catalog()
        for c in cats:
            if a.liste.lower() in c.lower():
                g, r = cat.get((c, "BGF")), cat.get((c, "BRI"))
                print(f"{c} | BGF mittel {format_de(g.mittel, 0) if g else '–'} €/m² (S. {g.uebersichtsseite if g else '–'})"
                      f" | BRI mittel {format_de(r.mittel, 0) if r else '–'} €/m³")
        return 0
    if a.vorschlag:
        s = bki.suggest_category("", a.typ, [a.text])
        print(json.dumps(s.model_dump(), ensure_ascii=False, indent=1))
        return 0
    if not a.kategorie:
        ap.error("--kategorie fehlt (oder --liste / --vorschlag)")
    kat = a.kategorie if a.kategorie in cats else None
    if kat is None:
        near = [c for c in cats if a.kategorie.lower() in c.lower()]
        if len(near) != 1:
            sys.exit(f"Kategorie nicht eindeutig: {near or 'keine Treffer'}")
        kat = near[0]
    rf = None
    if a.faktor is not None:
        if not (a.region and a.quelle):
            sys.exit("Regionalfaktor nur mit --region und --quelle (Beleg).")
        rf = bki.Regionalfaktor(region=a.region, faktor=a.faktor, quelle=a.quelle)
    cat = bki.load_catalog()
    kw = {b: cat[(kat, b)] for b in ("BGF", "BRI") if (kat, b) in cat}
    res = bki.orientation(kat, _num(a.bgf), _num(a.bri), kw, rf, a.netto)
    print(f"## Bauwerkskosten {bki.KG_UMFANG} – {kat}")
    print(f"{res.region}{f' · Faktor {format_de(rf.faktor, 3)} ({rf.quelle})' if rf else ''} · {res.steuer} · Kostenstand {res.kostenstand}\n")
    for ln in res.lines:
        k = ln.kennwert
        menge = format_de(ln.menge, 2, ln.mengeneinheit) if ln.menge is not None else "nicht angegeben"
        print(f"### Über {ln.bezugsgroesse}: {menge}")
        print("| | Von | Mittel | Bis |\n|---|---|---|---|")
        print(f"| Kennwert ({k.einheit}) | {format_de(k.von, 0)} | {format_de(k.mittel, 0)} | {format_de(k.bis, 0)} |")
        if ln.menge is not None:
            print(f"| Kosten | {bki.fmt_eur_k(ln.von)} | **{bki.fmt_eur_k(ln.mittel)}** | {bki.fmt_eur_k(ln.bis)} |")
        print(f"Quelle: {k.quelle}" + (f" · {bki.HINWEIS_GRAFISCH}" if k.erfassungsart == "grafisch_gerundet" else ""))
        if ln.hinweis:
            print(f"Hinweis: {ln.hinweis}")
        print()
    for h in res.hinweise:
        print(f"- {h}")
    if a.json:
        print("\n```json\n" + res.model_dump_json(indent=1) + "\n```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
