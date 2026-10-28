# Lista explícita de recursos: nenhum dado operacional ou configuração local.
from pathlib import Path

raiz = Path(SPECPATH)
a = Analysis([str(raiz / 'notas.py')], pathex=[str(raiz)],
    datas=[(str(raiz / 'web' / nome), 'web') for nome in
           ('index.html', 'notas.css', 'notas.js', 'nunes-tema.js', 'nunes-assinatura.css')]
          + [(str(raiz / 'icons' / nome), 'icons') for nome in
             ('icone.ico', 'icone.svg', 'icone-192.png', 'icone-512.png', 'tema-lua.svg', 'tema-lua-sol.svg')]
          + [(str(raiz / 'desktop-winforms.config'), '.')],
    hiddenimports=['webview.platforms.edgechromium', 'webview.platforms.winforms',
                   'win32com.propsys.propsys', 'win32com.propsys.pscon', 'win32com.shell.shell'],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'cefpython3'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Busca e Move Notas',
          console=False, icon=str(raiz / 'icons/icone.ico'), uac_admin=False)
coll = COLLECT(exe, a.binaries, a.datas, name='Busca e Move Notas')
