@echo off
REM VolleyStat - Script di installazione per Windows
REM Esegui con doppio click, oppure da cmd/PowerShell: install.bat

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ============================================
echo    VolleyStat - Installazione (Windows)
echo ============================================
echo.

REM --- Cerca un interprete Python funzionante (py launcher, poi python) ---
set "PYTHON="

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 --version >nul 2>nul
    if %errorlevel%==0 set "PYTHON=py -3"
)

if not defined PYTHON (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python --version >nul 2>nul
        if %errorlevel%==0 set "PYTHON=python"
    )
)

if not defined PYTHON (
    echo [ERRORE] Python non trovato.
    echo.
    echo Installa Python da https://www.python.org/downloads/windows/
    echo IMPORTANTE: nella prima schermata dell'installer spunta
    echo             "Add python.exe to PATH" prima di procedere.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('%PYTHON% --version 2^>^&1') do set "PYVER=%%v"
echo [OK] Python trovato: %PYVER% (%PYTHON%)

REM --- Verifica che il modulo venv sia disponibile ---
%PYTHON% -m venv --help >nul 2>nul
if not %errorlevel%==0 (
    echo [ERRORE] Il modulo "venv" non e' disponibile in questa installazione di Python.
    echo Reinstalla Python da python.org lasciando le opzioni di default
    echo ^(includono pip e venv^), oppure ripara l'installazione esistente.
    pause
    exit /b 1
)

REM --- Crea l'ambiente virtuale in .venv se non esiste ---
if not exist ".venv\" (
    echo [..] Creo ambiente virtuale ^(.venv^)...
    %PYTHON% -m venv .venv
) else (
    echo [OK] Ambiente virtuale gia' presente
)

REM --- Verifica che pip funzioni nel venv, altrimenti lo ricrea ---
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if not %errorlevel%==0 (
    echo [!!] pip non funziona nel venv, lo ricreo...
    rmdir /s /q ".venv"
    %PYTHON% -m venv .venv
)

REM --- Installa Flask nell'ambiente virtuale ---
echo [..] Installo Flask...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet flask

if not %errorlevel%==0 (
    echo [ERRORE] Installazione di Flask fallita. Controlla la connessione internet.
    pause
    exit /b 1
)

echo.
echo [OK] Installazione completata!
echo.
echo Per avviare VolleyStat: run.bat
echo.
pause
