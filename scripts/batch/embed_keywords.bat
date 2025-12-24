@echo off
REM Enhanced batch script for keyword extraction and embedding in NEF files
REM Usage: embed_keywords.bat "C:\Path\To\NEF\Folder" [output_folder] [confidence_threshold] [embed_keywords]

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
    echo Usage: embed_keywords.bat "C:\Path\To\NEF\Folder" [output_folder] [confidence_threshold] [embed_keywords]
    echo.
    echo Examples:
    echo   embed_keywords.bat "D:\Photos\NEF_Files"
    echo   embed_keywords.bat "D:\Photos\NEF_Files" "D:\Keywords"
    echo   embed_keywords.bat "D:\Photos\NEF_Files" "D:\Keywords" 0.05
    echo   embed_keywords.bat "D:\Photos\NEF_Files" "D:\Keywords" 0.05 true
    echo.
    echo Parameters:
    echo   embed_keywords: true/false - whether to embed keywords directly in NEF files
    pause
    exit /b 1
)

set INPUT_DIR=%~1
set OUTPUT_DIR=%~2
set CONFIDENCE_THRESHOLD=%~3
set EMBED_KEYWORDS=%~4

REM Set default values if not provided
if "%CONFIDENCE_THRESHOLD%"=="" set CONFIDENCE_THRESHOLD=0.03
if "%EMBED_KEYWORDS%"=="" set EMBED_KEYWORDS=false

REM Check if input directory exists
if not exist "%INPUT_DIR%" (
    echo Error: Input directory does not exist: %INPUT_DIR%
    pause
    exit /b 1
)

echo ========================================
echo NEF Keyword Embedder Tool
echo ========================================
echo Input Directory: %INPUT_DIR%
if not "%OUTPUT_DIR%"=="" (
    echo Output Directory: %OUTPUT_DIR%
) else (
    echo Output Directory: %INPUT_DIR% (same as input)
)
echo Confidence Threshold: %CONFIDENCE_THRESHOLD%
echo Embed Keywords in NEF: %EMBED_KEYWORDS%
echo ========================================
echo.

REM Check if keyword embedder script exists
if not exist "scripts\python\nef_keyword_embedder.py" (
    echo Error: nef_keyword_embedder.py not found
    echo Please ensure you're running this from the project root directory
    pause
    exit /b 1
)

REM Build the Python command
set PYTHON_CMD=python scripts\python\nef_keyword_embedder.py --input-dir "%INPUT_DIR%" --confidence-threshold %CONFIDENCE_THRESHOLD%

if not "%OUTPUT_DIR%"=="" (
    set PYTHON_CMD=!PYTHON_CMD! --output-dir "%OUTPUT_DIR%"
)

if "%EMBED_KEYWORDS%"=="true" (
    set PYTHON_CMD=!PYTHON_CMD! --embed-keywords
)

echo Running keyword extraction and embedding...
echo Command: !PYTHON_CMD!
echo.

REM Run the keyword extraction and embedding
!PYTHON_CMD!

if errorlevel 1 (
    echo.
    echo Error: Keyword extraction/embedding failed
    echo Please check the error messages above
) else (
    echo.
    echo Keyword extraction and embedding completed successfully!
    if "%EMBED_KEYWORDS%"=="true" (
        echo Keywords have been embedded directly into NEF files
        echo Original files have been backed up with .backup extension
    )
)

echo.
pause
