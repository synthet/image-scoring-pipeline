@echo off
REM Run score analysis script in WSL (same pattern as run_webui.bat)
REM Usage: scripts\run_analysis.bat [--stats] [--distribution] [--spot-check N] [--verify-norm] [-o report.txt]

for %%I in ("%~dp0") do set "SCRIPT_DIR=%%~fI"
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
wsl bash -c "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:!FB_LIB! && source ~/.venvs/tf/bin/activate && cd '!WSL_PATH!' && python scripts/analysis/score_analysis.py %*"
pause
