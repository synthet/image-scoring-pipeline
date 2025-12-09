import subprocess
import sys
import os

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def main():
    print("Checking requirements...")
    try:
        import gradio
    except ImportError:
        print("Installing gradio...")
        install("gradio")

    try:
        import pydantic
    except ImportError:
        print("Installing pydantic...")
        install("pydantic")
        
    print("Launching WebUI...")
    
    # We run webui.py in a subprocess so this launcher stays clean
    # or we can import it. Subprocess is safer for restarts/updates if we ever add them.
    cmd = [sys.executable, "webui.py"]
    subprocess.run(cmd)

if __name__ == "__main__":
    main()
