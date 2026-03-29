import subprocess
import sys
import os
import platform


def _extract_webui_open_args(argv: list[str]) -> tuple[list[str], str | None]:
    """Strip --webui-open=browser|electron|none and return (rest, mode or None if unset). Last wins."""
    prefix = "--webui-open="
    out: list[str] = []
    mode: str | None = None
    for a in argv:
        if a.startswith(prefix):
            raw = a[len(prefix) :].strip().lower()
            if raw in ("browser", "electron", "none"):
                mode = raw
            else:
                print(f"Warning: ignoring invalid --webui-open value: {a!r}")
            continue
        out.append(a)
    return out, mode


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
    # When FIREBIRD_USE_LOCAL_PATH=1, we use local file access (no server) - do NOT start the server
    # or it will lock the file and cause "no permission" or "file in use" errors.
    use_local = os.environ.get("FIREBIRD_USE_LOCAL_PATH", "").strip() in ("1", "true", "yes")
    
    # The database file is on Windows, so we must ensure the Windows Firebird server is running.
    # We use 'firebird.exe -a' (Application mode) to listen for TCP connections from WSL.
    
    fb_exe_rel = os.path.join("Firebird", "firebird.exe")
    fb_root = os.path.abspath("Firebird")
    
    # Check if Firebird is running (skip when using local path or running in Docker)
    in_docker = os.environ.get("DOCKER_CONTAINER", "").strip() in ("1", "true", "yes")
    is_running = False
    if not use_local and not in_docker:
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

    if not use_local and not in_docker and not is_running:
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
    os.environ["GRADIO_MCP_SERVER"] = "True"
    print("Enabled Gradio MCP Server (GRADIO_MCP_SERVER=True)")

    webui_argv, webui_extra = _extract_webui_open_args(sys.argv[1:])
    if webui_extra is not None:
        os.environ["WEBUI_OPEN_UI"] = webui_extra

    cmd = [sys.executable, "webui.py"] + webui_argv
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nKeyboard interruption... closing.")

if __name__ == "__main__":
    main()
