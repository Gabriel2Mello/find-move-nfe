"""Desktop com HTTP real e arquivos sintéticos; sem interface fiscal ou rede."""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Event, Thread
import time
import unittest
from unittest.mock import Mock, patch

import caminhos_desktop as caminhos
import desktop_notas as desktop
import desktop_windows
from integracao_hub import IntegracaoLocal, ConflitoAplicacao, solicitar_encerramento
from notas import Servidor


class TestDesktop(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {'NUNES_NOTAS_DADOS': str(self.pasta / 'dados')}))
        self.integracao = self.enterContext(IntegracaoLocal('find-move-nfe', desktop.NOME, False,
            self.pasta / 'presenca', sem_navegador=True))
        self.servidor = Servidor(modo_desktop=True)
        self.janela = desktop.Janela(self.servidor)
        self.janela.janela = Mock()
        self.servidor.desktop = self.janela
        self.integracao.registro['desktop'] = 1
        self.integracao.publicar(self.servidor, self.servidor.encerrar, self.servidor.situacao)
        self.thread = Thread(target=self.servidor.serve_forever, kwargs={'poll_interval': .01})
        self.thread.start()
        self.addCleanup(self.fechar)

    def fechar(self):
        self.servidor.encerrar()
        if self.servidor.worker:
            self.servidor.worker.join()
        self.servidor.shutdown()
        self.thread.join(3)
        self.servidor.server_close()
        self.assertFalse(self.thread.is_alive())

    def pedido(self, rota='/desktop/ativar', metodo='POST', corpo=b'{}', extras=None, pagina=False):
        headers = ({'X-Notas-Token': self.servidor.token, 'Origin': self.servidor.origem}
            if pagina else {'X-Nunes-Instancia': self.integracao.registro['token']})
        headers['Content-Type'] = 'application/json'
        c = http.client.HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=3)
        try:
            c.request(metodo, rota, body=corpo, headers=headers | (extras or {}))
            resposta = c.getresponse()
            return resposta.status, resposta.read()
        finally:
            c.close()

    def test_ativacao_preserva_estado_e_confirma_identidade(self):
        self.servidor.logs.append('Resultado sintético anterior')
        self.servidor.resultado = {'concluidos': 2}
        antes = self.servidor.situacao()
        codigo, corpo = self.pedido()
        self.assertEqual(codigo, 200)
        dados = json.loads(corpo)
        for chave in ('id', 'pid', 'instancia', 'protocolo'):
            self.assertEqual(dados[chave], self.integracao.registro[chave])
        self.assertEqual(dados['desktop'], 1)
        self.assertTrue(self.janela.ativar.is_set())
        self.assertEqual(self.servidor.situacao(), antes)

    def test_ativacao_exige_host_token_origin_metodo_e_comando_fixo(self):
        for extras, metodo, corpo, esperado in [
            ({'Host': 'localhost'}, 'POST', b'{}', 403),
            ({'Origin': 'null'}, 'POST', b'{}', 403),
            ({'X-Nunes-Instancia': 'invalido'}, 'POST', b'{}', 403),
            ({'X-Nunes-Instancia': self.servidor.token}, 'POST', b'{}', 403),
            ({}, 'GET', None, 405), ({}, 'POST', b'[]', 400),
            ({}, 'POST', b'{"comando":"executar"}', 400),
            ({'Content-Type': 'text/plain'}, 'POST', b'{}', 400)]:
            with self.subTest(extras=extras, metodo=metodo, corpo=corpo):
                self.assertEqual(self.pedido(extras=extras, metodo=metodo, corpo=corpo)[0], esperado)
                self.assertFalse(self.janela.ativar.is_set())

    def test_sem_janela_nao_ativa(self):
        self.servidor.desktop = None
        self.assertEqual(self.pedido()[0], 409)

    def test_queda_de_presenca_nao_encerra_e_nao_cria_paginas(self):
        evento = self.servidor.abrir_pagina('sintetica')
        self.servidor.fechar_pagina('sintetica', evento)
        self.servidor.sem_paginas_desde -= 1000
        self.servidor.service_actions()
        self.assertFalse(self.servidor.encerrando)
        self.assertEqual(self.servidor.situacao()['paginas'], 0)

    def test_exclusividade_nao_reserva_sisplan(self):
        with self.assertRaises(ConflitoAplicacao):
            with IntegracaoLocal('find-move-nfe', desktop.NOME, False, self.integracao.pasta):
                pass
        with IntegracaoLocal('sintetica-sisplan', 'Sintética', True, self.integracao.pasta):
            self.assertFalse(self.integracao.registro['sisplan'])

    def test_iniciador_confirma_saude_e_sessao(self):
        with patch('desktop_windows.permitir_foco') as foco:
            self.assertTrue(desktop.ativar_existente(self.integracao.caminho, espera=1))
        foco.assert_called_once_with(os.getpid())
        with patch('desktop_windows.mesma_sessao', return_value=False):
            with self.assertRaises(RuntimeError):
                desktop.ativar_existente(self.integracao.caminho, espera=1)

    def test_trava_liberada_volta_ao_iniciador(self):
        with patch('desktop_notas.trava_ocupada', return_value=False):
            self.assertFalse(desktop.ativar_existente(self.integracao.caminho))
        with patch('desktop_notas.trava_ocupada', side_effect=[True, False]), \
             patch('desktop_notas.consultar_instancia', return_value={'respondendo': True, 'encerrando': True}):
            self.assertFalse(desktop.ativar_existente(self.integracao.caminho, espera=1))

    def test_tema_persiste_e_exige_seguranca_da_pagina(self):
        self.assertEqual(caminhos.ler_tema(), '')
        self.assertEqual(self.pedido('/api/tema', corpo=b'{"tema":"escuro"}', pagina=True)[0], 200)
        self.assertEqual(caminhos.ler_tema(), 'escuro')
        html = self.pedido('/', 'GET', None)[1]
        self.assertIn(b'name="notas-desktop" content="1"', html)
        self.assertIn(b'name="notas-tema" content="escuro"', html)
        self.assertEqual(self.pedido('/api/tema', pagina=True, extras={'Origin': 'null'})[0], 403)
        self.assertEqual(self.pedido('/api/tema', pagina=True, corpo=b'{"tema":"outro"}')[0], 400)
        self.assertEqual(caminhos.ler_tema(), 'escuro')

    def test_pasta_http_nao_recebe_caminhos_nem_comandos(self):
        escolher = self.janela.escolher_pasta = Mock(return_value={'alterado': False})
        for corpo, extras, codigo in [(b'{"campo":"destino","pasta":"C:/indevido"}', {}, 400),
                (b'{"campo":"destino"}', {'Origin': 'null'}, 403),
                (b'{"campo":"destino"}', {'X-Notas-Token': 'errado'}, 403)]:
            self.assertEqual(self.pedido('/api/escolher-pasta', corpo=corpo, extras=extras, pagina=True)[0], codigo)
            escolher.assert_not_called()
        codigo, corpo = self.pedido('/api/escolher-pasta', corpo=b'{"campo":"destino"}', pagina=True)
        self.assertEqual((codigo, json.loads(corpo)), (200, {'alterado': False}))
        escolher.assert_called_once_with('destino')

    def test_pasta_nativa_destino_persiste_origem_temporaria_cancelar_preserva(self):
        destino = self.pasta / 'cópias'
        destino.mkdir()
        def selecionar(*a, **kw):
            self.assertTrue(self.servidor.configurando)
            with self.assertRaises(ValueError):
                self.servidor.iniciar({'acao': 'buscar'})
            with self.assertRaises(ValueError):
                self.janela.escolher_pasta('destino')
            return (str(destino),)
        self.janela.janela.create_file_dialog.side_effect = selecionar
        self.assertEqual(self.janela.escolher_pasta('destino')['pasta'], str(destino))
        self.assertEqual(self.servidor.configuracao()['destino'], str(destino))
        self.assertFalse(self.servidor.configurando)
        self.janela.janela.create_file_dialog.side_effect = None
        self.janela.janela.create_file_dialog.return_value = (str(self.pasta),)
        self.assertEqual(self.janela.escolher_pasta('caminho-0')['pasta'], str(self.pasta))
        self.assertEqual(self.servidor.configuracao()['destino'], str(destino))
        self.janela.janela.create_file_dialog.return_value = None
        self.assertEqual(self.janela.escolher_pasta('destino'), {'alterado': False})
        self.assertEqual(self.servidor.configuracao()['destino'], str(destino))
        with self.assertRaises(ValueError):
            self.janela.escolher_pasta('comando')

    def test_abrir_pasta_http_autenticado_aceita_somente_campo_e_pasta(self):
        pasta = str(self.pasta)
        corpo = json.dumps({'campo': 'destino', 'pasta': pasta}).encode()
        with patch('desktop_notas.os.startfile') as abrir:
            for extras in ({'Origin': 'null'}, {'X-Notas-Token': 'errado'}, {'Host': 'indevido'}):
                self.assertEqual(self.pedido('/api/abrir-pasta', corpo=corpo, extras=extras, pagina=True)[0], 403)
            for dados in ({'campo': 'destino'}, {'campo': 'destino', 'pasta': pasta, 'comando': 'open'},
                          {'campo': 'comando', 'pasta': pasta}, {'campo': 'destino', 'pasta': 1}):
                self.assertEqual(self.pedido('/api/abrir-pasta', corpo=json.dumps(dados).encode(), pagina=True)[0], 400)
            abrir.assert_not_called()
            for campo in ('destino', 'caminho-0', 'caminho-1', 'caminho-2', 'caminho-3'):
                codigo, resposta = self.pedido('/api/abrir-pasta', corpo=json.dumps({'campo': campo, 'pasta': pasta}).encode(), pagina=True)
                self.assertEqual((codigo, json.loads(resposta)), (200, {'ok': True}))
            self.assertEqual(abrir.call_count, 5)
            abrir.assert_called_with(str(self.pasta.resolve()), 'explore')
        self.assertIsNone(self.servidor.worker)
        self.assertFalse(self.servidor.arquivo_preferencias.exists())

    def test_abrir_pasta_recusa_arquivos_e_nao_cria_diretorios(self):
        arquivo = self.pasta / 'teste.cmd'
        arquivo.write_text('conteudo sintetico', encoding='utf-8')
        ausente = self.pasta / 'inexistente'
        with patch('desktop_notas.os.startfile') as abrir:
            for pasta in ('', ' \t', str(arquivo), str(ausente), '\x00', 'a\nb', 'a\rb', 'a' * 4097):
                with self.assertRaises(ValueError):
                    self.janela.abrir_pasta('destino', pasta)
                self.assertFalse(self.servidor.configurando)
            abrir.assert_not_called()
        self.assertFalse(ausente.exists())

    def test_abrir_pasta_preserva_trava_e_libera_apos_falha_do_explorador(self):
        with patch('desktop_notas.os.startfile') as abrir:
            for estado in ('ocupado', 'encerrando', 'configurando'):
                setattr(self.servidor, estado, True)
                try:
                    with self.assertRaises(ValueError):
                        self.janela.abrir_pasta('destino', str(self.pasta))
                finally:
                    setattr(self.servidor, estado, False)
            abrir.assert_not_called()
            def explorar(*args):
                self.assertTrue(self.servidor.configurando)
                with self.assertRaises(ValueError):
                    self.servidor.iniciar({'acao': 'buscar'})
                raise OSError('Explorador sintético indisponível')
            abrir.side_effect = explorar
            codigo, _ = self.pedido('/api/abrir-pasta', corpo=json.dumps({'campo': 'destino', 'pasta': str(self.pasta)}).encode(), pagina=True)
            self.assertEqual(codigo, 400)
            self.assertFalse(self.servidor.configurando)

    def test_abrir_pasta_recusa_encerramento_durante_validacao_do_caminho(self):
        def diretorio():
            self.servidor.encerrando = True
            return True
        with patch('desktop_notas.Path.is_dir', side_effect=diretorio), patch('desktop_notas.os.startfile') as abrir:
            try:
                with self.assertRaisesRegex(ValueError, 'encerrando'):
                    self.janela.abrir_pasta('destino', str(self.pasta))
                abrir.assert_not_called()
                self.assertFalse(self.servidor.configurando)
            finally:
                self.servidor.encerrando = False

    def test_x_ocupado_confirma_uma_vez_e_hub_nao_reconfirma(self):
        entrou, liberar = Event(), Event()
        def lento(*a, **kw):
            entrou.set()
            liberar.wait(3)
            return {'cancelado': kw['cancelar'].is_set()}
        with patch('notas.preparar', return_value=({'1234'}, [], self.pasta)), patch('notas.executar', lento):
            self.servidor.iniciar({'acao': 'buscar'})
            self.assertTrue(entrou.wait(1))
            janela = self.janela.janela
            try:
                janela.create_confirmation_dialog.return_value = False
                def confirmar(*args):
                    self.assertTrue(self.servidor.configurando)
                    return janela.create_confirmation_dialog.return_value
                janela.create_confirmation_dialog.side_effect = confirmar
                self.assertFalse(self.janela.fechar(janela))
                self.assertFalse(self.servidor.encerrando)
                janela.create_confirmation_dialog.return_value = True
                self.assertFalse(self.janela.fechar(janela))
                self.assertTrue(self.servidor.ocupado)
                self.assertTrue(self.servidor.cancelar.is_set())
                chamadas = janela.create_confirmation_dialog.call_count
                self.janela.fechar(janela)
                self.assertEqual(janela.create_confirmation_dialog.call_count, chamadas)
                solicitar_encerramento(self.integracao.registro)
                with self.assertRaises(ValueError):
                    self.servidor.iniciar({'acao': 'buscar'})
            finally:
                liberar.set()
                self.servidor.worker.join(3)
        self.assertTrue(self.servidor.resultado['cancelado'])


