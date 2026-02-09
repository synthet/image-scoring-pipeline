@echo off
REM Remove test run artifacts (temp dirs, output dirs, log files)
cd /d "%~dp0\..\.."
python scripts\maintenance\cleanup_test_artifacts.py %*
pause
