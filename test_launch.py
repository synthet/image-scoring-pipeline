import traceback
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

try:
    print("Attempting to import webui...")
    import webui
    print("Import successful. Calling webui.main()...")
    webui.main()
except Exception as e:
    print("\n--- CRASH DETECTED ---")
    traceback.print_exc()
    sys.exit(1)
except SystemExit as e:
    print(f"\n--- SYSTEM EXIT: {e.code} ---")
    sys.exit(e.code)
