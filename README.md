# Separador local de bitácoras - sin API key

Carga un PDF, separa las páginas y ejecuta OCR local con EasyOCR. No utiliza OpenAI ni requiere secretos.

## Uso

```bash
pip install -r requirements.txt
streamlit run app.py
```

La primera ejecución descarga los pesos públicos de EasyOCR. Después, el análisis se ejecuta localmente en CPU.

## Salida

- `MMM-DD-YY_2457-015.pdf` por página.
- `REVIEW_...pdf` cuando la fecha o folio no son confiables.
- CSV de auditoría dentro del ZIP.

## Precisión

EasyOCR es OCR general. La escritura manuscrita difícil puede requerir corrección en la tabla antes de descargar. Esta versión no envía el PDF a una API externa.
