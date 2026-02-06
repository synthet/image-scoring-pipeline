#!/usr/bin/env python3
"""
NEF JPEG Extraction Diagnostic Tool

Tests multiple strategies for extracting JPEG previews from Nikon NEF files
across different camera models (D90, Z6ii, Z8, etc.).

Usage:
    python scripts/test_nef_extraction.py
"""

import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional

try:
    import fdb
except ImportError:
    print("❌ fdb (firebirdsql) module not found. Install with: pip install fdb")
    exit(1)


class NEFExtractor:
    """Test different JPEG extraction strategies"""
    
    @staticmethod
    def find_all_jpegs(data: bytes) -> List[Tuple[int, int, int]]:
        """
        Strategy 1: Find all JPEG markers (SOI/EOI) and return complete JPEGs
        Returns: List of (start_offset, end_offset, size) tuples
        """
        results = []
        
        # Find all SOI markers (0xFF 0xD8)
        soi_positions = []
        for i in range(512, len(data) - 1):
            if data[i] == 0xFF and data[i + 1] == 0xD8:
                soi_positions.append(i)
        
        # For each SOI, find its EOI
        for start in soi_positions:
            # Find next EOI (0xFF 0xD9)
            for i in range(start + 2, len(data) - 1):
                if data[i] == 0xFF and data[i + 1] == 0xD9:
                    end = i + 2
                    size = end - start
                    if size > 10000:  # Filter out tiny thumbnails
                        results.append((start, end, size))
                    break
        
        return results
    
    @staticmethod
    def find_largest_jpeg(data: bytes) -> Optional[Tuple[int, int, int]]:
        """
        Strategy 2: Find all JPEGs and return the largest one
        Returns: (start_offset, end_offset, size) or None
        """
        jpegs = NEFExtractor.find_all_jpegs(data)
        if not jpegs:
            return None
        return max(jpegs, key=lambda x: x[2])
    
    @staticmethod
    def find_jpegs_by_size_threshold(data: bytes, min_kb: int = 500) -> List[Tuple[int, int, int]]:
        """
        Strategy 3: Find JPEGs above a certain size threshold
        Returns: List of (start_offset, end_offset, size) tuples
        """
        all_jpegs = NEFExtractor.find_all_jpegs(data)
        min_bytes = min_kb * 1024
        return [j for j in all_jpegs if j[2] >= min_bytes]
    
    @staticmethod
    def extract_jpeg_at_offset(data: bytes, offset: int) -> Optional[Tuple[int, int, int]]:
        """
        Strategy 4: Try to extract JPEG at a specific offset
        Returns: (start_offset, end_offset, size) or None
        """
        if offset >= len(data) - 2:
            return None
        
        # Check for SOI at this offset
        if data[offset] != 0xFF or data[offset + 1] != 0xD8:
            return None
        
        # Find EOI
        for i in range(offset + 2, len(data) - 1):
            if data[i] == 0xFF and data[i + 1] == 0xD9:
                end = i + 2
                size = end - offset
                return (offset, end, size)
        
        return None


