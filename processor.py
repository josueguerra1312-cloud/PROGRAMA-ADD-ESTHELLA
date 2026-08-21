from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass, asdict
from datetime import date
from typing import Iterable

import fitz  # PyMuPDF
from openai import OpenAI

MONTHS = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}
DATE_RE = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(0[1-9]|[12][0-9]|3[01])-([0-9]{2})$")
FOLIO_RE = re.compile(r"\b(\d{4})\s*[- ]?\s*(\d{3})\b")


@dataclass
class PageResult:
    page: int
    folio: str
    date_name: str
    confidence: float
    status: str
    notes: str
    preview_png: bytes
    original_pdf: bytes

    def public_dict(self) -> dict:
        data = asdict(self)
        data.pop("preview_png", None)
        data.pop("original_pdf", None)
        return data


def _safe_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("La IA no devolvió un objeto JSON.")
    return json.loads(text[start:end + 1])


def _normalize_folio(value: str, text_hint: str = "") -> str:
    for candidate in (value or "", text_hint or ""):
        match = FOLIO_RE.search(candidate)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
    return "REVIEW"


def _normalize_date(value: str) -> str:
    value = (value or "").upper().strip().replace("_", "-").replace("/", "-")
    value = re.sub(r"\s+", "", value)
    if not DATE_RE.fullmatch(value):
        return "REVIEW"
    month_text, day_text, year_text = value.split("-")
    month = list(MONTHS.values()).index(month_text) + 1
    try:
        date(2000 + int(year_text), month, int(day_text))
    except ValueError:
        return "REVIEW"
    return value


def make_filename(date_name: str, folio: str, duplicate_index: int = 1) -> str:
    date_name = _normalize_date(date_name)
    folio = _normalize_folio(folio)
    base = f"{date_name}_{folio}"
    if duplicate_index > 1:
        base += f"_{duplicate_index:02d}"
    return base + ".pdf"


def render_page(page: fitz.Page, dpi: int = 180) -> bytes:
    zoom = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("png")


def one_page_pdf(source: fitz.Document, page_number: int) -> bytes:
    target = fitz.open()
    target.insert_pdf(source, from_page=page_number, to_page=page_number)
    data = target.tobytes(garbage=4, deflate=True)
    target.close()
    return data


def analyze_page_with_ai(png: bytes, text_hint: str, client: OpenAI, model: str) -> dict:
    image_b64 = base64.b64encode(png).decode("ascii")
    prompt = f"""
Analiza una página de una bitácora de mantenimiento aeronáutico.
Extrae:
1) El folio impreso cerca de la parte superior, normalmente dos bloques como 2457 015.
2) La fecha de operación escrita a mano. Revisa fechas repetidas en el cuerpo, firmas y acciones de mantenimiento. Usa la fecha principal de la bitácora, no una fecha de impresión del formulario.

Texto extraído del PDF como pista (puede contener errores OCR):
{text_hint[:6000]}

Devuelve SOLO JSON con esta forma exacta:
{{
  "folio": "2457-015 o UNKNOWN",
  "date": "MMM-DD-YY o UNKNOWN",
  "confidence": 0.0,
  "notes": "explicación corta en español"
}}

Meses válidos: JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC.
No inventes. Si día, mes o año no son suficientemente legibles usa UNKNOWN.
La confianza debe estar entre 0 y 1 y considerar conjuntamente fecha y folio.
""".strip()
    response = client.responses.create(
        model=model,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}", "detail": "high"},
            ],
        }],
    )
    return _safe_json(response.output_text)


def process_pdf(pdf_bytes: bytes, api_key: str, model: str = "gpt-4.1-mini", dpi: int = 180) -> list[PageResult]:
    if not api_key:
        raise ValueError("Falta OPENAI_API_KEY.")
    client = OpenAI(api_key=api_key)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    results: list[PageResult] = []
    try:
        for index, page in enumerate(doc):
            preview = render_page(page, dpi=dpi)
            text_hint = page.get_text("text") or ""
            try:
                raw = analyze_page_with_ai(preview, text_hint, client, model)
                folio = _normalize_folio(str(raw.get("folio", "")), text_hint)
                date_name = _normalize_date(str(raw.get("date", "")))
                confidence = max(0.0, min(1.0, float(raw.get("confidence", 0))))
                notes = str(raw.get("notes", ""))[:500]
                status = "OK" if folio != "REVIEW" and date_name != "REVIEW" and confidence >= 0.75 else "REVISAR"
            except Exception as exc:
                folio = _normalize_folio("", text_hint)
                date_name = "REVIEW"
                confidence = 0.0
                status = "ERROR"
                notes = f"No se pudo analizar con IA: {exc}"
            results.append(PageResult(
                page=index + 1,
                folio=folio,
                date_name=date_name,
                confidence=confidence,
                status=status,
                notes=notes,
                preview_png=preview,
                original_pdf=one_page_pdf(doc, index),
            ))
    finally:
        doc.close()
    return results


def build_zip(results: Iterable[PageResult], edits: list[dict] | None = None) -> bytes:
    results = list(results)
    edits_by_page = {int(row["page"]): row for row in (edits or [])}
    counts: dict[str, int] = {}
    report_rows = []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in results:
            edit = edits_by_page.get(item.page, {})
            date_name = _normalize_date(str(edit.get("date_name", item.date_name)))
            folio = _normalize_folio(str(edit.get("folio", item.folio)))
            key = f"{date_name}_{folio}"
            counts[key] = counts.get(key, 0) + 1
            filename = make_filename(date_name, folio, counts[key])
            archive.writestr(filename, item.original_pdf)
            report_rows.append({
                "page": item.page,
                "date_name": date_name,
                "folio": folio,
                "filename": filename,
                "confidence": item.confidence,
                "status": "OK" if date_name != "REVIEW" and folio != "REVIEW" else "REVISAR",
                "notes": item.notes,
            })
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=report_rows[0].keys() if report_rows else ["page"])
        writer.writeheader()
        writer.writerows(report_rows)
        archive.writestr("reporte_bitacoras.csv", csv_buffer.getvalue().encode("utf-8-sig"))
    return buffer.getvalue()
