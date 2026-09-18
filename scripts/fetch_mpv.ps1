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

# Upstream rebuilds the "git-release" tag continuously and deletes the previous
# nightly archives, so a pinned asset name breaks the moment mpv publishes a new
# build (the old file simply 404s). Resolve whichever x86_64 build the tag
# currently carries, and verify it against the digest GitHub publishes.
$ReleaseApiUrl = "https://api.github.com/repos/mpv-player/mpv/releases/tags/git-release"
$ReleaseHeaders = @{ "User-Agent" = "Macast-RTX-Edition-build" }
if ($env:GH_TOKEN) {
    $ReleaseHeaders["Authorization"] = "Bearer $($env:GH_TOKEN)"
}

$Release = Invoke-RestMethod -Uri $ReleaseApiUrl -Headers $ReleaseHeaders -UseBasicParsing
$Asset = $Release.assets |
    Where-Object { $_.name -like "*-x86_64-pc-windows-msvc.zip" } |
    Select-Object -First 1
if (-not $Asset) {
    throw "No x86_64-pc-windows-msvc archive is attached to the mpv git-release tag."
}

$ArchiveName = $Asset.name
$MpvVersion = [System.IO.Path]::GetFileNameWithoutExtension($ArchiveName) -replace "^mpv-", ""
$VersionRoot = Join-Path $ArtifactRoot $MpvVersion
$ArchivePath = Join-Path $VersionRoot $ArchiveName
$ExtractRoot = Join-Path $VersionRoot "extracted"
$MpvPath = Join-Path $ExtractRoot "mpv.exe"
$VulkanPath = Join-Path $ExtractRoot "vulkan-1.dll"

New-Item -ItemType Directory -Path $VersionRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath $ArchivePath)) {
    Write-Host "Downloading $ArchiveName ..."
    Invoke-WebRequest -UseBasicParsing -Uri $Asset.browser_download_url -OutFile $ArchivePath
}

$ActualSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash

# Read the digest through PSObject so StrictMode does not trip if an older API
# response omits the field.
$DigestProperty = $Asset.PSObject.Properties | Where-Object { $_.Name -eq "digest" }
if ($DigestProperty -and $DigestProperty.Value) {
    $ExpectedSha256 = $DigestProperty.Value -replace "^sha256:", ""
    if ($ActualSha256 -ne $ExpectedSha256.ToUpperInvariant()) {
        throw "mpv archive checksum mismatch. Preserve the file for inspection: $ArchivePath"
    }
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
if ($VersionLine -notmatch "^mpv ") {
    throw "Unexpected mpv binary version: $VersionLine"
}

[pscustomobject]@{
    Version = $MpvVersion
    Archive = $ArchivePath
    ArchiveSha256 = $ActualSha256
    Mpv = $MpvPath
    Vulkan = $VulkanPath
}
