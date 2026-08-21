# Correccion de folio sin guion

Ejecuta desde la raiz del repositorio:

```bash
python aplicar_correccion_folio_v2.py
python -m py_compile app.py processor.py
```

Resultado esperado:

- Tabla: `2457015`
- PDF: `REVIEW_2457015.pdf` o `JAN-07-26_2457015.pdf`
- CSV: `2457015`

La correccion tambien cambia la clave de sesion para descartar resultados antiguos que conservaban `2457-015`.
