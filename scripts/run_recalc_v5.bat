@echo off
REM Recalculate all scores using v5.0 percentile normalization
REM Runs in WSL with the same environment as the WebUI
REM Usage: scripts\run_recalc_v5.bat [--dry-run]

for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
setlocal enabledelayedexpansion
set "WSL_PATH=!PROJECT_ROOT:\=/!"
set "WSL_PATH=!WSL_PATH::=!"
set "WSL_PATH=/mnt/!WSL_PATH!"
set "WSL_PATH=!WSL_PATH:/mnt/C=/mnt/c!"
set "WSL_PATH=!WSL_PATH:/mnt/D=/mnt/d!"
set "WSL_PATH=!WSL_PATH:/mnt/E=/mnt/e!"
set "WSL_PATH=!WSL_PATH:/mnt/F=/mnt/f!"
if "!WSL_PATH:~-1!"=="/" set "WSL_PATH=!WSL_PATH:~0,-1!"
set "FB_LIB=!WSL_PATH!/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib"
wsl bash -c "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:!FB_LIB! && source ~/.venvs/tf/bin/activate && cd '!WSL_PATH!' && python scripts/python/recalc_scores_v5.py %*"
