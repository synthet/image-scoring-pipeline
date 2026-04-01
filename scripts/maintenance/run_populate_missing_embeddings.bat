@echo off
REM Back-compat alias: forwards to the canonical launcher (see populate_missing_embeddings.py docstring).
call "%~dp0run_populate_embeddings.bat" %*
