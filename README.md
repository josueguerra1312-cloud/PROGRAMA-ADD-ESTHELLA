# Separador inteligente de bitácoras

Aplicación en Python y Streamlit que recibe un PDF con múltiples bitácoras, separa una página por archivo, identifica la fecha manuscrita y el folio, permite corregir los resultados y descarga un ZIP.

## Nombre de salida

`MMM-DD-YY_FOLIO.pdf`

Ejemplo: `JAN-07-26_2457-015.pdf`

Si la IA no puede leer un dato con seguridad, utiliza `REVIEW` para evitar inventarlo.

## Archivos del repositorio

Todos los archivos se encuentran en la raíz, sin subcarpetas:

- `app.py`: interfaz Streamlit.
- `processor.py`: análisis, validación, separación y ZIP.
- `requirements.txt`: dependencias.
- `.env.example`: variables de entorno de ejemplo.
- `.gitignore`: evita publicar secretos.
- `test_processor.py`: pruebas básicas.
- `LICENSE`: licencia MIT.

## Instalación local

```bash
python -m venv .venv
```

En Windows:

```bash
.venv\Scripts\activate
```

En macOS o Linux:

```bash
source .venv/bin/activate
```

Instala dependencias:

```bash
pip install -r requirements.txt
```

Copia `.env.example` como `.env` y agrega tu clave:

```text
OPENAI_API_KEY=tu_clave_real
OPENAI_VISION_MODEL=gpt-4.1-mini
```

Ejecuta:

```bash
streamlit run app.py
```

## Crear el repositorio en GitHub

1. Crea un repositorio vacío en GitHub, por ejemplo `separador-bitacoras`.
2. Coloca estos archivos en la raíz.
3. Ejecuta:

```bash
git init
git add .
git commit -m "Primera version del separador de bitacoras"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/separador-bitacoras.git
git push -u origin main
```

## Despliegue en Streamlit Community Cloud

- Selecciona el repositorio y `app.py` como archivo principal.
- Agrega `OPENAI_API_KEY` en Secrets; nunca la escribas directamente en el código.
- Opcionalmente agrega `OPENAI_VISION_MODEL`.

## Controles de calidad

- Fecha válida en formato `MMM-DD-YY`.
- Folio normalizado como `2457-015`.
- Filas dudosas marcadas para revisión.
- Sufijo automático para nombres duplicados.
- CSV de auditoría incluido en el ZIP.

## Advertencia

La lectura manuscrita puede fallar. Antes de utilizar los archivos como registros oficiales, una persona autorizada debe revisar las fechas, folios y documentos generados. El procesamiento mediante una API externa puede implicar transferencia de datos; valida previamente las políticas de privacidad y seguridad de tu organización.
