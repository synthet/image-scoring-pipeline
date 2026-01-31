@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    Model Sources Test Script
echo    TensorFlow Hub + Kaggle Hub
echo ========================================
echo.

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

REM Check if we're in WSL environment or Windows
where wsl >nul 2>&1
if %errorlevel% == 0 (
    echo Using WSL environment for testing...
    echo.
    
    REM Parse command line arguments
    set "ARGS="
    
    :parse_args
    if "%~1"=="" goto end_parse
    if "%~1"=="--test-kaggle" set "ARGS=!ARGS! --test-kaggle"
    if "%~1"=="--skip-download" set "ARGS=!ARGS! --skip-download"
    if "%~1"=="--verbose" set "ARGS=!ARGS! --verbose"
    shift
    goto parse_args
    
    :end_parse
    
    REM Get project root (scripts/batch -> project root)
    for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
    REM Convert to WSL path format
    set "WSL_PATH=!PROJECT_ROOT:\=/!"
    set "WSL_PATH=!WSL_PATH::=!"
    set "WSL_PATH=/mnt/!WSL_PATH!"
    for %%A in (A B C D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
        call set "WSL_PATH=%%WSL_PATH:%%A=%%A%%"
    )
    call :LowerCase WSL_PATH
    
    REM Run test in WSL with TensorFlow virtual environment
    wsl bash -c "source ~/.venvs/tf/bin/activate && cd !WSL_PATH! && python tests/test_model_sources.py !ARGS!"
    goto :eof
    
:LowerCase
    set "%~1=!%~1:A=a!"
    set "%~1=!%~1:B=b!"
    set "%~1=!%~1:C=c!"
    set "%~1=!%~1:D=d!"
    set "%~1=!%~1:E=e!"
    set "%~1=!%~1:F=f!"
    set "%~1=!%~1:G=g!"
    set "%~1=!%~1:H=h!"
    set "%~1=!%~1:I=i!"
    set "%~1=!%~1:J=j!"
    set "%~1=!%~1:K=k!"
    set "%~1=!%~1:L=l!"
    set "%~1=!%~1:M=m!"
    set "%~1=!%~1:N=n!"
    set "%~1=!%~1:O=o!"
    set "%~1=!%~1:P=p!"
    set "%~1=!%~1:Q=q!"
    set "%~1=!%~1:R=r!"
    set "%~1=!%~1:S=s!"
    set "%~1=!%~1:T=t!"
    set "%~1=!%~1:U=u!"
    set "%~1=!%~1:V=v!"
    set "%~1=!%~1:W=w!"
    set "%~1=!%~1:X=x!"
    set "%~1=!%~1:Y=y!"
    set "%~1=!%~1:Z=z!"
    goto :eof
) else (
    echo Using Windows Python environment for testing...
    echo Warning: TensorFlow may not be properly configured in Windows.
    echo WSL is recommended for accurate testing.
    echo.
    
    REM Run test with Windows Python
    python "%~dp0..\..\tests\test_model_sources.py" %*
)

echo.
echo Press any key to exit...
pause >nul

