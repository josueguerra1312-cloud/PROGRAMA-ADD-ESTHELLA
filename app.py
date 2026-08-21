import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from processor import build_zip, file_hash, process_pdf

load_dotenv()
st.set_page_config(page_title="Separador de bitácoras", page_icon="📄", layout="wide")
st.title("Separador inteligente de bitácoras")
st.caption("Carga un PDF: el análisis comienza automáticamente y al terminar aparece la descarga.")

# Prioridad: Streamlit Secrets -> variable de entorno/.env.
def get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)

api_key = get_secret("OPENAI_API_KEY")
model = get_secret("OPENAI_VISION_MODEL", "gpt-4.1-mini")
dpi = int(get_secret("ANALYSIS_DPI", "180"))
threshold = float(get_secret("CONFIDENCE_THRESHOLD", "0.75"))

with st.sidebar:
    st.header("Estado")
    st.write("IA configurada:", "Sí" if api_key else "No")
    st.write("Modelo:", model)
    st.write("DPI:", dpi)
    if not api_key:
        st.warning("Sin OPENAI_API_KEY se separarán las páginas, pero las fechas quedarán como REVIEW.")

uploaded = st.file_uploader("Carga el PDF con múltiples bitácoras", type=["pdf"], accept_multiple_files=False)

if uploaded is not None:
    pdf_bytes = uploaded.getvalue()
    current_hash = file_hash(pdf_bytes)
    st.info(f"Archivo cargado: {uploaded.name} ({len(pdf_bytes)/1024/1024:.1f} MB)")

    # Procesa automáticamente solo si el archivo cambió; evita llamar otra vez a la API en cada rerun.
    if st.session_state.get("processed_hash") != current_hash:
        progress_bar = st.progress(0, text="Preparando análisis automático...")
        status_box = st.empty()
        def update_progress(done, total):
            progress_bar.progress(done / total, text=f"Analizando página {done} de {total}")
            status_box.caption("No cierres esta pestaña mientras se procesa el documento.")
        try:
            st.session_state.results = process_pdf(pdf_bytes, api_key, model=model, dpi=dpi, progress=update_progress)
            st.session_state.processed_hash = current_hash
            st.session_state.source_name = uploaded.name
            progress_bar.progress(1.0, text="Proceso terminado")
            status_box.success("Las páginas fueron procesadas. Revisa los datos y descarga el ZIP.")
        except Exception as exc:
            st.session_state.pop("processed_hash", None)
            st.exception(exc)

results = st.session_state.get("results")
if results:
    rows = []
    for result in results:
        visual_status = "OK" if result.status == "OK" and result.confidence >= threshold else "REVISAR"
        rows.append({"page":result.page,"date_name":result.date_name,"folio":result.folio,
                     "confidence":round(result.confidence,3),"status":visual_status,"notes":result.notes})

    ok_count = sum(row["status"] == "OK" for row in rows)
    c1, c2, c3 = st.columns(3)
    c1.metric("Páginas", len(rows)); c2.metric("Analizadas", ok_count); c3.metric("Por revisar", len(rows)-ok_count)
    st.subheader("Revisión antes de descargar")
    st.caption("Puedes corregir fecha y folio directamente. Usa MMM-DD-YY y folio 2457-015.")
    edited = st.data_editor(
        pd.DataFrame(rows), hide_index=True, use_container_width=True,
        disabled=["page","confidence","status","notes"], key=f"editor_{st.session_state.get('processed_hash','')}",
        column_config={
            "page":st.column_config.NumberColumn("Página",format="%d"),
            "date_name":st.column_config.TextColumn("Fecha MMM-DD-YY"),
            "folio":st.column_config.TextColumn("Folio"),
            "confidence":st.column_config.ProgressColumn("Confianza",min_value=0.0,max_value=1.0),
            "status":st.column_config.TextColumn("Estado"),
            "notes":st.column_config.TextColumn("Notas"),
        })

    with st.expander("Vista previa de páginas"):
        selected_page = st.selectbox("Página", [r.page for r in results])
        selected = next(r for r in results if r.page == selected_page)
        st.image(selected.preview_png, caption=f"Página {selected.page}", use_container_width=True)

    zip_bytes = build_zip(results, edited.to_dict("records"))
    st.download_button("Descargar PDFs separados y reporte", zip_bytes, "bitacoras_procesadas.zip",
                       "application/zip", type="primary", use_container_width=True)
else:
    st.caption("El análisis y la descarga aparecerán automáticamente después de cargar un PDF.")
