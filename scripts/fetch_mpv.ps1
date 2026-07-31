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

$MpvVersion = "0.41.0"
$ArchiveName = "mpv-v$MpvVersion-x86_64-pc-windows-msvc.zip"
$ExpectedSha256 = "4E197F729F5071C6772F35FFFD96E0F36E3E8A044BD9479B136BB09B7C6A80FF"
$DownloadUrl = "https://github.com/mpv-player/mpv/releases/download/v$MpvVersion/$ArchiveName"
$VersionRoot = Join-Path $ArtifactRoot "mpv-v$MpvVersion"
$ArchivePath = Join-Path $VersionRoot $ArchiveName
$ExtractRoot = Join-Path $VersionRoot "extracted"
$MpvPath = Join-Path $ExtractRoot "mpv.exe"
$VulkanPath = Join-Path $ExtractRoot "vulkan-1.dll"

New-Item -ItemType Directory -Path $VersionRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath $ArchivePath)) {
    Write-Host "Downloading official mpv v$MpvVersion..."
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
if ($VersionLine -notmatch "v0\.41\.0") {
    throw "Unexpected mpv binary version: $VersionLine"
}

[pscustomobject]@{
    Version = $MpvVersion
    Archive = $ArchivePath
    ArchiveSha256 = $ActualSha256
    Mpv = $MpvPath
    Vulkan = $VulkanPath
}
