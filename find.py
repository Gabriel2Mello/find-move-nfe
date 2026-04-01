from time import perf_counter
from pathlib import Path
from os import environ
from os import getcwd

start_time = perf_counter()

def pdf_number(file):
    digits = ''.join(filter(str.isdigit, file))
    if len(digits) >= 5:
        return digits[-5:-1]

def xml_number(file):
    digits = ''.join(filter(str.isdigit, file))
    if len(digits) >= 14:
        return digits[-14:-10]

PATHS = [
  Path(environ['CAMINHO_DANFE_MATRIZ']),
  Path(environ['CAMINHO_DANFE_FILIAL']),
  Path(environ['CAMINHO_XML_MATRIZ']),
  Path(environ['CAMINHO_XML_FILIAL'])
]

base_dir = Path(getcwd())
notas_salvas_path = base_dir / 'notas'

numero_notas_path = base_dir / 'notas.txt'
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

                if not source.exists():
                    print('Caminho: ', source, ' não encontrado')
                    continue

                source.copy_into(notas_salvas_path)

elapsed_time = perf_counter()
print(f"Done in: {elapsed_time - start_time:0.2f} seconds")

