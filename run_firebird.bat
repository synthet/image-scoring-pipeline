@echo off
echo Starting Firebird Server in Application Mode...
echo Press Ctrl+C to stop.
"%~dp0Firebird\firebird.exe" -a -p 3050
