import os
import time
from firebird.driver import connect, driver_config

FB_CLIENT_LIBRARY = r"D:\Projects\image-scoring\Firebird\fbclient.dll"
driver_config.fb_client_library.value = FB_CLIENT_LIBRARY

DB_PATH = r"d:\Projects\image-scoring\scoring_history.fdb"
dsn = f"inet://127.0.0.1/{DB_PATH}"
print("Connecting to", dsn)
conn = connect(dsn, user="sysdba", password="masterkey", charset="UTF8")
print("Connected.")
time.sleep(15)
conn.close()
