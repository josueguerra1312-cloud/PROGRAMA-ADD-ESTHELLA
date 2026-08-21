# Separador de bitácoras sin claves

Versión compatible con Streamlit Cloud y Python 3.14. Usa PyMuPDF, Pillow y Tesseract instalado mediante `packages.txt`. No usa OpenCV, RapidOCR, EasyOCR, PyTorch ni API externa.

## Despliegue

Todos estos archivos deben estar en la raíz:

- `app.py`
- `processor.py`
- `requirements.txt`
- `packages.txt`

Actualiza GitHub y usa **Reboot app**. Si el entorno conserva dependencias antiguas, elimina la app de Streamlit Cloud y vuelve a desplegarla.

## Limitación

Tesseract reconoce mejor texto impreso que manuscrito. Las fechas dudosas quedan como `REVIEW` y pueden corregirse en la tabla antes de descargar.
