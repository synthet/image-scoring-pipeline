@echo off
setlocal
cd /d "%~dp0..\.."

REM One-shot: run python inside image-scoring-gpu-shell.
REM Usage: scripts\batch\docker_gpu_run.bat scripts\doctor.py --no-gpu
REM        scripts\batch\docker_gpu_run.bat -c "import torch; print(torch.cuda.is_available())"
REM Long jobs: set GPU_SHELL_DETACH=1
REM HF Hub auth: set GPU_SHELL_DOTENV=D:\Projects\image-scoring-model\.env
REM   (or rely on sibling image-scoring-model\.env when present)

if "%~1"=="" (
    echo Usage: %~nx0 [python args...]
    echo Example: %~nx0 scripts\doctor.py --no-gpu
    exit /b 1
)

REM If the caller already starts with "python", do not prepend a second one.
if /i "%~1"=="python" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0..\powershell\Invoke-GpuShell.ps1' %*; exit $LASTEXITCODE"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0..\powershell\Invoke-GpuShell.ps1' python %*; exit $LASTEXITCODE"
)
exit /b %ERRORLEVEL%
