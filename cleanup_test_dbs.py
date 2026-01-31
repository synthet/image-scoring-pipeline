import glob
import os
import time

def cleanup():
    patterns = ["TEST_*.fdb", "test_*.fdb"]
    for pattern in patterns:
        files = glob.glob(pattern)
        for f in files:
            path = os.path.abspath(f)
            print(f"Removing {path}...")
            try:
                os.remove(path)
                print("Done.")
            except Exception as e:
                print(f"Failed: {e}")

if __name__ == "__main__":
    cleanup()
