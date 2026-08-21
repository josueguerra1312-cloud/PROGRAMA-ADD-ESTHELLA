from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from typing import Iterable

import fitz
from openai import OpenAI

MONTHS = {1:"JAN",2:"FEB",3:"MAR",4:"APR",5:"MAY",6:"JUN",7:"JUL",8:"AUG",9:"SEP",10:"OCT",11:"NOV",12:"DEC"}
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


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_folio(value: str, text_hint: str = "") -> str:
    for candidate in (value or "", text_hint or ""):
        match = FOLIO_RE.search(candidate)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
    return "REVIEW"


def normalize_date(value: str) -> str:
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


def safe_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("La respuesta no contiene JSON válido")
    return json.loads(text[start:end + 1])


def render_page(page: fitz.Page, dpi: int = 180) -> bytes:
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    return pix.tobytes("png")


def one_page_pdf(source: fitz.Document, page_number: int) -> bytes:
    target = fitz.open()
    target.insert_pdf(source, from_page=page_number, to_page=page_number)
    data = target.tobytes(garbage=4, deflate=True)
    target.close()
    return data


def analyze_with_vision(png: bytes, text_hint: str, client: OpenAI, model: str) -> dict:
    image_b64 = base64.b64encode(png).decode("ascii")
    prompt = f"""Analiza esta página de una bitácora de mantenimiento aeronáutico.
Extrae el folio impreso superior, normalmente como 2457 015, y la fecha principal de operación escrita a mano.
Busca la fecha en encabezado, vuelos, firmas y acciones de mantenimiento; compara repeticiones. No uses una fecha de impresión del formato.
Texto OCR auxiliar, posiblemente incorrecto:\n{text_hint[:5000]}
Devuelve solamente JSON:
{{"folio":"2457-015 o UNKNOWN","date":"MMM-DD-YY o UNKNOWN","confidence":0.0,"notes":"explicación breve"}}
Meses: JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC. No inventes datos ilegibles."""
    response = client.responses.create(
        model=model,
        input=[{"role":"user","content":[
            {"type":"input_text","text":prompt},
            {"type":"input_image","image_url":f"data:image/png;base64,{image_b64}","detail":"high"},
        ]}],
    )
    return safe_json(response.output_text)


def process_pdf(pdf_bytes: bytes, api_key: str | None, model: str = "gpt-4.1-mini", dpi: int = 180, progress=None) -> list[PageResult]:
    client = OpenAI(api_key=api_key) if api_key else None
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    results = []
    total = len(doc)
    try:
        for index, page in enumerate(doc):
            preview = render_page(page, dpi)
            text_hint = page.get_text("text") or ""
            folio = normalize_folio("", text_hint)
            date_name, confidence = "REVIEW", 0.0
            status = "REVISAR"
            notes = "PDF separado. Falta configurar OPENAI_API_KEY para analizar la fecha manuscrita."
            if client:
                try:
                    raw = analyze_with_vision(preview, text_hint, client, model)
                    folio = normalize_folio(str(raw.get("folio", "")), text_hint)
                    date_name = normalize_date(str(raw.get("date", "")))
                    confidence = max(0.0, min(1.0, float(raw.get("confidence", 0))))
                    notes = str(raw.get("notes", ""))[:500]
                    status = "OK" if folio != "REVIEW" and date_name != "REVIEW" and confidence >= 0.75 else "REVISAR"
                except Exception as exc:
                    status = "ERROR"
                    notes = f"La página fue separada, pero el análisis IA falló: {exc}"
            results.append(PageResult(index+1, folio, date_name, confidence, status, notes, preview, one_page_pdf(doc, index)))
            if progress:
                progress(index + 1, total)
    finally:
        doc.close()
    return results


def make_filename(date_name: str, folio: str, duplicate_index: int = 1) -> str:
    date_name, folio = normalize_date(date_name), normalize_folio(folio)
    base = f"{date_name}_{folio}"
    return f"{base}{f'_{duplicate_index:02d}' if duplicate_index > 1 else ''}.pdf"


def build_zip(results: Iterable[PageResult], edits: list[dict] | None = None) -> bytes:
    results = list(results)
    edits_by_page = {int(row["page"]): row for row in (edits or [])}
    counts, report = {}, []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in results:
            edit = edits_by_page.get(item.page, {})
            date_name = normalize_date(str(edit.get("date_name", item.date_name)))
            folio = normalize_folio(str(edit.get("folio", item.folio)))
            key = f"{date_name}_{folio}"
            counts[key] = counts.get(key, 0) + 1
            filename = make_filename(date_name, folio, counts[key])
            archive.writestr(filename, item.original_pdf)
            report.append({"page":item.page,"date_name":date_name,"folio":folio,"filename":filename,
                           "confidence":item.confidence,"status":"OK" if date_name != "REVIEW" and folio != "REVIEW" else "REVISAR",
                           "notes":item.notes})
        csv_out = io.StringIO()
        fields = ["page","date_name","folio","filename","confidence","status","notes"]
        writer = csv.DictWriter(csv_out, fieldnames=fields)
        writer.writeheader(); writer.writerows(report)
        archive.writestr("reporte_bitacoras.csv", csv_out.getvalue().encode("utf-8-sig"))
    return buffer.getvalue()
