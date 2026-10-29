"""Interface local única de busca e movimentação, integrada ao Hub Nunes."""
from collections import deque
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from threading import Event, RLock, Thread
import time

from integracao_hub import MedidorAbertura, atender_integracao, IntegracaoLocal, ConflitoAplicacao
from operacoes import caminhos_ambiente, executar, preparar, caminho_resumido
from limpeza_copias import preparar_limpeza, executar_limpeza, diretorio
from sincronizar_estatisticas import Sincronizador
from caminhos_desktop import pasta_dados, recursos, ler_tema, salvar_tema, vinculo_central

RAIZ = Path(__file__).resolve().parent


class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    TOLERANCIA = 5
    LIMITE_INICIAL = 120

    def __init__(self, *, modo_desktop=False):
        self.modo_desktop = modo_desktop
        self.desktop = None
        self.finalizado = Event()
        self.configurando = False
        self.sincronizador = None
        self.token = secrets.token_urlsafe(32)
        self.mutex = RLock()
        self.paginas = {}
        self.teve_pagina = False
        self.sem_paginas_desde = time.monotonic()
        self.encerrando = False
        self.ocupado = False
        self.cancelar = Event()
        self.worker = None
        self.logs = deque(maxlen=300)
        self.resultado = None
        self.andamento = None
        self.limpeza_pendente = None
        self.acao = ''
        self.versao = 0
        self.dados = pasta_dados(RAIZ)
        self.arquivo_preferencias = self.dados / '.local' / 'preferencias.json'
        self.revisoes_preferencias = {}
        super().__init__(('127.0.0.1', 0), Handler)
        self.origem = f'http://127.0.0.1:{self.server_port}'

    def situacao(self):
        with self.mutex:
            return dict(ocupado=self.ocupado, encerrando=self.encerrando, paginas=len(self.paginas),
                        versao=self.versao, acao=self.acao, logs=list(self.logs), resultado=self.resultado,
                        andamento=self.andamento.copy() if self.andamento is not None else None)

    def configuracao(self):
        with self.mutex:
            destino = str(self.dados / 'notas')
            try:
                dados = json.loads(self.arquivo_preferencias.read_text(encoding='utf-8'))
            except FileNotFoundError:
                pass
            else:
                if not isinstance(dados, dict):
                    raise ValueError('Preferências inválidas. Confira .local/preferencias.json.')
                destino = self.validar_destino(dados.get('destino'))
            # A interface recebe notas digitadas; notas.txt pertence ao console.
            return dict(notas='', caminhos=caminhos_ambiente(), destino=destino)

    @staticmethod
    def validar_destino(destino):
        if (not isinstance(destino, str) or not destino.strip() or len(destino) > 4096
                or any(c in destino for c in ('\x00', '\r', '\n'))):
            raise ValueError('Informe uma pasta válida para salvar as cópias.')
        return destino.strip()

    def salvar_configuracao(self, dados):
        destino = self.validar_destino(dados.get('destino'))
        pagina, revisao = dados.get('pagina', ''), dados.get('revisao', 0)
        if (not isinstance(pagina, str) or len(pagina) > 100 or not pagina.isascii()
                or type(revisao) is not int or revisao < 0):
            raise ValueError('Revisão de preferências inválida.')
        with self.mutex:
            # Um envio antigo pode chegar depois do keepalive ao fechar a aba.
            if self.ocupado and self.acao == 'limpar':
                raise ValueError('Aguarde a limpeza antes de alterar a pasta de cópias.')
            if pagina and revisao <= self.revisoes_preferencias.get(pagina, -1):
                return
            self.arquivo_preferencias.parent.mkdir(parents=True, exist_ok=True)
            temporario = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                        dir=self.arquivo_preferencias.parent, prefix='preferencias-', suffix='.tmp',
                        delete=False) as stream:
                    temporario = Path(stream.name)
                    json.dump({'destino': destino}, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporario.replace(self.arquivo_preferencias)
            finally:
                if temporario is not None:
                    temporario.unlink(missing_ok=True)
            if pagina:
                self.revisoes_preferencias[pagina] = revisao

    def relatar(self, texto):
        with self.mutex:
            self.logs.append(texto)
            self.versao += 1

    def atualizar_andamento(self, resumo):
        totais = {campo: resumo[campo] for campo in ('encontrados', 'concluidos', 'ignorados', 'erros')}
        with self.mutex:
            if totais != self.andamento:
                self.andamento = totais
                self.versao += 1

    def iniciar(self, dados):
        with self.mutex:
            if self.ocupado or self.encerrando or self.configurando:
                raise ValueError('Aguarde o término da operação atual.')
            acao = dados.get('acao')
            if acao not in ('buscar', 'mover'):
                raise ValueError('Ação inválida.')
            caminhos = dados.get('caminhos')
            if isinstance(caminhos, list):
                caminhos = caminhos.copy()
            self.limpeza_pendente = None
            self.ocupado = True
            self.cancelar.clear()
            self.logs.clear()
            self.resultado = None
            self.andamento = dict.fromkeys(('encontrados', 'concluidos', 'ignorados', 'erros'), 0)
            self.acao = acao
            self.versao += 1
            self.worker = Thread(target=self.trabalhar,
                args=(acao, dados.get('notas'), caminhos, dados.get('destino')))
            self.worker.start()

    def preparar_limpeza(self, caminhos):
        if (not isinstance(caminhos, list) or len(caminhos) != 4
                or any(not isinstance(c, str) or len(c) > 4096 or '\x00' in c for c in caminhos)):
            raise ValueError('Pastas de origem inválidas.')
        with self.mutex:
            if self.ocupado or self.encerrando or self.configurando:
                raise ValueError('Aguarde o término da operação atual.')
            self.configurando = True
            self.limpeza_pendente = None
        try:
            configurado = self.configuracao()['destino']
            plano = preparar_limpeza(configurado, caminhos + caminhos_ambiente(),
                                     [RAIZ, recursos(), self.dados, Path(sys.executable).parent, Path.home()])
            confirmacao = secrets.token_urlsafe(32)
            with self.mutex:
                if self.encerrando or self.configuracao()['destino'] != configurado:
                    raise ValueError('O destino ou o estado da aplicação mudou. Prepare a limpeza novamente.')
                self.limpeza_pendente = (confirmacao, configurado, plano)
            return dict(confirmacao=confirmacao, destino=str(plano.destino), quantidade=len(plano.arquivos))
        finally:
            with self.mutex:
                self.configurando = False

    def iniciar_limpeza(self, confirmacao):
        with self.mutex:
            pendente = self.limpeza_pendente
            if (not isinstance(confirmacao, str) or pendente is None
                    or not secrets.compare_digest(confirmacao.encode(), pendente[0].encode())):
                raise ValueError('Confirmação de limpeza inválida ou já utilizada.')
            self.limpeza_pendente = None
            _, configurado, plano = pendente
            if self.ocupado or self.encerrando or self.configurando:
                raise ValueError('Aguarde o término da operação atual.')
            self.conferir_destino_limpeza(configurado, plano)
            self.ocupado = True
            self.cancelar.clear()
            self.logs.clear()
            self.resultado = None
            self.andamento = None
            self.acao = 'limpar'
            self.versao += 1
            self.worker = Thread(target=self.trabalhar_limpeza, args=(configurado, plano))
            self.worker.start()

    def conferir_destino_limpeza(self, configurado, plano):
        if (self.configuracao()['destino'] != configurado
                or Path(configurado).resolve() != plano.destino
                or diretorio(plano.destino) != plano.identidade):
            raise ValueError('A pasta de cópias mudou; prepare a limpeza novamente.')

    def trabalhar_limpeza(self, configurado, plano):
        try:
            resultado = executar_limpeza(plano, cancelar=self.cancelar, relatar=self.relatar,
                conferir_configuracao=lambda: self.conferir_destino_limpeza(configurado, plano))
        except Exception as erro:
            self.relatar(f'Limpeza interrompida: {erro}')
            resultado = {'erro': str(erro)}
        resultado['limpeza_id'] = secrets.token_hex(16)
        with self.mutex:
            self.resultado = resultado
            self.ocupado = False
            self.versao += 1
            if self.encerrando:
                Thread(target=self.shutdown, daemon=True).start()

    def trabalhar(self, acao, notas, caminhos, destino):
        try:
            # Consultas a pastas de rede não podem reter a trava do estado/GUI.
            numeros, pastas, destino = preparar(notas, caminhos, destino)
            if self.cancelar.is_set():
                resultado = dict(encontrados=0, concluidos=0, ignorados=0, erros=0,
                                 cancelado=True, nao_encontradas=sorted(numeros))
            else:
                resultado = executar(acao, numeros, pastas, destino, cancelar=self.cancelar, relatar=self.relatar,
                                     formatar_caminho=lambda arquivo: caminho_resumido(arquivo, caminhos),
                                     progresso=self.atualizar_andamento)
        except Exception as erro:
            self.relatar(f'Não foi possível concluir: {erro}')
            resultado = {'erro': str(erro)}
        with self.mutex:
            self.resultado = resultado
            self.ocupado = False
            self.versao += 1
            if self.encerrando:
                Thread(target=self.shutdown, daemon=True).start()

    def abrir_pagina(self, pagina):
        with self.mutex:
            if self.encerrando:
                raise ValueError('A ferramenta está encerrando.')
            anterior = self.paginas.get(pagina)
            if anterior is not None:
                anterior.set()
            evento = Event()
            self.paginas[pagina] = evento
            self.teve_pagina = True
            return evento

    def fechar_pagina(self, pagina, evento=None):
        with self.mutex:
            atual = self.paginas.get(pagina)
            if atual is not None and (evento is None or atual is evento):
                self.paginas.pop(pagina)
                atual.set()
                if not self.paginas:
                    self.sem_paginas_desde = time.monotonic()

    def encerrar(self):
        with self.mutex:
            if self.encerrando:
                return
            self.encerrando = True
            self.versao += 1
            self.cancelar.set()
            for evento in self.paginas.values():
                evento.set()
            if not self.ocupado:
                Thread(target=self.shutdown, daemon=True).start()

    def service_actions(self):
        if self.modo_desktop:
            return
        with self.mutex:
            limite = self.TOLERANCIA if self.teve_pagina else self.LIMITE_INICIAL
            if not self.paginas and time.monotonic() - self.sem_paginas_desde >= limite:
                self.encerrar()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass

    def responder(self, codigo, corpo, tipo='application/json; charset=utf-8'):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(corpo)

    def json(self, codigo, dados):
        self.responder(codigo, json.dumps(dados, ensure_ascii=False).encode())

    def host_valido(self):
        return self.headers.get_all('Host') == [f'127.0.0.1:{self.server.server_port}']

    def autorizado(self):
        return self.host_valido() and self.headers.get_all('X-Notas-Token') == [self.server.token]

    def acompanhar(self):
        pagina = self.headers.get('X-Notas-Pagina', '')
        if not pagina or len(pagina) > 100 or not pagina.isascii():
            self.json(400, {'erro': 'Página inválida.'})
            return
        try:
            evento = self.server.abrir_pagina(pagina)
        except ValueError as erro:
            self.json(409, {'erro': str(erro)})
            return
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            anterior = ''
            while not evento.is_set() and not self.server.encerrando:
                atual = json.dumps(self.server.situacao(), ensure_ascii=False)
                # Ocioso: mantém a conexão para detectar a última aba, sem reenviar estado.
                mensagem = 'data: ' + atual + '\n\n' if atual != anterior else ': presenca\n\n'
                self.wfile.write(mensagem.encode())
                self.wfile.flush()
                anterior = atual
                if evento.wait(1):
                    break
        except (OSError, ValueError):
            pass
        finally:
            self.server.fechar_pagina(pagina, evento)

    def do_GET(self):
        from desktop_notas import atender_ativacao
        if atender_ativacao(self):
            return
        if atender_integracao(self):
            return
        if not self.host_valido():
            self.json(403, {'erro': 'Host não permitido.'})
        elif self.path.startswith('/api/'):
            if not self.autorizado():
                self.json(403, {'erro': 'Acesso não autorizado.'})
            elif self.path == '/api/estado':
                self.json(200, self.server.situacao())
            elif self.path == '/api/configuracao':
                try:
                    self.json(200, self.server.configuracao())
                except (OSError, ValueError) as erro:
                    self.json(500, {'erro': f'Não foi possível carregar as preferências: {erro}'})
            elif self.path == '/api/presenca':
                self.acompanhar()
            else:
                self.json(404, {'erro': 'Recurso não encontrado.'})
        elif self.path == '/':
            html = (recursos() / 'web/index.html').read_text(encoding='utf-8')
            html = (html.replace('{{TOKEN}}', self.server.token)
                    .replace('{{DESKTOP}}', '1' if self.server.modo_desktop else '0')
                    .replace('{{TEMA}}', ler_tema() if self.server.modo_desktop else ''))
            self.responder(200, html.encode(), 'text/html; charset=utf-8')
        else:
            arquivos = {'/notas.css': ('web/notas.css', 'text/css; charset=utf-8'),
                        '/notas.js': ('web/notas.js', 'text/javascript; charset=utf-8'),
                        '/nunes-tema.js': ('web/nunes-tema.js', 'text/javascript; charset=utf-8'),
                        '/nunes-assinatura.css': ('web/nunes-assinatura.css', 'text/css; charset=utf-8'),
                        '/icone.svg': ('icons/icone.svg', 'image/svg+xml'),
                        '/icons/tema-lua.svg': ('icons/tema-lua.svg', 'image/svg+xml'),
                        '/icons/tema-lua-sol.svg': ('icons/tema-lua-sol.svg', 'image/svg+xml'),
                        '/favicon.ico': ('icons/icone.ico', 'image/x-icon')}
            if self.path in arquivos:
                arquivo, tipo = arquivos[self.path]
                self.responder(200, (recursos() / arquivo).read_bytes(), tipo)
            else:
                self.json(404, {'erro': 'Recurso não encontrado.'})

    def do_POST(self):
        from desktop_notas import atender_ativacao
        if atender_ativacao(self):
            return
        if atender_integracao(self):
            return
        try:
            tamanhos = self.headers.get_all('Content-Length') or []
            if (len(tamanhos) != 1 or not tamanhos[0].isascii() or not tamanhos[0].isdigit()
                    or len(tamanhos[0]) > 5 or self.headers.get_all('Transfer-Encoding')):
                raise ValueError('Requisição inválida.')
            tamanho = int(tamanhos[0])
            if not 0 < tamanho <= 65536:
                raise ValueError('Requisição inválida.')
            corpo = self.rfile.read(tamanho)
            # Consumir o corpo limitado antes de responder evita um reset TCP no Windows.
            if (not self.autorizado() or self.headers.get_all('Origin') != [self.server.origem]
                    or self.headers.get_all('Content-Type') != ['application/json']):
                self.json(403, {'erro': 'Requisição não permitida. Reabra a ferramenta.'})
                return
            if tamanho > 32768:
                raise ValueError('Requisição inválida.')
            dados = json.loads(corpo)
            if not isinstance(dados, dict):
                raise ValueError('Requisição inválida.')
            if self.path == '/api/tema' and self.server.modo_desktop:
                if set(dados) != {'tema'}:
                    raise ValueError('Preferência de tema inválida.')
                salvar_tema(dados.get('tema'))
            elif self.path == '/api/escolher-pasta' and self.server.desktop is not None:
                if set(dados) != {'campo'} or not isinstance(dados['campo'], str):
                    raise ValueError('Pedido de pasta inválido.')
                self.json(200, self.server.desktop.escolher_pasta(dados['campo']))
                return
            elif self.path == '/api/abrir-pasta' and self.server.desktop is not None:
                if (set(dados) != {'campo', 'pasta'} or not isinstance(dados['campo'], str)
                        or not isinstance(dados['pasta'], str)):
                    raise ValueError('Pedido de abertura de pasta inválido.')
                self.server.desktop.abrir_pasta(dados['campo'], dados['pasta'])
            elif self.path == '/api/iniciar':
                self.server.iniciar(dados)
            elif self.path == '/api/preparar-limpeza':
                if set(dados) != {'caminhos'}:
                    raise ValueError('Pedido de limpeza inválido.')
                self.json(200, self.server.preparar_limpeza(dados['caminhos']))
                return
            elif self.path == '/api/limpar':
                if set(dados) != {'confirmacao'}:
                    raise ValueError('Pedido de limpeza inválido.')
                self.server.iniciar_limpeza(dados['confirmacao'])
            elif self.path == '/api/configuracao':
                self.server.salvar_configuracao(dados)
            elif self.path == '/api/cancelar':
                self.server.cancelar.set()
            elif self.path == '/api/fechar-pagina':
                pagina = dados.get('pagina')
                if not isinstance(pagina, str):
                    raise ValueError('Página inválida.')
                self.server.fechar_pagina(pagina)
            elif self.path == '/api/encerrar':
                self.json(200, {'solicitado': True})
                self.server.encerrar()
                return
            else:
                self.json(404, {'erro': 'Ação não encontrada.'})
                return
            self.json(200, {'ok': True})
        except (OSError, ValueError, TypeError) as erro:
            self.json(400, {'erro': str(erro)})


def main(integracao):
    with MedidorAbertura('find-move-nfe') as medidor, ExitStack() as recursos:
        servidor = None
        etapa = 'servidor_e_estado'
        try:
            with medidor.etapa('servidor_e_estado'):
                servidor = Servidor(modo_desktop=True)
            etapa = 'sincronizacao'
            with medidor.etapa('sincronizacao'):
                vinculo = vinculo_central()
                if vinculo is None or vinculo.is_file():
                    servidor.sincronizador = recursos.enter_context(
                        Sincronizador(relatar=servidor.relatar, arquivo=vinculo))
            etapa = 'publicacao'
            with medidor.etapa('publicacao'):
                integracao.registro['desktop'] = 1
                integracao.publicar(servidor, servidor.encerrar, servidor.situacao)
            etapa = 'janela_webview2'
            from desktop_notas import executar as executar_desktop
            executar_desktop(servidor, recursos.close)
        except KeyboardInterrupt:
            if servidor is not None:
                servidor.cancelar.set()
        except Exception as erro:
            try:
                integracao.registrar_falha(erro)
            except OSError:
                pass
            informar_falha_abertura(erro, etapa)
            return 1
        finally:
            if servidor is not None:
                servidor.encerrar()
                if servidor.worker is not None:
                    servidor.worker.join()
            recursos.close()
            if servidor is not None:
                if servidor.sincronizador is not None and servidor.sincronizador.worker is not None:
                    servidor.sincronizador.worker.join()
                servidor.server_close()
    return 0


def informar_falha(mensagem):
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, mensagem, 'Busca e Move Notas', 0x10)
    else:
        print(mensagem, file=sys.stderr)


