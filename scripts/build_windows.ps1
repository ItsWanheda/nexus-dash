$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
py -m pip install --upgrade pip
py -m pip install -r requirements-desktop.txt
py -m PyInstaller --noconfirm --clean NEXUS-DASH.spec
$Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($Iscc) {
    & $Iscc.Source "installer\NEXUS-DASH.iss"
} else {
    Write-Warning "Inno Setup was not found; creating a portable ZIP."
    if (Test-Path "dist\NEXUS-DASH-windows-x64.zip") { Remove-Item "dist\NEXUS-DASH-windows-x64.zip" }
    Compress-Archive -Path "dist\NEXUS-DASH\*" -DestinationPath "dist\NEXUS-DASH-windows-x64.zip"
}
