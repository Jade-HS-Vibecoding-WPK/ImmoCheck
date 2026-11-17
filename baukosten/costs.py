"""Preiskatalog, Kennwertzuordnung und Kostensumme.

Eurobetrag = ermittelte Menge × zugeordneter Preis. Mengen ungerundet, Positionsbetrag
kaufmännisch auf Cent gerundet, Summe einmal über die gerundeten Positionen.
Fehlende Preise/Mengen oder ungeklärte Widersprüche bleiben „offen“ und werden nicht summiert.
"""
from __future__ import annotations

import csv
import io
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .models import CatalogEntry, CostPosition, CostResult, Quantity

CSV_FIELDS = ["id", "bauteiltyp", "ausfuehrung", "kg", "leistung", "einheit", "bezugsgroesse", "preis", "herkunft",
              "beleg", "preisstand", "brutto_netto", "region", "umfasst", "kennwert_art", "aktiv"]

BAUTEILTYPEN = {
    "bodenplatte": "Bodenplatte (KG 322)",
    "fenster": "Fenster / Außenfenster (KG 334)",
    "aussentuer": "Außentür (KG 334)",
    "fassadenbekleidung": "Äußere Bekleidung (KG 335)",
    "dachbelag": "Dachbelag (KG 363)",
    "gebaeude": "Gebäudekennwert €/m² BGF (nur Orientierung)",
}


def norm_unit(u: str) -> str:
    s = (u or "").strip().lower().replace("€/", "").replace("eur/", "")
    if s in ("m2", "m²", "qm", "m^2"):
        return "m²"
    if s in ("st", "stk", "stk.", "stück", "stueck", "st."):
        return "Stk"
    if s in ("m3", "m³", "cbm"):
        return "m³"
    if s in ("m", "lfm", "lfdm"):
        return "m"
    if "bgf" in s:
        return "m² BGF"
    return u.strip()


def _num(s: str) -> float:
    s = str(s).strip().replace("€", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    return float(s)


def read_catalog_csv(data: str | bytes) -> list[CatalogEntry]:
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig")
    sample = data[:2000]
    delim = ";" if sample.count(";") >= sample.count(",") else ","
    rows = csv.DictReader(io.StringIO(data), delimiter=delim)
    out = []
    for n, r in enumerate(rows, 1):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        if not r.get("bauteiltyp") or not r.get("preis"):
            continue
        out.append(CatalogEntry(
            id=r.get("id") or f"K{n:03d}", bauteiltyp=r["bauteiltyp"].lower(), ausfuehrung=r.get("ausfuehrung", ""),
            kg=r.get("kg", ""), leistung=r.get("leistung", ""), einheit=norm_unit(r.get("einheit", "")),
            bezugsgroesse=r.get("bezugsgroesse", ""), preis=_num(r["preis"]), herkunft=r.get("herkunft", ""),
            beleg=r.get("beleg", ""), preisstand=r.get("preisstand", ""),
            brutto_netto="netto" if r.get("brutto_netto", "brutto").lower().startswith("n") else "brutto",
            region=r.get("region", ""), umfasst=r.get("umfasst", ""),
            kennwert_art="gebaeude" if r.get("kennwert_art", "").lower().startswith("geb") else "bauteil",
            aktiv=r.get("aktiv", "ja").lower() not in ("nein", "0", "false", "n"),
        ))
    return out


def load_catalog(path: Path) -> list[CatalogEntry]:
    if not path.exists():
        return []
    return read_catalog_csv(path.read_bytes())


def catalog_to_csv(entries: list[CatalogEntry]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, delimiter=";")
    w.writeheader()
    for e in entries:
        d = e.model_dump()
        d["preis"] = f"{e.preis:.2f}".replace(".", ",")
        d["aktiv"] = "ja" if e.aktiv else "nein"
        w.writerow({k: d.get(k, "") for k in CSV_FIELDS})
    return buf.getvalue()


def save_catalog(path: Path, entries: list[CatalogEntry]) -> None:
    path.write_text(catalog_to_csv(entries), encoding="utf-8")


# ----------------------------------------------------------------------------------------
# Zuordnung
# ----------------------------------------------------------------------------------------


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-zäöüß]{4,}", (s or "").lower())}


def candidates_for(q: Quantity, catalog: list[CatalogEntry]) -> list[CatalogEntry]:
    out = []
    for e in catalog:
        if not e.aktiv or e.kennwert_art != "bauteil" or e.bauteiltyp != q.bauteiltyp:
            continue
        if e.einheit not in set(q.values) | {q.primary_unit}:
            continue
        out.append(e)
    return out


def _fit(q: Quantity, e: CatalogEntry) -> float:
    """Passung Ausführung: 1 = Material/Ausführung stimmt überein, 0.5 = allgemeiner Kennwert, 0 = andere Ausführung."""
    if not e.ausfuehrung.strip() or e.ausfuehrung.strip().lower() in ("allgemein", "alle", "-"):
        return 0.5
    et, qt = _tokens(e.ausfuehrung), _tokens(q.ausfuehrung)
    if not qt:
        return 0.25
    return 1.0 if et & qt else 0.0


def layers(e: CatalogEntry) -> set[str]:
    return {s.strip().lower() for s in re.split(r"[;,]", e.umfasst or "") if s.strip()}


