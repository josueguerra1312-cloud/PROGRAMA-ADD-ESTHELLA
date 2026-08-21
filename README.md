# Separador automático de bitácoras

Aplicación Streamlit que procesa automáticamente un PDF al cargarlo, separa cada página, analiza fecha manuscrita y folio mediante visión, permite correcciones y genera un ZIP.

## Configuración local

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copia `.env.example` como `.env` y agrega una clave válida:

```env
OPENAI_API_KEY=tu_clave
OPENAI_VISION_MODEL=gpt-4.1-mini
ANALYSIS_DPI=180
CONFIDENCE_THRESHOLD=0.75
```

Ejecuta:

```bash
streamlit run app.py
```

## Streamlit Community Cloud

En **App settings > Secrets**, agrega:

```toml
OPENAI_API_KEY = "tu_clave"
OPENAI_VISION_MODEL = "gpt-4.1-mini"
ANALYSIS_DPI = "180"
CONFIDENCE_THRESHOLD = "0.75"
```

La aplicación inicia el procesamiento automáticamente cuando detecta un PDF nuevo. El hash del archivo evita repetir llamadas a la API en cada actualización de la interfaz.

Si no hay clave, la aplicación no se bloquea: separa todas las páginas, detecta folios disponibles en el texto y deja las fechas como `REVIEW` para corrección manual.

## Salida

- Un PDF por página: `MMM-DD-YY_2457-015.pdf`.
- Sufijos `_02`, `_03` para duplicados.
- `reporte_bitacoras.csv` dentro del ZIP.

## Importante

La escritura manuscrita puede ser ambigua. Revisa los resultados marcados como `REVISAR` antes de usar archivos como registros oficiales. Confirma además que la política de la organización permite enviar las imágenes a un servicio externo de IA.
