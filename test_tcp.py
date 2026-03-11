import os
from firebird.driver import connect, driver_config

FB_CLIENT_LIBRARY = r"D:\Projects\image-scoring\Firebird\fbclient.dll"
driver_config.fb_client_library.value = FB_CLIENT_LIBRARY

DB_PATH = r"d:\Projects\image-scoring\scoring_history.fdb"
dsn = f"127.0.0.1/3050:{DB_PATH}"
print("Connecting to", dsn)
try:
    conn = connect(dsn, user="sysdba", password="masterkey", charset="UTF8")
    print("Connected successfully.")
    conn.close()
except Exception as e:
    print("Failed:", e)
