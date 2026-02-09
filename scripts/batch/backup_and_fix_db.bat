@echo off
REM Backup and fix database. Stop WebUI first for DB access.
cd /d "%~dp0\..\.."
python scripts\maintenance\backup_and_fix_db.py
pause
