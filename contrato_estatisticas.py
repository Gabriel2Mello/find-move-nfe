"""Contrato v1 da central local e dos clientes distribuídos independentemente."""
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from urllib.parse import parse_qs, urlsplit

VERSAO = 1
LIMITE_LOTE = 100
LIMITE_CORPO = 262144
CAMPOS = ('id', 'evento', 'ocorrido_em', 'dia', 'execucao', 'referencia', 'empresa', 'setor', 'tipo')
FUSO = timezone(timedelta(hours=-3))
APLICACOES = {
    'find-move-nfe': ('arquivo_transferido', ('busca_pdf', 'busca_xml', 'move_pdf', 'move_xml')),
    'cofre-nfe': ('documento_baixado', ('nfe', 'cte')),
}


def aplicacao_da_consulta(query):
    parametros = parse_qs(query, keep_blank_values=True, strict_parsing=True, max_num_fields=1)
    if parametros and (set(parametros) != {'aplicacao'} or len(parametros['aplicacao']) != 1):
        raise ValueError('Consulta inválida.')
    aplicacao = parametros.get('aplicacao', ['find-move-nfe'])[0]
    if aplicacao not in APLICACOES:
        raise ValueError('Aplicação fora do escopo da central.')
    return aplicacao


def caminho_resumo(aplicacao):
    if aplicacao not in APLICACOES:
        raise ValueError('Aplicação fora do escopo da central.')
    return '/v1/resumo' + ('' if aplicacao == 'find-move-nfe' else '?aplicacao=' + aplicacao)


def validar_evento(bruto):
    if (not isinstance(bruto, dict) or set(bruto) != set(CAMPOS)
            or any(not isinstance(valor, str) for valor in bruto.values())):
        raise ValueError('Estrutura de evento inválida.')
    arquivo = (bruto['evento'] == 'arquivo_transferido'
               and bruto['tipo'] in APLICACOES['find-move-nfe'][1]
               and len(bruto['referencia']) == 4 and bruto['referencia'].isascii()
               and bruto['referencia'].isdigit() and not bruto['empresa'])
    documento = (bruto['evento'] == 'documento_baixado'
                 and bruto['tipo'] in APLICACOES['cofre-nfe'][1]
                 and bruto['empresa'] in ('MATRIZ', 'FILIAL')
                 and 1 <= len(bruto['referencia']) <= 512)
    if (len(bruto['id']) != 64 or any(c not in '0123456789abcdef' for c in bruto['id'])
            or not (arquivo or documento) or bruto['setor']):
        raise ValueError('Evento fora do escopo do piloto.')
    if not bruto['execucao'].strip() or len(bruto['execucao']) > 128:
        raise ValueError('Execução inválida.')
    instante = datetime.fromisoformat(bruto['ocorrido_em'])
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError('Instante sem fuso.')
    instante = instante.astimezone(timezone.utc)
    dia = date.fromisoformat(bruto['dia'])
    if dia.year < 2000 or dia.isoformat() != bruto['dia'] or instante.astimezone(FUSO).date() != dia:
        raise ValueError('Dia divergente do instante.')
    return {**bruto, 'ocorrido_em': instante.isoformat(timespec='microseconds')}


def serializar(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def assinatura(evento):
    return sha256(serializar(validar_evento(evento)).encode('utf-8')).hexdigest()


def validar_cliente(dados):
    if not isinstance(dados, dict) or set(dados) != {'protocolo', 'url', 'central_id', 'token'}:
        raise ValueError('Configuração da central inválida.')
    if type(dados['protocolo']) is not int or dados['protocolo'] != VERSAO:
        raise ValueError('Protocolo incompatível.')
    if (not isinstance(dados['central_id'], str) or len(dados['central_id']) != 32
            or any(c not in '0123456789abcdef' for c in dados['central_id'])
            or not isinstance(dados['token'], str) or not 32 <= len(dados['token']) <= 128
            or not dados['token'].isascii() or any(c.isspace() for c in dados['token'])):
        raise ValueError('Identidade ou acesso da central inválido.')
    if not isinstance(dados['url'], str):
        raise ValueError('Endereço da central inválido.')
    url = urlsplit(dados['url'])
    if (url.scheme != 'http' or url.hostname != '127.0.0.1' or url.port is None
            or not 1 <= url.port <= 65535 or url.username is not None or url.password is not None
            or url.path or url.query or url.fragment or dados['url'] != f'http://127.0.0.1:{url.port}'):
        raise ValueError('Este piloto aceita somente HTTP em 127.0.0.1 com porta explícita.')
    return dict(dados)
