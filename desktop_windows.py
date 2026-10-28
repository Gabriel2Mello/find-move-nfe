"""Identidade Shell e foco apenas das janelas/atalhos pertencentes ao Hub."""
import ctypes
from ctypes import wintypes
import json
import logging
from pathlib import Path
import subprocess
import sys

from integracao_hub import gravar_registro

APP_ID = 'Nunes.Hub.Desktop.1'


def ler_geometria(pasta):
    try:
        dados = json.loads((Path(pasta) / 'desktop-janela.json').read_text(encoding='utf-8'))
        if (not isinstance(dados, dict) or dados.get('formato') != 1
                or type(dados.get('maximizada')) is not bool
                or not isinstance(dados.get('retangulo'), list) or len(dados['retangulo']) != 4
                or any(type(valor) is not int or abs(valor) > 100000 for valor in dados['retangulo'])
                or not 100 <= dados['retangulo'][2] <= 20000
                or not 100 <= dados['retangulo'][3] <= 20000):
            return None
        return dados
    except (OSError, ValueError):
        # Preferência visual ausente/corrompida não impede iniciar o Hub.
        return None


def ajustar_retangulo(retangulo, area, minimo):
    x, y, largura, altura = retangulo
    esquerda, topo, disponivel_x, disponivel_y = area
    largura = min(max(largura, minimo[0]), disponivel_x)
    altura = min(max(altura, minimo[1]), disponivel_y)
    return (min(max(x, esquerda), esquerda + disponivel_x - largura),
            min(max(y, topo), topo + disponivel_y - altura), largura, altura)


def restaurar_geometria(formulario, dados):
    from System.Drawing import Point, Rectangle
    from System.Windows.Forms import FormStartPosition, FormWindowState
    from dpi_windows import monitor_do_retangulo
    area = monitor_do_retangulo(dados['retangulo'])['area_util']
    # Primeiro atravessar o monitor, deixando WinForms processar WM_DPICHANGED.
    # Aplicar posição e tamanho juntos antes de Show pode escalar os pixels
    # salvos uma segunda vez (por exemplo, 1180px vira 944px em 125% -> 100%).
    posicao = ajustar_retangulo(dados['retangulo'], area, (1, 1))
    formulario.StartPosition = FormStartPosition.Manual
    formulario.Location = Point(*posicao[:2])
    retangulo = ajustar_retangulo(dados['retangulo'], area,
                                  (formulario.MinimumSize.Width, formulario.MinimumSize.Height))
    formulario.Bounds = Rectangle(*retangulo)
    if dados['maximizada']:
        formulario.WindowState = FormWindowState.Maximized


def salvar_geometria(formulario, pasta):
    from System.Windows.Forms import FormWindowState
    try:
        estado = formulario.WindowState
        retangulo = formulario.Bounds if estado == FormWindowState.Normal else formulario.RestoreBounds
        # Ao fechar minimizada, conservar o estado de restauração do Windows.
        if estado == FormWindowState.Minimized:
            import win32gui
            maximizada = bool(win32gui.GetWindowPlacement(formulario.Handle.ToInt64())[0] & 2)
        else:
            maximizada = estado == FormWindowState.Maximized
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        gravar_registro(pasta / 'desktop-janela.json', {
            'formato': 1, 'retangulo': [retangulo.X, retangulo.Y, retangulo.Width, retangulo.Height],
            'maximizada': maximizada,
        })
    except OSError:
        # Falha de preferência não bloqueia fechamento nem altera presença.
        logging.getLogger(__name__).warning('Não foi possível salvar a posição da janela do Hub.')


def mesma_sessao(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    atual, outra = wintypes.DWORD(), wintypes.DWORD()
    return bool(kernel.ProcessIdToSessionId(kernel.GetCurrentProcessId(), ctypes.byref(atual))
                and kernel.ProcessIdToSessionId(pid, ctypes.byref(outra)) and atual.value == outra.value)


def permitir_foco(pid):
    if not mesma_sessao(pid):
        raise RuntimeError('A instância localizada não pertence a esta sessão Windows.')
    # A Shell pode conceder o direito à segunda execução iniciada pelo usuário.
    # A recusa é normal: SetForegroundWindow ainda pode sinalizar na barra.
    ctypes.windll.user32.AllowSetForegroundWindow(pid)


def identidade_processo(app_id=APP_ID):
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
    shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
    if shell.SetCurrentProcessExplicitAppUserModelID(app_id) < 0:
        raise RuntimeError('Não foi possível configurar a identidade Windows do Hub.')


def comando_reabrir(argumentos, entrada=None):
    if getattr(sys, 'frozen', False):
        return [sys.executable, *argumentos]
    python = Path(sys.executable).with_name('pythonw.exe')
    return [str(python), str(entrada or Path(__file__).with_name('hub.py')), *argumentos]


def propriedades_janela(hwnd, comando, icone, *, app_id=APP_ID, nome='Hub Nunes'):
    import pythoncom
    from win32com.propsys import propsys, pscon
    pythoncom.CoInitialize()
    try:
        propriedades = propsys.SHGetPropertyStoreForWindow(hwnd, propsys.IID_IPropertyStore)
        for chave, valor in (
            (pscon.PKEY_AppUserModel_RelaunchCommand, subprocess.list2cmdline(comando)),
            (pscon.PKEY_AppUserModel_RelaunchDisplayNameResource, nome),
            (pscon.PKEY_AppUserModel_RelaunchIconResource, str(icone) + ',0'),
            (pscon.PKEY_AppUserModel_ID, app_id),
        ):
            propriedades.SetValue(chave, propsys.PROPVARIANTType(valor, pythoncom.VT_LPWSTR))
        propriedades.Commit()
    finally:
        pythoncom.CoUninitialize()


def criar_atalho(destino, comando, icone, *, app_id=APP_ID, descricao='Central de acesso às automações Nunes'):
    import pythoncom
    from win32com.shell import shell
    from win32com.propsys import propsys, pscon
    pythoncom.CoInitialize()
    try:
        atalho = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                                           pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
        atalho.SetPath(comando[0])
        atalho.SetArguments(subprocess.list2cmdline(comando[1:]))
        atalho.SetWorkingDirectory(str(Path(comando[0]).parent))
        atalho.SetIconLocation(str(icone), 0)
        atalho.SetDescription(descricao)
        propriedades = atalho.QueryInterface(propsys.IID_IPropertyStore)
        propriedades.SetValue(pscon.PKEY_AppUserModel_ID,
                               propsys.PROPVARIANTType(app_id, pythoncom.VT_LPWSTR))
        propriedades.Commit()
        atalho.QueryInterface(pythoncom.IID_IPersistFile).Save(str(destino), 1)
    finally:
        pythoncom.CoUninitialize()


def focalizar(hwnd):
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    if user.IsIconic(hwnd):
        user.ShowWindow(hwnd, 9)  # SW_RESTORE; preserva maximização quando aplicável.
    if not user.SetForegroundWindow(hwnd):
        class Flash(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.UINT), ('hwnd', wintypes.HWND),
                        ('dwFlags', wintypes.DWORD), ('uCount', wintypes.UINT), ('dwTimeout', wintypes.DWORD)]
        dados = Flash(ctypes.sizeof(Flash), hwnd, 3, 3, 0)
        user.FlashWindowEx(ctypes.byref(dados))
