# ICS Beta launcher. An occupied port is an error; existing processes are never killed.
[CmdletBinding()]
param(
    [string]$Config = "config/cameras.lhires-dual-zwo.example.json",
    [string]$SdkLibrary = $env:ICS_ZWO_SDK_LIBRARY,
    [switch]$ForceSim,
    [ValidateRange(1, 65535)][int]$Port = 8123,
    [switch]$NoBrowser,
    [string]$Python = ""
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot
if (-not $Python) {
    $localPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) { $Python = $localPython }
    else {
        $command = Get-Command python -ErrorAction SilentlyContinue
        if ($command -and $command.Source -notmatch 'WindowsApps') { $Python = $command.Source }
    }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    throw 'Python unavailable. Create .venv and install .[dev], or pass -Python with an installed interpreter.'
}
if (-not (Test-Path -LiteralPath $Config)) { throw "Camera config not found: $Config" }
if (-not $ForceSim -and $SdkLibrary -and -not (Test-Path -LiteralPath $SdkLibrary)) {
    throw "ZWO SDK not found: $SdkLibrary. Supply -SdkLibrary or explicitly use -ForceSim."
}
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw "Port $Port is occupied. Stop the existing service gracefully or choose -Port." }
$env:ICS_BETA_CAMERA_CONFIG = (Resolve-Path -LiteralPath $Config).Path
if ($SdkLibrary) { $env:ICS_ZWO_SDK_LIBRARY = $SdkLibrary }
$env:PYTHONPATH = Join-Path $RepoRoot 'src'
$env:PYTHONUNBUFFERED = '1'
if ($ForceSim) { $env:ICS_BETA_FORCE_SIM = '1' }
else { Remove-Item Env:ICS_BETA_FORCE_SIM -ErrorAction SilentlyContinue }
Write-Host "ICS Beta: http://127.0.0.1:$Port/ui/v7 (Ctrl-C stops gracefully)"
Write-Host "Profile: $env:ICS_BETA_CAMERA_CONFIG"
if ($ForceSim) { Write-Host 'Explicit simulation mode; frames are simulated.' }
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/ui/v7" }
& $Python -m uvicorn justls.ics.app.main:app --host 127.0.0.1 --port $Port
