@echo off
REM Backfill EXIF and XMP metadata into IMAGE_EXIF/IMAGE_XMP tables.
REM Runs in WSL with same env as WebUI (requires Firebird connection).
REM
REM Usage: run_backfill_exif_xmp.bat [--limit N] [--folder path] [--dry-run] [--all]
REM By default processes only images without cached EXIF/XMP. Use --all to reprocess everything.
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
setlocal enabledelayedexpansion
set "WSL_PATH=!PROJECT_ROOT:\=/!"
set "WSL_PATH=!WSL_PATH::=!"
set "WSL_PATH=/mnt/!WSL_PATH!"
set "WSL_PATH=!WSL_PATH:/mnt/C=/mnt/c!"
set "WSL_PATH=!WSL_PATH:/mnt/D=/mnt/d!"
set "WSL_PATH=!WSL_PATH:/mnt/E=/mnt/e!"
set "WSL_PATH=!WSL_PATH:/mnt/F=/mnt/f!"
if "!WSL_PATH:~-1!"=="/" set "WSL_PATH=!WSL_PATH:~0,-1!"

wsl bash -c "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:!WSL_PATH!/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib && source ~/.venvs/tf/bin/activate && cd !WSL_PATH! && python scripts/maintenance/backfill_exif_xmp.py %*"
pause
