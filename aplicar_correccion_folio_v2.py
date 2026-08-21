from pathlib import Path

processor = Path('processor.py')
app = Path('app.py')

if not processor.exists() or not app.exists():
    raise SystemExit('Ejecuta este archivo desde la raiz del repositorio, junto a app.py y processor.py.')

p = processor.read_text(encoding='utf-8')

# Sustituye la funcion completa, aunque la version anterior use guion o espacio.
start = p.find('def normalize_folio(')
end = p.find('\ndef ', start + 1)
if start < 0 or end < 0:
    raise SystemExit('No se encontro normalize_folio en processor.py')

new_function = '''def normalize_folio(value:str)->str:
    """Devuelve el folio usando solo digitos: 2457-015 -> 2457015."""
    digits = re.sub(r"\\D", "", str(value or ""))
    match = re.search(r"(\\d{7})", digits)
    return match.group(1) if match else "REVIEW"
'''
p = p[:start] + new_function + p[end:]

# Defensa adicional: el nombre final nunca puede contener guiones en el folio.
old = "folio=normalize_folio(folio);base=f'{dt}_{folio}'"
new = "folio=normalize_folio(folio);base=f'{dt}_{folio}'"
# La normalizacion anterior ya garantiza solo digitos; se conserva make_filename.
processor.write_text(p, encoding='utf-8')

a = app.read_text(encoding='utf-8')
# Importa normalize_folio para limpiar tambien la tabla visible.
a = a.replace(
    'from processor import build_zip,file_hash,process_pdf',
    'from processor import build_zip,file_hash,process_pdf,normalize_folio'
)
# Limpia valores antiguos guardados por la sesion antes de mostrarlos.
a = a.replace(
    "'folio':r.folio,",
    "'folio':normalize_folio(r.folio),"
)
# Fuerza un nuevo procesamiento tras esta actualizacion.
a = a.replace(
    "if st.session_state.get('processed_hash')!=current:",
    "cache_key = 'folio_sin_guion_v2_' + current\n    if st.session_state.get('processed_hash')!=cache_key:"
)
a = a.replace(
    "st.session_state.processed_hash=current;",
    "st.session_state.processed_hash=cache_key;"
)
app.write_text(a, encoding='utf-8')

# Actualiza pruebas si existen.
test = Path('test_processor.py')
if test.exists():
    t = test.read_text(encoding='utf-8')
    t = t.replace("'2457-015'", "'2457015'")
    t = t.replace("'JAN-07-26_2457-015.pdf'", "'JAN-07-26_2457015.pdf'")
    test.write_text(t, encoding='utf-8')

print('OK: folios corregidos sin guiones en tabla, CSV y nombres PDF.')
