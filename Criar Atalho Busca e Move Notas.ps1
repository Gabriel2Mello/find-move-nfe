$ErrorActionPreference = 'Stop'
$executavelNotas = Join-Path $PSScriptRoot 'Busca e Move Notas.exe'
$scriptNotas = Join-Path $PSScriptRoot 'notas.py'
$iconeNotas = Join-Path $PSScriptRoot 'icons\icone.ico'
$argumentosNotas = ''
if (Test-Path -LiteralPath $executavelNotas -PathType Leaf) {
    $destinoNotas = $executavelNotas
    $iconeNotas = Join-Path $PSScriptRoot '_internal\icons\icone.ico'
} else {
    $destinoNotas = $null
    foreach ($ambienteNotas in @('.venv-desktop', '.venv')) {
        $pythonNotas = Join-Path $PSScriptRoot "$ambienteNotas\Scripts\pythonw.exe"
        if (Test-Path -LiteralPath $pythonNotas -PathType Leaf) {
            $destinoNotas = (Resolve-Path -LiteralPath $pythonNotas).Path
            break
        }
    }
    if (-not $destinoNotas) { throw 'Python não encontrado em .venv-desktop ou .venv. Consulte o README.' }
    $argumentosNotas = '"' + $scriptNotas + '"'
    if (-not (Test-Path -LiteralPath $scriptNotas -PathType Leaf)) { throw 'notas.py não encontrado.' }
}
if (-not (Test-Path -LiteralPath $iconeNotas -PathType Leaf)) { throw 'Ícone da aplicação não encontrado.' }
$caminhoAtalhoNotas = Join-Path $PSScriptRoot 'Abrir Busca e Move Notas.lnk'
if ($argumentosNotas) {
    $argumentosAtalhoNotas = '"' + $scriptNotas + '" --criar-atalho "' + $caminhoAtalhoNotas + '"'
} else {
    $argumentosAtalhoNotas = '--criar-atalho "' + $caminhoAtalhoNotas + '"'
}
$processoAtalhoNotas = Start-Process -FilePath $destinoNotas -ArgumentList $argumentosAtalhoNotas -WindowStyle Hidden -Wait -PassThru
if ($processoAtalhoNotas.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $caminhoAtalhoNotas -PathType Leaf)) {
    throw 'O iniciador não confirmou a criação do atalho Busca e Move Notas.'
}
Write-Output 'Atalho Busca e Move Notas criado com identidade desktop Nunes.'
