@echo off
REM Analyze JSON results from MUSIQ batch processing
REM Finds best and worst images overall and by each model

echo ========================================
echo    MUSIQ Results Analyzer
echo    Finding best and worst images
echo ========================================
echo.

REM Get project root
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
set "ANALYZE_DIR=!PROJECT_ROOT!"

REM Check if directory exists
if not exist "!ANALYZE_DIR!" (
    echo ERROR: Directory not found: !ANALYZE_DIR!
    echo.
    pause
    exit /b 1
)

echo Analyzing directory: !ANALYZE_DIR!
echo.

REM Convert to WSL path
set "WSL_PROJECT=!PROJECT_ROOT:\=/!"
set "WSL_PROJECT=!WSL_PROJECT::=!"
set "WSL_PROJECT=/mnt/!WSL_PROJECT!"
set "WSL_PROJECT=!WSL_PROJECT:/mnt/C=/mnt/c!"
set "WSL_PROJECT=!WSL_PROJECT:/mnt/D=/mnt/d!"

REM Run the analysis through WSL2
wsl bash -c "source ~/.venvs/tf/bin/activate && cd !WSL_PROJECT! && python scripts/analysis/analyze_json_results.py --directory '!ANALYZE_DIR!'"

echo.
echo Analysis complete!
echo Check the generated analysis_summary_*.json file for detailed results.
echo.
pause
