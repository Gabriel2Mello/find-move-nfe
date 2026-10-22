"""Contagem de arquivos sintéticos, sem notas nem métricas de produção."""
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

import metricas_nunes as metricas
from operacoes import MONTHS, executar


class TestMetricasFindMove(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch('sincronizar_estatisticas.ler_configuracao', return_value=None))
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.raiz = Path(self.temp)
        self.origem = self.raiz / 'origem'
        self.origem.mkdir()
        self.destino = self.raiz / 'copias'
        self.metricas = self.raiz / 'metricas'
        self.enterContext(patch.dict(os.environ, {'NUNES_METRICAS_DADOS': str(self.metricas)}))
        self.pdf = self.origem / 'NFe12341.pdf'
        self.xml = self.origem / ('NFe' + '0' * 30 + '1234' + '0' * 10 + '.xml')
        for arquivo in (self.pdf, self.xml):
            arquivo.write_bytes(b'arquivo fiscal sintetico')
        self.mensagens = []

    def rodar(self, acao, **campos):
        return executar(acao, {'1234'}, [self.origem], self.destino,
                        relatar=self.mensagens.append, **campos)

    def consultar(self):
        return metricas.consultar_metricas({'inicio': '2000-01-01', 'fim': '2099-12-31',
                                            'aplicacao': 'find-move-nfe'}, painel=True)

    def test_busca_e_movimentacao_somam_pdf_e_xml_no_mesmo_contador(self):
        self.assertEqual(self.rodar('buscar')['concluidos'], 2)
        self.assertEqual(self.rodar('mover')['concluidos'], 2)
        dados = self.consultar()
        self.assertEqual(dados['totais']['arquivo_transferido'], 4)
        self.assertEqual({e['tipo'] for e in dados['historico']},
                         {'busca_pdf', 'busca_xml', 'move_pdf', 'move_xml'})
        self.assertTrue(self.destino.joinpath(self.pdf.name).is_file())
        self.assertFalse(self.pdf.exists())
        csv = metricas.exportar_csv({'aplicacao': 'find-move-nfe'}).decode('utf-8-sig')
        self.assertIn('Arquivos buscados e movidos', csv)

    def test_existentes_e_nova_execucao_nao_duplicam_contagem(self):
        self.rodar('buscar')
        primeira = self.consultar()['historico']
        self.assertEqual(self.rodar('buscar')['ignorados'], 2)
        for arquivo in self.destino.iterdir():
            arquivo.unlink()
        self.assertEqual(self.rodar('buscar')['concluidos'], 2)
        self.assertEqual(self.consultar()['totais']['arquivo_transferido'], 2)
        self.assertEqual(self.consultar()['historico'], primeira)

    def test_novo_destino_representa_outra_entrega(self):
        self.rodar('buscar')
        self.destino = self.raiz / 'outras-copias'
        self.rodar('buscar')
        self.assertEqual(self.consultar()['totais']['arquivo_transferido'], 4)

    def test_falha_e_cancelamento_nao_contam(self):
        with patch('operacoes.shutil.copy2', side_effect=OSError('falha sintetica')):
            self.assertEqual(self.rodar('buscar')['erros'], 2)
        cancelar = Event()
        cancelar.set()
        self.assertTrue(self.rodar('mover', cancelar=cancelar)['cancelado'])
        self.assertEqual(self.consultar()['totais']['arquivo_transferido'], 0)

    def test_conflito_concorrente_nao_conta(self):
        renomear = os.rename
        def concorrente(origem, alvo):
            Path(alvo).write_bytes(b'outro escritor sintetico')
            return renomear(origem, alvo)
        with patch('operacoes.os.rename', side_effect=concorrente):
            self.assertEqual(self.rodar('buscar')['ignorados'], 2)
        self.assertEqual(self.consultar()['totais']['arquivo_transferido'], 0)

    def test_movimento_com_remocao_falha_nao_conta(self):
        import errno
        renomear, remover = os.rename, Path.unlink
        originais = (self.pdf, self.xml)
        def outro_volume(origem, alvo):
            if Path(origem) in originais:
                raise OSError(errno.EXDEV, 'outro volume sintetico')
            return renomear(origem, alvo)
        def bloqueado(caminho, *args, **kwargs):
            if caminho in originais:
                raise PermissionError('origem bloqueada')
            return remover(caminho, *args, **kwargs)
        with patch('operacoes.os.rename', side_effect=outro_volume), patch.object(Path, 'unlink', bloqueado):
            self.assertEqual(self.rodar('mover')['erros'], 2)
        self.assertTrue(self.pdf.exists())
        self.assertEqual(self.consultar()['totais']['arquivo_transferido'], 0)

    def test_fila_preserva_eventos_e_consolida_sem_duplicar(self):
        with patch('metricas_nunes._abrir', side_effect=sqlite3.OperationalError('ocupado')), self.assertLogs(level='WARNING'):
            self.assertEqual(self.rodar('buscar')['concluidos'], 2)
        eventos = list((self.metricas / 'recuperar').glob('*.json'))
        self.assertEqual(len(eventos), 2)
        for evento in eventos:
            bruto = json.loads(evento.read_text(encoding='utf-8'))
            self.assertEqual(bruto['evento'], 'arquivo_transferido')
        for arquivo in self.destino.iterdir():
            arquivo.unlink()
        self.rodar('buscar')
        self.assertEqual(self.consultar()['totais']['arquivo_transferido'], 2)
        self.assertEqual(list((self.metricas / 'recuperar').glob('*.json')), [])

    def test_falha_total_da_metrica_avisa_sem_repetir_ou_desfazer_transferencia(self):
        with patch('metricas_nunes._abrir', side_effect=sqlite3.OperationalError('ocupado')), \
             patch('metricas_nunes.pasta_metricas', side_effect=OSError('disco indisponivel')), \
             self.assertLogs(level='ERROR'):
            resumo = self.rodar('buscar')
        self.assertEqual((resumo['concluidos'], resumo['erros']), (2, 0))
        self.assertEqual(len(list(self.destino.iterdir())), 2)
        self.assertEqual(sum('métrica' in m.lower() for m in self.mensagens), 2)

    def test_referencia_nao_revela_chave_nome_completo_ou_pastas(self):
        self.rodar('buscar')
        banco = (self.metricas / 'resultados.sqlite3').read_bytes()
        for privado in (self.xml.stem, str(self.origem), str(self.destino)):
            self.assertNotIn(privado.encode(), banco)
        self.assertEqual({e['referencia'] for e in self.consultar()['historico']}, {'1234'})

    def test_movimento_existente_nao_conta(self):
        data = datetime.fromtimestamp(self.pdf.stat().st_mtime)
        pasta = self.origem / str(data.year) / MONTHS[data.month]
        pasta.mkdir(parents=True)
        for arquivo in (self.pdf, self.xml):
            (pasta / arquivo.name).write_bytes(b'preexistente sintetico')
        self.assertEqual(self.rodar('mover')['ignorados'], 2)
        self.assertEqual(self.consultar()['totais']['arquivo_transferido'], 0)


    def test_console_registra_os_mesmos_sucessos(self):
        from operacoes import VARIAVEIS, console
        from io import StringIO
        (self.raiz / 'notas.txt').write_text('1234', encoding='utf-8')
        with patch.object(Path, 'cwd', return_value=self.raiz), \
             patch.dict(os.environ, {v: str(self.origem) for v in VARIAVEIS}), \
             patch('builtins.input', return_value=''), patch('sys.stdout', StringIO()):
            console('buscar')
        self.assertEqual(self.consultar()['totais']['arquivo_transferido'], 2)

    def test_worker_web_registra_os_mesmos_sucessos(self):
        from notas import Servidor
        servidor = Servidor()
        self.addCleanup(servidor.server_close)
        servidor.iniciar({'acao': 'mover', 'notas': '1234', 'caminhos': [str(self.origem)] * 4,
                          'destino': str(self.destino)})
        self.assertIsNotNone(servidor.worker)
        servidor.worker.join(5)
        self.assertFalse(servidor.worker.is_alive())
        self.assertEqual(servidor.resultado['concluidos'], 2)
        self.assertEqual(self.consultar()['totais']['arquivo_transferido'], 2)
