# Separador local de bitácoras - sin claves

Esta versión usa RapidOCR + ONNX Runtime. No usa EasyOCR, OpenAI ni secretos.

## Archivos
Todos deben estar en la raíz del repositorio.

## Streamlit Cloud
1. Reemplaza los archivos del repositorio.
2. Elimina `easyocr` y `torch` de cualquier archivo de dependencias antiguo.
3. En Streamlit Cloud elimina la app y vuelve a desplegarla seleccionando Python 3.12 en Advanced settings.
4. Usa `app.py` como Main file path.

## Local
```bash
pip install -r requirements.txt
streamlit run app.py
```

El análisis se inicia al cargar el PDF. Las lecturas dudosas se marcan `REVIEW` para corrección manual.
