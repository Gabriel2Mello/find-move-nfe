"""Regressões de integridade, somente com arquivos sintéticos temporários."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import errno
import os
from pathlib import Path
from io import StringIO
import shutil
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from operacoes import MONTHS, VARIAVEIS, console, executar


class TestTransferencias(unittest.TestCase):
    def __init__(self, methodName='runTest'):
        super().__init__(methodName)
        self.raiz = Path()
        self.contador = 0
        self.rename = os.rename
        self.copy2 = shutil.copy2
        self.unlink = Path.unlink

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.raiz = Path(temp.name)

    def caso(self, acao):
        self.contador += 1
        pasta = self.raiz / str(self.contador)
        pasta.mkdir()
        origem = pasta / 'NFe12341.pdf'
        origem.write_bytes(b'nota sintetica original')
        destino = pasta / 'copias'
        data = datetime.fromtimestamp(origem.stat().st_mtime)
        mes = MONTHS[data.month]
        assert mes is not None
        alvo = (destino if acao == 'buscar' else pasta / str(data.year) / mes) / origem.name
        mensagens = []
        def rodar():
            return executar(acao, {'1234'}, [pasta], destino, relatar=mensagens.append)
        return origem, alvo, mensagens, rodar

    def outro_volume(self, origem):
        def renomear(source, target, *args, **kwargs):
            if Path(source) == origem:
                raise OSError(errno.EXDEV, 'outro volume simulado')
            return self.rename(source, target, *args, **kwargs)
        return renomear

    def test_destino_criado_entre_verificacao_e_publicacao(self):
        for acao in ('buscar', 'mover'):
            with self.subTest(acao=acao):
                origem, alvo, mensagens, rodar = self.caso(acao)
                def concorrente(source, target, *args, **kwargs):
                    if Path(target) == alvo:
                        alvo.write_bytes(b'arquivo de outro escritor')
                    return self.rename(source, target, *args, **kwargs)
                with patch('os.rename', side_effect=concorrente):
                    resumo = rodar()
                self.assertEqual(alvo.read_bytes(), b'arquivo de outro escritor')
                self.assertEqual(origem.read_bytes(), b'nota sintetica original')
                self.assertEqual((resumo['concluidos'], resumo['ignorados'], resumo['erros']), (0, 1, 0))
                self.assertTrue(any('Conflito' in m for m in mensagens))
                self.assertEqual(list(alvo.parent.glob('.nunes-*.tmp')), [])

    def test_erro_de_permissao_nao_vira_copia_com_remocao(self):
        origem, alvo, _, rodar = self.caso('mover')
        with patch('os.rename', side_effect=PermissionError('acesso negado')), patch('shutil.copy2', wraps=self.copy2) as copiar:
            resumo = rodar()
        self.assertEqual(resumo['erros'], 1)
        self.assertEqual(resumo['concluidos'], 0)
        self.assertTrue(origem.exists())
        self.assertFalse(alvo.exists())
        copiar.assert_not_called()

    def test_outro_volume_confirma_copia_e_preserva_modificacao(self):
        origem, alvo, _, rodar = self.caso('mover')
        conteudo, modificacao = origem.read_bytes(), origem.stat().st_mtime_ns
        def remover(path, *args, **kwargs):
            if path == origem:
                self.assertEqual(alvo.read_bytes(), conteudo)
            return self.unlink(path, *args, **kwargs)
        with patch('os.rename', side_effect=self.outro_volume(origem)), patch.object(Path, 'unlink', remover):
            resumo = rodar()
        self.assertEqual(resumo['concluidos'], 1)
        self.assertFalse(origem.exists())
        self.assertEqual(alvo.read_bytes(), conteudo)
        self.assertEqual(alvo.stat().st_mtime_ns, modificacao)

    def test_outro_volume_conflito_preserva_origem_e_destino(self):
        origem, alvo, _, rodar = self.caso('mover')
        entre_volumes = self.outro_volume(origem)
        def concorrente(source, target, *args, **kwargs):
            if Path(source) != origem and Path(target) == alvo:
                alvo.write_bytes(b'concorrente')
            return entre_volumes(source, target, *args, **kwargs)
        with patch('os.rename', side_effect=concorrente):
            resumo = rodar()
        self.assertEqual((resumo['concluidos'], resumo['ignorados']), (0, 1))
        self.assertEqual(origem.read_bytes(), b'nota sintetica original')
        self.assertEqual(alvo.read_bytes(), b'concorrente')

    def test_copia_parcial_ou_divergente_nao_publica_nem_remove(self):
        for acao in ('buscar', 'mover'):
            for falhar in (False, True):
                with self.subTest(acao=acao, falhar=falhar):
                    origem, alvo, _, rodar = self.caso(acao)
                    def copiar(source, target):
                        Path(target).write_bytes(b'incompleto')
                        if falhar:
                            raise OSError('falha durante escrita')
                    with patch('os.rename', side_effect=self.outro_volume(origem)), patch('shutil.copy2', side_effect=copiar):
                        resumo = rodar()
                    self.assertEqual((resumo['erros'], resumo['concluidos']), (1, 0))
                    self.assertEqual(origem.read_bytes(), b'nota sintetica original')
                    self.assertFalse(alvo.exists())
                    self.assertEqual(list(alvo.parent.glob('.nunes-*.tmp')), [])

    def test_falha_de_sincronizacao_preserva_origem(self):
        for acao in ('buscar', 'mover'):
            with self.subTest(acao=acao):
                origem, alvo, _, rodar = self.caso(acao)
                with patch('os.rename', side_effect=self.outro_volume(origem)), patch('os.fsync', side_effect=OSError('disco indisponivel')):
                    resumo = rodar()
                self.assertEqual((resumo['erros'], resumo['concluidos']), (1, 0))
                self.assertTrue(origem.exists())
                self.assertFalse(alvo.exists())

    def test_origem_modificada_durante_copia_exige_conferencia(self):
        origem, alvo, _, rodar = self.caso('mover')
        def copiar(source, target):
            self.copy2(source, target)
            origem.write_bytes(b'origem alterada por outro processo')
        with patch('os.rename', side_effect=self.outro_volume(origem)), patch('shutil.copy2', side_effect=copiar):
            resumo = rodar()
        self.assertEqual((resumo['erros'], resumo['concluidos']), (1, 0))
        self.assertEqual(origem.read_bytes(), b'origem alterada por outro processo')
        self.assertFalse(alvo.exists())

    def test_falha_de_publicacao_preserva_origem(self):
        origem, alvo, _, rodar = self.caso('mover')
        def falhar(source, target, *args, **kwargs):
            if Path(source) == origem:
                raise OSError(errno.EXDEV, 'outro volume')
            raise PermissionError('destino indisponivel')
        with patch('os.rename', side_effect=falhar):
            resumo = rodar()
        self.assertEqual((resumo['erros'], resumo['concluidos']), (1, 0))
        self.assertTrue(origem.exists())
        self.assertFalse(alvo.exists())

    def test_falha_ao_remover_origem_preserva_ambas_sem_sucesso(self):
        origem, alvo, mensagens, rodar = self.caso('mover')
        def remover(path, *args, **kwargs):
            if path == origem:
                raise PermissionError('origem bloqueada')
            return self.unlink(path, *args, **kwargs)
        with patch('os.rename', side_effect=self.outro_volume(origem)), patch.object(Path, 'unlink', remover):
            resumo = rodar()
        self.assertEqual((resumo['erros'], resumo['concluidos']), (1, 0))
        self.assertEqual(origem.read_bytes(), alvo.read_bytes())
        self.assertTrue(any('confira' in m.lower() and str(alvo) in m for m in mensagens))
        self.assertEqual(rodar()['ignorados'], 1)
        self.assertTrue(origem.exists())

    def test_destino_alterado_apos_publicar_preserva_origem(self):
        origem, alvo, _, rodar = self.caso('mover')
        entre_volumes = self.outro_volume(origem)
        def adulterar(source, target, *args, **kwargs):
            resultado = entre_volumes(source, target, *args, **kwargs)
            if Path(target) == alvo:
                alvo.write_bytes(b'alteracao externa apos publicacao')
            return resultado
        with patch('os.rename', side_effect=adulterar):
            resumo = rodar()
        self.assertEqual((resumo['erros'], resumo['concluidos']), (1, 0))
        self.assertEqual(origem.read_bytes(), b'nota sintetica original')
        self.assertEqual(alvo.read_bytes(), b'alteracao externa apos publicacao')

    def test_origem_substituida_apos_publicar_nao_e_removida(self):
        origem, alvo, _, rodar = self.caso('mover')
        entre_volumes = self.outro_volume(origem)
        def substituir(source, target, *args, **kwargs):
            resultado = entre_volumes(source, target, *args, **kwargs)
            if Path(target) == alvo:
                origem.unlink()
                origem.write_bytes(b'outra nota')
            return resultado
        with patch('os.rename', side_effect=substituir):
            resumo = rodar()
        self.assertEqual((resumo['erros'], resumo['concluidos']), (1, 0))
        self.assertEqual(origem.read_bytes(), b'outra nota')
        self.assertEqual(alvo.read_bytes(), b'nota sintetica original')

    def test_dois_escritores_publicam_uma_unica_copia(self):
        origens = [self.caso('buscar')[0] for _ in range(2)]
        origens[1].write_bytes(b'segunda nota sintetica')
        destino = self.raiz / 'destino compartilhado'
        barreira = Barrier(2)
        def simultaneo(source, target, *args, **kwargs):
            if Path(target).parent == destino:
                barreira.wait(timeout=5)
            return self.rename(source, target, *args, **kwargs)
        def rodar(origem):
            return executar('buscar', {'1234'}, [origem.parent], destino, relatar=lambda _: None)
        with patch('os.rename', side_effect=simultaneo), ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(rodar, origens))
        self.assertEqual(sum(r['concluidos'] for r in resultados), 1)
        self.assertEqual(sum(r['ignorados'] for r in resultados), 1)
        self.assertEqual(sum(r['erros'] for r in resultados), 0)
        self.assertIn((destino / origens[0].name).read_bytes(), [p.read_bytes() for p in origens])
        self.assertEqual(list(destino.glob('.nunes-*.tmp')), [])

    def test_console_informa_colisao_sem_perder_arquivos(self):
        origem, alvo, _, _ = self.caso('mover')
        (origem.parent / 'notas.txt').write_text('1234', encoding='utf-8')
        def concorrente(source, target, *args, **kwargs):
            if Path(target) == alvo:
                alvo.write_bytes(b'concorrente console')
            return self.rename(source, target, *args, **kwargs)
        saida = StringIO()
        with patch.object(Path, 'cwd', return_value=origem.parent), patch.dict(os.environ, {v: str(origem.parent) for v in VARIAVEIS}), patch('builtins.input', return_value=''), patch('sys.stdout', saida), patch('os.rename', side_effect=concorrente):
            console('mover')
        self.assertIn('Conflito', saida.getvalue())
        self.assertIn('Concluídos: 0', saida.getvalue())
        self.assertTrue(origem.exists())
        self.assertEqual(alvo.read_bytes(), b'concorrente console')

    def test_worker_web_publica_resultado_de_conflito(self):
        from notas import Servidor
        origem, alvo, _, _ = self.caso('mover')
        servidor = Servidor()
        self.addCleanup(servidor.server_close)
        def concorrente(source, target, *args, **kwargs):
            if Path(target) == alvo:
                alvo.write_bytes(b'concorrente web')
            return self.rename(source, target, *args, **kwargs)
        with patch('os.rename', side_effect=concorrente):
            servidor.iniciar(dict(acao='mover', notas='1234', caminhos=[str(origem.parent)] * 4, destino=str(origem.parent / 'copias')))
            assert servidor.worker is not None
            servidor.worker.join(3)
            self.assertFalse(servidor.worker.is_alive())
        estado = servidor.situacao()
        self.assertFalse(estado['ocupado'])
        resultado, logs = estado['resultado'], estado['logs']
        assert isinstance(resultado, dict) and isinstance(logs, list)
        self.assertEqual(resultado['concluidos'], 0)
        self.assertEqual(resultado['ignorados'], 1)
        self.assertEqual(resultado['erros'], 0)
        self.assertTrue(any('Conflito' in m for m in logs))
        self.assertEqual(origem.read_bytes(), b'nota sintetica original')
        self.assertEqual(alvo.read_bytes(), b'concorrente web')


if __name__ == '__main__':
    unittest.main()
