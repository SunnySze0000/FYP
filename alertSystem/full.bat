@echo off
rem Double-click to run the full collection and research (skips the quick trial).
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0run.ps1" full
