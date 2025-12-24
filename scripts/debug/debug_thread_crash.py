
import threading
import sys
import time
import os

# Add path to scripts/python
current_dir = os.getcwd()
scripts_dir = os.path.join(current_dir, "scripts", "python")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

def load_in_thread():
    print("Thread started. Importing script...")
    try:
        from run_all_musiq_models import MultiModelMUSIQ
        scorer = MultiModelMUSIQ()
        print("Loading PAQ2PIQ in thread...")
        # Try loading just the one that crashed
        scorer.load_model("paq2piq")
        print("PAQ2PIQ Loaded!")
        
        print("Loading remaining models...")
        scorer.load_model("spaq")
        scorer.load_model("ava")
        scorer.load_model("koniq")
        print("All models loaded!")
    except Exception as e:
        print(f"Exception in thread: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Main thread running...")
    t = threading.Thread(target=load_in_thread)
    t.start()
    while t.is_alive():
        time.sleep(1)
    t.join()
    print("Main thread done.")
