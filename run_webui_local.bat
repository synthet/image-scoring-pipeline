@echo off
REM WebUI using local Firebird path (bypasses Windows Firebird server).
REM Use when inet connection fails with "file in use" or similar.
REM If you get "no permission", close any Firebird process first (Task Manager).
for %%I in ("%~dp0") do set "PROJECT_ROOT=%%~fI"
setlocal enabledelayedexpansion
set "WSL_PATH=!PROJECT_ROOT:\=/!"
set "WSL_PATH=!WSL_PATH::=!"
set "WSL_PATH=/mnt/!WSL_PATH!"
set "WSL_PATH=!WSL_PATH:/mnt/C=/mnt/c!"
set "WSL_PATH=!WSL_PATH:/mnt/D=/mnt/d!"
set "WSL_PATH=!WSL_PATH:/mnt/E=/mnt/e!"
set "WSL_PATH=!WSL_PATH:/mnt/F=/mnt/f!"
if "!WSL_PATH:~-1!"=="/" set "WSL_PATH=!WSL_PATH:~0,-1!"

wsl bash -c "export FIREBIRD_USE_LOCAL_PATH=1 && export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:!WSL_PATH!/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib && export ENABLE_MCP_SERVER=${ENABLE_MCP_SERVER:-1} && source ~/.venvs/tf/bin/activate && python launch.py %*"
pause
