from __future__ import annotations
import csv, hashlib, io, re, zipfile
from dataclasses import dataclass
from datetime import date
from typing import Iterable
import pymupdf
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract
from pytesseract import Output

MONTHS={1:'JAN',2:'FEB',3:'MAR',4:'APR',5:'MAY',6:'JUN',7:'JUL',8:'AUG',9:'SEP',10:'OCT',11:'NOV',12:'DEC'}
FOLIO_RE=re.compile(r'\b(\d{4})\s*[- ]?\s*(\d{3})\b')
DATE_PATTERNS=[
 re.compile(r'(?<!\d)([0-3]?\d)[/\-.]([01]?\d)[/\-.](20\d{2}|\d{2})(?!\d)'),
 re.compile(r'(?<!\d)(20\d{2})[/\-.]([01]?\d)[/\-.]([0-3]?\d)(?!\d)')]

@dataclass
class PageResult:
    page:int; folio:str; date_name:str; confidence:float; status:str; notes:str; preview_png:bytes; original_pdf:bytes

def file_hash(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def normalize_folio(value:str)->str:
    m=FOLIO_RE.search(value or '')
    return f'{m.group(1)}-{m.group(2)}' if m else 'REVIEW'
def valid_date(day:int,month:int,year:int)->str:
    year=year if year>=100 else 2000+year
    try:date(year,month,day)
    except ValueError:return 'REVIEW'
    return f'{MONTHS[month]}-{day:02d}-{year%100:02d}'
def render_page(page:pymupdf.Page,dpi:int=180)->bytes:
    pix=page.get_pixmap(matrix=pymupdf.Matrix(dpi/72,dpi/72),alpha=False)
    return pix.tobytes('png')
def one_page_pdf(doc:pymupdf.Document,index:int)->bytes:
    out=pymupdf.open();out.insert_pdf(doc,from_page=index,to_page=index)
    data=out.tobytes(garbage=4,deflate=True);out.close();return data
def preprocess(image:Image.Image)->Image.Image:
    gray=ImageOps.grayscale(image)
    gray=ImageEnhance.Contrast(gray).enhance(2.1)
    return gray.filter(ImageFilter.SHARPEN)
def ocr_text_conf(image:Image.Image,psm:int=6)->tuple[str,float]:
    data=pytesseract.image_to_data(image,lang='eng',config=f'--oem 1 --psm {psm}',output_type=Output.DICT,timeout=50)
    words=[];scores=[]
    for text,conf in zip(data.get('text',[]),data.get('conf',[])):
        text=str(text).strip()
        try:c=float(conf)
        except Exception:c=-1
        if text:words.append(text)
        if c>=0:scores.append(c/100)
    return ' '.join(words),(sum(scores)/len(scores) if scores else 0.0)
def date_candidates(samples:list[tuple[str,float]])->list[tuple[str,float,str]]:
    found=[]
    for text,conf in samples:
        clean=(text or '').replace('O','0').replace('o','0').replace('|','1').replace('—','-')
        for idx,pattern in enumerate(DATE_PATTERNS):
            for m in pattern.finditer(clean):
                vals=list(map(int,m.groups()))
                d,mo,y=(vals if idx==0 else (vals[2],vals[1],vals[0]))
                value=valid_date(d,mo,y)
                if value!='REVIEW':found.append((value,conf,m.group(0)))
    return found
def choose_date(items:list[tuple[str,float,str]])->tuple[str,float,str]:
    if not items:return 'REVIEW',0.0,'No se detectó una fecha válida. Corrígela manualmente.'
    scores={};raws={}
    for value,conf,raw in items:
        scores[value]=scores.get(value,0)+max(.15,conf);raws.setdefault(value,[]).append(raw)
    best=max(scores,key=scores.get);total=sum(scores.values()) or 1
    confidence=min(.99,scores[best]/total+(0.1 if len(raws[best])>1 else 0))
    return best,confidence,'Lecturas OCR: '+', '.join(raws[best][:5])
def analyze_local(png:bytes,pdf_text:str)->tuple[str,str,float,str,str]:
    image=Image.open(io.BytesIO(png)).convert('RGB');w,h=image.size
    folio=normalize_folio(pdf_text);samples=[]
    regions=[image.crop((0,0,w,int(h*.42))),image.crop((0,int(h*.35),w,int(h*.88))),image]
    for region in regions:
        try:samples.append(ocr_text_conf(preprocess(region),6))
        except RuntimeError:pass
    if folio=='REVIEW':
        header=image.crop((int(w*.42),0,w,int(h*.24)))
        text,_=ocr_text_conf(preprocess(header),6);folio=normalize_folio(text)
    date_name,confidence,notes=choose_date(date_candidates(samples))
    status='OK' if folio!='REVIEW' and date_name!='REVIEW' and confidence>=.55 else 'REVISAR'
    return folio,date_name,confidence,status,notes
def process_pdf(pdf_bytes:bytes,dpi:int=180,progress=None)->list[PageResult]:
    doc=pymupdf.open(stream=pdf_bytes,filetype='pdf');results=[];total=len(doc)
    try:
        for i,page in enumerate(doc):
            png=render_page(page,dpi);text=page.get_text('text') or ''
            try:folio,dt,conf,status,notes=analyze_local(png,text)
            except Exception as exc:folio,dt,conf,status,notes=normalize_folio(text),'REVIEW',0.0,'ERROR',f'OCR local falló: {exc}'
            results.append(PageResult(i+1,folio,dt,conf,status,notes,png,one_page_pdf(doc,i)))
            if progress:progress(i+1,total)
    finally:doc.close()
    return results
def make_filename(dt:str,folio:str,n:int=1)->str:
    dt=dt if re.fullmatch(r'[A-Z]{3}-\d{2}-\d{2}',dt or '') else 'REVIEW';folio=normalize_folio(folio);base=f'{dt}_{folio}'
    return f'{base}{f"_{n:02d}" if n>1 else ""}.pdf'
def build_zip(results:Iterable[PageResult],edits:list[dict]|None=None)->bytes:
    results=list(results);edits_by={int(x['page']):x for x in(edits or [])};counts={};report=[];buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED)as z:
        for item in results:
            edit=edits_by.get(item.page,{});dt=str(edit.get('date_name',item.date_name)).upper();folio=str(edit.get('folio',item.folio));key=f'{dt}_{folio}';counts[key]=counts.get(key,0)+1;name=make_filename(dt,folio,counts[key]);z.writestr(name,item.original_pdf)
            report.append({'page':item.page,'date_name':dt,'folio':normalize_folio(folio),'filename':name,'confidence':item.confidence,'status':item.status,'notes':item.notes})
        s=io.StringIO();fields=['page','date_name','folio','filename','confidence','status','notes'];writer=csv.DictWriter(s,fieldnames=fields);writer.writeheader();writer.writerows(report);z.writestr('reporte_bitacoras.csv',s.getvalue().encode('utf-8-sig'))
    return buf.getvalue()
