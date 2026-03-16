@echo off
REM Remove stale log files (logs/, *.log, Firebird logs).
REM No WSL or database required - runs with system Python.
REM
REM Usage: run_cleanup_stale_logs.bat [--dry-run] [--days N] [--all]
REM   --dry-run   Show what would be removed (default: no)
REM   --days N    Remove logs older than N days (default: 7)
REM   --all       Remove all logs regardless of age
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
python scripts/maintenance/cleanup_stale_logs.py %*
pause
