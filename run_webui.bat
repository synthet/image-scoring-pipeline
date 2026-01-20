wsl bash -c "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/mnt/d/Projects/image-scoring/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib && source ~/.venvs/tf/bin/activate && python launch.py %*"
pause
