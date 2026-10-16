@echo off
setlocal
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo O Python do Busca e Move Notas nao foi encontrado. Consulte o README.
  pause
  exit /b 1
)
start "" /D "%~dp0." "%~dp0.venv\Scripts\pythonw.exe" "%~dp0notas.py"
