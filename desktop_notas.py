"""Janela Busca e Move Notas: HTTP local autenticado, sem API Python exposta à página."""
import json
import os
from pathlib import Path
import secrets
import time
from threading import Event, Thread
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

import desktop_windows
from integracao_hub import consultar_instancia, ler_registro, texto, trava_ocupada
from caminhos_desktop import pasta_preferencias, recursos

APP_ID = 'Nunes.BuscaMoveNotas.Desktop.1'
NOME = 'Busca e Move Notas'


class SemRedirecionamento(HTTPRedirectHandler):
  def redirect_request(self, req, fp, code, msg, headers, newurl):
    return None


def ativar_existente(caminho, espera=15):
  limite = time.monotonic() + espera
  while time.monotonic() < limite:
    if not trava_ocupada(caminho.with_suffix('.lock')):
      return False
    registro = ler_registro(caminho)
    saude = consultar_instancia(registro)
    if saude.get('respondendo') and not saude.get('encerrando'):
      if registro.get('id') != 'find-move-nfe':
        raise RuntimeError('O registro localizado não pertence ao Busca e Move Notas.')
      desktop_windows.permitir_foco(registro['pid'])
      pedido = Request(texto(registro['url']) + '/desktop/ativar', data=b'{}', method='POST',
                       headers={'X-Nunes-Instancia': texto(registro['token']), 'Content-Type': 'application/json'})
      try:
        with build_opener(ProxyHandler({}), SemRedirecionamento()).open(pedido, timeout=3) as resposta:
          dados = json.loads(resposta.read(4096))
      except HTTPError as erro:
        codigo = erro.code
        try:
          motivo = json.loads(erro.read(4096)) if codigo == 409 else {}
        finally:
          erro.close()
        if codigo == 409 and isinstance(motivo, dict) and motivo.get('estado') == 'encerrando':
          time.sleep(.1)
          continue
        raise RuntimeError('A instância existente recusou a ativação. Feche a versão anterior normalmente e reabra.') from erro
      except (OSError, HTTPException):
        time.sleep(.1)
        continue
      if (not isinstance(dados, dict) or dados.get('protocolo') != 1 or dados.get('id') != 'find-move-nfe'
          or dados.get('instancia') != registro.get('instancia') or dados.get('pid') != registro.get('pid')
          or dados.get('desktop') != 1):
        raise RuntimeError('Resposta de ativação de outra instância ou versão da Busca e Move Notas.')
      return True
    time.sleep(.1)
  raise RuntimeError('A Busca e Move Notas está iniciando, sem resposta ou encerrando. Aguarde e tente novamente.')


def atender_ativacao(handler):
  if handler.path != '/desktop/ativar':
    return False
  servidor = handler.server
  integracao = getattr(servidor, 'integracao_nunes', None)
  corpo = None
  tamanhos = handler.headers.get_all('Content-Length') or []
  if handler.command == 'POST' and len(tamanhos) == 1 and tamanhos[0].isascii() and tamanhos[0].isdigit():
    tamanho = int(tamanhos[0]) if len(tamanhos[0]) <= 4 else 4097
    if tamanho <= 4096:
      corpo = handler.rfile.read(tamanho)
  if (not handler.host_valido() or integracao is None or handler.headers.get_all('Origin') is not None
      or len(handler.headers.get_all('X-Nunes-Instancia') or []) != 1
      or not secrets.compare_digest(handler.headers.get('X-Nunes-Instancia', '').encode(),
                                    texto(integracao.registro['token']).encode())):
    handler.json(403, {'erro': 'Ativação não autorizada.'})
  elif handler.command != 'POST':
    handler.json(405, {'erro': 'Método não permitido.'})
  elif (handler.headers.get_all('Content-Length') != ['2']
        or handler.headers.get_all('Transfer-Encoding') is not None
        or handler.headers.get_all('Content-Type') != ['application/json'] or corpo != b'{}'):
    handler.json(400, {'erro': 'Pedido de ativação inválido.'})
  elif servidor.encerrando:
    handler.json(409, {'erro': 'A Busca e Move Notas está encerrando.', 'estado': 'encerrando'})
  elif servidor.desktop is None:
    handler.json(409, {'erro': 'Instância sem janela desktop.', 'estado': 'sem_desktop'})
  else:
    servidor.desktop.ativar.set()
    handler.json(200, {chave: integracao.registro[chave] for chave in
                      ('protocolo', 'id', 'instancia', 'pid')} | {'desktop': 1})
  return True


