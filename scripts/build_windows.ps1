[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$OutputRoot,
    [string]$ArtifactRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content -LiteralPath (Join-Path $RepositoryRoot "macast\.version") -Raw -Encoding UTF8).Trim()
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepositoryRoot ".build\windows-v$Version"
}
elseif (-not [System.IO.Path]::IsPathRooted($OutputRoot)) {
    $OutputRoot = Join-Path $RepositoryRoot $OutputRoot
}
if (-not $ArtifactRoot) {
    $ArtifactRoot = Join-Path $RepositoryRoot ".artifacts"
}
elseif (-not [System.IO.Path]::IsPathRooted($ArtifactRoot)) {
    $ArtifactRoot = Join-Path $RepositoryRoot $ArtifactRoot
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$ArtifactRoot = [System.IO.Path]::GetFullPath($ArtifactRoot)

if (Test-Path -LiteralPath $OutputRoot) {
    throw "Refusing to overwrite an existing build directory: $OutputRoot"
}

$WorkRoot = Join-Path $OutputRoot "work"
$DistRoot = Join-Path $OutputRoot "dist"
$SpecRoot = Join-Path $OutputRoot "spec"
$TranslationRoot = Join-Path $OutputRoot "i18n"
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
New-Item -ItemType Directory -Path $WorkRoot, $DistRoot, $SpecRoot, $TranslationRoot | Out-Null

$PythonCommand = Get-Command $Python -ErrorAction Stop
$PythonPath = $PythonCommand.Source
$PythonVersion = (& $PythonPath -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
if ([version]$PythonVersion -lt [version]"3.10") {
    throw "Python 3.10 or newer is required; found $PythonVersion."
}

& $PythonPath -c "import PyInstaller, babel"
if ($LASTEXITCODE -ne 0) {
    throw "Build dependencies are missing. Install requirements/build-windows.txt first."
}

$Mpv = & (Join-Path $PSScriptRoot "fetch_mpv.ps1") -ArtifactRoot $ArtifactRoot
$MpvPath = $Mpv.Mpv
$VulkanPath = $Mpv.Vulkan

& $PythonPath (Join-Path $PSScriptRoot "compile_translations.py") `
    --source (Join-Path $RepositoryRoot "i18n") `
    --output $TranslationRoot
if ($LASTEXITCODE -ne 0) {
    throw "Translation compilation failed."
}

$ApplicationName = "Macast-RTX-Edition-v$Version"
$PyInstallerArguments = @(
    "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", $ApplicationName,
    "--workpath", $WorkRoot,
    "--distpath", $DistRoot,
    "--specpath", $SpecRoot,
    "--additional-hooks-dir", $RepositoryRoot,
    "--icon", (Join-Path $RepositoryRoot "macast\assets\icon.ico"),
    "--add-data", "$(Join-Path $RepositoryRoot 'macast\.version');.",
    "--add-data", "$(Join-Path $RepositoryRoot 'macast\xml');macast\xml",
    "--add-data", "$TranslationRoot;i18n",
    "--add-data", "$(Join-Path $RepositoryRoot 'macast\scripts');macast\scripts",
    "--add-data", "$(Join-Path $RepositoryRoot 'macast\assets\settings.js');macast\assets",
    "--add-data", "$(Join-Path $RepositoryRoot 'macast\assets\settings.css');macast\assets",
    "--add-binary", "$MpvPath;bin",
    "--add-binary", "$VulkanPath;bin"
)

Get-ChildItem -LiteralPath (Join-Path $RepositoryRoot "macast\assets") -File |
    Where-Object { $_.Extension -in @(".png", ".ico", ".icns") } |
    ForEach-Object {
        $PyInstallerArguments += @("--add-data", "$($_.FullName);macast\assets")
    }

$PyInstallerArguments += (Join-Path $RepositoryRoot "Macast.py")
& $PythonPath @PyInstallerArguments
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

$ExecutablePath = Join-Path $DistRoot "$ApplicationName.exe"
if (-not (Test-Path -LiteralPath $ExecutablePath)) {
    throw "Build completed without the expected executable: $ExecutablePath"
}

$ExecutableHash = (Get-FileHash -LiteralPath $ExecutablePath -Algorithm SHA256).Hash
$ChecksumPath = Join-Path $DistRoot "SHA256SUMS.txt"
if (Test-Path -LiteralPath $ChecksumPath) {
    throw "Refusing to overwrite $ChecksumPath"
}
"$($ExecutableHash.ToLowerInvariant())  $ApplicationName.exe" |
    Set-Content -LiteralPath $ChecksumPath -Encoding ASCII

Write-Host "Built $ExecutablePath"
Write-Host "SHA256 $ExecutableHash"
