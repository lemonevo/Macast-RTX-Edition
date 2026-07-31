[CmdletBinding()]
param(
    [string]$ArtifactRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $ArtifactRoot) {
    $ArtifactRoot = Join-Path $RepositoryRoot ".artifacts"
}

$MpvVersion = "0.41.0-dev-g63ada87ec"
$MpvBuildId = "30636475556"
$MpvCommit = "63ada87ec"
$ArchiveName = "mpv-v$MpvVersion-$MpvBuildId-x86_64-pc-windows-msvc.zip"
$ExpectedSha256 = "B195E12366FC95EABF22A0D409C160069BB222371C7F4570C2CEF7B217EE80F7"
$DownloadUrl = "https://github.com/mpv-player/mpv/releases/download/git-release/$ArchiveName"
$VersionRoot = Join-Path $ArtifactRoot "mpv-v$MpvVersion-$MpvBuildId"
$ArchivePath = Join-Path $VersionRoot $ArchiveName
$ExtractRoot = Join-Path $VersionRoot "extracted"
$MpvPath = Join-Path $ExtractRoot "mpv.exe"
$VulkanPath = Join-Path $ExtractRoot "vulkan-1.dll"

New-Item -ItemType Directory -Path $VersionRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath $ArchivePath)) {
    Write-Host "Downloading official mpv git-release $MpvVersion..."
    Invoke-WebRequest -UseBasicParsing -Uri $DownloadUrl -OutFile $ArchivePath
}

$ActualSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash
if ($ActualSha256 -ne $ExpectedSha256) {
    throw "mpv archive checksum mismatch. Preserve the file for inspection: $ArchivePath"
}

if (-not (Test-Path -LiteralPath $ExtractRoot)) {
    New-Item -ItemType Directory -Path $ExtractRoot | Out-Null
    $Bandizip = "C:\Program Files\Bandizip\bz.exe"
    if (Test-Path -LiteralPath $Bandizip) {
        & $Bandizip x -aos "-o:$ExtractRoot" $ArchivePath
        if ($LASTEXITCODE -ne 0) {
            throw "Bandizip failed to extract mpv."
        }
    }
    else {
        Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExtractRoot
    }
}

foreach ($RequiredFile in @($MpvPath, $VulkanPath)) {
    if (-not (Test-Path -LiteralPath $RequiredFile)) {
        throw "The extracted mpv package is incomplete: $RequiredFile"
    }
}

$VersionLine = (& $MpvPath --version | Select-Object -First 1)
if ($VersionLine -notmatch [regex]::Escape("g$MpvCommit")) {
    throw "Unexpected mpv binary version: $VersionLine"
}

[pscustomobject]@{
    Version = $MpvVersion
    Commit = $MpvCommit
    Archive = $ArchivePath
    ArchiveSha256 = $ActualSha256
    Mpv = $MpvPath
    Vulkan = $VulkanPath
}
