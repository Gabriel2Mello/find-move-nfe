"""Ensaio opt-in de fonte/pacote e Hub, com arquivos sintéticos isolados."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import HTTPError

from integracao_hub import ler_registro, consultar_instancia, solicitar_encerramento

RAIZ = Path(__file__).resolve().parents[1]


def esperar(condicao, limite=40):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        valor = condicao()
        if valor:
            return valor
        time.sleep(.1)
    raise RuntimeError('Condição de ensaio não confirmada no prazo; processos não serão terminados à força.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fonte', action='store_true')
    parser.add_argument('--hub', type=Path, help='Executável do Hub; padrão usa a fonte local.')
    parser.add_argument('--hub-desktop', action='store_true')
    parser.add_argument('--pausa-visual', action='store_true', help='Aguarda continuar.txt na pasta de ensaio.')
    args = parser.parse_args()
    pasta = Path(tempfile.mkdtemp(prefix='notas-desktop-sintetico-'))
    print(f'Ensaio: {pasta}', flush=True)
    dados = pasta / 'dados'
    (dados / '.local').mkdir(parents=True)
    origem, destino = pasta / 'ORIGEM-SINTETICA', pasta / 'COPIAS-SINTETICAS'
    origem.mkdir()
    destino.mkdir()
    (origem / 'NFe12341.pdf').write_bytes(b'DANFE sintetico sem documento fiscal')
    (dados / 'notas.txt').write_text('1234', encoding='utf-8')
    (dados / '.local/preferencias.json').write_text(json.dumps({'destino': str(destino)}), encoding='utf-8')
    (dados / 'desktop-tema.json').write_text('{"tema":"escuro"}', encoding='utf-8')
    (dados / 'desktop-janela.json').write_text(json.dumps({'formato': 1, 'retangulo': [70, 80, 1080, 780],
        'maximizada': False}), encoding='utf-8')
    ambiente = dict(os.environ, NUNES_NOTAS_DADOS=str(dados), NUNES_HUB_DADOS=str(pasta / 'presenca'),
        NUNES_METRICAS_DADOS=str(pasta / 'metricas'), NUNES_CENTRAL_CONFIG=str(pasta / 'central-ausente.json'),
        **{v: str(origem) for v in ('CAMINHO_DANFE_MATRIZ', 'CAMINHO_DANFE_FILIAL',
                                  'CAMINHO_XML_MATRIZ', 'CAMINHO_XML_FILIAL')})
    if args.fonte:
        instalacao, entrada = RAIZ, 'notas.py'
        comando = [sys.executable, str(RAIZ / entrada)]
        ambientes = ['.venv-desktop']
    else:
        instalacao = pasta / 'pacote-independente'
        shutil.copytree(RAIZ / 'dist/Busca e Move Notas', instalacao)
        entrada, ambientes = 'Busca e Move Notas.exe', []
        comando = [str(instalacao / entrada)]
        assert not (instalacao / 'notas.txt').exists()
        assert not (instalacao / '.local').exists()
    config = pasta / 'aplicacoes.json'
    config.write_text(json.dumps([{'id': 'find-move-nfe', 'nome': 'Busca e Move Notas', 'categoria': 'Teste',
        'descricao': 'SINTÉTICO', 'cor': '#0E7490', 'icone': 'notas.svg', 'sisplan': False,
        'modo': 'desktop', 'pasta': str(instalacao), 'entrada': entrada, 'ambientes': ambientes}]), encoding='utf-8')
    registro = pasta / 'presenca/find-move-nfe.json'
    hub_registro = pasta / 'presenca/nunes-hub.json'
    log = (pasta / 'processos.log').open('w', encoding='utf-8')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    processo = subprocess.Popen(comando, cwd=pasta, env=ambiente, stdout=log, stderr=log, creationflags=flags)
    atual, hub_proc = None, None
    opener = build_opener(ProxyHandler({}))

    def saude(caminho):
        r = ler_registro(caminho)
        return r if consultar_instancia(r).get('respondendo') else None

    def token(r, nome):
        with opener.open(r['url'], timeout=5) as resposta:
            html = resposta.read()
        return re.search(rb'name="' + nome.encode() + rb'-token" content="([^"]+)"', html).group(1).decode(), html

    def pedido(r, nome, chave, rota, dados=None):
        req = Request(r['url'] + rota, data=json.dumps(dados).encode() if dados is not None else None,
            headers={f'X-{nome}-Token': chave, 'Content-Type': 'application/json', 'Origin': r['url']})
        try:
            with opener.open(req, timeout=10) as resposta:
                return json.load(resposta)
        except HTTPError as erro:
            try:
                detalhe = json.load(erro)
            finally:
                erro.close()
            raise RuntimeError(f'{rota}: {detalhe}') from None

    resultado = {'fonte': args.fonte, 'pasta_ensaio': str(pasta), 'somente_arquivos_sinteticos': True}
    try:
        atual = esperar(lambda: saude(registro))
        esperar(lambda: consultar_instancia(atual).get('paginas', 0) > 0)
        chave, html = token(atual, 'notas')
        assert b'name="notas-desktop" content="1"' in html
        assert b'name="notas-tema" content="escuro"' in html
        config_inicial = pedido(atual, 'Notas', chave, '/api/configuracao')
        assert config_inicial['destino'] == str(destino)
        assert config_inicial['notas'] == '', 'Web/desktop não carregam notas.txt'
        pedido(atual, 'Notas', chave, '/api/iniciar', {'acao': 'buscar', 'notas': '1234',
            'destino': str(destino), 'caminhos': [str(origem)] * 4})
        esperar(lambda: pedido(atual, 'Notas', chave, '/api/estado')['resultado'])
        estado = pedido(atual, 'Notas', chave, '/api/estado')
        assert estado['resultado']['concluidos'] == 1
        assert (origem / 'NFe12341.pdf').read_bytes() == (destino / 'NFe12341.pdf').read_bytes()
        pedido(atual, 'Notas', chave, '/api/iniciar', {'acao': 'mover', 'notas': '1234',
            'destino': str(destino), 'caminhos': [str(origem)] * 4})
        esperar(lambda: pedido(atual, 'Notas', chave, '/api/estado')['resultado'])
        estado = pedido(atual, 'Notas', chave, '/api/estado')
        assert estado['resultado']['concluidos'] == 1
        assert not (origem / 'NFe12341.pdf').exists()
        assert len(list(origem.rglob('NFe12341.pdf'))) == 1
        resultado['copia_verificada_e_movimento_reais_sinteticos'] = True
        segundo = subprocess.run(comando, cwd=pasta, env=ambiente, capture_output=True, timeout=25, creationflags=flags)
        assert segundo.returncode == 0, segundo.stderr
        assert saude(registro)['instancia'] == atual['instancia']
        assert pedido(atual, 'Notas', chave, '/api/estado') == estado
        resultado['abertura_direta_e_segunda_abertura_sem_perder_resultado'] = True
        if args.pausa_visual:
            print('Janela pronta. Crie continuar.txt na pasta do ensaio para prosseguir.', flush=True)
            esperar(lambda: (pasta / 'continuar.txt').exists(), limite=1800)
        if consultar_instancia(atual).get('respondendo'):
            solicitar_encerramento(atual)
        assert processo.wait(25) == 0
        assert ler_registro(registro)['estado'] == 'encerrado'
        assert json.loads((dados / 'desktop-janela.json').read_text())['formato'] == 1
        resultado['geometria_salva'] = True
        hub_raiz = RAIZ.parent / 'nunes-hub'
        if args.hub:
            hub_instalacao = pasta / 'hub-independente'
            shutil.copytree(args.hub.resolve().parent, hub_instalacao)
            shutil.copyfile(config, hub_instalacao / 'aplicacoes.json')
            comando_hub = [str(hub_instalacao / args.hub.name)]
        else:
            comando_hub = [str(hub_raiz / '.venv/Scripts/python.exe'), str(hub_raiz / 'hub.py'),
                '--config', str(config)]  # NUNES_HUB_DADOS já isola a sessão.
        if not args.hub_desktop:
            comando_hub += ['--sem-navegador']
        hub_proc = subprocess.Popen(comando_hub, cwd=pasta, env=ambiente, stdout=log, stderr=log, creationflags=flags)
        hub = esperar(lambda: saude(hub_registro))
        if args.hub_desktop:
            esperar(lambda: consultar_instancia(hub).get('paginas', 0) > 0)
        resultado['janela_real_hub'] = args.hub_desktop
        hub_chave, _ = token(hub, 'hub')
        pedido(hub, 'Hub', hub_chave, '/api/abrir', {'id': 'find-move-nfe', 'abertura': 'ensaio-desktop'})
        atual = esperar(lambda: saude(registro))
        esperar(lambda: consultar_instancia(atual).get('paginas', 0) > 0)
        pedido(hub, 'Hub', hub_chave, '/api/mostrar-ferramenta', {'id': 'find-move-nfe'})
        resultado['abertura_e_ativacao_autenticadas_pelo_hub'] = True
        pedido(hub, 'Hub', hub_chave, '/api/encerrar', {})
        assert hub_proc.wait(20) == 0
        assert consultar_instancia(atual)['respondendo']
        resultado['fechar_hub_mantem_ferramenta'] = True
        assert (dados / 'notas.txt').read_text() == '1234'
        solicitar_encerramento(atual)
        esperar(lambda: ler_registro(registro).get('estado') == 'encerrado')
        resultado['encerramento_autenticado_e_notas_txt_preservado'] = True
        evidencia = RAIZ / '.local/qa-desktop'
        evidencia.mkdir(parents=True, exist_ok=True)
        (evidencia / ('fonte.json' if args.fonte else 'pacote.json')).write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(resultado, ensure_ascii=False), flush=True)
        return 0
    finally:
        for caminho in (registro, hub_registro):
            r = saude(caminho)
            if r:
                solicitar_encerramento(r)
        if processo.poll() is None:
            processo.wait(25)
        if hub_proc and hub_proc.poll() is None:
            hub_proc.wait(25)
        log.close()


if __name__ == '__main__':
    raise SystemExit(main())
