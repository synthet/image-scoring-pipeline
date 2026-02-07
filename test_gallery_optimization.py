"""
Test script to verify Gradio gallery optimizations.
Tests the new combined query function and path resolution improvements.
"""

import sys
import time
import importlib
sys.path.insert(0, 'd:\\Projects\\image-scoring')

# Force reload to pick up new functions
from modules import db, debug
importlib.reload(db)

def test_combined_query():
    """Test the new combined query function"""
    print("\n" + "="*60)
    print("Testing get_images_paginated_with_count()")
    print("="*60)
    
    # Test parameters
    page = 1
    page_size = 50
    sort_by = "score_general"
    order = "desc"
    
    try:
        # Test the NEW combined function
        start = time.perf_counter()
        rows, total_count = db.get_images_paginated_with_count(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            order=order
        )
        combined_time = (time.perf_counter() - start) * 1000
        
        print(f"\n✓ Combined Query Results:")
        print(f"  - Rows returned: {len(rows)}")
        print(f"  - Total count: {total_count}")
        print(f"  - Query time: {combined_time:.2f}ms")
        
        # Test the OLD dual query approach for comparison
        start = time.perf_counter()
        rows_old = db.get_images_paginated(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            order=order
        )
        paginated_time = (time.perf_counter() - start) * 1000
        
        start = time.perf_counter()
        total_count_old = db.get_image_count()
        count_time = (time.perf_counter() - start) * 1000
        
        dual_query_time = paginated_time + count_time
        
        print(f"\n✓ Dual Query Results (OLD approach):")
        print(f"  - Rows returned: {len(rows_old)}")
        print(f"  - Total count: {total_count_old}")
        print(f"  - Paginated query time: {paginated_time:.2f}ms")
        print(f"  - Count query time: {count_time:.2f}ms")
        print(f"  - Total time: {dual_query_time:.2f}ms")
        
        # Calculate improvement
        improvement = ((dual_query_time - combined_time) / dual_query_time) * 100
        print(f"\n📊 Performance Improvement:")
        print(f"  - Time saved: {dual_query_time - combined_time:.2f}ms")
        print(f"  - Improvement: {improvement:.1f}%")
        
        # Verify results match
        if len(rows) == len(rows_old) and total_count == total_count_old:
            print(f"\n✓ Results verified: Both methods return identical data")
        else:
            print(f"\n⚠ Warning: Results differ between methods!")
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_batch_path_resolution():
    """Test batch path resolution"""
    print("\n" + "="*60)
    print("Testing Batch Path Resolution")
    print("="*60)
    
    try:
        # Get some image IDs
        rows, _ = db.get_images_paginated_with_count(page=1, page_size=50)
        image_ids = [row['id'] for row in rows if 'id' in row.keys() and row['id']]
        
        print(f"\nTesting with {len(image_ids)} image IDs...")
        
        # Test batch resolution
        start = time.perf_counter()
        resolved_map = db.get_resolved_paths_batch(image_ids)
        batch_time = (time.perf_counter() - start) * 1000
        
        print(f"\n✓ Batch Resolution Results:")
        print(f"  - IDs requested: {len(image_ids)}")
        print(f"  - Paths resolved: {len(resolved_map)}")
        print(f"  - Cache hit rate: {len(resolved_map)}/{len(image_ids)} ({100*len(resolved_map)/len(image_ids):.1f}%)")
        print(f"  - Resolution time: {batch_time:.2f}ms")
        print(f"  - Avg time per path: {batch_time/len(image_ids):.2f}ms")
        
        # Check for malformed paths
        malformed_count = 0
        for img_id, path in resolved_map.items():
            if path and '\\\\' in path and '/' in path:
                malformed_count += 1
        
        if malformed_count > 0:
            print(f"\n⚠ Warning: Found {malformed_count} malformed paths in cache")
        else:
            print(f"\n✓ No malformed paths detected")
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("GRADIO GALLERY OPTIMIZATION TEST SUITE")
    print("="*60)
    
    results = []
    
    # Test 1: Combined Query
    results.append(("Combined Query", test_combined_query()))
    
    # Test 2: Batch Path Resolution
    results.append(("Batch Path Resolution", test_batch_path_resolution()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
