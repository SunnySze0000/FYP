@echo off
rem Double-click: D4 live feasibility check (about 1 minute). Result in results\<time>_live_check\summary.md
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
set PYTHONUTF8=1
python -m walletlens live-check
