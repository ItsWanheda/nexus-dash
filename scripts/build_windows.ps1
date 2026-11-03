$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

# Use the interpreter configured by actions/setup-python / the active PATH.
# The Windows py launcher may select a different globally installed version.
$Python = (Get-Command python -ErrorAction Stop).Source
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with exit code $LASTEXITCODE" }

& $Python -m pip install -r requirements-desktop.txt
if ($LASTEXITCODE -ne 0) { throw "Desktop dependency installation failed with exit code $LASTEXITCODE" }

& $Python -m PyInstaller --noconfirm --clean NEXUS-DASH.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed with exit code $LASTEXITCODE" }

$Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($Iscc) {
    & $Iscc.Source "installer\NEXUS-DASH.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed with exit code $LASTEXITCODE" }
} else {
    Write-Warning "Inno Setup was not found; creating a portable ZIP."
    if (Test-Path "dist\NEXUS-DASH-windows-x64.zip") { Remove-Item "dist\NEXUS-DASH-windows-x64.zip" }
    Compress-Archive -Path "dist\NEXUS-DASH\*" -DestinationPath "dist\NEXUS-DASH-windows-x64.zip"
}
