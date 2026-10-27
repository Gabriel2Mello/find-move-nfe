"""Falhas transitórias de estatística ficam no log e continuam sendo tentadas."""
import unittest
from unittest.mock import Mock, patch

from sincronizar_estatisticas import Sincronizador


class TestAvisoCentral(unittest.TestCase):
    def test_falha_silenciosa_na_interface_preserva_retentativa_e_confirmacao(self):
        relatar = Mock()
        sincronizador = Sincronizador(relatar=relatar)
        sincronizador.cliente = Mock()
        sincronizador.cliente.sincronizar.side_effect = [
            OSError('Central sintética indisponível'),
            OSError('Central sintética indisponível'),
            {'confirmados_neste_ciclo': 2},
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
