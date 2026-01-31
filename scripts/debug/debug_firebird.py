
import os
import sys
from firebird.driver import connect, driver_config, create_database

# Setup Firebird env same as db.py
FB_DLL = os.path.abspath(os.path.join("Firebird", "fbclient.dll"))
FB_DIR = os.path.dirname(FB_DLL)

print(f"FB_DLL: {FB_DLL}")
print(f"FB_DIR: {FB_DIR}")

if os.path.exists(FB_DLL):
    os.environ["FIREBIRD"] = FB_DIR
    if FB_DIR not in os.environ["PATH"]:
        os.environ["PATH"] += ";" + FB_DIR
    
    # Check config
    print("Inspecting driver_config structure:")
    try:
        if hasattr(driver_config, 'fb_client_library'):
             driver_config.fb_client_library.value = FB_DLL
             print("Set fb_client_library")
    except Exception as e:
        print(f"Config warning: {e}")

else:
    print("Error: fbclient.dll not found")

# Try to create a DB via ISQL
DB_PATH = os.path.abspath("template.fdb")
ISQL_EXE = os.path.join(FB_DIR, "isql.exe")

if os.path.exists(DB_PATH):
    try:
        os.remove(DB_PATH)
    except: pass

print(f"Creating DB at: {DB_PATH} using {ISQL_EXE}")

import subprocess

try:
    # Use ISQL to create
    # CREATE DATABASE 'path';
    cmd = f"CREATE DATABASE '{DB_PATH}' user 'SYSDBA' password 'masterkey';"
    
    # Run isql
    # isql -q -i input_file? or just stdin
    process = subprocess.Popen([ISQL_EXE, '-q'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ)
    stdout, stderr = process.communicate(input=cmd.encode())
    
    if process.returncode != 0:
        print(f"ISQL failed: {stderr.decode()}")
    else:
        print("ISQL success")
        if os.path.exists(DB_PATH):
             print("DB File exists")
             # Try to connect to verify
             con = connect(DB_PATH, user='SYSDBA', password='masterkey')
             print("Successfully connected to DB")
             con.close()
        else:
             print("DB File NOT created")

    # Clean up
    # if os.path.exists(DB_PATH):
    #     try:
    #          # Close connection (already closed)
    #          # Wait a bit for handle release?
    #          import time
    #          time.sleep(1)
    #          os.remove(DB_PATH)
    #          print("Cleaned up DB file")
    #     except: pass
    pass
        
except Exception as e:
    print(f"Failed to create DB: {e}")
    import traceback
    traceback.print_exc()
