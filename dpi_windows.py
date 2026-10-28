"""DPI desktop Nunes 1.0: fonte no Hub, cópias locais explícitas nos consumidores.

Bootstrap no início do desktop, antes de CLR/HWND. Retângulos de monitores usam
pixels físicos; apenas as dimensões lógicas são divididas pela escala nativa.
"""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
from threading import Thread

PER_MONITOR_V2 = -4
_preparado = False


def _user():
  user = ctypes.WinDLL('user32', use_last_error=True)
  for nome, argumentos, retorno in (
      ('SetProcessDpiAwarenessContext', [ctypes.c_void_p], wintypes.BOOL),
      ('GetThreadDpiAwarenessContext', [], ctypes.c_void_p),
      ('GetWindowDpiAwarenessContext', [wintypes.HWND], ctypes.c_void_p),
      ('GetDpiForWindow', [wintypes.HWND], wintypes.UINT),
      ('AreDpiAwarenessContextsEqual', [ctypes.c_void_p, ctypes.c_void_p], wintypes.BOOL)):
    funcao = getattr(user, nome)
    funcao.argtypes, funcao.restype = argumentos, retorno
  return user


def _ativar_per_monitor_v2():
  user = _user()
  if not user.SetProcessDpiAwarenessContext(PER_MONITOR_V2):
    erro = ctypes.get_last_error()
    if erro != 5:  # ERROR_ACCESS_DENIED: um manifesto/API já definiu o modo.
      raise ctypes.WinError(erro)
  # Um override da thread atual NÃO comprova o padrão herdado pela GUI. Até
  # GetDpiAwarenessContextForProcess, no próprio processo, sofre esse override.
  herdado = []
  thread = Thread(target=lambda: herdado.append(bool(user.AreDpiAwarenessContextsEqual(
    user.GetThreadDpiAwarenessContext(), PER_MONITOR_V2))))
  thread.start()
  thread.join()
  if herdado != [True] or not user.AreDpiAwarenessContextsEqual(
      user.GetThreadDpiAwarenessContext(), PER_MONITOR_V2):
    raise RuntimeError('DPI incompatível: configure Per-Monitor V2 antes de criar threads de interface ou janelas.')


def preparar(dominio):
  """Configura este processo; repetir no mesmo desktop não reinicia o CLR."""
  global _preparado
  if _preparado or sys.platform != 'win32':
    return
  configuracao = Path(__file__).with_name('desktop-winforms.config')
  if not configuracao.is_file():
    raise RuntimeError('Configuração de DPI desktop ausente. Confira a instalação.')
  _ativar_per_monitor_v2()
  import pythonnet
  if pythonnet.get_runtime_info() is not None:
    raise RuntimeError('Configure o DPI desktop antes de carregar o runtime .NET.')
  # clr_loader aplica config_file somente a AppDomains nomeados.
  pythonnet.load('netfx', domain=dominio, config_file=str(configuracao))
  from System import AppDomain
  # O host Python não declara TargetFrameworkAttribute. Sem alvo >=4.7,
  # WinForms ignora sua configuração de DPI dinâmico, mesmo no .NET 4.8.
  AppDomain.CurrentDomain.SetData('TargetFrameworkName', '.NETFramework,Version=v4.8')
  _preparado = True


def validar_janela(hwnd):
  """Confere o HWND efetivo, sem confundir a thread chamadora com a da GUI."""
  user = _user()
  if not user.AreDpiAwarenessContextsEqual(user.GetWindowDpiAwarenessContext(hwnd), PER_MONITOR_V2):
    raise RuntimeError('A janela desktop não foi criada em Per-Monitor V2.')
  dpi = user.GetDpiForWindow(hwnd)
  if not dpi:
    raise ctypes.WinError(ctypes.get_last_error())
  return dpi


class _MonitorInfo(ctypes.Structure):
  _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
              ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD),
              ('szDevice', wintypes.WCHAR * 32)]


def _descrever_monitor(user, handle):
  user.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MonitorInfo)]
  user.GetMonitorInfoW.restype = wintypes.BOOL
  dados = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
  if not user.GetMonitorInfoW(handle, ctypes.byref(dados)):
    raise ctypes.WinError(ctypes.get_last_error())
  shcore = ctypes.WinDLL('shcore', use_last_error=True)
  shcore.GetScaleFactorForMonitor.argtypes = [wintypes.HMONITOR, ctypes.POINTER(ctypes.c_int)]
  shcore.GetScaleFactorForMonitor.restype = ctypes.c_long
  percentual = ctypes.c_int()
  erro = shcore.GetScaleFactorForMonitor(handle, ctypes.byref(percentual))
  if erro < 0:
    raise OSError(erro, 'Não foi possível consultar a escala do monitor.')
  escala = percentual.value / 100
  if escala <= 0:
    raise RuntimeError('Escala de monitor inválida.')
  def retangulo(r):
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)
  tela = retangulo(dados.rcMonitor)
  return {'nome': dados.szDevice, 'retangulo': tela, 'area_util': retangulo(dados.rcWork),
          'escala': escala, 'dpi': round(96 * escala),
          'dimensoes_logicas': (tela[2] / escala, tela[3] / escala)}


def monitores():
  """Enumera telas pela API nativa, sem as métricas de webview.screens."""
  user = _user()
  if not user.AreDpiAwarenessContextsEqual(user.GetThreadDpiAwarenessContext(), PER_MONITOR_V2):
    raise RuntimeError('Consulte monitores em uma thread Per-Monitor V2.')
  retorno, erros = [], []
  callback_tipo = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
  @callback_tipo
  def observar(handle, dc, retangulo, dados):
    try:
      retorno.append(_descrever_monitor(user, handle))
      return True
    except Exception as erro:
      erros.append(erro)
      return False
  user.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, callback_tipo, wintypes.LPARAM]
  user.EnumDisplayMonitors.restype = wintypes.BOOL
  sucesso = user.EnumDisplayMonitors(None, None, observar, 0)
  if erros:
    raise erros[0]
  if not sucesso:
    raise ctypes.WinError(ctypes.get_last_error())
  return retorno


def monitor_do_retangulo(retangulo):
  """Tela de maior interseção, ou a mais próxima se a posição foi removida."""
  user = _user()
  if not user.AreDpiAwarenessContextsEqual(user.GetThreadDpiAwarenessContext(), PER_MONITOR_V2):
    raise RuntimeError('Restaure a janela em uma thread Per-Monitor V2.')
  x, y, largura, altura = retangulo
  rect = wintypes.RECT(x, y, x + largura, y + altura)
  user.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
  user.MonitorFromRect.restype = wintypes.HMONITOR
  handle = user.MonitorFromRect(ctypes.byref(rect), 2)  # MONITOR_DEFAULTTONEAREST
  if not handle:
    raise ctypes.WinError(ctypes.get_last_error())
  return _descrever_monitor(user, handle)
