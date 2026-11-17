"""BKI-Gebäudekennwerte (KG 300+400) und kennwertbasierte Bauwerksorientierung über BGF und BRI.

Quelle des Startkatalogs: BKI Baukosten Gebäude Neubau 2026 – Statistische Kostenkennwerte,
Übersichtsdiagramme S. 152–154 (€/m² BGF) und S. 156–158 (€/m³ BRI). Werte grafisch am lokalen
Achsenraster abgelesen und auf 100 €/m² bzw. 25 €/m³ gerundet -> Erfassungsart ``grafisch_gerundet``.
Ein leeres Von-/Bis-Feld heißt „im Foto nicht auflösbar“ (kein Nullpreis).

Regeln:
- BGF- und BRI-Ansatz sind zwei Rechenwege für dasselbe Bauwerk: nie addieren, nie mitteln.
- Bauteilkosten werden keinem Gebäudeansatz zugeschlagen.
- Regionalfaktor nur mit Beleg, genau einmal angewendet. Netto = Brutto / 1,19 (Preisstand bleibt).
- Tabellarisch belegte Werte haben Vorrang vor grafischen Näherungen derselben Kategorie,
  Bezugsgröße und Preisbasis.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
CATALOG_FILE = ROOT / "data" / "katalog" / "bki_gebaeude_neubau_2026.csv"
TABLE_FILE = ROOT / "data" / "katalog" / "bki_tabellenwerte.csv"

AUSGABE = "BKI Baukosten Gebäude Neubau 2026 – Statistische Kostenkennwerte"
KG_UMFANG = "KG 300+400"
KOSTENSTAND = "1. Quartal 2026"
REGION_BUND = "Bundesdurchschnitt Deutschland"
STEUER_BRUTTO = "brutto inkl. 19 % MwSt."
MWST = 1.19
HINWEIS_GRAFISCH = "ca. · aus BKI-Übersicht grafisch abgelesen"
REGIONALFAKTOR_SEITE = 1144

Bezug = Literal["BGF", "BRI"]
EINHEIT = {"BGF": "€/m² BGF", "BRI": "€/m³ BRI"}
MENGENEINHEIT = {"BGF": "m²", "BRI": "m³"}


class BKIKennwert(BaseModel):
    kategorie: str
    bezugsgroesse: Bezug
    einheit: str
    kg_umfang: str = KG_UMFANG
    von: float | None = None
    mittel: float | None = None
    bis: float | None = None
    ausgabe: str = AUSGABE
    uebersichtsseite: int | None = None  # Diagrammseite (grafische Quelle) bzw. Tabellenseite
    detailseite_ab: int | None = None
    kostenstand: str = KOSTENSTAND
    regionalbezug: str = REGION_BUND
    steuerbasis: str = STEUER_BRUTTO
    erfassungsart: Literal["grafisch_gerundet", "tabellarisch_belegt"] = "grafisch_gerundet"
    beleg: str = ""  # z. B. "S. 1108, Tabelle Bauwerk"

    @property
    def key(self) -> tuple:
        return (self.kategorie, self.bezugsgroesse, self.kostenstand, self.regionalbezug, self.steuerbasis)

    @property
    def quelle(self) -> str:
        if self.erfassungsart == "grafisch_gerundet":
            return (f"BKI Gebäude Neubau 2026, Übersicht S. {self.uebersichtsseite} ({self.bezugsgroesse}), "
                    f"Detailkapitel ab S. {self.detailseite_ab}")
        return f"BKI Gebäude Neubau 2026, Tabelle {self.beleg or ('S. ' + str(self.uebersichtsseite))}"


def _num(s: str | None) -> float | None:
    s = (s or "").strip()
    if not s:
        return None  # im Foto nicht auflösbar – kein Nullpreis
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def read_graphical(path: Path = CATALOG_FILE) -> list[BKIKennwert]:
    out: list[BKIKennwert] = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            kat = r["gebaeudekategorie"].strip()
            detail = int(r["detailseite_ab"]) if r["detailseite_ab"].strip() else None
            for bez, page_col, pre in (("BGF", "diagrammseite_bgf", "bgf"), ("BRI", "diagrammseite_bri", "bri")):
                out.append(BKIKennwert(
                    kategorie=kat, bezugsgroesse=bez, einheit=EINHEIT[bez], von=_num(r[f"{pre}_von"]),
                    mittel=_num(r[f"{pre}_mittel"]), bis=_num(r[f"{pre}_bis"]),
                    uebersichtsseite=int(r[page_col]) if r[page_col].strip() else None, detailseite_ab=detail,
                    erfassungsart="grafisch_gerundet"))
    return out


TABLE_FIELDS = ["kategorie", "bezugsgroesse", "von", "mittel", "bis", "seite", "beleg", "kostenstand", "regionalbezug", "steuerbasis"]


def read_table_values(path: Path = TABLE_FILE) -> list[BKIKennwert]:
    """Später eingepflegte, gedruckte Tabellenwerte (Erfassungsart tabellarisch_belegt)."""
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if not r.get("kategorie") or r.get("bezugsgroesse") not in ("BGF", "BRI"):
                continue
            bez = r["bezugsgroesse"]
            out.append(BKIKennwert(
                kategorie=r["kategorie"].strip(), bezugsgroesse=bez, einheit=EINHEIT[bez], von=_num(r.get("von")),
                mittel=_num(r.get("mittel")), bis=_num(r.get("bis")),
                uebersichtsseite=int(r["seite"]) if (r.get("seite") or "").strip() else None,
                kostenstand=r.get("kostenstand") or KOSTENSTAND, regionalbezug=r.get("regionalbezug") or REGION_BUND,
                steuerbasis=r.get("steuerbasis") or STEUER_BRUTTO, erfassungsart="tabellarisch_belegt",
                beleg=r.get("beleg", "")))
    return out


def add_table_value(k: BKIKennwert, path: Path = TABLE_FILE) -> None:
    rows = read_table_values(path)
    rows = [r for r in rows if r.key != k.key] + [k.model_copy(update={"erfassungsart": "tabellarisch_belegt"})]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(TABLE_FIELDS)
    for r in rows:
        w.writerow([r.kategorie, r.bezugsgroesse, "" if r.von is None else r.von, "" if r.mittel is None else r.mittel,
                    "" if r.bis is None else r.bis, r.uebersichtsseite or "", r.beleg, r.kostenstand, r.regionalbezug, r.steuerbasis])
    path.write_text(buf.getvalue(), encoding="utf-8")


def load_catalog(graph_path: Path = CATALOG_FILE, table_path: Path = TABLE_FILE) -> dict[tuple[str, str], BKIKennwert]:
    """Kennwert je (Kategorie, Bezugsgröße); tabellarisch belegte Werte ersetzen die grafische Näherung
    nur bei gleicher Kategorie, Bezugsgröße und Preisbasis (Kostenstand, Region, Steuer)."""
    cat: dict[tuple[str, str], BKIKennwert] = {(k.kategorie, k.bezugsgroesse): k for k in read_graphical(graph_path)}
    for t in read_table_values(table_path):
        g = cat.get((t.kategorie, t.bezugsgroesse))
        if g is None or g.key == t.key:
            if g is not None:
                t = t.model_copy(update={"detailseite_ab": g.detailseite_ab, "uebersichtsseite": t.uebersichtsseite or g.detailseite_ab})
            cat[(t.kategorie, t.bezugsgroesse)] = t
    return cat


def categories(graph_path: Path = CATALOG_FILE) -> list[str]:
    seen: list[str] = []
    for k in read_graphical(graph_path):
        if k.kategorie not in seen:
            seen.append(k.kategorie)
    return seen


# ----------------------------------------------------------------------------------------
# Kategorievorschlag
# ----------------------------------------------------------------------------------------

_FAMILIES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"gemeinde(haus|zentrum|saal|räume|raum)|pfarr(heim|zentrum|haus)|begegnungs(stätte|zentrum)|bürgerhaus|dorfgemeinschaftshaus", re.I), "Gemeindezentren"),
    (re.compile(r"kirche|kapelle|sakral", re.I), "Sakralbauten"),
    (re.compile(r"friedhof|trauerhalle|aussegnungshalle", re.I), "Friedhofsgebäude"),
    (re.compile(r"kita\b|kindergarten|kindertages(stätte|einrichtung)|krippe", re.I), "Kindergarten"),
    (re.compile(r"grundschule|gymnasium|oberschule|gesamtschule|\bschule\b", re.I), "Schulen"),
    (re.compile(r"feuerwehr", re.I), "Feuerwehrhäuser"),
    (re.compile(r"sporthalle|turnhalle|mehrzweckhalle", re.I), "Sport- und Mehrzweckhallen"),
    (re.compile(r"büro|verwaltung|rathaus", re.I), "Büro und Verwaltung"),
    (re.compile(r"mehrfamilienhaus|\bmfh\b|wohnanlage", re.I), "Mehrfamilienhäuser"),
    (re.compile(r"einfamilienhaus|zweifamilienhaus|\befh\b|\bzfh\b", re.I), "Ein- und Zweifamilienhäuser"),
    (re.compile(r"pflegeheim", re.I), "Pflegeheime"),
    (re.compile(r"hotel", re.I), "Hotels"),
    (re.compile(r"bibliothek|museum|ausstellung", re.I), "Bibliotheken, Museen und Ausstellungen"),
    (re.compile(r"lagerhalle|lagergebäude", re.I), "Lagergebäude"),
    (re.compile(r"carport", re.I), "Carports"),
]
TIMBER_RE = re.compile(r"holzrahmenbau|holztafelbau|holzständerbau|holzständer|holzbauweise|holzskelettbau|"
                       r"brettsperrholz|holzmassivbau|holzbau\b", re.I)
CELLAR_RE = re.compile(r"\b(UG|KG)\b|untergeschoss|kellergeschoss|grundriss\s+keller", re.I)
WE_RE = re.compile(r"(\d{1,3})\s*(?:WE|wohneinheiten|wohnungen)\b", re.I)


class CategorySuggestion(BaseModel):
    kategorie: str | None = None
    optionen: list[str] = Field(default_factory=list)  # bei mehreren gleichwertigen Kategorien (z. B. 6 WE)
    begruendung: list[str] = Field(default_factory=list)


def suggest_category(name: str, building_type: str, plan_texts: list[str], storeys: list[str] | None = None,
                     all_categories: list[str] | None = None) -> CategorySuggestion:
    cats = all_categories or categories()
    head = f"{name} {building_type}"
    text = " ".join(plan_texts)
    s = CategorySuggestion()
    family = None
    for rx, fam in _FAMILIES:
        if rx.search(head):
            family = fam
            s.begruendung.append(f"Nutzung aus Projektangaben: „{rx.search(head).group(0)}“ → {fam}")
            break
    if family is None:
        for rx, fam in _FAMILIES:
            m = rx.search(text)
            if m:
                family = fam
                s.begruendung.append(f"Nutzung aus Planbeschriftung: „{m.group(0)}“ → {fam}")
                break
    if family is None:
        s.begruendung.append("Keine Nutzung erkannt – bitte Gebäudekategorie wählen.")
        return s
    fam_cats = [c for c in cats if c.startswith(family) or (family == "Schulen" and "Schulen" in c)
                or (family == "Lagergebäude" and c.startswith("Lagergebäude"))]
    if family == "Schulen":
        fam_cats = [c for c in cats if c in ("Allgemeinbildende Schulen", "Schulen – Holzbauweise")]
    timber = TIMBER_RE.search(text) or TIMBER_RE.search(head)
    cellar = any(CELLAR_RE.search(st or "") for st in (storeys or []))
    pick = fam_cats
    holz = [c for c in pick if "Holzbau" in c]
    if timber and holz:
        s.begruendung.append(f"Bauweise: „{timber.group(0)}“ belegt Holzbauweise des Gebäudes (Tragwerk, nicht nur Bekleidung)")
        pick = holz
    else:
        if timber and not holz:
            s.begruendung.append("Holzbauweise erkannt, für diese Gebäudeart aber keine eigene Holzbau-Kategorie im Band")
        pick = [c for c in pick if "Holzbau" not in c] or pick
    if any("Keller" in c for c in pick):
        with_k = [c for c in pick if "mit Keller" in c]
        without_k = [c for c in pick if "ohne Keller" in c]
        if cellar and with_k:
            pick = with_k
            s.begruendung.append("Untergeschoss im Plansatz → mit Keller")
        elif without_k:
            pick = without_k
            s.begruendung.append("Kein Untergeschoss im Plansatz → ohne Keller (prüfen)")
    if family == "Mehrfamilienhäuser":
        m = WE_RE.search(f"{head} {text}")
        if m:
            n = int(m.group(1))
            s.begruendung.append(f"{n} Wohneinheiten erkannt")
            if n == 6:
                pick = [c for c in pick if "bis zu 6 WE" in c or "6 bis 19 WE" in c]
                s.begruendung.append("Genau 6 WE: Buch führt „bis zu 6 WE“ und „6 bis 19 WE“ – bitte auswählen")
            elif n < 6:
                pick = [c for c in pick if "bis zu 6 WE" in c]
            elif n <= 19:
                pick = [c for c in pick if "6 bis 19 WE" in c]
            else:
                pick = [c for c in pick if "ab 20 WE" in c]
    std = [c for c in pick if "mittlerer Standard" in c]
    if len(pick) > 1 and std and not (family == "Mehrfamilienhäuser" and any("bis zu 6 WE" in c for c in pick) and any("6 bis 19" in c for c in pick)):
        s.optionen = pick
        s.kategorie = std[0]
        s.begruendung.append("Standard nicht belegt → Vorschlag „mittlerer Standard“ (prüfen)")
    elif len(pick) > 1 and family == "Mehrfamilienhäuser":
        s.optionen = [c for c in pick if "mittlerer Standard" in c] or pick
        s.kategorie = None
    else:
        s.kategorie = pick[0] if pick else None
        s.optionen = pick
    return s


# ----------------------------------------------------------------------------------------
# Region und Orientierungsrechnung
# ----------------------------------------------------------------------------------------


class Regionalfaktor(BaseModel):
    region: str  # z. B. "Landkreis Osnabrück"
    faktor: float
    quelle: str  # z. B. "BKI Gebäude Neubau 2026, Regionalfaktoren ab S. 1144"


class OrientationLine(BaseModel):
    bezugsgroesse: Bezug
    menge: float | None
    mengeneinheit: str
    kennwert: BKIKennwert
    faktor: float = 1.0  # Regionalfaktor × ggf. 1/1,19
    von: float | None = None  # ungerundet
    mittel: float | None = None
    bis: float | None = None
    status: Literal["ok", "offen"] = "ok"
    hinweis: str = ""

    @property
    def label(self) -> str:
        return f"Bauwerkskosten {KG_UMFANG} über {self.bezugsgroesse}"


class OrientationResult(BaseModel):
    kategorie: str | None
    lines: list[OrientationLine] = Field(default_factory=list)
    region: str = REGION_BUND
    regionalfaktor: Regionalfaktor | None = None
    steuer: str = STEUER_BRUTTO
    kostenstand: str = KOSTENSTAND
    netto: bool = False
    hinweise: list[str] = Field(default_factory=list)

    def line(self, bez: str) -> OrientationLine | None:
        return next((l for l in self.lines if l.bezugsgroesse == bez), None)


def orientation(kategorie: str | None, bgf: float | None, bri: float | None, kennwerte: dict[str, BKIKennwert],
                regionalfaktor: Regionalfaktor | None = None, netto: bool = False) -> OrientationResult:
    """BGF × €/m² BGF und BRI × €/m³ BRI getrennt – je Von/Mittel/Bis, ungerundet."""
    res = OrientationResult(kategorie=kategorie, regionalfaktor=regionalfaktor, netto=netto,
                            region=regionalfaktor.region if regionalfaktor else REGION_BUND,
                            steuer="netto (= brutto / 1,19)" if netto else STEUER_BRUTTO)
    if kategorie is None:
        res.hinweise.append("Keine Gebäudekategorie gewählt – Bauwerksorientierung nicht möglich.")
        return res
    f = (regionalfaktor.faktor if regionalfaktor else 1.0) / (MWST if netto else 1.0)
    for bez, menge in (("BGF", bgf), ("BRI", bri)):
        k = kennwerte.get(bez)
        if k is None:
            continue
        line = OrientationLine(bezugsgroesse=bez, menge=menge, mengeneinheit=MENGENEINHEIT[bez], kennwert=k, faktor=f)
        if menge is None:
            line.status = "offen"
            line.hinweis = f"{bez} nicht belegbar – Rechenweg offen"
        else:
            for fld in ("von", "mittel", "bis"):
                v = getattr(k, fld)
                setattr(line, fld, None if v is None else menge * v * f)  # leer bleibt leer
            if k.von is None or k.bis is None:
                line.hinweis = "Von-/Bis-Wert im Foto nicht auflösbar – Feld bleibt leer"
        res.lines.append(line)
    res.hinweise.append("BGF- und BRI-Ansatz beschreiben dasselbe Bauwerk – nicht addiert, nicht gemittelt.")
    res.hinweise.append("Streuung beschreibt die BKI-Vergleichsobjekte; keine Kostengarantie, keine Aussage zur Genauigkeit der Planerkennung.")
    res.hinweise.append("Nicht enthalten: Grundstück, Außenanlagen, Baunebenkosten und andere Leistungen außerhalb KG 300+400. "
                        "Aufteilung in KG 300/400 erfordert Tabellenwerte.")
    if not regionalfaktor:
        res.hinweise.append("Ohne belegten Regionalfaktor: Bundesdurchschnitt.")
    return res


def round_thousand(x: float | None) -> float | None:
    return None if x is None else round(x / 1000.0) * 1000.0


def fmt_eur_k(x: float | None) -> str:
    """Anzeige gerundet auf Tausend Euro, z. B. „ca. 350.000 €“; leer bleibt leer."""
    if x is None:
        return "–"
    v = round_thousand(x)
    return "ca. " + f"{v:,.0f}".replace(",", ".") + " €"
