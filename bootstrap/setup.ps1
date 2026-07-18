param([switch]$DryRun, [switch]$SkipRelease)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$modelRoot = 'G:\LLMs'
$tooling = Join-Path $root '.tooling'
$uvDir = Join-Path $tooling 'uv'
$pythonDir = Join-Path $tooling 'python'
$cacheDir = Join-Path $tooling 'cache\uv'
$manifest = Get-Content -Raw (Join-Path $root 'tools\manifests\toolchain.json') | ConvertFrom-Json
$actions = @(
    @{ name = 'install_uv'; target = (Join-Path $uvDir 'uv.exe') },
    @{ name = 'install_python'; target = $pythonDir },
    @{ name = 'create_model_root'; target = $modelRoot }
)
$result = [ordered]@{
    schema_version = 1
    root = $root
    model_root = $modelRoot
    uv_version = $manifest.uv.version
    python_version = $manifest.python.version
    actions = $actions
}

if ($DryRun) {
    $result | ConvertTo-Json -Depth 5
    exit 0
}

foreach ($target in @($tooling, $uvDir, $pythonDir, $cacheDir, $modelRoot, (Join-Path $modelRoot 'manifests'))) {
    if (-not $target.StartsWith('G:\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing non-G target: $target"
    }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
}

$uvExe = Join-Path $uvDir 'uv.exe'
if (-not (Test-Path -LiteralPath $uvExe)) {
    $installer = Join-Path $tooling 'uv-install.ps1'
    Invoke-WebRequest -UseBasicParsing -Uri $manifest.uv.installer -OutFile $installer
    $env:UV_UNMANAGED_INSTALL = $uvDir
    $env:UV_NO_MODIFY_PATH = '1'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $installer
    if ($LASTEXITCODE -ne 0) {
        throw "uv installation failed: $LASTEXITCODE"
    }
}

$env:UV_PYTHON_INSTALL_DIR = $pythonDir
$env:UV_CACHE_DIR = $cacheDir
& $uvExe python install $manifest.python.version --install-dir $pythonDir --no-bin
if ($LASTEXITCODE -ne 0) {
    throw "uv python install failed: $LASTEXITCODE"
}

$pythonExe = (& $uvExe python find $manifest.python.version --managed-python).Trim()
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Managed Python was not found beneath $pythonDir"
}

$runtime = [ordered]@{
    schema_version = 1
    uv = $uvExe
    python = $pythonExe
    uv_version = (& $uvExe --version).Trim()
    python_version = (& $pythonExe --version).Trim()
}
$runtime | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $tooling 'runtime.json')
if (-not $SkipRelease) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'setup-release.ps1')
    if ($LASTEXITCODE -ne 0) {
        throw "Release tool setup failed: $LASTEXITCODE"
    }
}
$result | ConvertTo-Json -Depth 5
