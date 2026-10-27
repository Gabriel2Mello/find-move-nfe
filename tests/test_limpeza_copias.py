"""Limpeza somente em pastas sintéticas temporárias, sem métricas de negócio."""
import http.client
import json
import os
from pathlib import Path
import stat
import tempfile
from threading import Event, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from limpeza_copias import preparar_limpeza, executar_limpeza, diretorio
from notas import Servidor
from operacoes import VARIAVEIS


class TestLimpezaArquivos(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.destino = self.raiz / 'copias'
        self.destino.mkdir()
        self.logs = []

    def plano(self):
        return preparar_limpeza(self.destino, [], [])

    def executar(self, plano, cancelar=None, conferir=lambda: None):
        return executar_limpeza(plano, cancelar=cancelar or Event(), relatar=self.logs.append,
                                conferir_configuracao=conferir)

    def test_exclui_todos_os_tipos_de_arquivo_sem_entrar_em_subpastas(self):
        for nome in ('nota.pdf', 'nota.xml', '.oculto', 'outro.txt'):
            (self.destino / nome).write_text('sintético', encoding='utf-8')
        subpasta = self.destino / 'subpasta'
        subpasta.mkdir()
        protegido = subpasta / 'preservado.pdf'
        protegido.write_bytes(b'preservar')
        with patch('operacoes.registrar_evento') as metricas:
            resumo = self.executar(self.plano())
            metricas.assert_not_called()
        self.assertEqual((resumo['encontrados'], resumo['concluidos'], resumo['erros']), (4, 4, 0))
        self.assertEqual(list(self.destino.iterdir()), [subpasta])
        self.assertEqual(protegido.read_bytes(), b'preservar')

    def test_vazia_nao_exclui_nada(self):
        resumo = self.executar(self.plano())
        self.assertEqual(resumo['encontrados'], 0)
        self.assertEqual(resumo['concluidos'], 0)
        self.assertTrue(self.destino.is_dir())

    def test_preserva_arquivos_novos_e_alterados_apos_preparacao(self):
        antigo = self.destino / 'antigo.pdf'
        antigo.write_bytes(b'antigo')
        plano = self.plano()
        antigo.write_bytes(b'conteudo alterado e maior')
        novo = self.destino / 'novo.pdf'
        novo.write_bytes(b'novo')
        resumo = self.executar(plano)
        self.assertEqual((resumo['concluidos'], resumo['ignorados']), (0, 1))
        self.assertEqual(antigo.read_bytes(), b'conteudo alterado e maior')
        self.assertEqual(novo.read_bytes(), b'novo')

    def test_links_e_pontos_de_redirecionamento_nao_entram_no_plano(self):
        arquivo = self.destino / 'link'
        arquivo.write_bytes(b'preservar')
        lstat = Path.lstat
        def simular_link(caminho):
            dados = lstat(caminho)
            if caminho == arquivo:
                valores = list(dados)
                valores[0] = stat.S_IFLNK | 0o777
                return os.stat_result(valores)
            return dados
        with patch('limpeza_copias.Path.lstat', autospec=True, side_effect=simular_link):
            self.assertEqual(self.plano().arquivos, ())
        def simular_redirecionamento(caminho):
            dados = lstat(caminho)
            if caminho == arquivo:
                return SimpleNamespace(st_mode=dados.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return dados
        with patch('limpeza_copias.Path.lstat', autospec=True, side_effect=simular_redirecionamento):
            self.assertEqual(self.plano().arquivos, ())
        self.assertTrue(arquivo.exists())

    def test_erro_de_permissao_preserva_arquivo_e_informa_falha(self):
        arquivo = self.destino / 'bloqueado.pdf'
        arquivo.write_bytes(b'preservar')
        plano = self.plano()
        with patch('limpeza_copias.Path.unlink', side_effect=PermissionError('sintético')):
            resumo = self.executar(plano)
        self.assertEqual((resumo['concluidos'], resumo['erros']), (0, 1))
        self.assertTrue(arquivo.exists())

    def test_cancelamento_preserva_arquivos_ainda_nao_excluidos(self):
        for nome in ('a.pdf', 'b.pdf'):
            (self.destino / nome).write_bytes(b'sintetico')
        parar = Event()
        def relatar(texto):
            if texto.startswith('Excluído:'):
                parar.set()
        resumo = executar_limpeza(self.plano(), cancelar=parar, relatar=relatar, conferir_configuracao=lambda: None)
        self.assertTrue(resumo['cancelado'])
        self.assertEqual(resumo['concluidos'], 1)
        self.assertTrue((self.destino / 'b.pdf').exists())

    def test_mudanca_de_destino_preserva_resumo_parcial_e_interrompe(self):
        for nome in ('a.pdf', 'b.pdf'):
            (self.destino / nome).write_bytes(b'sintetico')
        chamadas = []
        def conferir():
            chamadas.append(True)
            if len(chamadas) > 1:
                raise ValueError('destino mudou')
        resumo = self.executar(self.plano(), conferir=conferir)
        self.assertEqual((resumo['concluidos'], resumo['erros']), (1, 1))
        self.assertTrue((self.destino / 'b.pdf').exists())

    def test_recusa_raiz_origem_e_pastas_que_contenham_aplicacao(self):
        for destino, origens, protegidas in (
            (Path(self.destino.anchor), [], []),
            (self.destino, [str(self.destino)], []),
            (self.raiz, [str(self.destino)], []),
            (self.raiz, [], [self.destino]),
        ):
            with self.assertRaises(ValueError):
                preparar_limpeza(destino, origens, protegidas)


class TestLimpezaHTTP(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.destino = self.raiz / 'copias'
        self.destino.mkdir()
        self.origens = [str(self.raiz / ('origem-' + str(i))) for i in range(4)]
        self.enterContext(patch.dict(os.environ, dict(zip(VARIAVEIS, self.origens)) |
                                     {'NUNES_NOTAS_DADOS': str(self.raiz / 'dados')}))
        self.servidor = Servidor(modo_desktop=True)
        self.servidor.salvar_configuracao({'destino': str(self.destino)})
        self.thread = Thread(target=self.servidor.serve_forever, kwargs={'poll_interval': .01})
        self.thread.start()
        self.addCleanup(self.fechar)

    def fechar(self):
        if self.servidor.worker:
            self.servidor.worker.join(3)
            self.assertFalse(self.servidor.worker.is_alive())
        self.servidor.shutdown()
        self.thread.join(3)
        self.servidor.server_close()

    def pedido(self, rota, dados, extras=None):
        conexao = http.client.HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=3)
        try:
            conexao.request('POST', rota, body=json.dumps(dados), headers={
                'X-Notas-Token': self.servidor.token, 'Origin': self.servidor.origem,
                'Content-Type': 'application/json'} | (extras or {}))
            resposta = conexao.getresponse()
            return resposta.status, json.loads(resposta.read())
        finally:
            conexao.close()

    def preparar(self):
        codigo, plano = self.pedido('/api/preparar-limpeza', {'caminhos': self.origens})
        self.assertEqual(codigo, 200, plano)
        return plano

    def test_preparar_nao_apaga_e_executar_exige_confirmacao_de_uso_unico(self):
        arquivo = self.destino / 'nota.pdf'
        arquivo.write_bytes(b'sintetico')
        plano = self.preparar()
        self.assertEqual(plano['quantidade'], 1)
        self.assertTrue(arquivo.exists())
        self.assertEqual(self.pedido('/api/limpar', {'confirmacao': 'errada'})[0], 400)
        self.assertTrue(arquivo.exists())
        self.assertEqual(self.pedido('/api/limpar', {'confirmacao': plano['confirmacao']})[0], 200)
        self.servidor.worker.join(3)
        self.assertFalse(arquivo.exists())
        self.assertEqual(self.servidor.resultado['concluidos'], 1)
        self.assertTrue(self.servidor.resultado['limpeza_id'])
        self.assertEqual(self.pedido('/api/limpar', {'confirmacao': plano['confirmacao']})[0], 400)

    def test_http_recusa_origin_token_host_e_caminhos_de_exclusao_enviados_pela_pagina(self):
        for extras in ({'Origin': 'null'}, {'X-Notas-Token': 'errado'}, {'Host': 'indevido'}):
            self.assertEqual(self.pedido('/api/preparar-limpeza', {'caminhos': self.origens}, extras)[0], 403)
        self.assertEqual(self.pedido('/api/preparar-limpeza', {'caminhos': self.origens, 'destino': str(self.raiz)})[0], 400)
        self.assertEqual(self.pedido('/api/limpar', {'confirmacao': 'x', 'destino': str(self.raiz)})[0], 400)
        self.assertIsNone(self.servidor.worker)

    def test_destino_alterado_apos_preparacao_nao_e_limpo(self):
        arquivo = self.destino / 'nota.pdf'
        arquivo.write_bytes(b'preservar')
        plano = self.preparar()
        self.servidor.salvar_configuracao({'destino': str(self.raiz / 'outra')})
        self.assertEqual(self.pedido('/api/limpar', {'confirmacao': plano['confirmacao']})[0], 400)
        self.assertTrue(arquivo.exists())
        self.assertIsNone(self.servidor.worker)

    def test_diretorio_substituido_e_operacao_ocupada_bloqueiam_limpeza(self):
        plano = self.preparar()
        with patch('notas.diretorio', return_value=(0, 0)):
            self.assertEqual(self.pedido('/api/limpar', {'confirmacao': plano['confirmacao']})[0], 400)
        for estado in ('ocupado', 'configurando', 'encerrando'):
            setattr(self.servidor, estado, True)
            try:
                self.assertEqual(self.pedido('/api/preparar-limpeza', {'caminhos': self.origens})[0], 400)
            finally:
                setattr(self.servidor, estado, False)

    def test_destino_bloqueado_durante_limpeza_e_estado_crescente(self):
        self.servidor.ocupado = True
        self.servidor.acao = 'limpar'
        with self.assertRaises(ValueError):
            self.servidor.salvar_configuracao({'destino': str(self.raiz / 'outra')})
        self.servidor.ocupado = False
        plano = self.preparar()
        versao = self.servidor.versao
        self.servidor.iniciar_limpeza(plano['confirmacao'])
        self.servidor.worker.join(3)
        self.assertGreater(self.servidor.versao, versao)
        self.assertFalse(self.servidor.ocupado)

    def test_encerramento_cancela_apos_o_arquivo_em_andamento(self):
        for nome in ('a.pdf', 'b.pdf'):
            (self.destino / nome).write_bytes(b'sintetico')
        plano = self.preparar()
        entrou, liberar = Event(), Event()
        excluir = Path.unlink
        def lento(caminho, *args, **kwargs):
            entrou.set()
            if not liberar.wait(3):
                raise OSError('Ensaio sem liberação')
            return excluir(caminho, *args, **kwargs)
        with patch('limpeza_copias.Path.unlink', autospec=True, side_effect=lento):
            try:
                self.servidor.iniciar_limpeza(plano['confirmacao'])
                self.assertTrue(entrou.wait(1))
                self.servidor.encerrar()
            finally:
                liberar.set()
                self.servidor.worker.join(3)
        self.assertEqual(self.servidor.resultado['concluidos'], 1)
        self.assertTrue(self.servidor.resultado['cancelado'])
        self.assertTrue((self.destino / 'b.pdf').exists())