def find_sample_files_from_db(db_path: str, samples_per_model: int = 2) -> Dict[str, List[str]]:
    """Query database for sample NEF files"""
    
    samples = {'D90': [], 'Z6II': [], 'Z8': [], 'OTHER': []}
    
    try:
        conn = fdb.connect(
            database=db_path,
            user='SYSDBA',
            password='masterkey',
            charset='UTF8'
        )
        cursor = conn.cursor()
        
        # Get NEF files
        query = """
            SELECT FIRST 20 FILE_PATH, WIN_PATH, FILE_NAME
            FROM IMAGES
            WHERE UPPER(FILE_NAME) LIKE '%.NEF'
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        for row in rows:
            file_path = row[1] if row[1] else row[0]  # Prefer WIN_PATH
            file_name = row[2]
            
            if not file_path or not os.path.exists(file_path):
                continue
            
            # Try to categorize by camera model based on filename or path
            path_lower = file_path.lower()
            if 'd90' in path_lower or '_d90' in file_name.lower():
                if len(samples['D90']) < samples_per_model:
                    samples['D90'].append(file_path)
            elif 'z6' in path_lower or '_z6' in file_name.lower():
                if len(samples['Z6II']) < samples_per_model:
                    samples['Z6II'].append(file_path)
            elif 'z8' in path_lower or '_z8' in file_name.lower():
                if len(samples['Z8']) < samples_per_model:
                    samples['Z8'].append(file_path)
            else:
                if len(samples['OTHER']) < samples_per_model:
                    samples['OTHER'].append(file_path)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Database error: {e}")
    
    return samples


def find_sample_files_from_disk(base_path: str = "D:/Photos", samples_per_model: int = 2) -> Dict[str, List[str]]:
    """Find sample NEF files from disk by scanning directories"""
    
    samples = {'D90': [], 'Z6II': [], 'Z8': [], 'OTHER': []}
    
    print(f"🔍 Scanning {base_path} for NEF files...")
    
    if not os.path.exists(base_path):
        print(f"❌ Path not found: {base_path}")
        return samples
    
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if not file.lower().endswith('.nef'):
                continue
            
            file_path = os.path.join(root, file)
            file_lower = file.lower()
            
            # Categorize by filename/path patterns
            if ('d90' in file_lower or 'd90' in root.lower()) and len(samples['D90']) < samples_per_model:
                samples['D90'].append(file_path)
            elif ('z6' in file_lower or 'z6' in root.lower()) and len(samples['Z6II']) < samples_per_model:
                samples['Z6II'].append(file_path)
            elif ('z8' in file_lower or 'z8' in root.lower()) and len(samples['Z8']) < samples_per_model:
                samples['Z8'].append(file_path)
            elif len(samples['OTHER']) < samples_per_model:
                samples['OTHER'].append(file_path)
            
            # Stop if we have enough samples
            if all(len(v) >= samples_per_model for v in samples.values()):
                return samples
    
    return samples


def analyze_file(file_path: str) -> Dict:
    """Analyze a single NEF file with all strategies"""
    
    print(f"\n{'='*80}")
    print(f"📸 Analyzing: {Path(file_path).name}")
    print(f"   Path: {file_path}")
    print(f"{'='*80}")
    
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        file_size_mb = len(data) / (1024 * 1024)
        print(f"\n📊 File size: {file_size_mb:.2f} MB")
        
        results = {}
        
        # Strategy 1: Find all JPEGs
        print("\n🔬 Strategy 1: Find all JPEGs")
        all_jpegs = NEFExtractor.find_all_jpegs(data)
        results['all_jpegs'] = all_jpegs
        
        if all_jpegs:
            print(f"   Found {len(all_jpegs)} JPEG(s):")
            for i, (start, end, size) in enumerate(all_jpegs, 1):
                print(f"   {i}. Offset {start:,} → {end:,} ({size / 1024:.1f} KB)")
        else:
            print("   ❌ No JPEGs found")
        
        # Strategy 2: Largest JPEG
        print("\n🔬 Strategy 2: Largest JPEG")
        largest = NEFExtractor.find_largest_jpeg(data)
        results['largest_jpeg'] = largest
        
        if largest:
            start, end, size = largest
            print(f"   ✅ Found at offset {start:,} → {end:,} ({size / 1024:.1f} KB)")
            
            # Save it for visual verification
            output_dir = Path("test_output")
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"{Path(file_path).stem}_extracted.jpg"
            with open(output_file, 'wb') as f:
                f.write(data[start:end])
            print(f"   💾 Saved to: {output_file}")
        else:
            print("   ❌ No JPEG found")
        
        # Strategy 3: Size threshold filtering
        for threshold_kb in [100, 500, 1000]:
            print(f"\n🔬 Strategy 3: JPEGs > {threshold_kb} KB")
            filtered = NEFExtractor.find_jpegs_by_size_threshold(data, threshold_kb)
            results[f'threshold_{threshold_kb}kb'] = filtered
            
            if filtered:
                print(f"   Found {len(filtered)} JPEG(s):")
                for i, (start, end, size) in enumerate(filtered, 1):
                    print(f"   {i}. Offset {start:,} ({size / 1024:.1f} KB)")
            else:
                print(f"   ❌ No JPEGs above {threshold_kb} KB")
        
        return results
        
    except Exception as e:
        print(f"\n❌ Error analyzing file: {e}")
        import traceback
        traceback.print_exc()
        return {}


def main():
    print("🔧 NEF JPEG Extraction Diagnostic Tool")
    print("="*80)
    
    # Try to find samples from both database and disk
    samples = {}
    
    # Try database first
    db_path = "D:/Projects/image-scoring/SCORING_HISTORY.FDB"
    if os.path.exists(db_path):
        print(f"\n📂 Querying database: {db_path}")
        samples = find_sample_files_from_db(db_path, samples_per_model=2)
    
    # Supplement with disk scan if needed
    if not any(samples.values()):
        print("\n📂 Scanning disk for NEF files...")
        samples = find_sample_files_from_disk("D:/Photos", samples_per_model=2)
    
    # Print what we found
    print("\n📋 Sample Files Found:")
    for model, files in samples.items():
        if files:
            print(f"\n{model}:")
            for f in files:
                print(f"  • {Path(f).name}")
    
    # Analyze each file
    all_results = {}
    
    for model, files in samples.items():
        if not files:
            continue
        
        print(f"\n\n{'#'*80}")
        print(f"# Testing {model} Files")
        print(f"{'#'*80}")
        
        model_results = []
        for file_path in files:
            results = analyze_file(file_path)
            model_results.append({
                'file': file_path,
                'results': results
            })
        
        all_results[model] = model_results
    
    # Summary
    print("\n\n" + "="*80)
    print("📋 SUMMARY")
    print("="*80)
    
    for model, model_results in all_results.items():
        print(f"\n{model}:")
        for item in model_results:
            file_name = Path(item['file']).name
            results = item['results']
            
            largest = results.get('largest_jpeg')
            if largest:
                size_kb = largest[2] / 1024
                print(f"  ✅ {file_name}: {size_kb:.1f} KB preview found")
            else:
                print(f"  ❌ {file_name}: No preview found")
    
    print("\n✅ Diagnostic complete!")
    print("\n💡 Check test_output/ folder for extracted JPEG previews")


if __name__ == "__main__":
    main()



class NEFExtractor:
    """Test different JPEG extraction strategies"""
    
    @staticmethod
    def find_all_jpegs(data: bytes) -> List[Tuple[int, int, int]]:
        """
        Strategy 1: Find all JPEG markers (SOI/EOI) and return complete JPEGs
        Returns: List of (start_offset, end_offset, size) tuples
        """
        results = []
        
        # Find all SOI markers (0xFF 0xD8)
        soi_positions = []
        for i in range(512, len(data) - 1):
            if data[i] == 0xFF and data[i + 1] == 0xD8:
                soi_positions.append(i)
        
        # For each SOI, find its EOI
        for start in soi_positions:
            # Find next EOI (0xFF 0xD9)
            for i in range(start + 2, len(data) - 1):
                if data[i] == 0xFF and data[i + 1] == 0xD9:
                    end = i + 2
                    size = end - start
                    if size > 10000:  # Filter out tiny thumbnails
                        results.append((start, end, size))
                    break
        
        return results
    
    @staticmethod
    def find_largest_jpeg(data: bytes) -> Optional[Tuple[int, int, int]]:
        """
        Strategy 2: Find all JPEGs and return the largest one
        Returns: (start_offset, end_offset, size) or None
        """
        jpegs = NEFExtractor.find_all_jpegs(data)
        if not jpegs:
            return None
        return max(jpegs, key=lambda x: x[2])
    
    @staticmethod
    def find_jpegs_by_size_threshold(data: bytes, min_kb: int = 500) -> List[Tuple[int, int, int]]:
        """
        Strategy 3: Find JPEGs above a certain size threshold
        Returns: List of (start_offset, end_offset, size) tuples
        """
        all_jpegs = NEFExtractor.find_all_jpegs(data)
        min_bytes = min_kb * 1024
        return [j for j in all_jpegs if j[2] >= min_bytes]
    
    @staticmethod
    def extract_jpeg_at_offset(data: bytes, offset: int) -> Optional[Tuple[int, int, int]]:
        """
        Strategy 4: Try to extract JPEG at a specific offset
        Returns: (start_offset, end_offset, size) or None
        """
        if offset >= len(data) - 2:
            return None
        
        # Check for SOI at this offset
        if data[offset] != 0xFF or data[offset + 1] != 0xD8:
            return None
        
        # Find EOI
        for i in range(offset + 2, len(data) - 1):
            if data[i] == 0xFF and data[i + 1] == 0xD9:
                end = i + 2
                size = end - offset
                return (offset, end, size)
        
        return None


def find_sample_files(db: Database, camera_models: List[str], samples_per_model: int = 3) -> Dict[str, List[str]]:
    """Query database for sample NEF files from each camera model"""
    
    samples = {}
    
    for model in camera_models:
        print(f"\n🔍 Searching for {model} NEF files...")
        
        # Query for NEF files with this camera model in metadata
        # We'll search in the images table for .NEF files
        query = """
            SELECT DISTINCT i.FILE_PATH, i.WIN_PATH
            FROM IMAGES i
            WHERE UPPER(i.FILE_NAME) LIKE '%.NEF'
            LIMIT ?
        """
        
        rows = db.execute_query(query, (samples_per_model,))
        
        file_paths = []
        for row in rows:
            # Prefer Windows path if available
            path = row[1] if row[1] else row[0]
            if path and os.path.exists(path):
                file_paths.append(path)
        
        samples[model] = file_paths
        print(f"   Found {len(file_paths)} files")
        for path in file_paths:
            print(f"   • {Path(path).name}")
    
    return samples


def analyze_file(file_path: str) -> Dict:
    """Analyze a single NEF file with all strategies"""
    
    print(f"\n{'='*80}")
    print(f"📸 Analyzing: {Path(file_path).name}")
    print(f"   Path: {file_path}")
    print(f"{'='*80}")
    
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        file_size_mb = len(data) / (1024 * 1024)
        print(f"\n📊 File size: {file_size_mb:.2f} MB")
        
        results = {}
        
        # Strategy 1: Find all JPEGs
        print("\n🔬 Strategy 1: Find all JPEGs")
        all_jpegs = NEFExtractor.find_all_jpegs(data)
        results['all_jpegs'] = all_jpegs
        
        if all_jpegs:
            print(f"   Found {len(all_jpegs)} JPEG(s):")
            for i, (start, end, size) in enumerate(all_jpegs, 1):
                print(f"   {i}. Offset {start:,} → {end:,} ({size / 1024:.1f} KB)")
        else:
            print("   ❌ No JPEGs found")
        
        # Strategy 2: Largest JPEG
        print("\n🔬 Strategy 2: Largest JPEG")
        largest = NEFExtractor.find_largest_jpeg(data)
        results['largest_jpeg'] = largest
        
        if largest:
            start, end, size = largest
            print(f"   ✅ Found at offset {start:,} → {end:,} ({size / 1024:.1f} KB)")
        else:
            print("   ❌ No JPEG found")
        
        # Strategy 3: Size threshold filtering
        for threshold_kb in [100, 500, 1000]:
            print(f"\n🔬 Strategy 3: JPEGs > {threshold_kb} KB")
            filtered = NEFExtractor.find_jpegs_by_size_threshold(data, threshold_kb)
            results[f'threshold_{threshold_kb}kb'] = filtered
            
            if filtered:
                print(f"   Found {len(filtered)} JPEG(s):")
                for i, (start, end, size) in enumerate(filtered, 1):
                    print(f"   {i}. Offset {start:,} ({size / 1024:.1f} KB)")
            else:
                print(f"   ❌ No JPEGs above {threshold_kb} KB")
        
        # Strategy 4: Known offsets (common positions)
        print("\n🔬 Strategy 4: Check common offsets")
        common_offsets = [512, 1024, 2048, 4096, 8192, 16384, 32768]
        offset_results = []
        
        for offset in common_offsets:
            result = NEFExtractor.extract_jpeg_at_offset(data, offset)
            if result:
                start, end, size = result
                offset_results.append(result)
                print(f"   ✅ Offset {offset:,}: Found JPEG ({size / 1024:.1f} KB)")
        
        results['offset_checks'] = offset_results
        
        if not offset_results:
            print("   ❌ No JPEGs at common offsets")
        
        return results
        
    except Exception as e:
        print(f"\n❌ Error analyzing file: {e}")
        import traceback
        traceback.print_exc()
        return {}


def main():
    print("🔧 NEF JPEG Extraction Diagnostic Tool")
    print("="*80)
    
    # Connect to database
    db_path = Path("D:/Projects/image-scoring/SCORING_HISTORY.FDB")
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return
    
    print(f"📂 Connecting to database: {db_path}")
    db = Database(str(db_path))
    
    # Camera models to test
    camera_models = ["D90", "Z6II", "Z8"]
    
    # Find sample files
    samples = find_sample_files(db, camera_models, samples_per_model=2)
    
    # Analyze each file
    all_results = {}
    
    for model, files in samples.items():
        if not files:
            print(f"\n⚠️  No {model} files found, skipping...")
            continue
        
        print(f"\n\n{'#'*80}")
        print(f"# Testing {model} Files")
        print(f"{'#'*80}")
        
        model_results = []
        for file_path in files:
            results = analyze_file(file_path)
            model_results.append({
                'file': file_path,
                'results': results
            })
        
        all_results[model] = model_results
    
    # Summary
    print("\n\n" + "="*80)
    print("📋 SUMMARY")
    print("="*80)
    
    for model, model_results in all_results.items():
        print(f"\n{model}:")
        for item in model_results:
            file_name = Path(item['file']).name
            results = item['results']
            
            largest = results.get('largest_jpeg')
            if largest:
                size_kb = largest[2] / 1024
                print(f"  ✅ {file_name}: {size_kb:.1f} KB preview found")
            else:
                print(f"  ❌ {file_name}: No preview found")
    
    print("\n✅ Diagnostic complete!")


if __name__ == "__main__":
    main()
