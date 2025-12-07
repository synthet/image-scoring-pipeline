@echo off
REM Batch script for keyword extraction from NEF files
REM Usage: extract_keywords.bat "C:\Path\To\NEF\Folder" [output_folder] [confidence_threshold]

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
    echo Usage: extract_keywords.bat "C:\Path\To\NEF\Folder" [output_folder] [confidence_threshold]
    echo.
    echo Examples:
    echo   extract_keywords.bat "D:\Photos\NEF_Files"
    echo   extract_keywords.bat "D:\Photos\NEF_Files" "D:\Keywords"
    echo   extract_keywords.bat "D:\Photos\NEF_Files" "D:\Keywords" 0.05
    pause
    exit /b 1
)

set INPUT_DIR=%~1
set OUTPUT_DIR=%~2
set CONFIDENCE_THRESHOLD=%~3

REM Set default confidence threshold if not provided
if "%CONFIDENCE_THRESHOLD%"=="" set CONFIDENCE_THRESHOLD=0.03

REM Check if input directory exists
if not exist "%INPUT_DIR%" (
    echo Error: Input directory does not exist: %INPUT_DIR%
    pause
    exit /b 1
)

echo ========================================
echo Keyword Extraction Tool
echo ========================================
echo Input Directory: %INPUT_DIR%
if not "%OUTPUT_DIR%"=="" (
    echo Output Directory: %OUTPUT_DIR%
) else (
    echo Output Directory: %INPUT_DIR% (same as input)
)
echo Confidence Threshold: %CONFIDENCE_THRESHOLD%
echo ========================================
echo.

REM Check if keyword extraction script exists
if not exist "scripts\python\keyword_extractor.py" (
    echo Error: keyword_extractor.py not found
    echo Please ensure you're running this from the project root directory
    pause
    exit /b 1
)

REM Build the Python command
set PYTHON_CMD=python scripts\python\keyword_extractor.py --input-dir "%INPUT_DIR%" --confidence-threshold %CONFIDENCE_THRESHOLD%

if not "%OUTPUT_DIR%"=="" (
    set PYTHON_CMD=!PYTHON_CMD! --output-dir "%OUTPUT_DIR%"
)

echo Running keyword extraction...
echo Command: !PYTHON_CMD!
echo.

REM Run the keyword extraction
!PYTHON_CMD!

if errorlevel 1 (
    echo.
    echo Error: Keyword extraction failed
    echo Please check the error messages above
) else (
    echo.
    echo Keyword extraction completed successfully!
)

echo.
pause
