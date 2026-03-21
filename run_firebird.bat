@echo off
setlocal
REM Run from the Firebird install dir so relative paths in firebird.conf resolve consistently.
cd /d "%~dp0Firebird"
if not exist "temp\" mkdir temp
echo Starting Firebird Server in Application Mode...
echo Firebird dir: %CD%
echo Press Ctrl+C to stop.
firebird.exe -a -p 3050
