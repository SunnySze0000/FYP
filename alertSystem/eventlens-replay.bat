@echo off
rem Double-click: EventLens on the research data as it was on 13 Jun 2025 02:30 UTC (Israel strikes Iran).
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
set PYTHONUTF8=1
python -m walletlens app --replay 2025-06-13T02:30 --port 8766
