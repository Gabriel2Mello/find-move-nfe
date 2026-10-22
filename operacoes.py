"""Busca e organização de notas, compartilhadas pelo console e pela interface."""
from datetime import datetime
from os import environ, walk
from pathlib import Path
import errno
import hashlib
import json
import os
import re
import shutil
import tempfile

from metricas_nunes import registrar_evento
from sincronizar_estatisticas import Sincronizador

VARIAVEIS = ('CAMINHO_DANFE_MATRIZ', 'CAMINHO_DANFE_FILIAL',
             'CAMINHO_XML_MATRIZ', 'CAMINHO_XML_FILIAL')
MONTHS = (None, 'JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL', 'MAIO', 'JUNHO',
          'JULHO', 'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO')
RE_DIGITS = re.compile(r'\d+')


def pdf_number(filename):
    digits = ''.join(RE_DIGITS.findall(filename))
    return digits[-5:-1] if len(digits) >= 5 else None


def xml_number(filename):
    digits = ''.join(RE_DIGITS.findall(filename))
    return digits[-14:-10] if len(digits) >= 14 else None


def caminhos_ambiente():
    return [environ.get(nome, '') for nome in VARIAVEIS]


def preparar(notas, caminhos, destino):
    if not isinstance(notas, str):
        raise ValueError('Informe os números das notas.')
    numeros = set(re.split(r'[\s,;]+', notas.strip())) - {''}
    if not numeros or any(not re.fullmatch(r'[0-9]{1,4}', n) for n in numeros):
        raise ValueError('Informe notas com até quatro dígitos, separadas por espaço, vírgula ou linha.')
    if not isinstance(caminhos, list) or len(caminhos) != 4 or any(
            not isinstance(c, str) or not c.strip() for c in caminhos):
        raise ValueError('Informe as quatro pastas de DANFE e XML.')
    pastas = list(dict.fromkeys(Path(c.strip()).resolve() for c in caminhos))
    for pasta in pastas:
        if not pasta.is_dir():
            raise ValueError(f'Pasta de origem não encontrada: {pasta}')
    if not isinstance(destino, str) or not destino.strip():
        raise ValueError('Informe a pasta para salvar as cópias.')
    saida = Path(destino.strip()).resolve()
    if any(pasta == saida or pasta.is_relative_to(saida) for pasta in pastas):
        raise ValueError('A pasta de cópias não pode conter uma pasta de origem.')
    if saida.exists() and not saida.is_dir():
        raise ValueError('O destino das cópias deve ser uma pasta.')
    return {n.zfill(4) for n in numeros}, pastas, saida


class ConflitoDestino(FileExistsError):
    """Outro arquivo já ocupa o nome definitivo; nenhuma substituição."""


def _renomear_sem_substituir(origem: Path, alvo: Path) -> None:
    try:
        if os.name == 'nt':
            # No Windows, rename recusa um nome já ocupado, inclusive na corrida.
            os.rename(origem, alvo)
        else:
            # rename POSIX substituiria o destino; link exige um nome livre.
            os.link(origem, alvo)
            origem.unlink()
    except FileExistsError as erro:
        raise ConflitoDestino(f'Destino já ocupado: {alvo}') from erro


def _assinatura(arquivo: Path) -> tuple[int, int, int, int, int]:
    estado = arquivo.stat()
    return (estado.st_dev, estado.st_ino, estado.st_size,
            estado.st_mtime_ns, estado.st_ctime_ns)


def _hash(arquivo: Path) -> bytes:
    digest = hashlib.sha256()
    with arquivo.open('rb') as stream:
        for bloco in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(bloco)
    return digest.digest()


def _conferir_origem(origem: Path, estado: tuple[int, int, int, int, int], digest: bytes) -> None:
    if _assinatura(origem) != estado or _hash(origem) != digest or _assinatura(origem) != estado:
        raise OSError('Origem alterada durante a transferência; confira o arquivo antes de repetir.')


def _copiar_verificado(origem: Path, alvo: Path, *, remover_origem: bool = False) -> None:
    estado = _assinatura(origem)
    with tempfile.NamedTemporaryFile(dir=alvo.parent, prefix='.nunes-', suffix='.tmp', delete=False) as stream:
        temporario = Path(stream.name)
    try:
        _ = shutil.copy2(origem, temporario)
        with temporario.open('r+b') as stream:
            os.fsync(stream.fileno())
        digest = _hash(temporario)
        _conferir_origem(origem, estado, digest)
        _renomear_sem_substituir(temporario, alvo)
        try:
            if _hash(alvo) != digest:
                raise OSError('Conteúdo publicado diverge da cópia verificada.')
            if remover_origem:
                _conferir_origem(origem, estado, digest)
                origem.unlink()
        except OSError as erro:
            # Após publicar, nunca apagar o destino como tentativa de rollback.
            raise OSError(f'Destino publicado em {alvo}; origem não removida pela operação. '
                          + 'Confira as duas pastas antes de repetir.') from erro
    finally:
        temporario.unlink(missing_ok=True)


