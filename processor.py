from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pymupdf
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pytesseract import Output

MONTHS = {1:'JAN', 2:'FEB', 3:'MAR', 4:'APR', 5:'MAY', 6:'JUN', 7:'JUL', 8:'AUG', 9:'SEP', 10:'OCT', 11:'NOV', 12:'DEC'}
FOLIO_SOURCE_RE = re.compile(r'(?<!\d)(\d{4})\s*[- ]?\s*(\d{3})(?!\d)')
DATE_PATTERNS = [
    re.compile(r'(?<!\d)([0-3]?\d)[/\-.]([01]?\d)[/\-.](20\d{2}|\d{2})(?!\d)'),
    re.compile(r'(?<!\d)(20\d{2})[/\-.]([01]?\d)[/\-.]([0-3]?\d)(?!\d)'),
]

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


def normalize_folio(value: str) -> str:
    """Devuelve exactamente siete dígitos, sin espacios ni guiones."""
    source = str(value or '')
    match = FOLIO_SOURCE_RE.search(source)
    if match:
        return match.group(1) + match.group(2)
    digits = re.sub(r'\D', '', source)
    return digits[:7] if len(digits) >= 7 else 'REVIEW'


def filename_folio(value: str) -> str:
    """Última barrera: jamás permite guiones en el folio del nombre final."""
    normalized = normalize_folio(value)
    if normalized == 'REVIEW':
        return 'REVIEW'
    return re.sub(r'\D', '', normalized)


def valid_date(day: int, month: int, year: int) -> str:
    year = year if year >= 100 else 2000 + year
    try:
        date(year, month, day)
    except ValueError:
        return 'REVIEW'
    return f'{MONTHS[month]}-{day:02d}-{year % 100:02d}'


