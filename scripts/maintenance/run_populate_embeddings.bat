@echo off
REM Populate missing embeddings in DB. Runs in WSL with same env as WebUI.
REM Get project root (parent of scripts)
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
REM Convert to WSL path
setlocal enabledelayedexpansion
set "WSL_PATH=!PROJECT_ROOT:\=/!"
set "WSL_PATH=!WSL_PATH::=!"
set "WSL_PATH=/mnt/!WSL_PATH!"
set "WSL_PATH=!WSL_PATH:/mnt/C=/mnt/c!"
set "WSL_PATH=!WSL_PATH:/mnt/D=/mnt/d!"
set "WSL_PATH=!WSL_PATH:/mnt/E=/mnt/e!"
set "WSL_PATH=!WSL_PATH:/mnt/F=/mnt/f!"
REM Remove trailing slash if present
if "!WSL_PATH:~-1!"=="/" set "WSL_PATH=!WSL_PATH:~0,-1!"

wsl bash -c "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:!WSL_PATH!/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib && source ~/.venvs/tf/bin/activate && cd !WSL_PATH! && python scripts/maintenance/populate_missing_embeddings.py %*"
pause