class Janela:
  def __init__(self, servidor):
    self.servidor = servidor
    self.ativar = Event()
    self.fechada = Event()
    self.erro = None
    self.liberar = False
    self.janela = None

  def escolher_pasta(self, campo):
    servidor = self.servidor
    if campo not in ('destino', 'caminho-0', 'caminho-1', 'caminho-2', 'caminho-3'):
      raise ValueError('Campo de pasta inválido.')
    with servidor.mutex:
      if servidor.encerrando or servidor.ocupado or servidor.configurando or self.janela is None:
        raise ValueError('Aguarde o fim da execução ou da escolha de pasta atual.')
      servidor.configurando = True
    try:
      import webview
      destino = self.janela.create_file_dialog(webview.FileDialog.FOLDER, directory=str(Path.home()))
      if not destino:
        return {'alterado': False}
      caminho = Path(destino[0] if isinstance(destino, (tuple, list)) else destino)
      if not caminho.is_absolute() or not caminho.is_dir():
        raise ValueError('Selecione uma pasta existente e acessível.')
      salvo = str(caminho.resolve())
      with servidor.mutex:
        if servidor.encerrando:
          raise ValueError('A Busca e Move Notas está encerrando; a pasta não foi alterada.')
        if campo == 'destino':
          servidor.salvar_configuracao({'destino': salvo})
      return {'alterado': True, 'campo': campo, 'pasta': salvo}
    finally:
      with servidor.mutex:
        servidor.configurando = False

  def abrir_pasta(self, campo, pasta):
    servidor = self.servidor
    if campo not in ('destino', 'caminho-0', 'caminho-1', 'caminho-2', 'caminho-3'):
      raise ValueError('Campo de pasta inválido.')
    if (not isinstance(pasta, str) or not pasta.strip() or len(pasta) > 4096
        or any(caractere in pasta for caractere in ('\x00', '\r', '\n'))):
      raise ValueError('Informe uma pasta válida para abrir.')
    with servidor.mutex:
      if servidor.encerrando or servidor.ocupado or servidor.configurando or self.janela is None:
        raise ValueError('Aguarde o fim da execução ou da escolha de pasta atual.')
      servidor.configurando = True
    try:
      caminho = Path(pasta.strip()).resolve()
      if not caminho.is_dir():
        raise ValueError('A pasta não existe ou está inacessível. Confira o caminho informado.')
      # O caminho é um valor literal; somente diretórios podem ser explorados.
      with servidor.mutex:
        if servidor.encerrando:
          raise ValueError('A Busca e Move Notas está encerrando; a pasta não foi aberta.')
        os.startfile(str(caminho), 'explore')
    finally:
      with servidor.mutex:
        servidor.configurando = False

  def fechar(self, janela):
    if self.liberar:
      desktop_windows.salvar_geometria(janela.native, pasta_preferencias())
      return True
    servidor = self.servidor
    # A mesma trava do início reserva a fronteira antes de confirmar/salvar.
    with servidor.mutex:
      if servidor.encerrando or servidor.configurando:
        return False
      ocupado = servidor.ocupado
      servidor.configurando = True
    if ocupado or not janela.events.loaded.is_set():
      try:
        if not ocupado or janela.create_confirmation_dialog(NOME,
            'Encerrar Busca e Move Notas? O arquivo em andamento será concluído antes da parada. Aguarde a janela fechar.'):
          servidor.encerrar()
      except Exception:
        servidor.relatar('Não foi possível confirmar o encerramento. Tente novamente pela janela ou pelo Hub.')
      finally:
        with servidor.mutex:
          servidor.configurando = False
    else:
      # O callback closing executa na thread WinForms. Não pode esperar JS ali.
      Thread(target=self.salvar_e_encerrar, args=(janela,), name='notas-fechamento').start()
    return False

  def salvar_e_encerrar(self, janela):
    terminou, resposta = Event(), []

    def salvo(valor):
      resposta.append(valor)
      terminou.set()

    try:
      janela.set_title(NOME + ' · Salvando preferências…')
      janela.evaluate_js('Promise.all([...destinosPendentes, salvamentoTema]).then(() => carregado ? salvarDestino() : true)',
                         callback=salvo)
      # Cada fetch tem seu prazo, mas a fila inteira pode levar mais tempo.
      # Não descartar a edição por um timeout externo à gravação.
      terminou.wait()
      if resposta == [False]:
        janela.set_title(NOME)
        return
      self.servidor.encerrar()
    except Exception:
      self.servidor.encerrar()
    finally:
      with self.servidor.mutex:
        self.servidor.configurando = False

  def aguardar(self, evento, limite=30):
    fim = time.monotonic() + limite
    while not self.fechada.is_set() and not self.servidor.encerrando:
      if evento.wait(.1):
        return True
      if time.monotonic() >= fim:
        raise RuntimeError('A janela ou a interface WebView2 não iniciou no prazo.')
    return False

  def executar(self):
    if os.name != 'nt':
      raise RuntimeError('O desktop da Busca e Move Notas requer Windows.')
    import webview
    desktop_windows.identidade_processo(APP_ID)
    webview.settings['ALLOW_DOWNLOADS'] = False
    webview.settings['ALLOW_FILE_URLS'] = False
    janela = webview.create_window(NOME, f'http://127.0.0.1:{self.servidor.server_port}',
                                  width=1080, height=780, min_size=(760, 540), text_select=True)
    self.janela = janela

    def restaurar():
      dados = desktop_windows.ler_geometria(pasta_preferencias())
      if dados:
        desktop_windows.restaurar_geometria(janela.native, dados)

    janela.events.before_show += restaurar
    janela.events.closing += lambda: self.fechar(janela)

    def fechou():
      self.fechada.set()
      self.servidor.encerrar()

    janela.events.closed += fechou

    def acompanhar():
      try:
        if not self.aguardar(janela.events.shown):
          self.servidor.finalizado.wait()
          self.liberar = True
          janela.destroy()
          return
        hwnd = janela.native.Handle.ToInt64()
        desktop_windows.propriedades_janela(hwnd,
          desktop_windows.comando_reabrir([], Path(__file__).with_name('notas.py')),
          recursos() / 'icons/icone.ico', app_id=APP_ID, nome=NOME)
        carregou = self.aguardar(janela.events.loaded)
        avisou = False
        while not self.fechada.wait(.1):
          if self.servidor.encerrando and not avisou:
            avisou = True
            janela.set_title('Busca e Move Notas · Encerrando — aguarde a operação atual')
            if carregou:
              janela.evaluate_js('pedir("/api/estado").then(receber).catch(() => {})')
          if self.servidor.finalizado.is_set():
            self.liberar = True
            janela.destroy()
            return
          if self.ativar.is_set():
            self.ativar.clear()
            desktop_windows.focalizar(hwnd)
      except Exception as erro:
        if not self.fechada.is_set():
          self.erro = erro
          self.servidor.encerrar()
          # Mesmo uma falha da GUI aguarda o executor alcançar a fronteira segura.
          self.servidor.finalizado.wait()
          self.liberar = True
          janela.destroy()

    webview.start(acompanhar, gui='edgechromium', debug=False, private_mode=True,
                  icon=str(recursos() / 'icons/icone.ico'))
    self.fechada.set()
    if self.erro:
      raise RuntimeError('Falha na janela desktop. Confira WebView2 e o diagnóstico local.') from self.erro


def executar(servidor, finalizar_sincronizador=lambda: None):
  janela = Janela(servidor)
  servidor.desktop = janela
  falhas = []

  def servir():
    try:
      servidor.serve_forever(poll_interval=.1)
    except Exception as erro:
      falhas.append(erro)
      servidor.encerrar()
    finally:
      if servidor.worker:
        servidor.worker.join()
      while servidor.configurando:
        time.sleep(.1)
      try:
        finalizar_sincronizador()
      except Exception as erro:
        falhas.append(erro)
      finally:
        if servidor.sincronizador is not None and servidor.sincronizador.worker is not None:
          servidor.sincronizador.worker.join()
        servidor.finalizado.set()

  thread = Thread(target=servir, name='notas-http', daemon=True)
  thread.start()
  try:
    janela.executar()
    if falhas:
      raise RuntimeError('O backend da Busca e Move Notas encerrou com falha.') from falhas[0]
  finally:
    servidor.encerrar()
    if servidor.worker:
      servidor.worker.join()
    servidor.shutdown()
    thread.join()
    servidor.desktop = None
