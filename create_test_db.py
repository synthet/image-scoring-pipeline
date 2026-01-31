
import os
import sys
import subprocess

def create_db(db_path):
    # Setup paths
    root_dir = os.path.dirname(os.path.abspath(__file__))
    fb_dir = os.path.join(root_dir, "Firebird")
    fb_dll = os.path.join(fb_dir, "fbclient.dll")
    isql_exe = os.path.join(fb_dir, "isql.exe")
    
    if not os.path.exists(isql_exe):
        print(f"Error: isql.exe not found at {isql_exe}")
        sys.exit(1)

    print(f"Creating DB: {db_path}")
    if os.path.exists(db_path):
        try: os.remove(db_path)
        except: pass

    cmd = f"CREATE DATABASE '{db_path}' user 'SYSDBA' password 'masterkey'; EXIT;"
    
    # Prepare env
    env = os.environ.copy()
    env["FIREBIRD"] = fb_dir
    if fb_dir not in env["PATH"]:
        env["PATH"] += ";" + fb_dir
        
    # Run ISQL
    print(f"Running ISQL...")
    # Using Popen to ensure we capture output and avoid 'run' quirks if any
    process = subprocess.Popen([isql_exe, '-q'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    stdout, stderr = process.communicate(input=cmd.encode())
    
    if process.returncode != 0:
        print(f"ISQL Failed (RC={process.returncode}):")
        print(stderr.decode())
        sys.exit(process.returncode)
    
    print("ISQL Success")
    if os.path.exists(db_path):
        print("DB File Created")
    else:
        print("DB File missing after success")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_test_db.py <db_path>")
        sys.exit(1)
        
    create_db(sys.argv[1])
