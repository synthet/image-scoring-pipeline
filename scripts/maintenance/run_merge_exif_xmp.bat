@echo off
REM Restore IMAGE_EXIF and IMAGE_XMP from corrupted DB into restored DB.
REM Close Web UI and Electron gallery first.
cd /d "%~dp0..\.."
python scripts/maintenance/merge_exif_xmp_from_corrupted.py %*
pause