def normalize_date_name(value: str) -> str:
    value = str(value or '').upper().strip()
    match = re.fullmatch(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(\d{2})-(\d{2})', value)
    if not match:
        return 'REVIEW'
    month = list(MONTHS.values()).index(match.group(1)) + 1
    return valid_date(int(match.group(2)), month, int(match.group(3)))


def render_page(page: pymupdf.Page, dpi: int = 180) -> bytes:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
    return pix.tobytes('png')


def one_page_pdf(doc: pymupdf.Document, index: int) -> bytes:
    output = pymupdf.open()
    output.insert_pdf(doc, from_page=index, to_page=index)
    data = output.tobytes(garbage=4, deflate=True)
    output.close()
    return data


def preprocess(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    gray = ImageEnhance.Contrast(gray).enhance(2.1)
    return gray.filter(ImageFilter.SHARPEN)


def ocr_text_conf(image: Image.Image, psm: int = 6) -> tuple[str, float]:
    data = pytesseract.image_to_data(
        image, lang='eng', config=f'--oem 1 --psm {psm}',
        output_type=Output.DICT, timeout=50
    )
    words, scores = [], []
    for text, confidence in zip(data.get('text', []), data.get('conf', [])):
        text = str(text).strip()
        try:
            score = float(confidence)
        except Exception:
            score = -1
        if text:
            words.append(text)
        if score >= 0:
            scores.append(score / 100)
    return ' '.join(words), (sum(scores) / len(scores) if scores else 0.0)


def date_candidates(samples: list[tuple[str, float]]) -> list[tuple[str, float, str]]:
    found = []
    for text, confidence in samples:
        clean = (text or '').replace('O', '0').replace('o', '0').replace('|', '1').replace('—', '-')
        for index, pattern in enumerate(DATE_PATTERNS):
            for match in pattern.finditer(clean):
                values = list(map(int, match.groups()))
                day, month, year = values if index == 0 else (values[2], values[1], values[0])
                value = valid_date(day, month, year)
                if value != 'REVIEW':
                    found.append((value, confidence, match.group(0)))
    return found


def choose_date(items: list[tuple[str, float, str]]) -> tuple[str, float, str]:
    if not items:
        return 'REVIEW', 0.0, 'No se detectó una fecha válida. Corrígela manualmente.'
    scores, raw_values = {}, {}
    for value, confidence, raw in items:
        scores[value] = scores.get(value, 0) + max(0.15, confidence)
        raw_values.setdefault(value, []).append(raw)
    best = max(scores, key=scores.get)
    confidence = min(0.99, scores[best] / (sum(scores.values()) or 1) + (0.1 if len(raw_values[best]) > 1 else 0))
    return best, confidence, 'Lecturas OCR: ' + ', '.join(raw_values[best][:5])


def analyze_local(png: bytes, pdf_text: str) -> tuple[str, str, float, str, str]:
    image = Image.open(io.BytesIO(png)).convert('RGB')
    width, height = image.size
    folio = normalize_folio(pdf_text)
    samples = []
    regions = [
        image.crop((0, 0, width, int(height * 0.42))),
        image.crop((0, int(height * 0.35), width, int(height * 0.88))),
        image,
    ]
    for region in regions:
        try:
            samples.append(ocr_text_conf(preprocess(region), 6))
        except RuntimeError:
            pass
    if folio == 'REVIEW':
        header = image.crop((int(width * 0.42), 0, width, int(height * 0.24)))
        text, _ = ocr_text_conf(preprocess(header), 6)
        folio = normalize_folio(text)
    date_name, confidence, notes = choose_date(date_candidates(samples))
    status = 'OK' if folio != 'REVIEW' and date_name != 'REVIEW' and confidence >= 0.55 else 'REVISAR'
    return folio, date_name, confidence, status, notes


def process_pdf(pdf_bytes: bytes, dpi: int = 180, progress=None) -> list[PageResult]:
    doc = pymupdf.open(stream=pdf_bytes, filetype='pdf')
    results = []
    try:
        total = len(doc)
        for index, page in enumerate(doc):
            png = render_page(page, dpi)
            pdf_text = page.get_text('text') or ''
            try:
                folio, date_name, confidence, status, notes = analyze_local(png, pdf_text)
            except Exception as exc:
                folio, date_name, confidence, status = normalize_folio(pdf_text), 'REVIEW', 0.0, 'ERROR'
                notes = f'OCR local falló: {exc}'
            results.append(PageResult(index + 1, folio, date_name, confidence, status, notes, png, one_page_pdf(doc, index)))
            if progress:
                progress(index + 1, total)
    finally:
        doc.close()
    return results


def make_filename(date_name: str, folio: str, duplicate_index: int = 1) -> str:
    clean_date = normalize_date_name(date_name)
    clean_folio = filename_folio(folio)
    base = f'{clean_date}_{clean_folio}'
    suffix = f'_{duplicate_index:02d}' if duplicate_index > 1 else ''
    return f'{base}{suffix}.pdf'


def build_zip(results: Iterable[PageResult], edits: list[dict] | None = None) -> bytes:
    results = list(results)
    edits_by_page = {int(row['page']): row for row in (edits or [])}
    counts, report = {}, []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for item in results:
            edit = edits_by_page.get(item.page, {})
            date_name = normalize_date_name(edit.get('date_name', item.date_name))
            # Importante: se limpia nuevamente justo antes de escribir ZIP y CSV.
            folio = filename_folio(edit.get('folio', item.folio))
            key = f'{date_name}_{folio}'
            counts[key] = counts.get(key, 0) + 1
            filename = make_filename(date_name, folio, counts[key])
            archive.writestr(filename, item.original_pdf)
            report.append({
                'page': item.page, 'date_name': date_name, 'folio': folio,
                'filename': filename, 'confidence': item.confidence,
                'status': item.status, 'notes': item.notes,
            })
        csv_buffer = io.StringIO()
        fields = ['page', 'date_name', 'folio', 'filename', 'confidence', 'status', 'notes']
        writer = csv.DictWriter(csv_buffer, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report)
        archive.writestr('reporte_bitacoras.csv', csv_buffer.getvalue().encode('utf-8-sig'))
    return buffer.getvalue()
