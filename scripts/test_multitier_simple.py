#!/usr/bin/env python3
"""
Simplified Multi-Tier NEF Extraction Test

Tests the extraction tiers using files already found in test_output.
No database or ExifTool required.
"""

import os
from pathlib import Path
from typing import Tuple, Optional
import struct


class MultiTierNEFExtractor:
    """Test extraction tiers 2 and 3 (TIFF SubIFD + Marker Scan)"""
    
    @staticmethod
    def extract_from_subifd(data: bytes) -> Optional[Tuple[bytes, str]]:
        """
        Tier 2: Parse TIFF structure and extract from SubIFD0
        Returns: (jpeg_bytes, method_description) or None
        """
        try:
            if len(data) < 8:
                return None
            
            # Read byte order
            if data[0:2] == b'II':
                endian = '<'
            elif data[0:2] == b'MM':
                endian = '>'
            else:
                return None
            
            # Verify TIFF magic (42)
            magic = struct.unpack(f'{endian}H', data[2:4])[0]
            if magic != 42:
                return None
            
            # Get IFD0 offset
            ifd0_offset = struct.unpack(f'{endian}I', data[4:8])[0]
            
            # Parse IFD0 for SubIFD tag (0x014a)
            subifd_offsets = MultiTierNEFExtractor._parse_ifd_for_subifd(data, ifd0_offset, endian)
            
            # Try each SubIFD
            for subifd_offset in subifd_offsets:
                jpeg = MultiTierNEFExtractor._extract_jpeg_from_ifd(data, subifd_offset, endian)
                if jpeg:
                    return (jpeg, f"TIFF SubIFD Parser (offset {subifd_offset})")
            
            return None
            
        except Exception as e:
            return None
    
    @staticmethod
    def _parse_ifd_for_subifd(data: bytes, ifd_offset: int, endian: str) -> list:
        """Parse IFD to find SubIFD offsets (tag 0x014a)"""
        offsets = []
        
        try:
            if ifd_offset + 2 > len(data):
                return offsets
            
            num_entries = struct.unpack(f'{endian}H', data[ifd_offset:ifd_offset+2])[0]
            
            for i in range(num_entries):
                entry_offset = ifd_offset + 2 + (i * 12)
                if entry_offset + 12 > len(data):
                    break
                
                tag = struct.unpack(f'{endian}H', data[entry_offset:entry_offset+2])[0]
                
                if tag == 0x014a:  # SubIFDs tag
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
                
                if tag == 0x0201:  # JPEGInterchangeFormat
                    jpeg_offset = value
                elif tag == 0x0202:  # JPEGInterchangeFormatLength
                    jpeg_length = value
            
            if jpeg_offset and jpeg_length and jpeg_offset + jpeg_length <= len(data):
                jpeg_data = data[jpeg_offset:jpeg_offset+jpeg_length]
                if jpeg_data[0:2] == b'\xff\xd8':
                    return jpeg_data
            
            return None
            
        except Exception:
            return None
    
    @staticmethod
    def extract_with_marker_scan(data: bytes) -> Optional[Tuple[bytes, str]]:
        """
        Tier 3: Find all JPEGs via SOI/EOI markers, return largest
        """
        try:
            results = []
            
            # Find all SOI markers
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
                        if size > 10000:
                            results.append((start, end, size))
                        break
            
            if not results:
                return None
            
            # Get largest
            results.sort(key=lambda x: x[2], reverse=True)
            start, end, size = results[0]
            
            return (data[start:end], f"Marker Scan ({len(results)} JPEGs found, using largest)")
            
        except Exception:
            return None


def find_nef_files():
    """Find NEF files to test"""
    nef_files = []
    
    # Check common locations
    search_paths = [
        "D:/Photos",
        "D:/Pictures",
        Path.home() / "Pictures"
    ]
    
    for search_path in search_paths:
        if not Path(search_path).exists():
            continue
        
        print(f"Searching: {search_path}")
        for root, dirs, files in os.walk(search_path):
            for file in files:
                if file.lower().endswith('.nef'):
                    nef_files.append(os.path.join(root, file))
                    if len(nef_files) >= 10:  # Limit to 10 files
                        return nef_files
    
    return nef_files


