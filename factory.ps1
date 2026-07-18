$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$runtimePath = Join-Path $root '.tooling\runtime.json'
if (-not (Test-Path -LiteralPath $runtimePath)) {
    throw 'Factory runtime missing. Run .\bootstrap\setup.ps1 first.'
}
$runtime = Get-Content -Raw $runtimePath | ConvertFrom-Json
& $runtime.python -m factory @args
exit $LASTEXITCODE
