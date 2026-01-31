
import os
import sys
import subprocess
import pytest
from firebird.driver import connect

FB_DLL = os.path.abspath(os.path.join("Firebird", "fbclient.dll"))
FB_DIR = os.path.dirname(FB_DLL)

def test_create_db_basic():
    print(f"FB_DLL: {FB_DLL}")
    print(f"FB_DIR: {FB_DIR}")

    if not os.path.exists(FB_DLL):
        pytest.fail("fbclient.dll not found")

    # DB Path
    import time
    import gc
    timestamp = int(time.time())
    db_path = os.path.abspath(f"TEST_basic_{timestamp}.fdb")
    
    print(f"Creating DB at: {db_path}")

    ISQL_EXE = os.path.join(FB_DIR, "isql.exe")
    cmd = f"CREATE DATABASE '{db_path}' user 'SYSDBA' password 'masterkey'; EXIT;"
    
    env = os.environ.copy()
    env["FIREBIRD"] = FB_DIR
    if FB_DIR not in env["PATH"]:
        env["PATH"] += ";" + FB_DIR
        
    # Run isql
    res = subprocess.run([ISQL_EXE, '-q'], input=cmd.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    
    print(f"ISQL Return Code: {res.returncode}")
    print(f"ISQL Stdout: {res.stdout.decode()}")
    print(f"ISQL Stderr: {res.stderr.decode()}")
    
    if res.returncode != 0:
        pytest.fail(f"ISQL Failed: {res.stderr.decode()}")
        
    assert os.path.exists(db_path), "DB File should exist"
    
    # Try to connect
    try:
        from firebird.driver import driver_config
        if hasattr(driver_config, 'fb_client_library'):
             driver_config.fb_client_library.value = FB_DLL

        con = connect(db_path, user='SYSDBA', password='masterkey')
        print("Successfully connected to DB")
        con.close()
    except Exception as e:
        pytest.fail(f"Connect failed: {e}")
    finally:
        if os.path.exists(db_path):
             try:
                 con.close() 
             except: pass
             
             # Force garbage collection to release file handles
             gc.collect()
             
             # Retry removal with delays for Windows file locking
             for attempt in range(5):
                 try:
                     time.sleep(0.5)
                     os.remove(db_path)
                     print("Cleaned up DB")
                     break
                 except Exception as e:
                     if attempt == 4:
                         print(f"Cleanup failed after 5 attempts: {e}")
