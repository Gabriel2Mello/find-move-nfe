"""Recursos imutáveis e dados do desktop; o console conserva seus contratos."""
import json
import os
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parent


def perfil():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'Nunes' / 'BuscaMoveNotas'


def pasta_dados(raiz=RAIZ):
    override = os.environ.get('NUNES_NOTAS_DADOS')
    if override:
        return Path(override).resolve()
    return perfil() if getattr(sys, 'frozen', False) else raiz


def pasta_preferencias():
    override = os.environ.get('NUNES_NOTAS_DADOS')
    return Path(override).resolve() if override else perfil()


def recursos():
    return Path(getattr(sys, '_MEIPASS', RAIZ))


def vinculo_central():
    if os.environ.get('NUNES_CENTRAL_CONFIG'):
        return None  # O contrato compartilhado aplica o override explícito.
    if getattr(sys, 'frozen', False) or os.environ.get('NUNES_NOTAS_DADOS'):
        # Arquivo ausente mantém sincronização desativada, sem ler a instalação.
        return pasta_dados() / '.local' / 'central.json'
    return None


def ler_tema():
    try:
        dados = json.loads((pasta_preferencias() / 'desktop-tema.json').read_text(encoding='utf-8'))
        if isinstance(dados, dict) and dados.get('tema') in ('claro', 'escuro'):
            return dados['tema']
    except (OSError, ValueError):
        pass
    # Deixa a interface recuperar a preferência legada válida antes do padrão.
    return ''


def salvar_tema(tema):
    from integracao_hub import gravar_registro
    if tema not in ('claro', 'escuro'):
        raise ValueError('Tema inválido.')
    pasta = pasta_preferencias()
    pasta.mkdir(parents=True, exist_ok=True)
    gravar_registro(pasta / 'desktop-tema.json', {'tema': tema})
