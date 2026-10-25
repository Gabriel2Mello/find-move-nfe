@echo off
setlocal
if exist "%~dp0Busca e Move Notas.exe" (
  start "" /D "%~dp0." "%~dp0Busca e Move Notas.exe"
  exit /b 0
)
set "pythonNotas=%~dp0.venv-desktop\Scripts\pythonw.exe"
if not exist "%pythonNotas%" set "pythonNotas=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%pythonNotas%" (
  echo O Python desktop do Busca e Move Notas nao foi encontrado. Consulte DESKTOP.md.
  pause
  exit /b 1
)
start "" /D "%~dp0." "%pythonNotas%" "%~dp0notas.py"
