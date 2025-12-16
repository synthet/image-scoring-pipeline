import sqlite3
import pandas as pd
import json
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

DB_FILE = "scoring_history.db"

def analyze_scores():
    if not os.path.exists(DB_FILE):
        print(f"Database file {DB_FILE} not found.")
        return

    conn = sqlite3.connect(DB_FILE)
    
    # Read data into DataFrame
    query = """
    SELECT 
        file_name,
        score as final_score,
        normalized_score,
        score_spaq,
        score_ava,
        score_koniq,
        score_paq2piq,
        score_liqe,
        scores_json
    FROM images
    """
    
    try:
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"Error reading database: {e}")
        conn.close()
        return

    conn.close()

    if df.empty:
        print("No images found in database.")
        return

    print("=== Database Score Analysis ===")
    print(f"Total Rows: {len(df)}")
    print("-" * 50)

    # Analyze numeric columns
    cols_to_check = [
        'final_score', 'normalized_score', 
        'score_spaq', 'score_ava', 
        'score_koniq', 'score_paq2piq', 'score_liqe'
    ]

    for col in cols_to_check:
        if col not in df.columns:
            print(f"Column {col} missing from dataframe (might not exist in DB schema yet).")
            continue
            
        series = df[col].dropna()
        if series.empty:
            print(f"Column {col}: No data (all null)")
        else:
            print(f"Column: {col}")
            print(f"  Min: {series.min():.4f}")
            print(f"  Max: {series.max():.4f}")
            print(f"  Avg: {series.mean():.4f}")
            # print(f"  Count: {len(series)}")
            print("-" * 20)

    # Inspect a sample JSON to verify metadata
    print("\n=== Sample JSON Payload Inspection (First VALID record) ===")
    
    # Find a record with valid JSON
    sample_row = None
    for idx, row in df.iterrows():
        if row['scores_json']:
            try:
                data = json.loads(row['scores_json'])
                sample_row = data
                print(f"File: {row['file_name']}")
                print(json.dumps(data, indent=2))
                break
            except:
                continue
    
    if not sample_row:
        print("No valid JSON payloads found.")

if __name__ == "__main__":
    analyze_scores()
