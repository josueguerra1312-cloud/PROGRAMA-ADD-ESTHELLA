from __future__ import annotations
import csv, hashlib, io, re, zipfile
from dataclasses import dataclass
from datetime import date
from typing import Iterable
import cv2
import numpy as np
import pymupdf

MONTHS={1:'JAN',2:'FEB',3:'MAR',4:'APR',5:'MAY',6:'JUN',7:'JUL',8:'AUG',9:'SEP',10:'OCT',11:'NOV',12:'DEC'}
FOLIO_RE=re.compile(r'\b(\d{4})\s*[- ]?\s*(\d{3})\b')
NUMERIC_DATE_RE=re.compile(r'(?<!\d)([0-3]?\d)[/\-.]([01]?\d)[/\-.](20\d{2}|\d{2})(?!\d)')
ISO_DATE_RE=re.compile(r'(?<!\d)(20\d{2})[/\-.]([01]?\d)[/\-.]([0-3]?\d)(?!\d)')

@dataclass
class PageResult:
    page:int; folio:str; date_name:str; confidence:float; status:str; notes:str; preview_png:bytes; original_pdf:bytes

def file_hash(data:bytes)->str: return hashlib.sha256(data).hexdigest()

def normalize_folio(value:str)->str:
    m=FOLIO_RE.search(value or '')
    return f'{m.group(1)}-{m.group(2)}' if m else 'REVIEW'

def valid_date_name(day:int,month:int,year:int)->str:
    year=year if year>=100 else 2000+year
    try: date(year,month,day)
    except ValueError: return 'REVIEW'
    return f'{MONTHS[month]}-{day:02d}-{year%100:02d}'

def extract_date_candidates(texts:list[tuple[str,float]])->list[tuple[str,float,str]]:
    found=[]
    for text,conf in texts:
        clean=(text or '').replace('O','0').replace('o','0').replace('|','1')
        for m in NUMERIC_DATE_RE.finditer(clean):
            d,mo,y=map(int,m.groups()); value=valid_date_name(d,mo,y)
            if value!='REVIEW': found.append((value,float(conf),m.group(0)))
        for m in ISO_DATE_RE.finditer(clean):
            y,mo,d=map(int,m.groups()); value=valid_date_name(d,mo,y)
            if value!='REVIEW': found.append((value,float(conf),m.group(0)))
    return found

def choose_date(candidates:list[tuple[str,float,str]])->tuple[str,float,str]:
    if not candidates: return 'REVIEW',0.0,'No se detectó una fecha válida; requiere revisión manual.'
    scores={}; samples={}
    for value,conf,raw in candidates:
        scores[value]=scores.get(value,0)+max(.15,conf); samples.setdefault(value,[]).append(raw)
    best=max(scores,key=scores.get); total=sum(scores.values()) or 1
    confidence=min(.99, scores[best]/total + (0.12 if len(samples[best])>1 else 0))
    return best,confidence,'Coincidencias OCR: '+', '.join(samples[best][:4])

def render_page(page:pymupdf.Page,dpi:int=160)->bytes:
    pix=page.get_pixmap(matrix=pymupdf.Matrix(dpi/72,dpi/72),alpha=False)
    return pix.tobytes('png')

def one_page_pdf(source:pymupdf.Document,index:int)->bytes:
    target=pymupdf.open(); target.insert_pdf(source,from_page=index,to_page=index)
    data=target.tobytes(garbage=4,deflate=True); target.close(); return data

def image_from_png(png:bytes):
    return cv2.imdecode(np.frombuffer(png,np.uint8),cv2.IMREAD_COLOR)

def analyze_local(png:bytes,pdf_text:str,reader)->tuple[str,str,float,str,str]:
    image=image_from_png(png); h,w=image.shape[:2]
    folio=normalize_folio(pdf_text)
    all_results=[]
    # Full page plus zones where dates commonly occur. Crops reduce layout noise.
    crops=[image, image[0:int(h*.42),:], image[int(h*.38):int(h*.88),:]]
    for crop in crops:
        gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        gray=cv2.createCLAHE(2.0,(8,8)).apply(gray)
        for _,text,conf in reader.readtext(gray,detail=1,paragraph=False,allowlist='0123456789/-., '):
            all_results.append((text,float(conf)))
    if folio=='REVIEW':
        header=image[0:int(h*.22),int(w*.45):w]
        header_results=reader.readtext(header,detail=1,paragraph=False,allowlist='0123456789- ')
        folio=normalize_folio(' '.join(x[1] for x in header_results))
    date_name,confidence,notes=choose_date(extract_date_candidates(all_results))
    status='OK' if folio!='REVIEW' and date_name!='REVIEW' and confidence>=.55 else 'REVISAR'
    return folio,date_name,confidence,status,notes

def process_pdf(pdf_bytes:bytes,reader,dpi:int=160,progress=None)->list[PageResult]:
    doc=pymupdf.open(stream=pdf_bytes,filetype='pdf'); results=[]; total=len(doc)
    try:
        for i,page in enumerate(doc):
            png=render_page(page,dpi); text=page.get_text('text') or ''
            try: folio,date_name,conf,status,notes=analyze_local(png,text,reader)
            except Exception as exc: folio,date_name,conf,status,notes=normalize_folio(text),'REVIEW',0.0,'ERROR',f'OCR local falló: {exc}'
            results.append(PageResult(i+1,folio,date_name,conf,status,notes,png,one_page_pdf(doc,i)))
            if progress: progress(i+1,total)
    finally: doc.close()
    return results

def make_filename(date_name:str,folio:str,n:int=1)->str:
    date_name=date_name if re.fullmatch(r'[A-Z]{3}-\d{2}-\d{2}',date_name or '') else 'REVIEW'
    folio=normalize_folio(folio); base=f'{date_name}_{folio}'
    return f'{base}{f"_{n:02d}" if n>1 else ""}.pdf'

def build_zip(results:Iterable[PageResult],edits:list[dict]|None=None)->bytes:
    results=list(results); edits_by={int(r['page']):r for r in (edits or [])}; counts={}; report=[]; buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for item in results:
            edit=edits_by.get(item.page,{}); dt=str(edit.get('date_name',item.date_name)).upper(); fol=str(edit.get('folio',item.folio))
            key=f'{dt}_{fol}'; counts[key]=counts.get(key,0)+1; name=make_filename(dt,fol,counts[key])
            z.writestr(name,item.original_pdf)
            report.append({'page':item.page,'date_name':dt,'folio':normalize_folio(fol),'filename':name,'confidence':item.confidence,'status':item.status,'notes':item.notes})
        s=io.StringIO(); fields=['page','date_name','folio','filename','confidence','status','notes']; wr=csv.DictWriter(s,fieldnames=fields); wr.writeheader(); wr.writerows(report)
        z.writestr('reporte_bitacoras.csv',s.getvalue().encode('utf-8-sig'))
    return buf.getvalue()
