@echo off
echo Debug: Argument 1 is: "%~1"
echo Debug: Argument 1 length: %~1
if "%~1"=="" (
    echo DEBUG: No argument provided
    pause
    exit /b 1
) else (
    echo DEBUG: Argument provided: "%~1"
    set "INPUT_FOLDER=%~1"
    echo DEBUG: INPUT_FOLDER set to: "%INPUT_FOLDER%"
    echo DEBUG: Folder exists check...
    if not exist "%INPUT_FOLDER%" (
        echo DEBUG: Folder does not exist: "%INPUT_FOLDER%"
    ) else (
        echo DEBUG: Folder exists! Processing...
    )
)
pause
