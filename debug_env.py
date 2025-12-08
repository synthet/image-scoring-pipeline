
import sys
import subprocess

print(f"Python executable: {sys.executable}")
try:
    import pyiqa
    print("pyiqa imported successfully")
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Exception: {e}")

print("\n--- PIP LIST ---")
subprocess.run([sys.executable, "-m", "pip", "list"])
