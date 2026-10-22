"""Replica métricas persistidas; não executa nem repete transferências fiscais."""
import argparse
from contextlib import closing
from http.client import HTTPException
import json
import logging
import os
from pathlib import Path
import sqlite3
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from contrato_estatisticas import (
    APLICACOES, CAMPOS, LIMITE_CORPO, LIMITE_LOTE, VERSAO, assinatura, caminho_resumo,
    serializar, validar_cliente, validar_evento,
)
from metricas_nunes import pasta_metricas

logger = logging.getLogger(__name__)
FALHAS = (OSError, ValueError, TypeError, KeyError, OverflowError, sqlite3.Error, HTTPException)


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def ler_configuracao(arquivo=None):
    explicita = arquivo is not None or bool(os.environ.get('NUNES_CENTRAL_CONFIG'))
    caminho = Path(arquivo or os.environ.get('NUNES_CENTRAL_CONFIG') or
                   Path(__file__).resolve().parent / '.local' / 'central.json')
    try:
        return validar_cliente(json.loads(caminho.read_text(encoding='utf-8')))
    except FileNotFoundError:
        if not explicita:
            return None
        raise ValueError('Configuração explícita da central ausente.') from None


def requisitar(config, caminho, dados=None):
    config = validar_cliente(config)
    corpo = None if dados is None else serializar(dados).encode('utf-8')
    if corpo is not None and len(corpo) > LIMITE_CORPO:
        raise ValueError('Lote acima do limite do protocolo.')
    pedido = Request(config['url'] + caminho, data=corpo, headers={
        'Authorization': 'Bearer ' + config['token'], 'Content-Type': 'application/json',
    })
    # Não entrega tokens a proxies do usuário ou destinos de redirecionamentos.
    try:
        resposta = build_opener(ProxyHandler({}), SemRedirecionamento()).open(pedido, timeout=1)
    except HTTPError as erro:
        erro.close()
        raise
    with resposta:
        if resposta.status != 200 or resposta.headers.get_content_type() != 'application/json':
            raise ValueError('Resposta da central inválida.')
        bruto = resposta.read(LIMITE_CORPO + 1)
        if len(bruto) > LIMITE_CORPO:
            raise ValueError('Resposta da central acima do limite.')
        resultado = json.loads(bruto)
    if (not isinstance(resultado, dict) or type(resultado.get('protocolo')) is not int
            or resultado['protocolo'] != VERSAO or resultado.get('central_id') != config['central_id']):
        raise ValueError('A resposta não identifica a central configurada.')
    return resultado


def ler_eventos(pasta, aplicacao='find-move-nfe'):
    """Snapshot do contrato local v1; não altera banco nem fila de recuperação."""
    pasta = Path(pasta)
    eventos = {}
    evento_alvo = APLICACOES[aplicacao][0]
    def adicionar(bruto):
        if not isinstance(bruto, dict):
            raise ValueError('Fila local inválida; preserve os arquivos.')
        if bruto.get('evento') != evento_alvo:
            return
        evento = validar_evento(bruto)
        anterior = eventos.get(evento['id'])
        if anterior is None or evento['ocorrido_em'] < anterior['ocorrido_em']:
            eventos[evento['id']] = evento
    caminho = pasta / 'resultados.sqlite3'
    if caminho.exists():
        with closing(sqlite3.connect(caminho.resolve().as_uri() + '?mode=ro', uri=True, timeout=.8)) as banco:
            if banco.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('Versão de métricas locais incompatível.')
            banco.row_factory = sqlite3.Row
            for linha in banco.execute('SELECT ' + ','.join(CAMPOS) +
                                      ' FROM eventos WHERE evento=? ORDER BY id', (evento_alvo,)):
                adicionar(dict(linha))
    for arquivo in sorted((pasta / 'recuperar').glob('*.json')):
        try:
            adicionar(json.loads(arquivo.read_text(encoding='utf-8')))
        except FileNotFoundError:
            # Outro leitor pode ter consolidado a fila; o próximo ciclo relê o banco.
            continue
    return eventos


