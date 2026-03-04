import subprocess
import sys
import os
import platform


def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def main():
    print("Checking requirements...")
    try:
        import gradio
    except ImportError:
        print("Installing gradio...")
        install("gradio>=5.0,<6.0")

    try:
        import pydantic
    except ImportError:
        print("Installing pydantic...")
        install("pydantic")
        
    print("Launching WebUI...")
    
    # Firebird Server Management
    # The database file is on Windows, so we must ensure the Windows Firebird server is running.
    # We use 'firebird.exe -a' (Application mode) to listen for TCP connections from WSL.
    
    fb_exe_rel = os.path.join("Firebird", "firebird.exe")
    fb_root = os.path.abspath("Firebird")
    
    # Check if Firebird is running
    is_running = False
    try:
        # Check using Windows tasklist (works from WSL too if interop is on)
        # We look for "firebird.exe"
        output = subprocess.check_output(
            ["tasklist.exe", "/FI", "IMAGENAME eq firebird.exe"], 
            stderr=subprocess.STDOUT,
            timeout=5
        ).decode(errors='ignore')
        if "firebird.exe" in output:
            is_running = True
    except FileNotFoundError:
        # Check linux ps if tasklist.exe not on path (rare for WSL, but possible)
        pass
    except Exception as e:
        print(f"Warning: Could not check for Firebird process: {e}")

    if not is_running:
        print("Firebird Server not running. Attempting to start...")
        try:
            if platform.system() == "Windows":
                 # Start detached
                 subprocess.Popen([fb_exe_rel, "-a"], cwd=fb_root, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                 # WSL: Invoke Windows executable using cmd.exe to ensure it runs in Windows context
                 # We need absolute Windows path. 
                 # Assuming mounted drive structure: /mnt/d/Projects/... -> d:\Projects\...
                 # A simple consistent way for WSL -> Windows path:
                 # wslpath -w <absolute_path>
                 
                 fb_exe_abs_wsl = os.path.abspath(fb_exe_rel)
                 try:
                     fb_exe_win = subprocess.check_output(["wslpath", "-w", fb_exe_abs_wsl]).decode().strip()
                     fb_root_win = subprocess.check_output(["wslpath", "-w", fb_root]).decode().strip()
                     
                     # Use cmd.exe /C start ... to launch invisible or minimized
                     subprocess.Popen(["cmd.exe", "/C", "start", "/MIN", "Firebird Server", fb_exe_win, "-a"])
                     print("Launched Firebird Server on Windows Host.")
                 except Exception as e:
                     print(f"Failed to launch Firebird from WSL: {e}")
                     print("Please run 'Firebird\\firebird.exe -a' manually in Windows.")
            
            # Give it a moment to bind port
            import time
            time.sleep(2)
            
        except Exception as e:
             print(f"Error starting Firebird: {e}")

    # We run webui.py in a subprocess so this launcher stays clean
    # or we can import it. Subprocess is safer for restarts/updates if we ever add them.
    cmd = [sys.executable, "webui.py"] + sys.argv[1:]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nKeyboard interruption... closing.")

if __name__ == "__main__":
    main()
