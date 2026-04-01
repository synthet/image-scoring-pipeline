import os
import sys


# from firebird.driver import create_database, connect, driver_config

def test_firebird_connection():
    # Setup environment
    fb_path = os.path.join(os.getcwd(), "Firebird")
    if os.path.exists(fb_path):
        os.environ["PATH"] += ";" + fb_path
        os.environ["FIREBIRD"] = fb_path
        print(f"Set FIREBIRD={fb_path}")

    try:
        from firebird.driver import create_database, connect, driver_config
    except ImportError:
         print("firebird-driver not installed")
         if "pytest" in sys.modules:
             import pytest
             pytest.skip("firebird-driver not installed")
         return

    # DB Path - use relative path with TEST_ prefix
    db_path = os.path.abspath("TEST_fb_simple.fdb")
    
    if os.path.exists(db_path):
        os.unlink(db_path)

    print(f"Creating DB at {db_path}")

    try:
        # Attempt creation with minimal args
        create_database(db_path, user='sysdba', password='masterkey')
        print("Creation SUCCESS")
        
        con = connect(db_path, user='sysdba', password='masterkey')
        print("Connection SUCCESS")
        con.close()
        
        # Cleanup with gc and retry
        import gc
        import time
        gc.collect()
        
        for attempt in range(5):
            try:
                time.sleep(0.5)
                if os.path.exists(db_path):
                    os.unlink(db_path)
                    print(f"Cleaned up {db_path}")
                break
            except Exception as e:
                if attempt == 4:
                    print(f"Cleanup failed after 5 attempts: {e}")
    except Exception as e:
        print(f"FAILURE: {e}")
        # import traceback
        # traceback.print_exc()

    # Print driver info
    print(f"Driver Config: {driver_config}")

if __name__ == "__main__":
    test_firebird_connection()

