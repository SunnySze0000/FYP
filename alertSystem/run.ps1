# WalletLens - one entry point for Windows PowerShell.
#
#   powershell -ExecutionPolicy Bypass -File run.ps1 <command>
#
#   all        setup + tests + connection check + quick trial + full run (the one to use)
#   go         connection check + quick trial + full run (what go.bat runs)
#   quick      small trial of every collector and research suite (about 15-30 min)
#   full       every collector in parallel, then every research suite (several hours)
#   research   rerun every research suite on whatever has been collected
#   wallets    install packages, download event-market trades, run the wallet study (W0-W5)
#   pilot      rebuild the Fed pilot from ..\FYP\tmp\polymarket and research it
#   check      test the internet connections the collectors need
#   test       run the test suite
#   status     show datasets and results
#   daily      rerun the daily-use applicability check D1-D6 (docs/05)
#   app        start EventLens, the event-risk monitor (live)
#
# Safe to stop (Ctrl+C) and rerun at any time: every download resumes from its cache.
# Results: results\OVERVIEW.md (start here), results\<run>\summary.md, logs\ for details.

param([Parameter(Position = 0)][string]$Command = "help")

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
Set-Location $PSScriptRoot

$py = $null
foreach ($candidate in @("python", "py", "python3")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) { $py = $candidate; break }
}
if (-not $py) { Write-Host "Python not found on PATH. Open an Anaconda Prompt and run this again." -ForegroundColor Red; exit 1 }

function Step($name, [scriptblock]$block, [switch]$Soft) {
    Write-Host ""
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $name" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) {
        if ($Soft) { Write-Host "WARNING: $name reported a problem; continuing." -ForegroundColor Yellow; return }
        Write-Host "FAILED: $name (exit $LASTEXITCODE). Send Claude the red lines above; rerunning resumes from the cache." -ForegroundColor Red
        exit 1
    }
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] done: $name" -ForegroundColor Green
}

function Setup { Step "install packages" { & $py -m pip install --quiet -r requirements.txt } }
function Tests { Step "tests" { & $py -m pytest -q tests } }
function Check { Step "connection check" { & $py -m walletlens check } }
function Quick { Step "quick trial: all collectors + research (small)" { & $py -m walletlens --profile quick run-all } }
function Full  { Step "full run: all collectors in parallel + research (hours)" { & $py -m walletlens run-all } }

switch ($Command) {
    "all"      { Setup; Tests; Check; Quick; Full; Write-Host "`nAll done. Open results\OVERVIEW.md" -ForegroundColor Green }
    "go"       { Check; Quick; Full; Write-Host "`nAll done. Open results\OVERVIEW.md" -ForegroundColor Green }
    "quick"    { Quick }
    "full"     { Full }
    "research" { Step "research on collected data" { & $py -m walletlens run-all --no-collect } }
    "wallets"  {
        Setup
        Step "event-market trades" { & $py -m walletlens collect --topic events --stages trades,trades_build }
        Step "wallet study W0-W5" { & $py -m walletlens research --topic wallets }
    }
    "pilot"    {
        $source = Join-Path $PSScriptRoot "..\FYP\tmp\polymarket"
        Step "Fed pilot" { & $py -m walletlens pilot --source $source }
    }
    "check"    { Check }
    "test"     { Tests }
    "setup"    { Setup }
    "status"   { & $py -m walletlens status }
    "daily"    { Step "daily-use check D1-D6" { & $py -m walletlens research --topic daily }; Step "export monitor model" { & $py -m walletlens export } }
    "app"      { & $py -m walletlens app }
    default    { Get-Content $PSCommandPath | Select-Object -First 20 | ForEach-Object { $_ -replace "^# ?", "" } }
}
