@echo off
setlocal enabledelayedexpansion

REM Resolve project root (script is in scripts/setup/)
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
cd /d "%PROJECT_ROOT%"
set "PROJECT_ROOT=%CD%"

echo.
echo === Windows Native WebUI Setup ===
echo Project root: %PROJECT_ROOT%
echo.

REM 1. Python version check (TF 2.15 needs 3.10-3.12)
echo [1/6] Checking Python version...
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.10 or newer is required. TensorFlow 2.15 needs Python 3.10-3.12.
    python --version 2>nul
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   Python %PYVER% OK.
echo.

REM 2. Create venv
echo [2/6] Creating virtual environment at .venv...
if exist ".venv\Scripts\activate.bat" (
    echo   .venv already exists. Skipping creation.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create .venv
        pause
        exit /b 1
    )
    echo   Created .venv
)
echo.

REM 3. Activate and install requirements
echo [3/6] Installing dependencies from requirements.txt...
call .venv\Scripts\activate.bat
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)
echo.

REM 4. Install PyTorch (CPU default)
echo [4/6] Installing PyTorch (CPU)... 
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo WARNING: PyTorch install failed. LIQE model may not work.
    echo For GPU: pip install torch torchvision
    echo See https://pytorch.org/get-started/locally/
) else (
    echo   PyTorch installed. For GPU: pip install torch torchvision
)
echo.

REM 5. Firebird check
echo [5/6] Checking Firebird binaries...
set "FB_EXE=%PROJECT_ROOT%\Firebird\firebird.exe"
set "FB_DLL=%PROJECT_ROOT%\Firebird\fbclient.dll"
if exist "%FB_EXE%" if exist "%FB_DLL%" (
    echo   Firebird OK: firebird.exe and fbclient.dll found.
) else (
    echo   WARNING: Firebird binaries not found in Firebird\
    echo   Required: firebird.exe, fbclient.dll
    echo   Download: https://firebirdsql.org/en/firebird-5-0/
    echo   Extract Embedded package into Firebird\ folder.
)
echo.

REM 6. Database check
echo [6/6] Checking database...
if exist "%PROJECT_ROOT%\scoring_history.fdb" (
    echo   Database scoring_history.fdb found.
) else (
    echo   Database not found. After setup, run:
    echo     python scripts\migrate_to_firebird.py
    echo   to create the database from SQLite or migrate.
)
echo.

echo === Setup complete ===
echo.
echo To launch the WebUI:
echo   run_webui_windows.bat
echo.
pause
