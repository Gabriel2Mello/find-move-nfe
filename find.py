"""Entrada console para copiar notas; também disponível em notas.py."""
from operacoes import console, pdf_number, xml_number
from integracao_hub import executar_console


def main():
    console('buscar')


if __name__ == '__main__':
    raise SystemExit(executar_console('find-move-nfe', 'Busca e Move Notas', main, sisplan=False))
