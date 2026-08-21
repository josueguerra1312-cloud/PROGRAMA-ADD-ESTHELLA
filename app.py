import pandas as pd
import pytesseract
import streamlit as st

from processor import build_zip, file_hash, normalize_folio, process_pdf

APP_VERSION = 'folio-digits-v3'
st.set_page_config(page_title='Separador de bitácoras', page_icon='📄', layout='wide')
st.title('Separador local de bitácoras')
st.caption('Sin claves ni APIs: separación y OCR local con Tesseract.')

try:
    pytesseract.get_tesseract_version()
except Exception:
    st.error('Tesseract no está instalado. Verifica packages.txt en la raíz del repositorio.')
    st.stop()

uploaded = st.file_uploader('Carga el PDF con múltiples bitácoras', type=['pdf'])
if uploaded:
    data = uploaded.getvalue()
    current_hash = file_hash(data)
    cache_key = f'{APP_VERSION}:{current_hash}'
    st.info(f'Archivo cargado: {uploaded.name} ({len(data)/1024/1024:.1f} MB)')
    if st.session_state.get('processed_hash') != cache_key:
        bar = st.progress(0, text='Preparando OCR local...')
        try:
            def update(done, total):
                bar.progress(done / total, text=f'Analizando página {done} de {total}')
            st.session_state.results = process_pdf(data, dpi=180, progress=update)
            st.session_state.processed_hash = cache_key
            bar.progress(1.0, text='Proceso terminado')
            st.success('Documento separado y analizado.')
        except Exception as exc:
            st.session_state.pop('processed_hash', None)
            st.exception(exc)

results = st.session_state.get('results')
if results:
    rows = [{
        'page': r.page,
        'date_name': r.date_name,
        'folio': normalize_folio(r.folio),
        'confidence': round(r.confidence, 3),
        'status': r.status,
        'notes': r.notes,
    } for r in results]
    ok = sum(row['status'] == 'OK' for row in rows)
    a, b, c = st.columns(3)
    a.metric('Páginas', len(rows)); b.metric('Detectadas', ok); c.metric('Por revisar', len(rows) - ok)
    st.warning('Tesseract puede fallar con escritura manuscrita. Corrige las filas REVIEW antes de descargar.')
    edited = st.data_editor(
        pd.DataFrame(rows), hide_index=True, use_container_width=True,
        disabled=['page', 'confidence', 'status', 'notes'],
        key=f'editor:{APP_VERSION}:{st.session_state.get("processed_hash", "")}',
        column_config={
            'page': st.column_config.NumberColumn('Página', format='%d'),
            'date_name': st.column_config.TextColumn('Fecha MMM-DD-YY'),
            'folio': st.column_config.TextColumn('Folio sin guiones'),
            'confidence': st.column_config.ProgressColumn('Confianza', min_value=0.0, max_value=1.0),
            'status': 'Estado', 'notes': 'Notas',
        },
    )
    with st.expander('Vista previa'):
        page_number = st.selectbox('Página', [r.page for r in results])
        selected = next(r for r in results if r.page == page_number)
        st.image(selected.preview_png, use_container_width=True)
    # build_zip vuelve a borrar cualquier separador del folio, incluso si se escribe manualmente.
    zip_bytes = build_zip(results, edited.to_dict('records'))
    st.download_button(
        'Descargar PDFs separados y reporte', zip_bytes,
        'bitacoras_procesadas.zip', 'application/zip',
        type='primary', use_container_width=True,
    )
