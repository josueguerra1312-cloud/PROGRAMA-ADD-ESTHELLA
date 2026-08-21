import pandas as pd
import streamlit as st
import pytesseract
from processor import build_zip,file_hash,process_pdf

st.set_page_config(page_title='Separador de bitácoras',page_icon='📄',layout='wide')
st.title('Separador local de bitácoras')
st.caption('Sin claves ni APIs: separación y OCR local con Tesseract.')
try:
    pytesseract.get_tesseract_version()
except Exception:
    st.error('Tesseract no está instalado. Verifica que packages.txt esté en la raíz del repositorio.')
    st.stop()
uploaded=st.file_uploader('Carga el PDF con múltiples bitácoras',type=['pdf'])
if uploaded:
    data=uploaded.getvalue();current=file_hash(data);st.info(f'Archivo cargado: {uploaded.name} ({len(data)/1024/1024:.1f} MB)')
    if st.session_state.get('processed_hash')!=current:
        bar=st.progress(0,text='Preparando OCR local...')
        try:
            def update(done,total):bar.progress(done/total,text=f'Analizando página {done} de {total}')
            st.session_state.results=process_pdf(data,dpi=180,progress=update);st.session_state.processed_hash=current;bar.progress(1.0,text='Proceso terminado');st.success('Documento separado y analizado.')
        except Exception as exc:st.session_state.pop('processed_hash',None);st.exception(exc)
results=st.session_state.get('results')
if results:
    rows=[{'page':r.page,'date_name':r.date_name,'folio':r.folio,'confidence':round(r.confidence,3),'status':r.status,'notes':r.notes}for r in results]
    ok=sum(x['status']=='OK'for x in rows);a,b,c=st.columns(3);a.metric('Páginas',len(rows));b.metric('Detectadas',ok);c.metric('Por revisar',len(rows)-ok)
    st.warning('Tesseract puede fallar con escritura manuscrita. Corrige las filas REVIEW antes de descargar.')
    edited=st.data_editor(pd.DataFrame(rows),hide_index=True,use_container_width=True,disabled=['page','confidence','status','notes'],column_config={'page':st.column_config.NumberColumn('Página',format='%d'),'date_name':st.column_config.TextColumn('Fecha MMM-DD-YY'),'folio':st.column_config.TextColumn('Folio'),'confidence':st.column_config.ProgressColumn('Confianza',min_value=0.0,max_value=1.0),'status':'Estado','notes':'Notas'})
    with st.expander('Vista previa'):
        p=st.selectbox('Página',[r.page for r in results]);selected=next(r for r in results if r.page==p);st.image(selected.preview_png,use_container_width=True)
    st.download_button('Descargar PDFs separados y reporte',build_zip(results,edited.to_dict('records')),'bitacoras_procesadas.zip','application/zip',type='primary',use_container_width=True)
