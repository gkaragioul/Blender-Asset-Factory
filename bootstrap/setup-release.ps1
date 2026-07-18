param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tooling = Join-Path $root '.tooling'
$manifestPath = Join-Path $root 'tools\manifests\release-toolchain.json'
$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
$nodeDir = Join-Path $tooling 'node'
$nodeHome = Join-Path $nodeDir ("node-v{0}-win-x64" -f $manifest.node.version)
$nodeExe = Join-Path $nodeHome 'node.exe'
$npmCmd = Join-Path $nodeHome 'npm.cmd'
$gltfpackDir = Join-Path $tooling 'gltfpack'
$gltfpackExe = Join-Path $gltfpackDir 'gltfpack.exe'
$releaseNodeDir = Join-Path $tooling 'release-node'
$cacheDir = Join-Path $tooling 'cache\release-downloads'
$npmCache = Join-Path $tooling 'cache\npm'
$runtimePath = Join-Path $tooling 'release-runtime.json'
$targets = @($tooling, $nodeDir, $nodeHome, $gltfpackDir, $releaseNodeDir, $cacheDir, $npmCache, $runtimePath)

$versions = [ordered]@{
    gltf_validator = $manifest.gltf_validator.version
    gltfpack = $manifest.gltfpack.version
    node = $manifest.node.version
    playwright_core = $manifest.playwright_core.version
    three = $manifest.three.version
}
$result = [ordered]@{
    schema_version = 1
    root = $root
    versions = $versions
    targets = $targets
}

foreach ($target in $targets) {
    $full = [IO.Path]::GetFullPath($target)
    if (-not $full.StartsWith('G:\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing non-G target: $full"
    }
}
if ($DryRun) {
    $result | ConvertTo-Json -Depth 5
    exit 0
}

foreach ($directory in @($tooling, $nodeDir, $gltfpackDir, $releaseNodeDir, $cacheDir, $npmCache)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

function Get-VerifiedArchive($Name, $Url, $ExpectedHash) {
    $archive = Join-Path $cacheDir $Name
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $archive
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedHash.ToLowerInvariant()) {
        throw "Checksum mismatch for ${Name}: expected $ExpectedHash, got $actual"
    }
    return $archive
}

if (-not (Test-Path -LiteralPath $nodeExe)) {
    $nodeArchive = Get-VerifiedArchive 'node-win-x64.zip' $manifest.node.url $manifest.node.sha256
    & tar.exe -xf $nodeArchive -C $nodeDir
    if ($LASTEXITCODE -ne 0) {
        throw "Node archive extraction failed: $LASTEXITCODE"
    }
}
if (-not (Test-Path -LiteralPath $nodeExe)) {
    throw "Node executable missing after verified extraction: $nodeExe"
}

if (-not (Test-Path -LiteralPath $gltfpackExe)) {
    $gltfpackArchive = Get-VerifiedArchive 'gltfpack-windows.zip' $manifest.gltfpack.url $manifest.gltfpack.sha256
    Expand-Archive -LiteralPath $gltfpackArchive -DestinationPath $gltfpackDir -Force
}
if (-not (Test-Path -LiteralPath $gltfpackExe)) {
    throw "gltfpack executable missing after verified extraction: $gltfpackExe"
}

Copy-Item -LiteralPath (Join-Path $root 'tools\release-node\package.json') -Destination (Join-Path $releaseNodeDir 'package.json') -Force
Copy-Item -LiteralPath (Join-Path $root 'tools\release-node\package-lock.json') -Destination (Join-Path $releaseNodeDir 'package-lock.json') -Force
$env:npm_config_cache = $npmCache
$env:npm_config_audit = 'false'
$env:npm_config_fund = 'false'
$env:npm_config_ignore_scripts = 'true'
$env:npm_config_progress = 'false'
$env:NODE_OPTIONS = '--dns-result-order=ipv4first'
& $npmCmd ci --prefix $releaseNodeDir --no-audit --no-fund --ignore-scripts --prefer-offline --fetch-retries=2 --fetch-retry-mintimeout=1000 --fetch-retry-maxtimeout=10000
if ($LASTEXITCODE -ne 0) {
    throw "Pinned release npm install failed: $LASTEXITCODE"
}

$runtime = [ordered]@{
    schema_version = 1
    node = $nodeExe
    node_version = (& $nodeExe --version).Trim()
    npm = $npmCmd
    gltfpack = $gltfpackExe
    gltfpack_version = $manifest.gltfpack.version
    node_modules = (Join-Path $releaseNodeDir 'node_modules')
    manifest = $manifestPath
}
$temporary = "$runtimePath.tmp"
$runtime | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath $temporary
Move-Item -LiteralPath $temporary -Destination $runtimePath -Force
$result | ConvertTo-Json -Depth 5
