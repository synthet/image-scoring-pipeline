from modules import db
import os

def reset_sequences():
    print("Connecting to Firebird...")
    conn = db.get_db()
    c = conn.cursor()
    
    tables = ['JOBS', 'IMAGES', 'FOLDERS', 'STACKS', 'FILE_PATHS']
    
    try:
        for table in tables:
            print(f"Resetting sequence for {table}...")
            # Get max ID
            c.execute(f"SELECT MAX(ID) FROM {table}")
            max_id = c.fetchone()[0] or 0
            
            # Reset identity sequence
            # Firebird 3.0+ syntax for Identity columns
            c.execute(f"ALTER TABLE {table} ALTER COLUMN ID RESTART WITH {max_id + 1}")
            print(f"  -> {table} sequence restarted with {max_id + 1}")
            
        conn.commit()
        print("\nAll sequences reset successfully.")
    except Exception as e:
        print(f"\nError resetting sequences: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    reset_sequences()
