"""Adaptador Busca e Move do diagnostico_nunes.py; fonte compartilhada no Hub."""
from diagnostico_nunes import registrar as registrar_nunes
from caminhos_desktop import pasta_preferencias, recursos

ARQUIVOS = ('pythonnet/runtime/Python.Runtime.dll', 'clr_loader/ffi/dlls/amd64/ClrLoader.dll',
            'webview/lib/Microsoft.Web.WebView2.Core.dll',
            'webview/lib/Microsoft.Web.WebView2.WinForms.dll', 'web/index.html')


def registrar(erro, etapa):
    return registrar_nunes(erro, etapa, aplicacao='find-move-nfe', pasta_preferencias=pasta_preferencias(),
                          raiz_recursos=recursos(), arquivos=ARQUIVOS)