def _mover_sem_substituir(origem: Path, alvo: Path) -> None:
    try:
        _renomear_sem_substituir(origem, alvo)
    except OSError as erro:
        # Só a diferença de volumes permite copiar. Permissão, conflito e
        # indisponibilidade não autorizam outro método de movimentação.
        if erro.errno != errno.EXDEV:
            raise
        _copiar_verificado(origem, alvo, remover_origem=True)


def _registrar_conclusao(acao, origem, alvo, numero, relatar):
    # Só a identidade em hash contém os caminhos/nomes fiscais completos.
    identidade = json.dumps([acao, os.path.normcase(os.path.abspath(origem)),
                            os.path.normcase(os.path.abspath(alvo))], ensure_ascii=False)
    tipo = ('busca_' if acao == 'buscar' else 'move_') + alvo.suffix.lower().lstrip('.')
    if not registrar_evento('arquivo_transferido', identidade, numero, tipo=tipo):
        relatar('Arquivo concluído, mas a métrica não pôde ser preservada. '
                'O relatório pode ficar incompleto; não repita a operação por isso.')


def executar(acao, numeros, pastas, destino, *, cancelar=None, relatar=print):
    """Conclui o arquivo atual antes de atender a uma solicitação de parada."""
    if acao not in ('buscar', 'mover'):
        raise ValueError('Ação inválida.')
    resumo = dict(encontrados=0, concluidos=0, ignorados=0, erros=0, cancelado=False)
    achadas, visitados = set(), set()
    ano = str(datetime.now().year)

    def erro_caminho(erro):
        resumo['erros'] += 1
        relatar(f'Erro de acesso: {erro}')

    if acao == 'buscar':
        destino.mkdir(parents=True, exist_ok=True)
    for base in pastas:
        for raiz, dirs, arquivos in walk(base, onerror=erro_caminho, followlinks=False):
            if cancelar is not None and cancelar.is_set():
                resumo['cancelado'] = True
                break
            root = Path(raiz)
            if root == destino or root.is_relative_to(destino):
                dirs[:] = []
                continue
            if acao == 'buscar' and root == base:
                dirs[:] = [d for d in dirs if d == ano]
            elif acao == 'mover':
                dirs[:] = [d for d in dirs if not d.isdigit()]
            for arquivo in arquivos:
                if cancelar is not None and cancelar.is_set():
                    resumo['cancelado'] = True
                    break
                nome = arquivo.lower()
                if not nome.startswith('nfe'):
                    continue
                numero = pdf_number(nome) if nome.endswith('.pdf') else xml_number(nome) if nome.endswith('.xml') else None
                if numero not in numeros:
                    continue
                source = root / arquivo
                if source in visitados:
                    continue
                visitados.add(source)
                achadas.add(numero)
                resumo['encontrados'] += 1
                try:
                    if acao == 'buscar':
                        alvo = destino / arquivo
                    else:
                        data = datetime.fromtimestamp(source.stat().st_mtime)
                        alvo = root / str(data.year) / MONTHS[data.month] / arquivo
                    if alvo.exists():
                        resumo['ignorados'] += 1
                        relatar(f'Já existe no destino: {arquivo}')
                        continue
                    alvo.parent.mkdir(parents=True, exist_ok=True)
                    if acao == 'buscar':
                        _copiar_verificado(source, alvo)
                    else:
                        _mover_sem_substituir(source, alvo)
                    resumo['concluidos'] += 1
                    _registrar_conclusao(acao, source, alvo, numero, relatar)
                    relatar(f'{"Copiado" if acao == "buscar" else "Movido"}: {arquivo}')
                except ConflitoDestino:
                    resumo['ignorados'] += 1
                    relatar(f'Conflito: já existe no destino; origem preservada: {arquivo}')
                except OSError as erro:
                    resumo['erros'] += 1
                    relatar(f'Erro em {arquivo}: {erro}')
            if resumo['cancelado']:
                break
        if resumo['cancelado']:
            break
    resumo['nao_encontradas'] = sorted(numeros - achadas)
    return resumo


def console(acao):
    with Sincronizador():
        return _console(acao)


def _console(acao):
    from time import perf_counter
    inicio = perf_counter()
    arquivo = Path.cwd() / 'notas.txt'
    try:
        numeros, pastas, destino = preparar(arquivo.read_text(), caminhos_ambiente(), str(Path.cwd() / 'notas'))
        print('Aguarde... buscando notas' if acao == 'buscar' else 'Aguarde... movendo notas')
        resumo = executar(acao, numeros, pastas, destino)
        print(f"Concluídos: {resumo['concluidos']} · Erros: {resumo['erros']}")
        print(f'Terminado em: {perf_counter() - inicio:.2f} segundos')
    except (OSError, ValueError) as erro:
        print(erro)
    input('Pressione Enter para fechar...')
