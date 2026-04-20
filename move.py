from time import perf_counter
from pathlib import Path
from datetime import datetime
from os import environ, getcwd
import shutil
import re


MONTHS = [
    None,
    'JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL',
    'MAIO', 'JUNHO', 'JULHO', 'AGOSTO', 'SETEMBRO',
    'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO'
]

RE_DIGITS = re.compile(r'\d+')

def pdf_number(filename):
    digits = ''.join(RE_DIGITS.findall(filename))
    if len(digits) >= 5:
        return digits[-5:-1]
    return None


def xml_number(filename):
    digits = ''.join(RE_DIGITS.findall(filename))
    if len(digits) >= 14:
        return digits[-14:-10]
    return None


def main():
    start_time = perf_counter()
    print('Aguarde...movendo notas')

    PATHS = [
        Path(environ['CAMINHO_DANFE_MATRIZ']),
        Path(environ['CAMINHO_DANFE_FILIAL']),
        Path(environ['CAMINHO_XML_MATRIZ']),
        Path(environ['CAMINHO_XML_FILIAL'])
    ]

    base_dir = Path(getcwd())
    numero_notas_path = base_dir / 'notas.txt'

    if not numero_notas_path.exists():
        print('Arquivo notas.txt não encontrado.')
        return

    lista_notas = set(numero_notas_path.read_text().split())

    for base_path in PATHS:
        if not base_path or not base_path.exists(): continue

        for root, dirs, files in base_path.walk():

            dirs[:] = [d for d in dirs if not d.isdigit()]

            for file in files:
                filename = file.lower()

                if not filename.startswith('nfe'): continue

                numero_nota = None
                if filename.endswith('.pdf'):
                    numero_nota = pdf_number(filename)

                elif filename.endswith('.xml'):
                    numero_nota = xml_number(filename)

                if numero_nota and numero_nota in lista_notas:
                    source = root / file

                    stat = source.stat()
                    date = datetime.fromtimestamp(stat.st_mtime)

                    move_path = root / str(date.year) / MONTHS[date.month]
                    move_path.mkdir(parents=True, exist_ok=True)

                    destino = move_path / file

                    try:
                        if not destino.exists():
                            shutil.move(str(source), str(destino))

                    except Exception as e:
                        print(f'Erro ao movimentar {file}: {e}')


    elapsed_time = perf_counter()
    print(f'\nTerminado em: {elapsed_time - start_time:0.2f} segundos')
    input('Pressione Enter para fechar...')


if __name__ == "__main__":
    main()

