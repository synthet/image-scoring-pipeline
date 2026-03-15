
import os
import sys
import time
import random
import statistics

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db

# Configuration for benchmark
NUM_IMAGES = 2000 
TAGS_POOL = ["nature", "landscape", "portrait", "street", "architecture", "wildlife", "macro", "astro", "sports", "sunset"]

def setup_benchmark_data(conn):
    """Populates the test database with a large amount of target data."""
    print(f"Setting up {NUM_IMAGES} benchmark images...")
    c = conn.cursor()
    
    # 1. Wipe existing data
    c.execute("DELETE FROM image_keywords")
    c.execute("DELETE FROM keywords_dim")
    c.execute("DELETE FROM images")
    conn.commit()
    
    # 2. Insert images and sync keywords
    # We use batching for performance
    for i in range(NUM_IMAGES):
        tags = random.sample(TAGS_POOL, k=random.randint(2, 5))
        tags_str = ", ".join(tags)
        c.execute("INSERT INTO images (file_name, file_path, keywords) VALUES (?, ?, ?)", 
                  (f"img_{i}.jpg", f"bench/img_{i}.jpg", tags_str))
        
        # We need the ID for the normalized sync
        if (i + 1) % 1000 == 0:
            print(f"  Inserted {i+1}/{NUM_IMAGES}...")
            conn.commit()
            
    conn.commit()
    
    print("Synching keywords to normalized tables (this may take a moment)...")
    c.execute("SELECT id, keywords FROM images")
    rows = c.fetchall()
    
    for row_id, kws in rows:
        db._sync_image_keywords(row_id, kws)
    
    print("Benchmark data setup complete.")

def measure_query_legacy(conn, tag):
    """Legacy query using LIKE on BLOB."""
    c = conn.cursor()
    start = time.perf_counter()
    c.execute("SELECT COUNT(*) FROM images WHERE keywords LIKE ?", (f"%{tag}%",))
    count = c.fetchone()[0]
    duration = time.perf_counter() - start
    return duration, count

def measure_query_normalized(conn, tag):
    """Normalized query using bridge table."""
    c = conn.cursor()
    start = time.perf_counter()
    query = """
    SELECT COUNT(*) FROM images i
    WHERE EXISTS (
        SELECT 1 FROM image_keywords ik
        JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
        WHERE ik.image_id = i.id AND kd.keyword_norm = ?
    )
    """
    c.execute(query, (tag.lower(),))
    count = c.fetchone()[0]
    duration = time.perf_counter() - start
    return duration, count

def main():
    # Use the test database
    db.DB_FILE = "scoring_history_test.fdb"
    db.DB_PATH = os.path.join(db._PROJECT_ROOT, db.DB_FILE)
    
    os.environ["FIREBIRD_USE_LOCAL_PATH"] = "1"
    
    conn = db.get_db()
    try:
        setup_benchmark_data(conn)
        
        target_tags = ["nature", "sunset", "macro", "nonexistent"]
        iterations = 5
        
        results = []
        
        print("\n" + "="*50)
        print(f"DATABASE PERFORMANCE BENCHMARK ({NUM_IMAGES} images)")
        print("="*50)
        print(f"{'Tag':<15} | {'Legacy (ms)':<15} | {'Normalized (ms)':<15} | {'Speedup':<10}")
        print("-" * 55)
        
        for tag in target_tags:
            l_times = []
            n_times = []
            
            for _ in range(iterations):
                l_dur, l_count = measure_query_legacy(conn, tag)
                n_dur, n_count = measure_query_normalized(conn, tag)
                l_times.append(l_dur * 1000)
                n_times.append(n_dur * 1000)
            
            avg_l = statistics.mean(l_times)
            avg_n = statistics.mean(n_times)
            speedup = avg_l / avg_n if avg_n > 0 else 0
            
            print(f"{tag:<15} | {avg_l:14.2f} | {avg_n:14.2f} | {speedup:8.1f}x")
            
        print("="*55)
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
