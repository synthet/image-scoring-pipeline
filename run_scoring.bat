@echo off
setlocal

:: If arguments provided, run CLI mode (Drag and Drop)
if not "%~1"=="" (
    echo [Batch] Detected argument: "%~1"
    powershell -ExecutionPolicy Bypass -File "Run-Scoring.ps1" "%~1"
    echo.
    echo Press any key to close...
    pause >nul
    exit /b
)

:: If no arguments, run GUI mode
echo [Batch] No arguments detected. Launching GUI...
python scripts/python/scoring_gui.py

endlocal
