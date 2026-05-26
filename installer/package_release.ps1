$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Version = "0.1.0"
$DistDir = Join-Path $Root "dist\GodTierBot"
$OutDir = Join-Path $Root "release_out"

if (Test-Path $OutDir) {
  Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Path $OutDir | Out-Null

$ZipPath = Join-Path $OutDir ("GodTierBot_app_" + $Version + ".zip")
Compress-Archive -Path (Join-Path $DistDir "*") -DestinationPath $ZipPath

$InstallerExe = Join-Path $OutDir ("GodTierBot_Setup_" + $Version + ".exe")

Write-Output $ZipPath
Write-Output $InstallerExe
