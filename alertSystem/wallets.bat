@echo off
rem Double-click: download trades of the event markets and run the wallet study (W0-W5).
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0run.ps1" wallets
