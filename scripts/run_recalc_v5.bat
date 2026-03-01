@echo off
REM Recalculate all scores using v5.0 percentile normalization
REM Runs in WSL with the same environment as the WebUI

wsl bash -c "export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH && source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python scripts/python/recalc_scores_v5.py %*"
