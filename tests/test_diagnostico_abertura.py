"""Falhas de abertura simuladas; nenhuma transferência de arquivos de negócio."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import diagnostico_abertura
import notas


class TestDiagnosticoAbertura(unittest.TestCase):
    def test_adaptador_identifica_aplicacao_e_grava_no_perfil(self):
        with tempfile.TemporaryDirectory() as pasta, patch('sys.frozen', False, create=True), \
             patch.dict('os.environ', {'NUNES_NOTAS_DADOS': pasta}):
            caminho = diagnostico_abertura.registrar(RuntimeError('segredo-sintetico'), 'janela_webview2')
            dados = json.loads(caminho.read_text(encoding='utf-8'))
            self.assertEqual(caminho, Path(pasta) / 'logs/find-move-nfe-diagnostico.txt')
            self.assertEqual(dados['aplicacao'], 'find-move-nfe')
            self.assertIn('web/index.html', dados['recursos'])
            self.assertNotIn('segredo-sintetico', caminho.read_text(encoding='utf-8'))

    def test_falha_ao_criar_servidor_informa_etapa(self):
        with patch('notas.Servidor', side_effect=OSError('sintetico')), \
             patch('notas.informar_falha_abertura') as informar:
            self.assertEqual(notas.main(Mock()), 1)
        self.assertEqual(informar.call_args.args[1], 'servidor_e_estado')

    def test_falha_na_janela_preserva_encerramento_e_erro_original(self):
        servidor = Mock(worker=None, sincronizador=None)
        integracao = Mock(registro={})
        integracao.registrar_falha.side_effect = PermissionError()
        with patch('notas.Servidor', return_value=servidor), \
             patch('notas.vinculo_central', return_value=Mock(is_file=lambda: False)), \
             patch('desktop_notas.executar', side_effect=RuntimeError('sintetico')), \
             patch('notas.informar_falha_abertura') as informar:
            self.assertEqual(notas.main(integracao), 1)
        self.assertEqual(informar.call_args.args[1], 'janela_webview2')
        servidor.encerrar.assert_called_once()
        servidor.server_close.assert_called_once()

    def test_mensagem_indica_caminho_sem_erro_bruto(self):
        with patch('diagnostico_abertura.registrar', return_value=Path('C:/teste/find-move-nfe-diagnostico.txt')), \
             patch('notas.informar_falha') as informar:
            notas.informar_falha_abertura(RuntimeError('segredo-sintetico'), 'janela_webview2')
        mensagem = informar.call_args.args[0]
        self.assertIn('janela_webview2', mensagem)
        self.assertIn('find-move-nfe-diagnostico.txt', mensagem)
        self.assertNotIn('segredo-sintetico', mensagem)
