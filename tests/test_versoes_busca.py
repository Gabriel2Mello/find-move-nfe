"""Seleção por emissão com documentos sintéticos e métricas isoladas."""
from datetime import datetime
import os
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from emissao_nfe import data_emissao
from operacoes import executar, console, VARIAVEIS


class TestVersoesBusca(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.origem = self.raiz / 'origem'
        self.origem.mkdir()
        self.destino = self.raiz / 'copias'
        self.ano = str(datetime.now().year)
        self.logs = []
        self.enterContext(patch.dict(os.environ, {
            'NUNES_METRICAS_DADOS': str(self.raiz / 'metricas'),
            'NUNES_NOTAS_DADOS': str(self.raiz / 'dados'),
            'NUNES_HUB_DADOS': str(self.raiz / 'presenca'),
        }))
        self.enterContext(patch('sincronizar_estatisticas.ler_configuracao', return_value=None))

    def pdf(self, pasta, emissao, modificacao, *, nome='Nfe0068444.pdf'):
        arquivo = self.origem / self.ano / pasta / nome
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        writer = PdfWriter()
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/Encoding'): NameObject('/WinAnsiEncoding'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        texto = f'DATA DE EMISSÃO\n{emissao}\nVENCIMENTO\n31/12/2099'
        comandos = 'BT /F1 10 Tf 30 750 Td ' + ' '.join(
            f'({linha}) Tj 0 -15 Td' for linha in texto.splitlines()) + ' ET'
        stream.set_data(comandos.encode('latin-1'))
        page[NameObject('/Contents')] = writer._add_object(stream)
        writer.write(arquivo)
        os.utime(arquivo, (modificacao, modificacao))
        return arquivo

    def xml(self, pasta, emissao, modificacao, *, legado=False, invalido=False):
        nome = 'NFe' + '0' * 30 + '6844' + '0' * 10 + '.xml'
        arquivo = self.origem / self.ano / pasta / nome
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        campo = 'dEmi' if legado else 'dhEmi'
        arquivo.write_text('<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">'
            f'<NFe><infNFe><ide><{campo}>{emissao}</{campo}></ide></infNFe></NFe>'
            '<protNFe><infProt><dhRecbto>2099-12-31T23:59:59Z</dhRecbto></infProt></protNFe>'
            '</nfeProc>' if not invalido else '<quebrado', encoding='utf-8')
        os.utime(arquivo, (modificacao, modificacao))
        return arquivo

    def rodar(self, **opcoes):
        return executar('buscar', {'6844'}, [self.origem], self.destino,
                        relatar=self.logs.append, **opcoes)

    def test_pdf_prioriza_emissao_independente_de_modificacao_e_ordem(self):
        nova = self.pdf('A', '20/10/2026', 100)
        antiga = self.pdf('B', '14/05/2026', 200)
        for pastas in ([nova.parent, antiga.parent], [antiga.parent, nova.parent]):
            with self.subTest(pastas=pastas):
                resultado = executar('buscar', {'6844'}, pastas, self.destino, relatar=self.logs.append)
                self.assertEqual((resultado['encontrados'], resultado['concluidos'],
                                  resultado['ignorados'], resultado['erros']), (2, 1, 0, 0))
                self.assertEqual((self.destino / nova.name).read_bytes(), nova.read_bytes())
                (self.destino / nova.name).unlink()
        self.assertTrue(nova.exists() and antiga.exists())
        self.assertTrue(any('encontrado em 2 locais diferentes' in l for l in self.logs))
        self.assertTrue(any(str(nova) in l and str(antiga) in l for l in self.logs))
        self.assertFalse(any('Já existe no destino' in l for l in self.logs))

    def test_pdf_emissao_igual_escolhe_modificacao_mais_recente(self):
        self.pdf('MAIO', '14/05/2026', 100)
        nova = self.pdf('OUTUBRO', '14/05/2026', 200)
        self.assertEqual(self.rodar()['concluidos'], 1)
        self.assertEqual((self.destino / nova.name).stat().st_mtime_ns, nova.stat().st_mtime_ns)
        self.assertTrue(any('Versão selecionada:' in l and str(nova) in l for l in self.logs))

    def test_xml_prioriza_emissao_e_nao_data_de_autorizacao(self):
        antiga = self.xml('A', '2026-05-14T12:00:00-03:00', 300)
        nova = self.xml('B', '2026-10-20T08:00:00-03:00', 100)
        self.assertEqual(self.rodar()['concluidos'], 1)
        self.assertEqual((self.destino / nova.name).read_bytes(), nova.read_bytes())
        self.assertTrue(antiga.exists())

    def test_xml_desempata_modificacao_com_fusos_equivalentes(self):
        self.xml('A', '2026-10-20T11:00:00Z', 100)
        nova = self.xml('B', '2026-10-20T08:00:00-03:00', 200)
        self.assertEqual(self.rodar()['concluidos'], 1)
        self.assertEqual((self.destino / nova.name).read_bytes(), nova.read_bytes())

    def test_xml_legado_demi(self):
        arquivo = self.xml('A', '2026-10-20', 100, legado=True)
        self.assertEqual(data_emissao(arquivo), datetime(2026, 10, 20))

    def test_emissao_nao_e_vencimento_ou_metadata_pdf(self):
        arquivo = self.pdf('A', '14/05/2026', 300)
        self.assertEqual(data_emissao(arquivo), datetime(2026, 5, 14))

    def test_pdf_considera_horario_de_emissao_quando_disponivel(self):
        self.pdf('A', '14/05/2026 08:00:00', 300)
        nova = self.pdf('B', '14/05/2026 10:30:00', 100)
        self.assertEqual(self.rodar()['concluidos'], 1)
        self.assertEqual((self.destino / nova.name).read_bytes(), nova.read_bytes())

    def test_emissao_ausente_ou_invalida_nao_escolhe_silenciosamente(self):
        for valor in ('', '31/02/2026'):
            with self.subTest(valor=valor):
                self.pdf('A', valor, 300)
                self.pdf('B', '14/05/2026', 100)
                resultado = self.rodar()
                self.assertEqual((resultado['concluidos'], resultado['erros']), (0, 1))
                self.assertEqual(resultado['nao_encontradas'], [])
                self.assertEqual(list(self.destino.iterdir()), [])

    def test_xml_invalido_impede_escolha_do_grupo(self):
        self.xml('A', '', 300, invalido=True)
        self.xml('B', '2026-10-20T12:00:00-03:00', 100)
        self.assertEqual(self.rodar()['erros'], 1)
        self.assertEqual(list(self.destino.iterdir()), [])

    def test_destino_preexistente_preservado_e_duplicidade_informada(self):
        self.pdf('A', '14/05/2026', 100)
        nova = self.pdf('B', '20/10/2026', 200)
        self.destino.mkdir()
        alvo = self.destino / nova.name
        alvo.write_bytes(b'preexistente')
        resultado = self.rodar()
        self.assertEqual((resultado['concluidos'], resultado['ignorados']), (0, 1))
        self.assertEqual(alvo.read_bytes(), b'preexistente')
        self.assertTrue(any('encontrado em 2 locais diferentes' in l for l in self.logs))
        self.assertTrue(any('Já existe no destino' in l for l in self.logs))

    def test_nomes_equivalentes_e_tres_locais(self):
        self.pdf('A', '14/05/2026', 100)
        self.pdf('B', '26/08/2026', 200, nome='NFE0068444.PDF')
        nova = self.pdf('C', '20/10/2026', 50)
        self.assertEqual(self.rodar()['concluidos'], 1)
        self.assertEqual(len(list(self.destino.iterdir())), 1)
        self.assertEqual((self.destino / nova.name).read_bytes(), nova.read_bytes())
        self.assertTrue(any('encontrado em 3 locais diferentes' in l for l in self.logs))

    def test_varreduras_sobrepostas_nao_repetem_a_mesma_origem(self):
        arquivo = self.pdf('A', '14/05/2026', 100)
        resultado = executar('buscar', {'6844'}, [self.origem, arquivo.parent],
                             self.destino, relatar=self.logs.append)
        self.assertEqual((resultado['encontrados'], resultado['concluidos']), (1, 1))
        self.assertFalse(any('locais diferentes' in l for l in self.logs))

    def test_empate_total_tem_resultado_estavel(self):
        a = self.pdf('A', '14/05/2026', 100)
        b = self.pdf('B', '14/05/2026', 100)
        for pastas in ([a.parent, b.parent], [b.parent, a.parent]):
            resultado = executar('buscar', {'6844'}, pastas, self.destino, relatar=self.logs.append)
            self.assertEqual(resultado['concluidos'], 1)
            self.assertIn(str(b), [l for l in self.logs if 'Versão selecionada:' in l][-1])
            (self.destino / b.name).unlink()

    def test_cancelamento_durante_leitura_nao_inicia_copia(self):
        self.pdf('A', '14/05/2026', 100)
        self.pdf('B', '20/10/2026', 200)
        cancelar = Event()
        def leitura(arquivo):
            cancelar.set()
            return datetime(2026, 5, 14)
        with patch('operacoes.data_emissao', side_effect=leitura), patch('operacoes._copiar_verificado') as copiar:
            resultado = self.rodar(cancelar=cancelar)
        self.assertTrue(resultado['cancelado'])
        copiar.assert_not_called()

    def test_origem_alterada_durante_leitura_nao_e_copiada(self):
        self.pdf('A', '14/05/2026', 100)
        self.pdf('B', '20/10/2026', 200)
        def leitura(arquivo):
            arquivo.write_bytes(b'alterada')
            return datetime(2026, 10, 20)
        with patch('operacoes.data_emissao', side_effect=leitura):
            resultado = self.rodar()
        self.assertEqual((resultado['concluidos'], resultado['erros']), (0, 1))

    def test_origem_alterada_apos_selecao_nao_e_copiada(self):
        self.pdf('A', '14/05/2026', 100)
        nova = self.pdf('B', '20/10/2026', 200)
        def relatar(texto):
            self.logs.append(texto)
            if texto.startswith('Versão selecionada:'):
                nova.write_bytes(b'alterada depois de ler a emissao')
        resultado = executar('buscar', {'6844'}, [self.origem], self.destino, relatar=relatar)
        self.assertEqual((resultado['concluidos'], resultado['erros']), (0, 1))

    def test_metrica_conta_apenas_a_versao_concluida(self):
        import metricas_nunes
        self.pdf('A', '14/05/2026', 100)
        self.pdf('B', '20/10/2026', 200)
        self.rodar()
        dados = metricas_nunes.consultar_metricas({'aplicacao': 'find-move-nfe'}, painel=True)
        self.assertEqual(dados['totais']['arquivo_transferido'], 1)

    def test_origem_trocada_na_entrada_da_copia_nao_publica_outra_emissao(self):
        from operacoes import _copiar_verificado
        self.pdf('A', '14/05/2026', 100)
        nova = self.pdf('B', '20/10/2026', 200)
        def trocar(origem, alvo, **opcoes):
            origem.write_bytes(b'outro documento depois da selecao')
            return _copiar_verificado(origem, alvo, **opcoes)
        with patch('operacoes._copiar_verificado', side_effect=trocar):
            resultado = self.rodar()
        self.assertEqual((resultado['concluidos'], resultado['erros']), (0, 1))
        self.assertFalse((self.destino / nova.name).exists())

    def test_worker_publica_locais_e_escolha_no_andamento(self):
        from notas import Servidor
        self.pdf('A', '14/05/2026', 100)
        nova = self.pdf('B', '14/05/2026', 200)
        servidor = Servidor()
        self.addCleanup(servidor.server_close)
        servidor.iniciar(dict(acao='buscar', notas='6844', caminhos=[str(self.origem)] * 4,
                             destino=str(self.destino)))
        servidor.worker.join(10)
        self.assertFalse(servidor.worker.is_alive())
        estado = servidor.situacao()
        self.assertEqual(estado['resultado']['concluidos'], 1)
        self.assertTrue(any('encontrado em 2 locais diferentes' in l for l in estado['logs']))
        self.assertTrue(any('Versão selecionada: MATRIZ · DANFE' in l and nova.name in l for l in estado['logs']))
        self.assertFalse(any(str(self.raiz) in l for l in estado['logs']))

    def test_console_compartilha_a_selecao_e_aviso(self):
        from io import StringIO
        self.pdf('A', '14/05/2026', 100)
        nova = self.pdf('B', '20/10/2026', 200)
        (self.raiz / 'notas.txt').write_text('6844')
        saida = StringIO()
        with patch.object(Path, 'cwd', return_value=self.raiz), \
                patch.dict(os.environ, {v: str(self.origem) for v in VARIAVEIS}), \
                patch('builtins.input', return_value=''), patch('sys.stdout', saida):
            self.assertEqual(console('buscar'), 0)
        self.assertIn('encontrado em 2 locais diferentes', saida.getvalue())
        self.assertEqual((self.raiz / 'notas' / nova.name).read_bytes(), nova.read_bytes())


if __name__ == '__main__':
    unittest.main()


class TestCaminhoResumido(unittest.TestCase):
    def test_empresa_tipo_e_subpastas(self):
        from operacoes import caminho_resumido
        with tempfile.TemporaryDirectory() as pasta:
            bases = [str(Path(pasta) / nome) for nome in ('dm', 'df', 'xm', 'xf')]
            for indice, (empresa, tipo) in enumerate((('MATRIZ', 'DANFE'), ('FILIAL', 'DANFE'), ('MATRIZ', 'XML'), ('FILIAL', 'XML'))):
                arquivo = Path(bases[indice]) / '2026/AGOSTO/Nfe0079974.pdf'
                self.assertEqual(caminho_resumido(arquivo, bases), empresa + ' · ' + tipo + '\\2026\\AGOSTO\\Nfe0079974.pdf')
