$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"

if (-not (Test-Path $Venv)) {
  python -m venv $Venv
}

& (Join-Path $Venv "Scripts\python.exe") -m pip install --upgrade pip
& (Join-Path $Venv "Scripts\python.exe") -m pip install -r (Join-Path $Root "requirements.txt")

$WinReq = Join-Path $Root "requirements-windows-mt5.txt"
if (Test-Path $WinReq) {
  & (Join-Path $Venv "Scripts\python.exe") -m pip install -r $WinReq
}

& (Join-Path $Venv "Scripts\python.exe") -m pip install pyinstaller

$Spec = Join-Path $PSScriptRoot "godtierbot.spec"
& (Join-Path $Venv "Scripts\pyinstaller.exe") --noconfirm --clean $Spec