class TestCaminhos(unittest.TestCase):
    def test_fechamento_espera_a_fila_de_preferencias_sem_timeout_proprio(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'NUNES_NOTAS_DADOS': temp}):
            servidor = Servidor(modo_desktop=True)
            self.addCleanup(servidor.server_close)
            janela = desktop.Janela(servidor)
            nativa = Mock()
            entrou, liberou = Event(), Event()
            callbacks = []
            def avaliar(script, callback):
                callbacks.append(callback)
                entrou.set()
            nativa.evaluate_js.side_effect = avaliar
            espera_real = Event()
            evento = Mock()
            evento.set.side_effect = espera_real.set
            # Simula imediatamente o vencimento de qualquer prazo global.
            evento.wait.side_effect = lambda *args: False if args else espera_real.wait()
            with patch.object(servidor, 'encerrar') as encerrar, patch('desktop_notas.Event', return_value=evento):
                thread = Thread(target=janela.salvar_e_encerrar, args=(nativa,))
                thread.start()
                try:
                    self.assertTrue(entrou.wait(1))
                    self.assertTrue(thread.is_alive())
                    encerrar.assert_not_called()
                    liberou.set()
                    callbacks[0](False)
                finally:
                    if callbacks and not liberou.is_set():
                        callbacks[0](False)
                    thread.join(3)
                self.assertFalse(thread.is_alive())
                encerrar.assert_not_called()
            nativa.set_title.assert_called_with(desktop.NOME)

    def test_x_ocioso_salva_fora_da_thread_gui_e_pode_recusar_falha(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'NUNES_NOTAS_DADOS': temp}):
            servidor = Servidor(modo_desktop=True)
            self.addCleanup(servidor.server_close)
            janela = desktop.Janela(servidor)
            nativa = Mock()
            with patch('desktop_notas.Thread') as thread:
                self.assertFalse(janela.fechar(nativa))
            self.assertTrue(servidor.configurando)
            nativa.evaluate_js.assert_not_called()
            thread.assert_called_once()
            def falhou(script, callback):
                callback(False)
            nativa.evaluate_js.side_effect = falhou
            janela.salvar_e_encerrar(nativa)
            self.assertFalse(servidor.encerrando)
            self.assertFalse(servidor.configurando)
            nativa.evaluate_js.side_effect = lambda script, callback: callback(True)
            with patch.object(servidor, 'shutdown'):
                janela.salvar_e_encerrar(nativa)
            self.assertTrue(servidor.encerrando)

    def test_saida_aguarda_sincronizador_antes_de_liberar_janela(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'NUNES_NOTAS_DADOS': temp}):
            servidor = Servidor(modo_desktop=True)
            self.addCleanup(servidor.server_close)
            liberou = Event()
            servidor.sincronizador = Mock(worker=Mock())
            def finalizar():
                self.assertFalse(servidor.finalizado.is_set())
            def entrou_gui(janela):
                servidor.encerrar()
                self.assertTrue(servidor.finalizado.wait(3))
                servidor.sincronizador.worker.join.assert_called_once_with()
                liberou.set()
            with patch.object(desktop.Janela, 'executar', entrou_gui):
                desktop.executar(servidor, finalizar)
            self.assertTrue(liberou.is_set())
            self.assertIsNone(servidor.desktop)

    def test_pacote_recursos_dados_e_override_independentes(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'LOCALAPPDATA': temp}):
            with patch.dict(os.environ, {'NUNES_NOTAS_DADOS': ''}), patch.object(sys, 'frozen', True, create=True), \
                 patch.object(sys, '_MEIPASS', temp + '/somente-recursos', create=True):
                self.assertEqual(caminhos.pasta_dados(), Path(temp) / 'Nunes/BuscaMoveNotas')
                self.assertEqual(caminhos.recursos(), Path(temp) / 'somente-recursos')
            with patch.dict(os.environ, {'NUNES_NOTAS_DADOS': temp + '/isolado'}):
                self.assertEqual(caminhos.pasta_dados(), Path(temp) / 'isolado')
                self.assertEqual(caminhos.pasta_preferencias(), Path(temp) / 'isolado')

    def test_geometria_invalida_e_monitor_removido(self):
        with tempfile.TemporaryDirectory() as temp:
            arquivo = Path(temp) / 'desktop-janela.json'
            for conteudo in ('{', '[]', '{"formato":1,"retangulo":[1,2,0,0],"maximizada":false}'):
                arquivo.write_text(conteudo, encoding='utf-8')
                self.assertIsNone(desktop_windows.ler_geometria(temp))
        self.assertEqual(desktop_windows.ajustar_retangulo((-1800, 900, 3000, 2000),
            (0, 40, 1280, 680), (760, 540)), (0, 40, 1280, 680))


if __name__ == '__main__':
    unittest.main()
