@echo off
echo Check for Admin rights...
NET SESSION >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo ==================================================
echo   Configuring Windows Firewall for Firebird
echo ==================================================
echo.

echo Opening TCP Port 3050 (Inbound)...
powershell -Command "New-NetFirewallRule -DisplayName 'Firebird SQL Server' -Direction Inbound -LocalPort 3050 -Protocol TCP -Action Allow -Profile Any"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Firewall rule added successfully!
) else (
    echo.
    echo [ERROR] Failed to add firewall rule.
)

echo.
echo You can now close this window and run the WebUI.
pause
