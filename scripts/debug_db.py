import sqlite3
import os
import time

DB_FILE = "scoring_history.db"

def check_write():
    print(f"Checking write access to {DB_FILE}...")
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        print("Attempting to create a dummy table...")
        cursor.execute("CREATE TABLE IF NOT EXISTS _debug_test (id INTEGER PRIMARY KEY)")
        print("Table creation successful.")
        
        print("Attempting to insert...")
        cursor.execute("INSERT INTO _debug_test (id) VALUES (NULL)")
        conn.commit()
        print("Insert successful.")
        
        cursor.execute("DROP TABLE _debug_test")
        conn.commit()
        print("Cleanup successful.")
        
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"OperationalError during write: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    check_write()