def round_cent(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


GROUP = {"bodenplatte": "boden", "fenster": "aussenwand_oeffnung", "aussentuer": "aussenwand_oeffnung",
         "fassadenbekleidung": "aussenwand", "dachbelag": "dach"}


def price_positions(quantities: list[Quantity], catalog: list[CatalogEntry], choices: dict[str, str],
                    bgf_hint: float | None = None) -> CostResult:
    positions: list[CostPosition] = []
    for q in quantities:
        cands = candidates_for(q, catalog)
        pos = CostPosition(key=q.key, kg=q.kg_hint, bauteil=q.bauteil, quantity=q, alternatives=cands)
        chosen: list[CatalogEntry] = []
        if q.key in choices and choices[q.key]:
            ids = choices[q.key].split("+")
            chosen = [e for e in cands if e.id in ids]
            if not chosen:
                pos.reasons.append("gewählter Kennwert nicht mehr im Katalog")
        if not chosen and cands:
            ranked = sorted(cands, key=lambda e: -_fit(q, e))
            fits = [e for e in ranked if _fit(q, e) > 0]
            best = [e for e in fits if _fit(q, e) == _fit(q, fits[0])] if fits else []
            if len(best) == 1:
                chosen = best
            elif len(best) > 1:
                pos.status = "auswahl"
                pos.reasons.append(f"{len(best)} passende Kennwerte – bitte auswählen")
            else:
                pos.status = "auswahl"
                pos.reasons.append("Kennwerte vorhanden, Ausführung passt nicht eindeutig – bitte prüfen/auswählen")
        if not cands:
            pos.reasons.append("kein passender Kennwert im Projektkatalog (Bauteiltyp/Einheit)")
        # Doppelte Bepreisung innerhalb der Auswahl verhindern
        if len(chosen) > 1:
            kept: list[CatalogEntry] = []
            for e in sorted(chosen, key=lambda e: -len(layers(e))):
                covered = set().union(*[layers(k) for k in kept]) if kept else set()
                if layers(e) and layers(e) <= covered:
                    pos.reasons.append(f"„{e.leistung or e.id}“ bereits im Aufbau „{kept[0].leistung or kept[0].id}“ enthalten – nicht doppelt bepreist")
                    continue
                kept.append(e)
            chosen = kept
        if chosen:
            pos.entry = chosen[0]
            pos.unit = chosen[0].einheit
            pos.kg = chosen[0].kg or q.kg_hint
            pos.menge = q.values.get(pos.unit)
            if len(chosen) > 1:
                pos.reasons.append("Kombination: " + " + ".join(e.leistung or e.id for e in chosen))
            pos.combo = chosen
        else:
            pos.unit = q.primary_unit
            pos.menge = q.values.get(q.primary_unit)
        positions.append(pos)

    # Doppelte Bepreisung zwischen Positionen derselben Bauteilgruppe
    seen: dict[str, list[tuple[CostPosition, set[str]]]] = {}
    for pos in positions:
        if pos.entry is None:
            continue
        g = GROUP.get(pos.quantity.bauteiltyp, pos.quantity.bauteiltyp)
        lay = set().union(*[layers(e) for e in (pos.combo or [pos.entry])])
        for other, olay in seen.get(g, []):
            if lay and olay and lay & olay and pos.quantity.primary_unit == other.quantity.primary_unit:
                pos.status = "pruefen"
                pos.reasons.append(f"Doppelte Bepreisung: {', '.join(sorted(lay & olay))} bereits in „{other.bauteil}“ enthalten")
        seen.setdefault(g, []).append((pos, lay))

    # Preisbasis vereinheitlichen
    bases = [p.entry.brutto_netto for p in positions if p.entry]
    basis = max(set(bases), key=bases.count) if bases else "brutto"
    stands = sorted({p.entry.preisstand for p in positions if p.entry and p.entry.preisstand})
    warnings = []
    if len(stands) > 1:
        warnings.append(f"Uneinheitlicher Preisstand der gewählten Kennwerte: {', '.join(stands)}")

    total = Decimal("0")
    for pos in positions:
        q = pos.quantity
        if pos.status in ("auswahl", "pruefen"):
            pos.betrag = None
            continue
        if pos.entry is None:
            pos.status = "offen"
            continue
        if pos.entry.brutto_netto != basis:
            pos.status = "pruefen"
            pos.reasons.append(f"abweichende Preisbasis ({pos.entry.brutto_netto}) – Projekt rechnet {basis}")
            continue
        if q.status != "ok" or pos.menge is None:
            pos.status = "pruefen" if q.status == "pruefen" else "offen"
            pos.reasons = (list(q.reasons) + pos.reasons) or ["Menge fehlt"]
            continue
        amount = Decimal("0")
        for e in (pos.combo or [pos.entry]):
            amount += round_cent(Decimal(repr(pos.menge)) * Decimal(repr(e.preis)))
        pos.betrag = float(amount)
        pos.status = "bepreist"
        total += amount
    for pos in positions:
        if pos.status == "offen" and not pos.reasons:
            pos.reasons = list(pos.quantity.reasons) or ["offen"]

    priced = [p for p in positions if p.status == "bepreist"]
    kgs = sorted({(p.kg or "?")[0] + "00" for p in priced})
    label = "Bepreiste Teilkosten" + (f" · KG {' / '.join(kgs)}" if kgs else "")
    orientation = []
    for e in catalog:
        if e.aktiv and e.kennwert_art == "gebaeude":
            txt = f"Orientierung (nicht addiert): {e.leistung or 'Gebäudekennwert'} {e.preis:,.0f} €/{e.einheit} ({e.herkunft}, {e.preisstand})".replace(",", ".")
            if bgf_hint:
                txt += f" × BGF ≈ {bgf_hint:.2f} m² ≈ {e.preis * bgf_hint:,.0f} €".replace(",", "X").replace(".", ",").replace("X", ".")
            orientation.append(txt)
    return CostResult(positions=positions, total=float(round_cent(total)), total_label=label, preisbasis=basis,
                      preisstand=", ".join(stands) or "–", open_count=len(positions) - len(priced),
                      priced_count=len(priced), orientation=orientation, warnings=warnings)
