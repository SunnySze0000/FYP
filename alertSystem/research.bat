@echo off
rem Double-click to rerun all research on the data already collected (no downloads).
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0run.ps1" research
