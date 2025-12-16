import sqlite3
import os

def check_specific():
    db_path = "scoring_history.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    files = [
        "DSC_6332.NEF",
        "DSC_6333.NEF",
        "DSC_6334.NEF",
        "DSC_6335.NEF"
    ]
    
    print(f"{'File':<25} | {'General':<8} | {'Tech':<8} | {'Aesthetic':<8} | {'Version'}")
    print("-" * 75)
    
    for f in files:
        c.execute("""
            SELECT file_name, score_general, score_technical, score_aesthetic, model_version 
            FROM imageS 
            WHERE file_name LIKE ?
        """, (f"{f.split('.')[0]}%",))
        row = c.fetchone()
        
        if row:
            print(f"{row[0]:<25} | {row[1]:<8} | {row[2]:<8} | {row[3]:<8} | {row[4]}")
        else:
            print(f"{f:<25} | NOT FOUND")
            
    conn.close()

if __name__ == "__main__":
    check_specific()
