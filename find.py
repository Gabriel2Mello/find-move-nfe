from time import perf_counter
from pathlib import Path
from os import environ, getcwd
import shutil
import re


PATHS = [
  Path(environ.get('CAMINHO_DANFE_MATRIZ', '')),
  Path(environ.get('CAMINHO_DANFE_FILIAL', '')),
  Path(environ.get('CAMINHO_XML_MATRIZ', '')),
  Path(environ.get('CAMINHO_XML_FILIAL', ''))
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
    print('Aguarde...buscando notas')
    start_time = perf_counter()

    base_dir = Path(getcwd())
    notas_salvas_path = base_dir / 'notas'
    notas_salvas_path.mkdir(exist_ok=True)

    numero_notas_path = base_dir / 'notas.txt'
    if not numero_notas_path.exists():
        print('Arquivo notas.txt não encontrado.')
        return

    lista_notas = set(numero_notas_path.read_text().split())

    for base_path in PATHS:
        if not base_path or not base_path.exists(): continue

        for root, _, files in base_path.walk():
            if notas_salvas_path in root.parents: continue
            if root == notas_salvas_path: continue

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
                    destino = notas_salvas_path / file

                    try:
                       shutil.copy2(source, destino)
                    except Exception as e:
                        print(f'Erro ao copiar {file}: {e}')


    elapsed_time = perf_counter()
    print(f"\nTerminado em: {elapsed_time - start_time:0.2f} segundos")
    input('Pressione Enter para fechar...')


if __name__ == "__main__":
    main()

