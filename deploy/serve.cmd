@echo off
rem Start the local deployment and keep this window open.
rem Double-click this file, or run it from any terminal.
rem The two services detach, so you can close this window afterwards.
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
    echo.
    echo Start failed. See .run\logs\app.err.log and .run\logs\receipts.err.log
)
if "%~1"=="" start "" http://127.0.0.1:8080/
echo.
echo Training page: http://127.0.0.1:8080/
echo Open it with a browser at that address; do NOT open index.html directly.
pause
