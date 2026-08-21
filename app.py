import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from processor import build_zip, process_pdf

load_dotenv()
st.set_page_config(page_title="Separador de bitácoras", page_icon="📄", layout="wide")
st.title("Separador inteligente de bitácoras")
st.caption("Divide un PDF, identifica fecha y folio, permite revisión y genera un ZIP.")

with st.sidebar:
    st.header("Configuración")
    api_key = st.text_input(
        "OpenAI API key",
        value=os.getenv("OPENAI_API_KEY", ""),
        type="password",
        help="En producción usa Streamlit Secrets; no subas tu clave a GitHub.",
    )
    model = st.text_input("Modelo con visión", value=os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini"))
    dpi = st.slider("Resolución de análisis (DPI)", 120, 240, 180, 20)
    threshold = st.slider("Umbral visual de confianza", 0.50, 0.95, 0.75, 0.05)

uploaded = st.file_uploader("Carga el PDF con múltiples bitácoras", type=["pdf"])

if uploaded is not None:
    pdf_bytes = uploaded.getvalue()
    st.info(f"Archivo cargado: {uploaded.name} ({len(pdf_bytes) / 1024 / 1024:.1f} MB)")
    if st.button("Analizar bitácoras", type="primary", disabled=not api_key):
        with st.status("Procesando páginas...", expanded=True) as status:
            st.write("Renderizando y enviando cada página al modelo de visión.")
            try:
                st.session_state.results = process_pdf(pdf_bytes, api_key, model=model, dpi=dpi)
                st.session_state.source_name = uploaded.name
                status.update(label="Análisis terminado", state="complete")
            except Exception as exc:
                status.update(label="Error de procesamiento", state="error")
                st.exception(exc)

results = st.session_state.get("results")
if results:
    st.subheader("Revisión")
    st.warning("Verifica especialmente las filas marcadas como REVISAR. La aplicación nunca debe sustituir la revisión técnica requerida.")
    rows = []
    for result in results:
        status = "OK" if result.status == "OK" and result.confidence >= threshold else "REVISAR"
        rows.append({
            "page": result.page,
            "date_name": result.date_name,
            "folio": result.folio,
            "confidence": round(result.confidence, 3),
            "status": status,
            "notes": result.notes,
        })
    edited = st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        disabled=["page", "confidence", "status", "notes"],
        column_config={
            "page": st.column_config.NumberColumn("Página", format="%d"),
            "date_name": st.column_config.TextColumn("Fecha MMM-DD-YY"),
            "folio": st.column_config.TextColumn("Folio"),
            "confidence": st.column_config.ProgressColumn("Confianza", min_value=0.0, max_value=1.0),
            "status": st.column_config.TextColumn("Estado"),
            "notes": st.column_config.TextColumn("Notas"),
        },
        key="review_editor",
    )

    review_pages = [r for r in results if r.status != "OK" or r.confidence < threshold]
    with st.expander(f"Ver páginas que requieren atención ({len(review_pages)})", expanded=bool(review_pages)):
        selected_page = st.selectbox("Página", [r.page for r in results])
        selected = next(r for r in results if r.page == selected_page)
        st.image(selected.preview_png, caption=f"Página {selected.page}", use_container_width=True)

    zip_bytes = build_zip(results, edits=edited.to_dict("records"))
    st.download_button(
        "Descargar PDFs y reporte ZIP",
        data=zip_bytes,
        file_name="bitacoras_procesadas.zip",
        mime="application/zip",
        type="primary",
        use_container_width=True,
    )
