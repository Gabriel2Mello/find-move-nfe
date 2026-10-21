from datetime import datetime
import http.client
import json
import os
from pathlib import Path
import tempfile
import shutil
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integracao_hub import IntegracaoLocal, consultar_instancia, solicitar_encerramento
from notas import Servidor
from operacoes import MONTHS, executar, pdf_number, preparar, xml_number


class TestOperacoes(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.raiz = Path(temp.name)
        self.pastas = [self.raiz / str(i) for i in range(4)]
        for p in self.pastas:
            p.mkdir()
        self.destino = self.raiz / 'copias'
        self.ano = str(datetime.now().year)

    def arquivo(self, relativo, pasta=0):
        arquivo = self.pastas[pasta] / relativo
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(b'nota sintetica')
        return arquivo

    def executar(self, acao, cancelar=None):
        return executar(acao, {'1234'}, self.pastas, self.destino,
                        cancelar=cancelar, relatar=lambda texto: None)

    def test_extracao_preserva_formatos_originais(self):
        self.assertEqual(pdf_number('NFe12341.pdf'), '1234')
        self.assertEqual(xml_number('NFe' + '0'*30 + '1234' + '0'*10 + '.xml'), '1234')
        self.assertIsNone(pdf_number('nfe1.pdf'))

    def test_busca_copia_raiz_e_ano_atual_sem_remover_origem(self):
        raiz = self.arquivo('NFe12341.pdf')
        atual = self.arquivo(self.ano + '/OUTUBRO/NFe12342.pdf')
        self.arquivo(str(int(self.ano)-1) + '/NFe12343.pdf')
        self.arquivo('outra/NFe12344.pdf')
        self.arquivo('NFe99991.pdf')
        xml = self.arquivo('NFe' + '0'*30 + '1234' + '0'*10 + '.xml', 2)
        r = self.executar('buscar')
        self.assertEqual(r['concluidos'], 3)
        for arquivo in (raiz, atual, xml):
            self.assertTrue(arquivo.exists())
            self.assertEqual((self.destino / arquivo.name).read_bytes(), arquivo.read_bytes())

    def test_mover_usa_modificacao_e_ignora_pastas_de_ano(self):
        arquivo = self.arquivo('pendentes/NFe12341.pdf')
        arquivado = self.arquivo('2020/JANEIRO/NFe12342.pdf')
        data = datetime.fromtimestamp(arquivo.stat().st_mtime)
        esperado = arquivo.parent / str(data.year) / MONTHS[data.month] / arquivo.name
        r = self.executar('mover')
        self.assertEqual(r['concluidos'], 1)
        self.assertFalse(arquivo.exists())
        self.assertTrue(esperado.exists())
        self.assertTrue(arquivado.exists())

    def test_destino_existente_preservado_nas_duas_acoes(self):
        arquivo = self.arquivo('NFe12341.pdf')
        self.destino.mkdir()
        (self.destino / arquivo.name).write_bytes(b'anterior')
        self.assertEqual(self.executar('buscar')['ignorados'], 1)
        self.assertEqual((self.destino / arquivo.name).read_bytes(), b'anterior')
        data = datetime.fromtimestamp(arquivo.stat().st_mtime)
        alvo = arquivo.parent / str(data.year) / MONTHS[data.month] / arquivo.name
        alvo.parent.mkdir(parents=True)
        alvo.write_bytes(b'arquivada')
        self.assertEqual(self.executar('mover')['ignorados'], 1)
        self.assertTrue(arquivo.exists())
        self.assertEqual(alvo.read_bytes(), b'arquivada')

    def test_validacao_antes_de_gravar(self):
        caminhos = [str(p) for p in self.pastas]
        for notas, pastas, destino in (('', caminhos, str(self.destino)),
                ('12345', caminhos, str(self.destino)), ('1234', caminhos[:3], str(self.destino)),
                ('1234', caminhos + [''], str(self.destino)),
                ('1234', [str(self.raiz / 'inexistente')]*4, str(self.destino)),
                ('1234', caminhos, str(self.raiz))):
            with self.assertRaises(ValueError):
                preparar(notas, pastas, destino)
        self.assertFalse(self.destino.exists())
        self.assertEqual(preparar('12, 1234;12\n', caminhos, str(self.destino))[0], {'0012', '1234'})

    def test_parada_preserva_originais(self):
        arquivo = self.arquivo('NFe12341.pdf')
        cancelar = Event()
        cancelar.set()
        r = self.executar('mover', cancelar)
        self.assertTrue(r['cancelado'])
        self.assertTrue(arquivo.exists())
        self.assertEqual(r['concluidos'], 0)

    def test_erro_de_copia_informado_e_nota_ausente(self):
        self.arquivo('NFe12341.pdf')
        with patch('operacoes.shutil.copy2', side_effect=OSError('teste')):
            r = self.executar('buscar')
        self.assertEqual(r['erros'], 1)
        self.assertEqual(r['concluidos'], 0)
        self.assertEqual(list(self.destino.iterdir()), [])
        self.assertEqual(self.executar('mover')['nao_encontradas'], [])
        self.assertEqual(executar('buscar', {'9999'}, self.pastas, self.destino,
                                 relatar=lambda texto: None)['nao_encontradas'], ['9999'])


class TestServidor(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch('notas.RAIZ', Path(temp)))
        # Recursos são código; preferências e notas operacionais ficam isoladas.
        from notas import RAIZ
        fonte = Path(__file__).resolve().parents[1]
        for pasta in ('web', 'icons'):
            shutil.copytree(fonte / pasta, RAIZ / pasta)
        self.servidor = Servidor()
        self.servidor.TOLERANCIA = .05
        Thread(target=self.servidor.serve_forever, kwargs={'poll_interval':.02}, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)

    def pedido(self, metodo, caminho, dados=None, headers=None):
        conexao = http.client.HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=3)
        self.addCleanup(conexao.close)
        conexao.request(metodo, caminho, body=json.dumps(dados) if dados is not None else None,
                       headers={'X-Notas-Token':self.servidor.token, 'Origin':self.servidor.origem,
                                'Content-Type':'application/json'} | (headers or {}))
        resposta = conexao.getresponse()
        return resposta.status, resposta.read()

    def aguardar(self, condicao):
        limite = time.monotonic() + 3
        while time.monotonic() < limite:
            if condicao():
                return
            time.sleep(.02)
        self.fail('Tempo esgotado.')

    def test_pagina_recursos_e_assinatura(self):
        codigo, html = self.pedido('GET', '/')
        self.assertEqual(codigo, 200)
        self.assertIn(self.servidor.token.encode(), html)
        self.assertIn(b'Gabriel2Mello', html)
        self.assertEqual(html.count(b'class="traco"'), 2)
        for recurso in ('/notas.css', '/notas.js', '/icone.svg', '/favicon.ico'):
            self.assertEqual(self.pedido('GET', recurso)[0], 200)
        self.assertEqual(self.pedido('GET', '/../../notas.py')[0], 404)

    def test_destino_persiste_apos_reabrir_servidor_sem_executar_operacao(self):
        destino = str(self.servidor.arquivo_preferencias.parent / 'cópias')
        self.assertEqual(self.pedido('POST', '/api/configuracao', {'destino': destino})[0], 200)
        self.assertEqual(json.loads(self.pedido('GET', '/api/configuracao')[1])['destino'], destino)
        novo = Servidor()
        self.addCleanup(novo.server_close)
        self.assertEqual(novo.configuracao()['destino'], destino)
        self.assertFalse(novo.ocupado)
        self.assertIsNone(novo.worker)

    def test_destino_padrao_e_configuracoes_de_origem_continuam_disponiveis(self):
        from operacoes import VARIAVEIS
        with patch.dict(os.environ, {v: 'origem sintética' for v in VARIAVEIS}):
            codigo, corpo = self.pedido('GET', '/api/configuracao')
        self.assertEqual(codigo, 200)
        dados = json.loads(corpo)
        self.assertEqual(dados['destino'], str(self.servidor.arquivo_preferencias.parent.parent / 'notas'))
        self.assertEqual(dados['caminhos'], ['origem sintética'] * 4)
        self.assertFalse(self.servidor.arquivo_preferencias.exists())

    def test_configuracao_recusa_invalida_e_preserva_anterior_na_falha_de_gravacao(self):
        self.assertEqual(self.pedido('POST', '/api/configuracao', {'destino': 'anterior'})[0], 200)
        for destino in ('', '  ', None, [], 'invalido\x00', 'x' * 4097):
            self.assertEqual(self.pedido('POST', '/api/configuracao', {'destino': destino})[0], 400)
        with patch.object(Path, 'replace', side_effect=OSError('falha sintética')):
            self.assertEqual(self.pedido('POST', '/api/configuracao', {'destino': 'novo'})[0], 400)
        self.assertEqual(self.servidor.configuracao()['destino'], 'anterior')
        self.assertEqual(list(self.servidor.arquivo_preferencias.parent.glob('*.tmp')), [])
        self.assertEqual(self.pedido('POST', '/api/configuracao', {'destino': 'indevido'},
                                     {'Origin': 'https://externo.example'})[0], 403)
        self.assertEqual(self.servidor.configuracao()['destino'], 'anterior')

    def test_envio_atrasado_ao_fechar_nao_substitui_preferencia_mais_nova(self):
        for revisao, destino in ((2, 'mais nova'), (1, 'atrasada')):
            self.assertEqual(self.pedido('POST', '/api/configuracao',
                {'destino': destino, 'pagina': 'aba', 'revisao': revisao})[0], 200)
        self.assertEqual(self.servidor.configuracao()['destino'], 'mais nova')

    def test_preferencias_corrompidas_sao_informadas_sem_apagar_arquivo(self):
        arquivo = self.servidor.arquivo_preferencias
        arquivo.parent.mkdir()
        for conteudo in ('{', '[]', '{"destino": null}'):
            arquivo.write_text(conteudo, encoding='utf-8')
            self.assertEqual(self.pedido('GET', '/api/configuracao')[0], 500)
            self.assertEqual(arquivo.read_text(encoding='utf-8'), conteudo)

    def test_versao_avanca_no_andamento_e_conclusao(self):
        inicial = self.servidor.situacao()['versao']
        entrou, liberar = Event(), Event()
        self.addCleanup(liberar.set)
        def lento(*args, **kwargs):
            entrou.set()
            liberar.wait(2)
            return {'concluidos': 0}
        with patch('notas.preparar', return_value=({'1234'}, [], Path('.'))), patch('notas.executar', lento):
            self.servidor.iniciar({'acao': 'mover'})
            self.assertTrue(entrou.wait(1))
            andamento = self.servidor.situacao()
            self.assertGreater(andamento['versao'], inicial)
            self.servidor.relatar('Teste de progresso')
            self.assertGreater(self.servidor.situacao()['versao'], andamento['versao'])
            liberar.set()
            self.servidor.worker.join(3)
        fim = self.servidor.situacao()
        self.assertFalse(fim['ocupado'])
        self.assertGreater(fim['versao'], andamento['versao'])
        self.assertEqual(self.servidor.situacao()['versao'], fim['versao'])

    def test_host_token_origin_e_tamanho(self):
        for headers in ({'Host':'externo.example'}, {'X-Notas-Token':'invalido'}, {'Origin':'https://externo.example'}, {'Content-Type':'text/plain'}):
            self.assertEqual(self.pedido('POST', '/api/iniciar', {}, headers)[0], 403)
        self.assertEqual(self.pedido('GET', '/api/estado', headers={'X-Notas-Token':'x'})[0], 403)
        self.assertEqual(self.pedido('POST', '/api/iniciar', {'notas':'x'*33000})[0], 400)

    def test_duas_abas_e_fechamento_da_ultima(self):
        a = self.servidor.abrir_pagina('a')
        self.servidor.abrir_pagina('b')
        self.servidor.fechar_pagina('a', a)
        self.servidor.sem_paginas_desde -= 10
        self.servidor.service_actions()
        self.assertFalse(self.servidor.encerrando)
        self.servidor.fechar_pagina('b')
        self.servidor.sem_paginas_desde -= 10
        self.servidor.service_actions()
        self.assertTrue(self.servidor.encerrando)

    def test_ocioso_envia_presenca_sem_republicar_estado(self):
        conexao = http.client.HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=3)
        self.addCleanup(conexao.close)
        conexao.request('GET', '/api/presenca', headers={
            'X-Notas-Token': self.servidor.token, 'X-Notas-Pagina': 'aba-ociosa'})
        resposta = conexao.getresponse()
        self.addCleanup(resposta.close)
        self.assertEqual(resposta.status, 200)
        self.assertTrue(resposta.readline().startswith(b'data: '))
        self.assertEqual(resposta.readline(), b'\n')
        self.assertEqual(resposta.readline(), b': presenca\n')
        self.servidor.fechar_pagina('aba-ociosa')

    def test_presenca_publica_conclusao_de_movimento_real_sem_nova_consulta(self):
        conexao = http.client.HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=3)
        self.addCleanup(conexao.close)
        conexao.request('GET', '/api/presenca', headers={
            'X-Notas-Token': self.servidor.token, 'X-Notas-Pagina': 'aba-movimento'})
        resposta = conexao.getresponse()
        self.addCleanup(resposta.close)
        inicial = json.loads(resposta.readline().decode()[6:])
        self.assertEqual(resposta.readline(), b'\n')
        with tempfile.TemporaryDirectory() as temp:
            pasta = Path(temp)
            origem = pasta / 'NFe12341.pdf'
            origem.write_bytes(b'movimento sintetico')
            codigo, _ = self.pedido('POST', '/api/iniciar', dict(
                acao='mover', notas='1234', caminhos=[str(pasta)]*4, destino=str(pasta/'copias')))
            self.assertEqual(codigo, 200)
            self.servidor.worker.join(2)
            self.assertFalse(self.servidor.ocupado)
            # Recebe a conclusão pela presença, inclusive se ela perder o estado intermediário.
            while True:
                linha = resposta.readline()
                self.assertTrue(linha)
                if linha.startswith(b'data: '):
                    fim = json.loads(linha[6:])
                    if fim['resultado'] is not None:
                        break
            self.assertGreater(fim['versao'], inicial['versao'])
            self.assertFalse(fim['ocupado'])
            self.assertEqual(fim['resultado']['concluidos'], 1)
            self.assertTrue(any('Movido:' in log for log in fim['logs']))
            self.assertFalse(origem.exists())
            self.assertEqual(len(list(pasta.rglob('NFe12341.pdf'))), 1)
        self.servidor.fechar_pagina('aba-movimento')

    def test_iniciar_via_http_copia_somente_arquivos_sinteticos(self):
        with tempfile.TemporaryDirectory() as temp:
            pasta = Path(temp)
            origem = pasta / 'NFe12341.pdf'
            origem.write_bytes(b'teste')
            codigo, _ = self.pedido('POST', '/api/iniciar', dict(
                acao='buscar', notas='1234', caminhos=[str(pasta)]*4, destino=str(pasta/'copias')))
            self.assertEqual(codigo, 200)
            self.aguardar(lambda: not self.servidor.ocupado)
            self.assertEqual(self.servidor.resultado['concluidos'], 1)
            self.assertTrue(origem.exists())
            self.assertTrue((pasta/'copias'/origem.name).exists())

    def test_encerrar_ocupado_aguarda_arquivo_e_bloqueia_nova_operacao(self):
        entrou, liberar = Event(), Event()
        self.addCleanup(liberar.set)
        def lento(*args, **kwargs):
            entrou.set()
            liberar.wait(3)
            return {'cancelado': kwargs['cancelar'].is_set()}
        with patch('notas.preparar', return_value=({'1234'}, [], Path('.'))), patch('notas.executar', lento):
            self.servidor.iniciar({'acao':'mover'})
            self.assertTrue(entrou.wait(2))
            self.servidor.encerrar()
            self.assertTrue(self.servidor.ocupado)
            self.assertTrue(self.servidor.cancelar.is_set())
            with self.assertRaises(ValueError):
                self.servidor.iniciar({'acao':'buscar'})
            liberar.set()
            self.servidor.worker.join(3)
            self.assertFalse(self.servidor.ocupado)
            self.assertTrue(self.servidor.resultado['cancelado'])

    def test_contrato_de_saude_e_encerramento_do_hub(self):
        with tempfile.TemporaryDirectory() as temp:
            with IntegracaoLocal('find-move-nfe', 'Busca e Move Notas', False, Path(temp), sem_navegador=True) as integracao:
                integracao.publicar(self.servidor, self.servidor.encerrar, self.servidor.situacao)
                self.assertTrue(consultar_instancia(integracao.registro)['respondendo'])
                self.assertEqual(consultar_instancia(integracao.registro)['paginas'], 0)
                solicitar_encerramento(integracao.registro)
                self.aguardar(lambda: self.servidor.encerrando)


if __name__ == '__main__':
    unittest.main()
