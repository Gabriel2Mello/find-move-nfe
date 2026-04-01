from time import perf_counter
from pathlib import Path
from datetime import datetime
from os import environ

start_time = perf_counter()

MONTHS = [
    None,
    'JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL',
    'MAIO', 'JUNHO', 'JULHO', 'AGOSTO', 'SETEMBRO',
    'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO'
]

def pdf_number(file):
    digits = ''.join(filter(str.isdigit, file))
    if len(digits) >= 5:
        return digits[-5:-1]

def xml_number(file):
    digits = ''.join(filter(str.isdigit, file))
    if len(digits) >= 14:
        return digits[-14:-10]

def readable_date(stat):
    mtime = stat.st_mtime
    return datetime.fromtimestamp(mtime)

PATHS = [
    Path(environ['CAMINHO_DANFE_MATRIZ']),
    Path(environ['CAMINHO_DANFE_FILIAL']),
    Path(environ['CAMINHO_XML_MATRIZ']),
    Path(environ['CAMINHO_XML_FILIAL'])
]

notas_salvas_path = Path('.') / 'notas'

numero_notas_path = Path('notas.txt')
lista_notas = numero_notas_path.read_text().split()

for base_path in PATHS:
    for root, dirs, files in base_path.walk(top_down=True):
        if root == notas_salvas_path:
            continue

        for file in files:
            numero_nota = None

            if file.lower().endswith('.pdf'):
                numero_nota = pdf_number(file)

            elif file.lower().endswith('.xml'):
                numero_nota = xml_number(file)

            if numero_nota in lista_notas:
                source = root / file

                date = readable_date(source.stat())
                move_base_path = root / f"{date.year}"

                if not move_base_path.exists():
                    continue

                move_path = move_base_path / MONTHS[date.month]

                if not move_path.exists():
                    continue

                source.move_into(move_path)

elapsed_time = perf_counter()
print(f"Done in: {elapsed_time - start_time:0.2f} seconds")

