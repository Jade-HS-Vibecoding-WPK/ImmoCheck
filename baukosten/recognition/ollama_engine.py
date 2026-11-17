"""Lokale KI-Erkennung über Ollama (läuft auf dem eigenen Rechner, ohne API-Schlüssel, ohne Datenübertragung).

Gleiches Prinzip wie ``ki_engine``: Planausschnitte als Bild plus PDF-Text mit IDs gehen an ein
bildfähiges Modell, die Antwort kommt als strukturiertes JSON (Schema ``KIErgebnis``) und wird
validiert und auf Seitenkoordinaten zurückprojiziert. Mengen rechnet das Modell nicht.

Konfiguration (Umgebungsvariablen oder .env):
    OLLAMA_HOST   Standard http://localhost:11434
    OLLAMA_MODEL  Standard qwen2.5vl:7b   (bildfähig, ca. 6 GB, läuft mit 16 GB RAM)
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

import pymupdf

from ..models import DocumentInfo, ViewRegion, ViewResult
from ..pdf_prep import PageGeometry
from . import ki_engine
from .ki_engine import KIError, KIErgebnis

ENGINE = "ollama"
PROMPT_VERSION = "ollama-1"
DEFAULT_MODEL = "qwen2.5vl:7b"
DEFAULT_HOST = "http://localhost:11434"


def host() -> str:
    return (os.environ.get("OLLAMA_HOST", "").strip() or DEFAULT_HOST).rstrip("/")


def configured_model() -> str:
    return os.environ.get("OLLAMA_MODEL", "").strip() or DEFAULT_MODEL


def _get(path: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(host() + path, timeout=timeout) as r:  # noqa: S310 – lokaler Dienst
        return json.loads(r.read().decode("utf-8"))


def status() -> tuple[str, str]:
    """(Zustand, Text): 'bereit' | 'kein_modell' | 'nicht_erreichbar'."""
    try:
        tags = _get("/api/tags")
    except Exception:  # noqa: BLE001
        return "nicht_erreichbar", f"Ollama läuft nicht unter {host()}"
    names = [m.get("name", "") for m in tags.get("models", [])]
    want = configured_model()
    if any(n == want or n.split(":")[0] == want.split(":")[0] and ":" not in want for n in names):
        return "bereit", f"Lokale KI bereit · Modell {want}"
    return "kein_modell", f"Modell {want} fehlt (installiert: {', '.join(names) or 'keines'})"


def available() -> bool:
    return status()[0] == "bereit"


# Kleine lokale Modelle lassen gern Felder weg: fehlende Pflichtfelder auffüllen, bevor validiert wird.
_LIST_FIELDS = ("ketten", "koten", "oeffnungen", "bauteile", "kostenangaben", "flaechenangaben", "hinweise")
_NULL_FIELDS = ("geschoss", "fassade", "links_himmelsrichtung", "norden_oben", "gebaeude_box", "grundriss_rechteckig")
_WERT_NULL = ("text_id", "bild", "box")


def _fix_wert(w):
    if isinstance(w, dict):
        for k in _WERT_NULL:
            w.setdefault(k, None)
        w.setdefault("original", "")
    elif isinstance(w, (int, float, str)):  # nacktes Zahlenfeld statt Objekt
        return {"text_id": None, "original": str(w), "bild": None, "box": None}
    return w


def normalize(raw: dict) -> dict:
    raw.setdefault("zeichnungsart", "sonstiges")
    raw.setdefault("titel", "")
    for k in _LIST_FIELDS:
        if raw.get(k) is None:
            raw[k] = []
    for k in _NULL_FIELDS:
        raw.setdefault(k, None)
    for ch in raw["ketten"]:
        ch["werte"] = [_fix_wert(w) for w in ch.get("werte") or []]
    for kt in raw["koten"]:
        kt["wert"] = _fix_wert(kt.get("wert"))
        kt.setdefault("bezeichnung", "")
        kt.setdefault("bezug", [])
    for o in raw["oeffnungen"]:
        for k in ("kennung", "bild", "box", "breite", "hoehe", "bruestung", "fassade"):
            o.setdefault(k, None)
            if k in ("breite", "hoehe", "bruestung") and o[k] is not None:
                o[k] = _fix_wert(o[k])
        o.setdefault("art", "unbekannt")
    for b in raw["bauteile"]:
        for k in ("ueberstand", "dachform", "neigung_grad", "bis_kote", "quelle", "buendig_mit_aussenkontur"):
            b.setdefault(k, None)
        b.setdefault("beschreibung", "")
        b.setdefault("material", "")
        b.setdefault("fassaden", [])
        b.setdefault("umlaufend", False)
    raw["kostenangaben"] = [_fix_wert(w) for w in raw["kostenangaben"]]
    for fa in raw["flaechenangaben"]:
        fa["wert"] = _fix_wert(fa.get("wert"))
        fa.setdefault("bezeichnung", "")
    return raw


def _messages(content: list[dict]) -> list[dict]:
    """Anthropic-Inhaltsblöcke (Text/Bild) in das Ollama-Chatformat umsetzen."""
    texts, images = [], []
    for b in content:
        if b["type"] == "text":
            texts.append(b["text"])
        elif b["type"] == "image":
            images.append(b["source"]["data"])
    return [{"role": "system", "content": ki_engine.SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(texts), "images": images}]


def call_model(content: list[dict], model: str | None = None, timeout: float = 900.0) -> KIErgebnis:
    model = model or configured_model()
    body = {"model": model, "messages": _messages(content), "stream": False,
            "format": KIErgebnis.model_json_schema(), "options": {"temperature": 0, "num_ctx": 16384}}
    req = urllib.request.Request(host() + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 – lokaler Dienst
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise KIError(f"Ollama-Fehler {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise KIError(f"Ollama nicht erreichbar ({host()}): {exc}") from exc
    text = (resp.get("message") or {}).get("content", "")
    if not text.strip():
        raise KIError("Leere Antwort des lokalen Modells.")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise KIError(f"Antwort ist kein gültiges JSON (evtl. abgeschnitten): {exc}") from exc
    if not isinstance(raw, dict):
        raise KIError("Antwort hat nicht die erwartete Struktur.")
    try:
        return KIErgebnis.model_validate(normalize(raw))
    except Exception as exc:  # noqa: BLE001
        raise KIError(f"Antwort passt nicht zum Schema: {str(exc)[:300]}") from exc


def analyze_view(pdf: pymupdf.Document, doc: DocumentInfo, view: ViewRegion, geo: PageGeometry,
                 model: str | None = None) -> ViewResult:
    model = model or configured_model()
    content, infos, spans = ki_engine.build_request(pdf, view, geo)
    k = call_model(content, model)
    res = ki_engine.to_view_result(k, doc, view, infos, spans, model)
    res.engine = f"{ENGINE}:{model}"
    return res
