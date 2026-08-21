from pathlib import Path

p = Path('processor.py')
s = p.read_text(encoding='utf-8')
old = "return f'{m.group(1)}-{m.group(2)}' if m else 'REVIEW'"
new = "return f'{m.group(1)}{m.group(2)}' if m else 'REVIEW'"
if old not in s:
    raise SystemExit('No se encontró la línea esperada en processor.py; quizá ya fue corregida.')
p.write_text(s.replace(old, new), encoding='utf-8')

t = Path('test_processor.py')
if t.exists():
    x = t.read_text(encoding='utf-8')
    x = x.replace("=='2457-015'", "=='2457015'")
    x = x.replace("=='JAN-07-26_2457-015.pdf'", "=='JAN-07-26_2457015.pdf'")
    t.write_text(x, encoding='utf-8')

print('Corrección aplicada: los folios se guardarán sin guion, por ejemplo 2457015.')
