#!/usr/bin/env python3
"""
Multi-Tier NEF Extraction Test Utility

Tests all 3 tiers of the proposed NEF extraction plan:
1. ExifTool extraction (exiftool-vendored equivalent)
2. TIFF SubIFD parsing
3. SOI/EOI marker scanning (current method)

Usage:
    python scripts/test_multitiernef_extraction.py
"""

import os
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
import struct

try:
    import fdb
except ImportError:
    print("❌ fdb (firebirdsql) module not found. Install with: pip install fdb")
    exit(1)


class MultiTierNEFExtractor:
    """Test all three extraction tiers"""
    
    # Tier 1: ExifTool Extraction
    @staticmethod
    def extract_with_exiftool(file_path: str) -> Optional[Tuple[bytes, str]]:
        """
        Tier 1: Use ExifTool to extract preview
        Returns: (jpeg_bytes, method_description) or None
        """
        try:
            # Check if exiftool is available
            result = subprocess.run(
                ['exiftool', '-ver'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None
            
            # Extract preview image using exiftool
            # -b = binary output
            # -JpgFromRaw = extract the JPEG preview from RAW
            result = subprocess.run(
                ['exiftool', '-b', '-JpgFromRaw', file_path],
                capture_output=True,
                timeout=10
            )
            
            if result.returncode == 0 and len(result.stdout) > 1000:
                return (result.stdout, "ExifTool -JpgFromRaw")
            
            # Try alternative tag
            result = subprocess.run(
                ['exiftool', '-b', '-PreviewImage', file_path],
                capture_output=True,
                timeout=10
            )
            
            if result.returncode == 0 and len(result.stdout) > 1000:
                return (result.stdout, "ExifTool -PreviewImage")
            
            return None
            
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
    
    # Tier 2: TIFF SubIFD Parsing
    @staticmethod
    def extract_from_subifd(data: bytes) -> Optional[Tuple[bytes, str]]:
        """
        Tier 2: Parse TIFF structure and extract from SubIFD0
        Returns: (jpeg_bytes, method_description) or None
        """
        try:
            # Check TIFF header
            if len(data) < 8:
                return None
            
            # Read byte order marker
            if data[0:2] == b'II':
                endian = '<'  # Little-endian (Intel)
            elif data[0:2] == b'MM':
                endian = '>'  # Big-endian (Motorola)
            else:
                return None
            
            # Verify TIFF magic number (42)
            magic = struct.unpack(f'{endian}H', data[2:4])[0]
            if magic != 42:
                return None
            
            # Get IFD0 offset
            ifd0_offset = struct.unpack(f'{endian}I', data[4:8])[0]
            
            # Parse IFD0 to find SubIFD tag (0x014a)
            subifd_offsets = MultiTierNEFExtractor._parse_ifd_for_subifd(data, ifd0_offset, endian)
            
            # Try each SubIFD
            for subifd_offset in subifd_offsets:
                jpeg = MultiTierNEFExtractor._extract_jpeg_from_ifd(data, subifd_offset, endian)
                if jpeg:
                    return (jpeg, "TIFF SubIFD Parser")
            
            return None
            
        except Exception as e:
            return None
    
    @staticmethod
    def _parse_ifd_for_subifd(data: bytes, ifd_offset: int, endian: str) -> List[int]:
        """Parse IFD to find SubIFD offsets (tag 0x014a)"""
        offsets = []
        
        try:
            if ifd_offset + 2 > len(data):
                return offsets
            
            # Read number of directory entries
            num_entries = struct.unpack(f'{endian}H', data[ifd_offset:ifd_offset+2])[0]
            
            # Each IFD entry is 12 bytes
            for i in range(num_entries):
                entry_offset = ifd_offset + 2 + (i * 12)
                if entry_offset + 12 > len(data):
                    break
                
                tag = struct.unpack(f'{endian}H', data[entry_offset:entry_offset+2])[0]
                
                # Tag 0x014a = SubIFDs
                if tag == 0x014a:
                    # Read value offset (bytes 8-12 of entry)
                    value_offset = struct.unpack(f'{endian}I', data[entry_offset+8:entry_offset+12])[0]
                    offsets.append(value_offset)
            
            return offsets
            
        except Exception:
            return offsets
    
    @staticmethod
    def _extract_jpeg_from_ifd(data: bytes, ifd_offset: int, endian: str) -> Optional[bytes]:
        """Extract JPEG from IFD using tags 0x0201 (offset) and 0x0202 (length)"""
        try:
            if ifd_offset + 2 > len(data):
                return None
            
            num_entries = struct.unpack(f'{endian}H', data[ifd_offset:ifd_offset+2])[0]
            
            jpeg_offset = None
            jpeg_length = None
            
            for i in range(num_entries):
                entry_offset = ifd_offset + 2 + (i * 12)
                if entry_offset + 12 > len(data):
                    break
                
                tag = struct.unpack(f'{endian}H', data[entry_offset:entry_offset+2])[0]
                value = struct.unpack(f'{endian}I', data[entry_offset+8:entry_offset+12])[0]
                
                if tag == 0x0201:  # JPEGInterchangeFormat (offset)
                    jpeg_offset = value
                elif tag == 0x0202:  # JPEGInterchangeFormatLength
                    jpeg_length = value
            
            if jpeg_offset and jpeg_length:
                if jpeg_offset + jpeg_length <= len(data):
                    jpeg_data = data[jpeg_offset:jpeg_offset+jpeg_length]
                    # Verify it's a JPEG
                    if jpeg_data[0:2] == b'\xff\xd8':
                        return jpeg_data
            
            return None
            
        except Exception:
            return None
    
    # Tier 3: Marker Scanning (Current Method)
    @staticmethod
    def extract_with_marker_scan(data: bytes) -> Optional[Tuple[bytes, str]]:
        """
        Tier 3: Find all JPEGs via SOI/EOI markers, return largest
        Returns: (jpeg_bytes, method_description) or None
        """
        try:
            results = []
            
            # Find all SOI markers (0xFF 0xD8)
            soi_positions = []
            for i in range(512, len(data) - 1):
                if data[i] == 0xFF and data[i + 1] == 0xD8:
                    soi_positions.append(i)
            
            # For each SOI, find its EOI
            for start in soi_positions:
                for i in range(start + 2, len(data) - 1):
                    if data[i] == 0xFF and data[i + 1] == 0xD9:
                        end = i + 2
                        size = end - start
                        if size > 10000:  # Filter out tiny thumbnails
                            results.append((start, end, size))
                        break
            
            if not results:
                return None
            
            # Sort by size and get largest
            results.sort(key=lambda x: x[2], reverse=True)
            start, end, size = results[0]
            
            return (data[start:end], f"Marker Scan (found {len(results)} JPEGs)")
            
        except Exception:
            return None


def find_sample_files_from_db(db_path: str, samples_per_model: int = 2) -> Dict[str, List[str]]:
    """Query database for sample NEF files"""
    
    samples = {'D90': [], 'Z6II': [], 'Z8': [], 'Z9': [], 'OTHER': []}
    
    try:
        conn = fdb.connect(
            database=db_path,
            user='SYSDBA',
            password='masterkey',
            charset='UTF8'
        )
        cursor = conn.cursor()
        
        query = """
            SELECT FIRST 30 FILE_PATH, WIN_PATH, FILE_NAME
            FROM IMAGES
            WHERE UPPER(FILE_NAME) LIKE '%.NEF'
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        for row in rows:
            file_path = row[1] if row[1] else row[0]
            file_name = row[2]
            
            if not file_path or not os.path.exists(file_path):
                continue
            
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
            elif 'z9' in path_lower or '_z9' in file_name.lower():
                if len(samples['Z9']) < samples_per_model:
                    samples['Z9'].append(file_path)
            else:
                if len(samples['OTHER']) < samples_per_model:
                    samples['OTHER'].append(file_path)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Database error: {e}")
    
    return samples


def analyze_file_multitier(file_path: str) -> Dict:
    """Test all 3 tiers on a single file"""
    
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
        output_dir = Path("test_output_multitier")
        output_dir.mkdir(exist_ok=True)
        
        # Tier 1: ExifTool
        print("\n🥇 TIER 1: ExifTool Extraction")
        tier1_result = MultiTierNEFExtractor.extract_with_exiftool(file_path)
        
        if tier1_result:
            jpeg_bytes, method = tier1_result
            size_kb = len(jpeg_bytes) / 1024
            print(f"   ✅ SUCCESS via {method}")
            print(f"   📏 Size: {size_kb:.1f} KB")
            
            # Save
            output_file = output_dir / f"{Path(file_path).stem}_tier1_exiftool.jpg"
            with open(output_file, 'wb') as f:
                f.write(jpeg_bytes)
            print(f"   💾 Saved to: {output_file}")
            
            results['tier1'] = {'success': True, 'size_kb': size_kb, 'method': method}
        else:
            print("   ❌ FAILED - ExifTool not available or no preview found")
            results['tier1'] = {'success': False}
        
        # Tier 2: TIFF SubIFD Parser
        print("\n🥈 TIER 2: TIFF SubIFD Parser")
        tier2_result = MultiTierNEFExtractor.extract_from_subifd(data)
        
        if tier2_result:
            jpeg_bytes, method = tier2_result
            size_kb = len(jpeg_bytes) / 1024
            print(f"   ✅ SUCCESS via {method}")
            print(f"   📏 Size: {size_kb:.1f} KB")
            
            # Save
            output_file = output_dir / f"{Path(file_path).stem}_tier2_subifd.jpg"
            with open(output_file, 'wb') as f:
                f.write(jpeg_bytes)
            print(f"   💾 Saved to: {output_file}")
            
            results['tier2'] = {'success': True, 'size_kb': size_kb, 'method': method}
        else:
            print("   ❌ FAILED - Could not parse TIFF SubIFD structure")
            results['tier2'] = {'success': False}
        
        # Tier 3: Marker Scan
        print("\n🥉 TIER 3: SOI/EOI Marker Scan")
        tier3_result = MultiTierNEFExtractor.extract_with_marker_scan(data)
        
        if tier3_result:
            jpeg_bytes, method = tier3_result
            size_kb = len(jpeg_bytes) / 1024
            print(f"   ✅ SUCCESS via {method}")
            print(f"   📏 Size: {size_kb:.1f} KB")
            
            # Save
            output_file = output_dir / f"{Path(file_path).stem}_tier3_marker.jpg"
            with open(output_file, 'wb') as f:
                f.write(jpeg_bytes)
            print(f"   💾 Saved to: {output_file}")
            
            results['tier3'] = {'success': True, 'size_kb': size_kb, 'method': method}
        else:
            print("   ❌ FAILED - No JPEG markers found")
            results['tier3'] = {'success': False}
        
        # Determine winning tier
        print(f"\n🏆 WINNING TIER:")
        if results.get('tier1', {}).get('success'):
            print(f"   Tier 1 (ExifTool) - {results['tier1']['size_kb']:.1f} KB")
        elif results.get('tier2', {}).get('success'):
            print(f"   Tier 2 (SubIFD Parser) - {results['tier2']['size_kb']:.1f} KB")
        elif results.get('tier3', {}).get('success'):
            print(f"   Tier 3 (Marker Scan) - {results['tier3']['size_kb']:.1f} KB")
        else:
            print(f"   ❌ ALL TIERS FAILED")
        
        return results
        
    except Exception as e:
        print(f"\n❌ Error analyzing file: {e}")
        import traceback
        traceback.print_exc()
        return {}


def main():
    print("🔧 Multi-Tier NEF Extraction Test Utility")
    print("="*80)
    print("\nTesting 3-tier extraction approach:")
    print("  🥇 Tier 1: ExifTool (exiftool-vendored equivalent)")
    print("  🥈 Tier 2: TIFF SubIFD Parser")
    print("  🥉 Tier 3: SOI/EOI Marker Scan")
    print()
    
    # Check if exiftool is available
    try:
        result = subprocess.run(['exiftool', '-ver'], capture_output=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.decode().strip()
            print(f"✅ ExifTool found: version {version}")
        else:
            print("⚠️  ExifTool not found - Tier 1 tests will be skipped")
    except FileNotFoundError:
        print("⚠️  ExifTool not found - Tier 1 tests will be skipped")
        print("   Install from: https://exiftool.org/")
    
    # Find sample files
    db_path = "D:/Projects/image-scoring/SCORING_HISTORY.FDB"
    if os.path.exists(db_path):
        print(f"\n📂 Querying database: {db_path}")
        samples = find_sample_files_from_db(db_path, samples_per_model=2)
    else:
        print(f"\n❌ Database not found: {db_path}")
        return
    
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
            results = analyze_file_multitier(file_path)
            model_results.append({
                'file': file_path,
                'results': results
            })
        
        all_results[model] = model_results
    
    # Summary
    print("\n\n" + "="*80)
    print("📊 COMPREHENSIVE SUMMARY")
    print("="*80)
    
    tier_stats = {'tier1': 0, 'tier2': 0, 'tier3': 0, 'failed': 0}
    
    for model, model_results in all_results.items():
        print(f"\n{model}:")
        for item in model_results:
            file_name = Path(item['file']).name
            results = item['results']
            
            if results.get('tier1', {}).get('success'):
                print(f"  🥇 {file_name}: Tier 1 ({results['tier1']['size_kb']:.1f} KB)")
                tier_stats['tier1'] += 1
            elif results.get('tier2', {}).get('success'):
                print(f"  🥈 {file_name}: Tier 2 ({results['tier2']['size_kb']:.1f} KB)")
                tier_stats['tier2'] += 1
            elif results.get('tier3', {}).get('success'):
                print(f"  🥉 {file_name}: Tier 3 ({results['tier3']['size_kb']:.1f} KB)")
                tier_stats['tier3'] += 1
            else:
                print(f"  ❌ {file_name}: ALL TIERS FAILED")
                tier_stats['failed'] += 1
    
    print("\n" + "="*80)
    print("📈 TIER SUCCESS STATISTICS")
    print("="*80)
    total = sum(tier_stats.values())
    if total > 0:
        print(f"\n  🥇 Tier 1 (ExifTool):     {tier_stats['tier1']:2d} / {total} ({100*tier_stats['tier1']/total:.0f}%)")
        print(f"  🥈 Tier 2 (SubIFD):       {tier_stats['tier2']:2d} / {total} ({100*tier_stats['tier2']/total:.0f}%)")
        print(f"  🥉 Tier 3 (Marker Scan):  {tier_stats['tier3']:2d} / {total} ({100*tier_stats['tier3']/total:.0f}%)")
        print(f"  ❌ Failed:               {tier_stats['failed']:2d} / {total} ({100*tier_stats['failed']/total:.0f}%)")
    
    print("\n✅ Multi-tier diagnostic complete!")
    print(f"\n💡 Check test_output_multitier/ folder for extracted previews from each tier")


if __name__ == "__main__":
    main()
