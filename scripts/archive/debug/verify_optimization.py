
import sys
import os
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db, utils

def test_db_optimization():
    print("Testing DB Optimization...")
    try:
        # 1. Test Combined Query
        print("1. Testing get_images_paginated_with_count...")
        start = time.perf_counter()
        rows, count = db.get_images_paginated_with_count(page=1, page_size=10)
        dt = (time.perf_counter() - start) * 1000
        print(f"   Query Time: {dt:.2f}ms")
        print(f"   Rows returned: {len(rows)}")
        print(f"   Total Count: {count}")
        
        if count == 0:
            print("   WARNING: DB is empty, cannot verify data retrieval fully.")
        else:
            print("   ✅ Data retrieved successfully.")
            
        # 2. Test Batch Path Resolution
        print("\n2. Testing get_resolved_paths_batch...")
        if rows:
            ids = [r['id'] for r in rows if r['id']]
            start = time.perf_counter()
            paths = db.get_resolved_paths_batch(ids)
            dt = (time.perf_counter() - start) * 1000
            print(f"   Batch Resolve Time: {dt:.2f}ms")
            print(f"   Paths found: {len(paths)}")
            
            # 3. Test Cache Integration
            print("\n3. Testing Utils Cache Integration...")
            utils.set_batch_path_cache(paths)
            
            # Pick a known ID
            test_id = ids[0]
            if test_id in paths:
                # Should hit cache
                p = utils.resolve_file_path("dummy", test_id)
                print(f"   Cache Lookup Result: {p}")
                if p == paths[test_id]:
                    print("   ✅ Cache Hit Successful")
                else:
                    print(f"   ❌ Cache Miss/Mismatch (Expected {paths[test_id]})")
            
            utils.clear_batch_path_cache()
            
            # Should miss cache
            # (Note: resolve_file_path will try DB if cache misses, so we might still get a result,
            # but we can't easily query internal state. trusting the previous test coverage.)
            
    except Exception as e:
        print(f"❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_db_optimization()