class Cliente:
    def __init__(self, config, origem=None, estado=None, *, aplicacao='find-move-nfe'):
        if aplicacao not in APLICACOES:
            raise ValueError('Aplicação fora do escopo da central.')
        self.aplicacao = aplicacao
        self.config = validar_cliente(config)
        self.origem = Path(origem) if origem is not None else pasta_metricas()
        nome = 'find-move' if aplicacao == 'find-move-nfe' else aplicacao
        self.estado = Path(estado) if estado is not None else self.origem / f'sincronizacao-{nome}.sqlite3'

    def conectar(self):
        self.estado.parent.mkdir(parents=True, exist_ok=True)
        banco = sqlite3.connect(self.estado, timeout=.8)
        try:
            with banco:
                banco.execute('BEGIN IMMEDIATE')
                versao = banco.execute('PRAGMA user_version').fetchone()[0]
                if versao not in (0, 1):
                    raise ValueError('Versão de confirmações incompatível.')
                if versao == 0:
                    if banco.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                        raise ValueError('Base de confirmações não reconhecida.')
                    banco.execute('CREATE TABLE confirmados (central_id TEXT NOT NULL, id TEXT NOT NULL, '
                                  'assinatura TEXT NOT NULL, PRIMARY KEY(central_id,id))')
                    banco.execute('PRAGMA user_version=1')
            return banco
        except BaseException:
            banco.close()
            raise

    def pendentes(self, *, somente_leitura=False):
        eventos = ler_eventos(self.origem, self.aplicacao)
        confirmados = {}
        if not somente_leitura or self.estado.exists():
            conexao = (sqlite3.connect(self.estado.resolve().as_uri() + '?mode=ro', uri=True, timeout=.8)
                       if somente_leitura else self.conectar())
            with closing(conexao) as banco:
                if banco.execute('PRAGMA user_version').fetchone()[0] != 1:
                    raise ValueError('Versão de confirmações incompatível.')
                confirmados = dict(banco.execute('SELECT id,assinatura FROM confirmados WHERE central_id=?',
                                                 (self.config['central_id'],)))
        return [evento for chave, evento in sorted(eventos.items())
                if confirmados.get(chave) != assinatura(evento)]

    def sincronizar(self):
        pendentes = self.pendentes()
        quantidade = 0
        # Limita cada ciclo; lotes maiores continuam no próximo ciclo/abertura.
        for inicio in range(0, min(len(pendentes), LIMITE_LOTE * 10), LIMITE_LOTE):
            lote = pendentes[inicio:inicio + LIMITE_LOTE]
            resposta = requisitar(self.config, '/v1/eventos', {
                'protocolo': VERSAO, 'central_id': self.config['central_id'], 'eventos': lote,
            })
            esperados = [{'id': evento['id'], 'assinatura': assinatura(evento)} for evento in lote]
            if (set(resposta) != {'protocolo', 'central_id', 'confirmados'}
                    or resposta['confirmados'] != esperados):
                raise ValueError('Confirmação não corresponde ao lote; eventos permanecem pendentes.')
            with closing(self.conectar()) as banco, banco:
                banco.executemany('INSERT INTO confirmados VALUES (?,?,?) ON CONFLICT(central_id,id) '
                                  'DO UPDATE SET assinatura=excluded.assinatura',
                                  [(self.config['central_id'], item['id'], item['assinatura']) for item in esperados])
            quantidade += len(lote)
        return {'confirmados_neste_ciclo': quantidade, 'pendentes': len(self.pendentes())}


class Sincronizador:
    """Um worker por entrada web/console, independente da execução de arquivos."""
    def __init__(self, relatar=print, arquivo=None, intervalo=5, *, aplicacao='find-move-nfe'):
        if aplicacao not in APLICACOES:
            raise ValueError('Aplicação fora do escopo da central.')
        self.aplicacao = aplicacao
        self.relatar = relatar
        self.arquivo = arquivo
        self.intervalo = intervalo
        self.parar = Event()
        self.worker = None

    def __enter__(self):
        try:
            config = ler_configuracao(self.arquivo)
            if config is not None:
                self.cliente = Cliente(config, aplicacao=self.aplicacao)
                self.worker = Thread(target=self._executar, daemon=True)
                self.worker.start()
        except FALHAS:
            self.relatar('Sincronização indisponível: confira a configuração da central. Métricas locais preservadas.')
        return self

    def _ciclo(self):
        try:
            resultado = self.cliente.sincronizar()
        except FALHAS:
            if self.ultimo != 'pendente':
                self.relatar('Estatísticas aguardando a central local. Não repita a operação de arquivos.')
                logger.warning('Sincronização pendente; dados locais não foram removidos.')
            self.ultimo = 'pendente'
        else:
            if resultado['confirmados_neste_ciclo']:
                self.relatar(f"Estatísticas: {resultado['confirmados_neste_ciclo']} evento(s) confirmado(s) pela central.")
            self.ultimo = 'ok'

    def _executar(self):
        self.ultimo = None
        self._ciclo()
        while not self.parar.wait(self.intervalo):
            self._ciclo()
        self._ciclo()

    def __exit__(self, tipo, valor, traceback):
        self.parar.set()
        if self.worker is not None:
            self.worker.join(2.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--aplicacao', choices=APLICACOES, default='find-move-nfe')
    parser.add_argument('--resumo', action='store_true', help='Consulta sem enviar eventos.')
    opcoes = parser.parse_args()
    try:
        config = ler_configuracao(opcoes.config)
        if config is None:
            print('Sincronização não habilitada nesta instalação.')
            return 0
        cliente = Cliente(config, aplicacao=opcoes.aplicacao)
        if not opcoes.resumo:
            print(serializar(cliente.sincronizar()))
        print(serializar({'central': requisitar(config, caminho_resumo(opcoes.aplicacao)),
                          'pendentes_locais': len(cliente.pendentes(somente_leitura=True))}))
        return 0
    except FALHAS:
        print('Não foi possível confirmar a sincronização. Confira configuração, central e registros locais.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
