# ICS Beta — PowerShell launcher
#
# Usage (from the repo root):
#     .\start_ics.ps1                 # default: lhires-dual-zwo profile
#     .\start_ics.ps1 -ForceSim       # safe mode (no SDK calls)
#     .\start_ics.ps1 -Config path\to\cameras.json
#     .\start_ics.ps1 -Port 9000
#     .\start_ics.ps1 -NoBrowser      # do not open the browser
#
# The script stops any process already listening on the target port,
# frees that handle, then starts uvicorn. It does not touch any other
# service. Keep this file next to the repository's `.env.example` so
# operators can find it without searching.

[CmdletBinding()]
param(
    [string]$Config = "config/cameras.lhires-dual-zwo.example.json",
    [string]$SdkLibrary = "F:\ASIStudio\ASICamera2.dll",
    [switch]$ForceSim,
    [int]$Port = 8123,
    [switch]$NoBrowser,
    [string]$Python = "C:\Users\UmutMahmut\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

# --- pre-flight --------------------------------------------------------------

if (-not (Test-Path $Python)) {
    throw "Python not found at $Python. Pass -Python to use a different interpreter."
}

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

if (-not (Test-Path $Config)) {
    throw "Camera config not found: $Config (cwd: $(Get-Location))"
}

if (-not $ForceSim -and -not (Test-Path $SdkLibrary)) {
    Write-Warning "ZWO SDK not found at $SdkLibrary. Pass -ForceSim to run in safe mode, or fix the path."
    Write-Warning "Falling back to ICS_BETA_FORCE_SIM=1 for this session."
    $ForceSim = $true
}

# --- free the port if a previous service is bound to it --------------------

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    foreach ($conn in $listener) {
        $pid = $conn.OwningProcess
        try {
            Write-Host "Stopping existing listener (PID=$pid) on port $Port"
            Stop-Process -Id $pid -Force -ErrorAction Stop
        } catch {
            Write-Warning "Could not stop PID=$pid ($($_.Exception.Message)). Another process may still hold the port."
        }
    }
    Start-Sleep -Seconds 1
}

# --- env wiring -------------------------------------------------------------

$env:ICS_BETA_CAMERA_CONFIG = (Resolve-Path $Config).Path
$env:ICS_ZWO_SDK_LIBRARY     = $SdkLibrary
$env:PYTHONUNBUFFERED        = "1"
if ($ForceSim) {
    $env:ICS_BETA_FORCE_SIM = "1"
} else {
    Remove-Item Env:ICS_BETA_FORCE_SIM -ErrorAction SilentlyContinue
}

# --- launch -----------------------------------------------------------------

Write-Host ""
Write-Host "ICS Beta starting on http://127.0.0.1:$Port/ui/v7"
Write-Host "  config    : $env:ICS_BETA_CAMERA_CONFIG"
Write-Host "  SDK       : $env:ICS_ZWO_SDK_LIBRARY"
if ($ForceSim) {
    Write-Host "  mode      : SAFE MODE (ICS_BETA_FORCE_SIM=1) — no SDK calls"
}
Write-Host "  press Ctrl-C in this window to stop the service."
Write-Host ""

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:$Port/ui/v7"
}

& $Python -m uvicorn justls.ics.app.main:app --host 127.0.0.1 --port $Port
