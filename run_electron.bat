@echo off
REM Get project root
for %%I in ("%~dp0") do set "PROJECT_ROOT=%%~fI"

REM Navigate to electron-gallery directory
cd /d "%PROJECT_ROOT%electron-gallery"

REM Run the electron app
npm run dev

pause
