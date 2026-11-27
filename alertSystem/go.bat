@echo off
rem Double-click to run: connection check, quick trial, then the full run.
rem Progress and errors are also written to logs\.
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0run.ps1" go
