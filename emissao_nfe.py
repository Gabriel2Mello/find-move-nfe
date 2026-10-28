"""Leitura da emissão fiscal para desempatar versões na busca."""
from datetime import datetime, timezone
from pathlib import Path
import re
import unicodedata
from xml.etree import ElementTree


DATA_DANFE = re.compile(r'\bDATA\s+(?:DE\s+)?EMISSAO\s*:?\s*(\d{2}/\d{2}/\d{4})\b'
                        r'(?:[ \t]+(\d{2}:\d{2}(?::\d{2})?))?')


def data_emissao(arquivo: Path) -> datetime:
    """Não usa pasta, criação do PDF, autorização ou vencimento como emissão."""
    if arquivo.suffix.lower() == '.xml':
        try:
            raiz = ElementTree.parse(arquivo).getroot()
            emissoes = []
            for ide in raiz.iter():
                if ide.tag.rsplit('}', 1)[-1] != 'ide':
                    continue
                campos = {c.tag.rsplit('}', 1)[-1]: c.text for c in ide}
                valor = campos.get('dhEmi') or campos.get('dEmi')
                if valor:
                    data = datetime.fromisoformat(valor.strip().replace('Z', '+00:00'))
                    # Evita misturar datas com e sem fuso na comparação.
                    if data.tzinfo is not None:
                        data = data.astimezone(timezone.utc).replace(tzinfo=None)
                    emissoes.append(data)
        except (ElementTree.ParseError, ValueError) as erro:
            raise ValueError('Emissão do XML inválida.') from erro
    else:
        try:
            from pypdf import PdfReader
            from pypdf.errors import PyPdfError
        except ImportError as erro:
            raise ValueError('Leitura da emissão exige pypdf; instale requirements.txt.') from erro
        try:
            with arquivo.open('rb') as stream:
                leitor = PdfReader(stream)
                texto = (leitor.pages[0].extract_text() or '') if leitor.pages else ''
            texto = ''.join(c for c in unicodedata.normalize('NFKD', texto.upper())
                            if not unicodedata.combining(c))
            emissoes = []
            for dia, hora in DATA_DANFE.findall(texto):
                formato = '%d/%m/%Y' + (' %H:%M:%S' if hora.count(':') == 2 else ' %H:%M' if hora else '')
                emissoes.append(datetime.strptime(dia + (' ' + hora if hora else ''), formato))
        except (PyPdfError, ValueError, IndexError) as erro:
            raise ValueError('Não foi possível ler a emissão do DANFE.') from erro
    if len(set(emissoes)) != 1:
        raise ValueError('Data de emissão ausente ou ambígua no documento.')
    return emissoes[0]