def informar_falha_abertura(erro, etapa):
    from diagnostico_abertura import registrar
    try:
        caminho = registrar(erro, etapa)
    except Exception:
        caminho = None
    mensagem = f'Não foi possível abrir Busca e Move Notas.\nEtapa: {etapa}. Erro: {type(erro).__name__}.'
    if caminho:
        mensagem += f'\n\nEnvie o conteúdo deste diagnóstico ao suporte:\n{caminho}'
    informar_falha(mensagem)


def iniciar():
    import argparse
    from desktop_notas import APP_ID, NOME, ativar_existente
    import desktop_windows
    parser = argparse.ArgumentParser(description='Busca e Move Notas desktop')
    parser.add_argument('--nunes-sem-navegador', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--criar-atalho', type=Path)
    args = parser.parse_args()
    try:
        if args.criar_atalho:
            desktop_windows.criar_atalho(args.criar_atalho.resolve(),
                desktop_windows.comando_reabrir([], Path(__file__).resolve()), recursos() / 'icons/icone.ico',
                app_id=APP_ID, descricao='Buscar DANFEs e XMLs ou organizar notas por ano e mês')
            return 0
        limite = time.monotonic() + 15
        while True:
            integracao = IntegracaoLocal('find-move-nfe', NOME, False, sem_navegador=True)
            try:
                with integracao:
                    return main(integracao)
            except ConflitoAplicacao:
                if ativar_existente(integracao.caminho, espera=max(0, limite - time.monotonic())):
                    return 0
    except Exception as erro:
        informar_falha(str(erro) if isinstance(erro, RuntimeError) else
                       f'Não foi possível abrir Busca e Move Notas ({type(erro).__name__}). Confira a instalação.')
        return 1


if __name__ == '__main__':
    raise SystemExit(iniciar())
