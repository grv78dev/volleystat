@echo off
REM VolleyStat - Avvia l'applicazione (Windows)
REM Esegui con doppio click, oppure da cmd/PowerShell: run.bat

setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ATTENZIONE] Ambiente virtuale non trovato.
    echo Esegui prima: install.bat
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo    VolleyStat - Avvio...
echo    Locale:  http://127.0.0.1:8000
echo    Tablet:  vedi IP mostrato all'avvio
echo    Ctrl+C per uscire
echo ============================================
echo.

".venv\Scripts\python.exe" app.py

pause
