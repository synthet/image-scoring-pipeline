@echo off
REM Complete AI Keyword Extraction and XMP Sidecar Creation Tool
REM Usage: complete_keyword_extraction.bat "C:\Path\To\NEF\Folder" [output_folder] [confidence_threshold] [create_xmp]

setlocal enabledelayedexpansion

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python and try again
    pause
    exit /b 1
)

REM Check if input directory is provided
if "%~1"=="" (
    echo Usage: complete_keyword_extraction.bat "C:\Path\To\NEF\Folder" [output_folder] [confidence_threshold] [create_xmp]
    echo.
    echo Examples:
    echo   complete_keyword_extraction.bat "D:\Photos\NEF_Files"
    echo   complete_keyword_extraction.bat "D:\Photos\NEF_Files" "D:\Keywords"
    echo   complete_keyword_extraction.bat "D:\Photos\NEF_Files" "D:\Keywords" 0.05
    echo   complete_keyword_extraction.bat "D:\Photos\NEF_Files" "D:\Keywords" 0.05 true
    echo.
    echo Parameters:
    echo   create_xmp: true/false - whether to create XMP sidecar files for NEF files
    echo.
    echo Features:
    echo   - AI-powered keyword extraction using BLIP + CLIP
    echo   - Automatic caption generation
    echo   - XMP sidecar file creation for NEF files
    echo   - JSON output with confidence scores
    echo   - Batch processing support
    pause
    exit /b 1
)

set INPUT_DIR=%~1
set OUTPUT_DIR=%~2
set CONFIDENCE_THRESHOLD=%~3
set CREATE_XMP=%~4

REM Set default values if not provided
if "%CONFIDENCE_THRESHOLD%"=="" set CONFIDENCE_THRESHOLD=0.03
if "%CREATE_XMP%"=="" set CREATE_XMP=false

REM Check if input directory exists
if not exist "%INPUT_DIR%" (
    echo Error: Input directory does not exist: %INPUT_DIR%
    pause
    exit /b 1
)

echo ========================================
echo Complete AI Keyword Extraction Tool
echo ========================================
echo Input Directory: %INPUT_DIR%
if not "%OUTPUT_DIR%"=="" (
    echo Output Directory: %OUTPUT_DIR%
) else (
    echo Output Directory: %INPUT_DIR% (same as input)
)
echo Confidence Threshold: %CONFIDENCE_THRESHOLD%
echo Create XMP Sidecar Files: %CREATE_XMP%
echo ========================================
echo.

REM Check if complete keyword extractor script exists
if not exist "scripts\python\complete_keyword_extractor.py" (
    echo Error: complete_keyword_extractor.py not found
    echo Please ensure you're running this from the project root directory
    pause
    exit /b 1
)

REM Build the Python command
set PYTHON_CMD=python scripts\python\complete_keyword_extractor.py --input-dir "%INPUT_DIR%" --confidence-threshold %CONFIDENCE_THRESHOLD%

if not "%OUTPUT_DIR%"=="" (
    set PYTHON_CMD=!PYTHON_CMD! --output-dir "%OUTPUT_DIR%"
)

if "%CREATE_XMP%"=="true" (
    set PYTHON_CMD=!PYTHON_CMD! --create-xmp
)

echo Running complete keyword extraction...
echo Command: !PYTHON_CMD!
echo.

REM Run the complete keyword extraction
!PYTHON_CMD!

if errorlevel 1 (
    echo.
    echo Error: Keyword extraction failed
    echo Please check the error messages above
) else (
    echo.
    echo Complete keyword extraction finished successfully!
    if "%CREATE_XMP%"=="true" (
        echo XMP sidecar files have been created for NEF files
        echo These files can be read by Adobe Lightroom, Photoshop, and other photo management software
    )
    echo.
    echo Output files created:
    echo   - Individual keyword JSON files for each image
    echo   - Batch processing summary JSON file
    if "%CREATE_XMP%"=="true" (
        echo   - XMP sidecar files for NEF files
    )
)

echo.
pause
