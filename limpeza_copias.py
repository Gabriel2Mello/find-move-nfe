"""Limpeza confirmada da raiz das cópias, sem recursão nem métricas de entrega."""
from dataclasses import dataclass
from pathlib import Path
import stat


def identidade(arquivo):
    return (arquivo.st_dev, arquivo.st_ino, arquivo.st_mode,
            arquivo.st_size, arquivo.st_mtime_ns, arquivo.st_ctime_ns)


def diretorio(pasta):
    dados = pasta.lstat()
    if not stat.S_ISDIR(dados.st_mode) or getattr(dados, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError('A pasta de cópias foi substituída ou é um redirecionamento.')
    return dados.st_dev, dados.st_ino


@dataclass(frozen=True)
class PlanoLimpeza:
    destino: Path
    identidade: tuple
    arquivos: tuple


def preparar_limpeza(destino, origens, protegidas):
    pasta = Path(destino).resolve(strict=True)
    if pasta.parent == pasta:
        raise ValueError('A limpeza não pode usar a raiz de um disco ou compartilhamento.')
    if any(base.resolve().is_relative_to(pasta) for base in protegidas):
        raise ValueError('A pasta de cópias não pode conter a instalação ou os dados da aplicação.')
    if any(Path(origem.strip()).resolve().is_relative_to(pasta) for origem in origens if origem.strip()):
        raise ValueError('A pasta de cópias não pode ser uma origem nem conter uma pasta de origem.')
    identificador = diretorio(pasta)
    arquivos = []
    for caminho in sorted(pasta.iterdir()):
        dados = caminho.lstat()
        if stat.S_ISREG(dados.st_mode) and not getattr(dados, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            arquivos.append((caminho.name, identidade(dados)))
    if diretorio(pasta) != identificador:
        raise ValueError('A pasta mudou durante a preparação da limpeza. Tente novamente.')
    return PlanoLimpeza(pasta, identificador, tuple(arquivos))


def executar_limpeza(plano, *, cancelar, relatar, conferir_configuracao):
    resumo = dict(encontrados=len(plano.arquivos), concluidos=0, ignorados=0,
                  erros=0, nao_encontradas=[], cancelado=False)
    relatar(f'Limpeza da pasta de cópias: {plano.destino}')
    for nome, esperado in plano.arquivos:
        if cancelar.is_set():
            resumo['cancelado'] = True
            break
        # A confirmação autoriza somente o destino e os arquivos examinados.
        try:
            conferir_configuracao()
            if diretorio(plano.destino) != plano.identidade:
                raise ValueError('A pasta de cópias mudou.')
        except (OSError, ValueError) as erro:
            resumo['erros'] += 1
            relatar(f'Limpeza interrompida: {erro}')
            return resumo
        caminho = plano.destino / nome
        try:
            dados = caminho.lstat()
            if identidade(dados) != esperado:
                resumo['ignorados'] += 1
                relatar(f'Preservado por alteração após a confirmação: {nome}')
                continue
            caminho.unlink()
            resumo['concluidos'] += 1
            relatar(f'Excluído: {nome}')
        except FileNotFoundError:
            resumo['ignorados'] += 1
            relatar(f'Arquivo já ausente: {nome}')
        except OSError as erro:
            resumo['erros'] += 1
            relatar(f'Não foi possível excluir {nome}: {erro}')
    relatar('Limpeza interrompida.' if resumo['cancelado'] else 'Limpeza concluída. Subpastas e links preservados.')
    return resumo