def analyze_file(file_path: str):
    """Test both tiers on a file"""
    
    print(f"\n{'='*80}")
    print(f"📸 {Path(file_path).name}")
    print(f"{'='*80}")
    
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        file_size_mb = len(data) / (1024 * 1024)
        print(f"File size: {file_size_mb:.2f} MB")
        
        output_dir = Path("test_output_multitier")
        output_dir.mkdir(exist_ok=True)
        
        # Tier 2: TIFF SubIFD
        print("\n🥈 Tier 2: TIFF SubIFD Parser")
        tier2 = MultiTierNEFExtractor.extract_from_subifd(data)
        
        if tier2:
            jpeg_bytes, method = tier2
            size_kb = len(jpeg_bytes) / 1024
            print(f"   ✅ {size_kb:.1f} KB - {method}")
            
            output_file = output_dir / f"{Path(file_path).stem}_tier2.jpg"
            with open(output_file, 'wb') as f:
                f.write(jpeg_bytes)
        else:
            print("   ❌ Failed")
        
        # Tier 3: Marker Scan
        print("🥉 Tier 3: Marker Scan")
        tier3 = MultiTierNEFExtractor.extract_with_marker_scan(data)
        
        if tier3:
            jpeg_bytes, method = tier3
            size_kb = len(jpeg_bytes) / 1024
            print(f"   ✅ {size_kb:.1f} KB - {method}")
            
            output_file = output_dir / f"{Path(file_path).stem}_tier3.jpg"
            with open(output_file, 'wb') as f:
                f.write(jpeg_bytes)
        else:
            print("   ❌ Failed")
        
        # Winner
        if tier2 and tier3:
            t2_size = len(tier2[0])
            t3_size = len(tier3[0])
            if t2_size == t3_size:
                print(f"\n🏆 Both tiers extracted same JPEG ({t2_size/1024:.1f} KB)")
            elif t2_size > t3_size:
                print(f"\n🏆 Tier 2 found larger preview ({t2_size/1024:.1f} KB vs {t3_size/1024:.1f} KB)")
            else:
                print(f"\n🏆 Tier 3 found larger preview ({t3_size/1024:.1f} KB vs {t2_size/1024:.1f} KB)")
        elif tier2:
            print(f"\n🏆 Only Tier 2 succeeded")
        elif tier3:
            print(f"\n🏆 Only Tier 3 succeeded")
        else:
            print(f"\n❌ Both tiers failed")
        
        return {'tier2': tier2 is not None, 'tier3': tier3 is not None}
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {'tier2': False, 'tier3': False}


def main():
    print("🔧 Simplified Multi-Tier NEF Extraction Test")
    print("="*80)
    
    # Find test files
    nef_files = find_nef_files()
    
    if not nef_files:
        print("❌ No NEF files found in D:/Photos or Pictures")
        return
    
    print(f"\n✅ Found {len(nef_files)} NEF file(s)")
    
    # Test each
    results = []
    for nef_file in nef_files[:5]:  # Test first 5
        result = analyze_file(nef_file)
        results.append(result)
    
    # Summary
    print("\n\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    
    tier2_success = sum(1 for r in results if r['tier2'])
    tier3_success = sum(1 for r in results if r['tier3'])
    total = len(results)
    
    print(f"\n🥈 Tier 2 (SubIFD):    {tier2_success}/{total} ({100*tier2_success/total:.0f}%)")
    print(f"🥉 Tier 3 (Marker):    {tier3_success}/{total} ({100*tier3_success/total:.0f}%)")
    
    print(f"\n💡 Extracted previews saved to: test_output_multitier/")


if __name__ == "__main__":
    main()
