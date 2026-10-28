"""Falhas transitórias de estatística ficam no log e continuam sendo tentadas."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

import sincronizar_estatisticas as sync
from contrato_estatisticas import assinatura
from metricas_nunes import registrar_evento
from sincronizar_estatisticas import Sincronizador


class TestAvisoCentral(unittest.TestCase):
    def test_falha_silenciosa_na_interface_preserva_retentativa_e_confirmacao(self):
        relatar = Mock()
        sincronizador = Sincronizador(relatar=relatar)
        sincronizador.cliente = Mock()
        sincronizador.cliente.sincronizar.side_effect = [
            OSError('Central sintética indisponível'),
            OSError('Central sintética indisponível'),
            {'confirmados_neste_ciclo': 2, 'pendentes': 0},
        ]
        with patch('sincronizar_estatisticas.logger') as logger:
            sincronizador._ciclo()
            sincronizador._ciclo()
            self.assertEqual(sincronizador.ultimo, 'pendente')
            relatar.assert_not_called()
            logger.warning.assert_called_once()
            sincronizador._ciclo()
        self.assertEqual(sincronizador.cliente.sincronizar.call_count, 3)
        self.assertEqual(sincronizador.ultimo, 'ok')
        relatar.assert_called_once_with('Estatísticas: 2 evento(s) confirmado(s) pela central.')

    def test_espera_ociosa_limitada_reinicia_apos_atividade_ou_falha_e_envia_ao_sair(self):
        sincronizador = Sincronizador(relatar=Mock())
        sincronizador.cliente = Mock()
        vazio = {'confirmados_neste_ciclo': 0, 'pendentes': 0}
        sincronizador.cliente.sincronizar.side_effect = [
            vazio, vazio, vazio, vazio,
            {'confirmados_neste_ciclo': 1, 'pendentes': 0},
            vazio, OSError('falha sintética'), vazio,
            {'confirmados_neste_ciclo': 1, 'pendentes': 0},  # Último envio ao encerrar.
        ]
        sincronizador.parar = Mock()
        sincronizador.parar.wait.side_effect = [False] * 7 + [True]
        with patch('sincronizar_estatisticas.logger'):
            sincronizador._executar()
        self.assertEqual([chamada.args[0] for chamada in sincronizador.parar.wait.call_args_list],
                         [10, 20, 30, 30, 5, 10, 5, 10])
        self.assertEqual(sincronizador.cliente.sincronizar.call_count, 9)
        self.assertEqual(sincronizador.relatar.call_count, 2)

    def test_pendencias_restantes_mantem_cadencia_base(self):
        sincronizador = Sincronizador(relatar=Mock())
        sincronizador.cliente = Mock()
        sincronizador.cliente.sincronizar.return_value = {'confirmados_neste_ciclo': 0, 'pendentes': 1}
        sincronizador.parar = Mock()
        sincronizador.parar.wait.return_value = True
        sincronizador._executar()
        sincronizador.parar.wait.assert_called_once_with(5)
        self.assertEqual(sincronizador.cliente.sincronizar.call_count, 2)

    def test_encerramento_interrompe_espera_ociosa_e_aguarda_ciclo_final(self):
        leu = Event()
        sincronizador = Sincronizador(intervalo=15)
        sincronizador.cliente = Mock()
        def sincronizar():
            leu.set()
            return {'confirmados_neste_ciclo': 0, 'pendentes': 0}
        sincronizador.cliente.sincronizar.side_effect = sincronizar
        sincronizador.worker = Thread(target=sincronizador._executar, daemon=True)
        sincronizador.worker.start()
        try:
            self.assertTrue(leu.wait(1))
        finally:
            sincronizador.__exit__(None, None, None)
        self.assertFalse(sincronizador.worker.is_alive())
        self.assertEqual(sincronizador.cliente.sincronizar.call_count, 2)


class TestHistoricoOcioso(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {'NUNES_METRICAS_DADOS': str(self.pasta)}))
        self.cliente = sync.Cliente({'protocolo': 1, 'central_id': 'c' * 32,
                                    'token': 's' * 32, 'url': 'http://127.0.0.1:1'}, self.pasta)
        self.enviados = []

        def confirmar(config, caminho, dados):
            self.enviados.extend(dados['eventos'])
            return {'protocolo': 1, 'central_id': config['central_id'],
                    'confirmados': [{'id': evento['id'], 'assinatura': assinatura(evento)}
                                   for evento in dados['eventos']]}

        self.http = self.enterContext(patch('sincronizar_estatisticas.requisitar', side_effect=confirmar))

    def registrar(self, identidade, dia=26):
        self.assertTrue(registrar_evento('arquivo_transferido', identidade, '1234', tipo='busca_pdf',
            ocorrido_em=datetime(2026, 10, dia, 15, tzinfo=timezone.utc)))

    def test_sem_novidades_le_um_snapshot_e_nao_envia_http(self):
        self.registrar('primeiro')
        self.cliente.sincronizar()
        self.http.reset_mock()
        with patch('sincronizar_estatisticas.ler_eventos', wraps=sync.ler_eventos) as ler:
            self.assertEqual(self.cliente.sincronizar(), {'confirmados_neste_ciclo': 0, 'pendentes': 0})
        ler.assert_called_once()
        self.http.assert_not_called()

    def test_proximo_ciclo_encontra_evento_novo_e_versao_anterior_do_mesmo_id(self):
        self.registrar('primeiro')
        self.cliente.sincronizar()
        self.assertEqual(self.cliente.sincronizar()['confirmados_neste_ciclo'], 0)
        self.registrar('segundo')
        self.assertEqual(self.cliente.sincronizar()['confirmados_neste_ciclo'], 1)
        # A fila pode trazer uma versão mais antiga de um ID já confirmado.
        antigo = {**self.enviados[0], 'ocorrido_em': '2026-10-25T15:00:00.000000+00:00', 'dia': '2026-10-25'}
        fila = self.pasta / 'recuperar'
        fila.mkdir()
        pendente = fila / 'sintetico.json'
        pendente.write_text(json.dumps(antigo), encoding='utf-8')
        self.assertEqual(self.cliente.sincronizar()['confirmados_neste_ciclo'], 1)
        self.assertEqual(self.enviados[-1], antigo)
        self.assertTrue(pendente.exists())
        self.assertEqual(self.cliente.sincronizar()['confirmados_neste_ciclo'], 0)

    def test_historico_invalido_nao_e_tratado_como_ocioso(self):
        fila = self.pasta / 'recuperar'
        fila.mkdir()
        arquivo = fila / 'invalido.json'
        arquivo.write_text('{', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.cliente.sincronizar()
        self.assertEqual(arquivo.read_text(encoding='utf-8'), '{')
        self.http.assert_not_called()

    def test_fila_consolidada_durante_snapshot_e_encontrada_no_proximo_ciclo(self):
        self.registrar('primeiro')
        self.cliente.sincronizar()
        antigo = {**self.enviados[0], 'ocorrido_em': '2026-10-25T15:00:00.000000+00:00', 'dia': '2026-10-25'}
        fila = self.pasta / 'recuperar'
        fila.mkdir()
        arquivo = fila / 'consolidacao-sintetica.json'
        arquivo.write_text(json.dumps(antigo), encoding='utf-8')
        ler_real = Path.read_text
        def consolidar(caminho, *args, **kwargs):
            if caminho == arquivo:
                self.registrar('primeiro', dia=25)
                arquivo.unlink()
                raise FileNotFoundError('Fila sintética já consolidada.')
            return ler_real(caminho, *args, **kwargs)
        with patch.object(Path, 'read_text', autospec=True, side_effect=consolidar):
            self.assertEqual(self.cliente.sincronizar()['confirmados_neste_ciclo'], 0)
        self.assertEqual(self.cliente.sincronizar()['confirmados_neste_ciclo'], 1)
        self.assertEqual(self.enviados[-1], antigo)
