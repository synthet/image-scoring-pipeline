@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  NEF Folder Processor
echo  MUSIQ + VILA Multi-Model Scoring
echo  + Nikon NEF Rating (1-5 stars)
echo ========================================
echo.

REM Check if folder path is provided
if "%~1"=="" (
    echo Usage: Drag and drop a folder containing NEF files onto this script
    echo.
    echo Or use: process_nef_folder.bat "C:\Path\To\Your\NEF\Folder"
    echo.
    pause
    exit /b 1
)

set "INPUT_FOLDER=%~1"

echo Processing folder: %INPUT_FOLDER%
echo.

REM Check if input folder exists
if not exist "%INPUT_FOLDER%" (
    echo ERROR: Folder does not exist: %INPUT_FOLDER%
    echo.
    pause
    exit /b 1
)

echo Step 1: Processing NEF files with MUSIQ models and rating...
echo.

REM Use WSL environment for processing
set "WSL_PATH=%INPUT_FOLDER%"
set "WSL_PATH=!WSL_PATH:\=/mnt/!"
set "WSL_PATH=!WSL_PATH:C:=c!"
set "WSL_PATH=!WSL_PATH:D:=d!"
set "WSL_PATH=!WSL_PATH:E:=e!"
set "WSL_PATH=!WSL_PATH:F:=f!"
set "WSL_PATH=!WSL_PATH:G:=g!"
set "WSL_PATH=!WSL_PATH:H:=h!"
set "WSL_PATH=!WSL_PATH:I:=i!"
set "WSL_PATH=!WSL_PATH:J:=j!"
set "WSL_PATH=!WSL_PATH:K:=k!"
set "WSL_PATH=!WSL_PATH:L:=l!"
set "WSL_PATH=!WSL_PATH:M:=m!"
set "WSL_PATH=!WSL_PATH:N:=n!"
set "WSL_PATH=!WSL_PATH:O:=o!"
set "WSL_PATH=!WSL_PATH:P:=p!"
set "WSL_PATH=!WSL_PATH:Q:=q!"
set "WSL_PATH=!WSL_PATH:R:=r!"
set "WSL_PATH=!WSL_PATH:S:=s!"
set "WSL_PATH=!WSL_PATH:T:=t!"
set "WSL_PATH=!WSL_PATH:U:=u!"
set "WSL_PATH=!WSL_PATH:V:=v!"
set "WSL_PATH=!WSL_PATH:W:=w!"
set "WSL_PATH=!WSL_PATH:X:=x!"
set "WSL_PATH=!WSL_PATH:Y:=y!"
set "WSL_PATH=!WSL_PATH:Z:=z!"

wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python scripts/python/batch_process_images.py --input-dir '!WSL_PATH!' --output-dir '!WSL_PATH!' --rate-nef"

echo.
echo Step 2: Generating HTML gallery...
echo.

REM Run the Python gallery generator
python "scripts\python\gallery_generator.py" "%INPUT_FOLDER%"

echo.
echo [SUCCESS] Processing completed!
echo Output file: %INPUT_FOLDER%\gallery.html
echo.

REM Open the gallery
if exist "%INPUT_FOLDER%\gallery.html" (
    echo Opening gallery in your default web browser...
    start "" "%INPUT_FOLDER%\gallery.html"
) else (
    echo [ERROR] Gallery file not found
)

echo.
pause
