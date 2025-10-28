@echo off
REM MUSIQ Image Gallery Creator - Easy Launcher
REM Usage: create_gallery.bat "C:\Path\To\Your\Images"

echo ========================================
echo    MUSIQ Image Gallery Creator
echo ========================================
echo.

if "%~1"=="" (
    echo ERROR: Please provide a folder path
    echo.
    echo Usage: create_gallery.bat "C:\Path\To\Your\Images"
    echo.
    echo Examples:
    echo   create_gallery.bat "D:\Photos\Vacation2025"
    echo   create_gallery.bat "C:\Users\%USERNAME%\Pictures\Recent"
    echo.
    pause
    exit /b 1
)

echo Input folder: %~1
echo.

REM Check if folder exists
if not exist "%~1" (
    echo ERROR: Folder does not exist: %~1
    echo Please check the path and try again.
    echo.
    pause
    exit /b 1
)

echo Starting gallery creation...
echo This may take a while depending on the number of images.
echo.

REM Run the PowerShell script
powershell -ExecutionPolicy Bypass -File "Create-Gallery.ps1" "%~1"

echo.
echo Gallery creation completed!
echo Check your folder for gallery.html
echo.
pause