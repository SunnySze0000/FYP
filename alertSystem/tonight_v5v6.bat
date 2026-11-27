@echo off
rem ===================================================================
rem TEMPORARY (H2: delete after V5 and V6 are done). Tonight's downloads.
rem   V6: 5-minute bars, last 60 days        (minutes)  -> FYP\alertSystem\data\raw\prices_5m
rem   V5: full Polymarket event universe     (hours)    -> fyptest1\data (where the download cache is)
rem Safe to stop with Ctrl+C and run again: every step resumes from its cache.
rem Keep the laptop plugged in and stop it from sleeping while this runs.
rem ===================================================================
cd /d "%~dp0"
set "APP=%~dp0"
set "DATA=%~dp0..\..\fyptest1"
set "PYTHONPATH=%APP%src"
set PYTHONUTF8=1
echo.
echo [1/5] V6: 5-minute bars (a few minutes)
python scripts\v6_download_5m.py "%APP%."
echo.
echo [2/5] V5: back up the current events dataset (once)
if not exist "%DATA%\data\processed\events_before_v5" xcopy /E /I /Y "%DATA%\data\processed\events" "%DATA%\data\processed\events_before_v5" >nul
set "WALLETLENS_HOME=%DATA%"
echo.
echo [3/5] V5: refresh the Polymarket market list (resumes)
python -m walletlens --profile v5 collect --topic polymarket --stages universe
echo.
echo [4/5] V5: event markets - assets, hourly prices, dataset (hours, resumes)
python -m walletlens --profile v5 collect --topic events --stages assets,prices,build
echo.
echo [5/5] V5: event-market trades for the wallet layer (longest; fine to stop and resume another night)
python -m walletlens --profile v5 collect --topic events --stages trades,trades_build
echo.
echo All done. Tell Claude: "V5 and V6 finished".
pause
