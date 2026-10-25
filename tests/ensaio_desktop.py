"""Janela real com arquivos sintéticos e cópia lenta para conferir X cooperativo.

Opt-in: python -m tests.ensaio_desktop. Não distribuído no pacote.
A lentidão termina a cópia atual antes de observar o cancelamento normal.
"""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time


def main():
    pasta = Path(tempfile.mkdtemp(prefix='notas-janela-sintetica-'))
    dados, origem, destino = pasta / 'dados', pasta / 'ORIGEM', pasta / 'COPIAS'
    (dados / '.local').mkdir(parents=True)
    origem.mkdir()
    destino.mkdir()
    notas = ', '.join(str(n) for n in range(1200, 1220))
    (dados / 'notas.txt').write_text(notas)
    (dados / '.local/preferencias.json').write_text(json.dumps({'destino': str(destino)}))
    os.environ.update(NUNES_NOTAS_DADOS=str(dados), NUNES_HUB_DADOS=str(pasta / 'presenca'),
        NUNES_METRICAS_DADOS=str(pasta / 'metricas'), NUNES_CENTRAL_CONFIG=str(pasta / 'central-ausente.json'),
        **{v: str(origem) for v in ('CAMINHO_DANFE_MATRIZ', 'CAMINHO_DANFE_FILIAL',
                                  'CAMINHO_XML_MATRIZ', 'CAMINHO_XML_FILIAL')})
    for n in range(1200, 1220):
        (origem / f'NFe{n}1.pdf').write_bytes(b'Conteudo sintetico ' * 4096)
    conectar = socket.socket.connect
    def somente_local(sock, endereco):
        if isinstance(endereco, tuple) and endereco[0] not in ('127.0.0.1', '::1'):
            raise RuntimeError('Rede externa bloqueada no ensaio.')
        return conectar(sock, endereco)
    socket.socket.connect = somente_local
    import operacoes
    copiar = operacoes._copiar_verificado
    def lenta(*args, **kwargs):
        time.sleep(4)
        return copiar(*args, **kwargs)
    operacoes._copiar_verificado = lenta
    import notas as aplicacao
    sys.argv = [str(Path(aplicacao.__file__))]
    print(f'Janela sintética: {pasta}', flush=True)
    print(f'Notas para informar manualmente na interface: {notas}', flush=True)
    return aplicacao.iniciar()


if __name__ == '__main__':
    raise SystemExit(main())
