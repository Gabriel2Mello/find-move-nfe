"""Diagnóstico local da abertura, sem mensagens, dados fiscais ou valores do ambiente."""
from datetime import datetime, timezone
import os
from pathlib import Path
import struct
import sys
import tempfile
import traceback

from integracao_hub import gravar_registro


def detalhes(erro, etapa, *, aplicacao, raiz_recursos, arquivos=()):
  causas = []
  vistos = set()
  atual = erro
  while atual is not None and id(atual) not in vistos and len(causas) < 12:
    vistos.add(id(atual))
    item = {'tipo': type(atual).__name__, 'locais': [
      f'{Path(q.filename).name}:{q.lineno} {q.name}'
      for q in traceback.extract_tb(getattr(atual, '__traceback__', None))]}
    for nome in ('winerror', 'errno', 'HResult'):
      valor = getattr(atual, nome, None)
      if isinstance(valor, int):
        item[nome] = valor
    causas.append(item)
    atual = (getattr(atual, '__cause__', None) or getattr(atual, '__context__', None)
             or getattr(atual, 'InnerException', None))
  recursos_verificados = {}
  for nome in arquivos:
    arquivo = Path(raiz_recursos) / nome
    recursos_verificados[nome] = {'presente': arquivo.is_file(),
                      'marca_download': Path(str(arquivo) + ':Zone.Identifier').is_file()}
  # Apenas enum conhecido: nenhum caminho ou valor livre do ambiente entra no relatório.
  runtime = os.environ.get('PYTHONNET_RUNTIME', 'padrao')
  if runtime not in ('padrao', 'netfx', 'coreclr', 'mono'):
    runtime = 'personalizado'
  return {'formato': 1, 'instante': datetime.now(timezone.utc).isoformat(),
          'aplicacao': aplicacao, 'etapa': etapa, 'python': sys.version.split()[0], 'bits': struct.calcsize('P') * 8,
          'empacotado': bool(getattr(sys, 'frozen', False)), 'pythonnet_runtime': runtime,
          'causas': causas, 'recursos': recursos_verificados}


def registrar(erro, etapa, *, aplicacao, pasta_preferencias, raiz_recursos, arquivos=(), nome=None):
  nome = nome or f'{aplicacao}-diagnostico.txt'
  if Path(nome).name != nome or '/' in nome or '\\' in nome or not nome.endswith('-diagnostico.txt'):
    raise ValueError('Nome de diagnostico invalido.')
  dados = detalhes(erro, etapa, aplicacao=aplicacao, raiz_recursos=raiz_recursos, arquivos=arquivos)
  pastas = []
  if getattr(sys, 'frozen', False):
    pastas.append(Path(sys.executable).resolve().parent)
  pastas.extend((Path(pasta_preferencias) / 'logs', Path(tempfile.gettempdir())))
  for pasta in pastas:
    try:
      pasta.mkdir(parents=True, exist_ok=True)
      caminho = pasta / nome
      gravar_registro(caminho, dados)
      return caminho
    except OSError:
      continue
  return None
