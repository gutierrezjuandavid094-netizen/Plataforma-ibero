$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectDir
python -m pip install -e ".[build]"
python -m PyInstaller --clean --noconfirm campus_flow.spec
Write-Host "Aplicación generada en $ProjectDir\dist\CampusFlow.exe"
