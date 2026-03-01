@echo off
REM Wrapper for cleanup_orphans.py
REM Usage: cleanup.bat [--force] [-v]

python "%~dp0maintenance\cleanup_orphans.py" %*
if %ERRORLEVEL% NEQ 0 (
    echo Cleanup script failed with error level %ERRORLEVEL%
)
pause
