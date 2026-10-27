param([string]$Python = (Join-Path $PSScriptRoot '.venv-desktop\Scripts\python.exe'))
$ErrorActionPreference = 'Stop'
& $Python -m PyInstaller --noconfirm --clean --distpath "$PSScriptRoot\dist" --workpath "$PSScriptRoot\build" "$PSScriptRoot\Busca e Move Notas.spec"
if ($LASTEXITCODE -ne 0) { throw 'O build desktop de Busca e Move Notas falhou.' }
$pacoteNotas = Join-Path $PSScriptRoot 'dist\Busca e Move Notas'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'DESKTOP.md') -Destination $pacoteNotas
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LEIA-ME.txt') -Destination $pacoteNotas
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Criar Atalho Busca e Move Notas.ps1') -Destination $pacoteNotas
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Abrir Busca e Move Notas.cmd') -Destination $pacoteNotas
Write-Output "Distribua a pasta inteira $pacoteNotas, incluindo _internal. Consulte DESKTOP.md."
