"""
Comprehensive NEF Extraction Quality Tester
Tests all available tiers and measures preview QUALITY (resolution + size).

Usage:
    python test_all_nef_tiers.py D:/Photos --limit 3 --output test_results
"""

import os
import sys
import subprocess
import struct
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import time
import argparse

try:
    from PIL import Image
except ImportError:
    print("⚠️  PIL not available - preview quality metrics will be limited")
    Image = None

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

# ============================================================================
# TIER 1a: ExifTool CLI
# ============================================================================

def test_tier1a_exiftool_cli(filepath: Path, output_dir: Path) -> Dict:
    """Test ExifTool command-line extraction"""
    try:
        output_file = output_dir / f"{filepath.stem}_tier1a.jpg"
        
        result = subprocess.run(
            ['exiftool', '-b', '-PreviewImage', str(filepath)],
            capture_output=True,
            timeout=10
        )
        
        if result.returncode == 0 and len(result.stdout) > 1000:
            output_file.write_bytes(result.stdout)
            size = len(result.stdout)
            
            # Measure quality
            quality = measure_preview_quality(output_file)
            
            return {
                'success': True,
                'size': size,
                'output_file': str(output_file),
                **quality,
                'message': f"✓ {size / 1024:.1f} KB, {quality.get('megapixels', 0):.1f} MP"
            }
        else:
            return {'success': False, 'message': '✗ No preview found'}
            
    except FileNotFoundError:
        return {'success': False, 'message': '✗ ExifTool not installed'}
    except subprocess.TimeoutExpired:
        return {'success': False, 'message': '✗ Timeout'}
    except Exception as e:
        return {'success': False, 'message': f'✗ Error: {str(e)}'}

# ============================================================================
# TIER 1b: exiftool-vendored (Node.js)
# ============================================================================

def test_tier1b_exiftool_vendored(filepath: Path, output_dir: Path) -> Dict:
    """Test exiftool-vendored (what we implemented in Electron)"""
    try:
        test_script = """
const { exiftool } = require('exiftool-vendored');
const fs = require('fs');

async function extract() {
    try {
        await exiftool.extractJpgFromRaw(process.argv[2], process.argv[3]);
        const stats = fs.statSync(process.argv[3]);
        console.log('SUCCESS', stats.size);
        process.exit(0);
    } catch (e) {
        console.log('FAILED', e.message);
        process.exit(1);
    } finally {
        await exiftool.end();
    }
}

extract();
"""
        
        output_file = output_dir / f"{filepath.stem}_tier1b.jpg"
        script_file = output_dir / "test_extract.js"
        script_file.write_text(test_script)
        
        result = subprocess.run(
            ['node', str(script_file), str(filepath), str(output_file)],
            capture_output=True,
            timeout=15,
            cwd=str(Path(__file__).resolve().parents[2].parent / "image-scoring-gallery")
        )
        
        output_text = result.stdout.decode('utf-8').strip()
        
        if 'SUCCESS' in output_text and output_file.exists():
            size = int(output_text.split()[1])
            quality = measure_preview_quality(output_file)
            
            return {
                'success': True,
                'size': size,
                'output_file': str(output_file),
                **quality,
                'message': f"✓ {size / 1024:.1f} KB, {quality.get('megapixels', 0):.1f} MP"
            }
        else:
            return {'success': False, 'message': f'✗ Failed: {output_text}'}
            
    except FileNotFoundError:
        return {'success': False, 'message': '✗ Node.js not installed'}
    except subprocess.TimeoutExpired:
        return {'success': False, 'message': '✗ Timeout'}
    except Exception as e:
        return {'success': False, 'message': f'✗ Error: {str(e)}'}

# ============================================================================
# TIER 2: TIFF SubIFD Parser
# ============================================================================

def parse_tiff_header(data: bytes) -> Tuple[bool, int]:
    """Parse TIFF header"""
    if len(data) < 8:
        return False, 0
    
    if data[0:2] == b'II':
        little_endian = True
        endian = '<'
    elif data[0:2] == b'MM':
        little_endian = False
        endian = '>'
    else:
        return False, 0
    
    magic = struct.unpack(f'{endian}H', data[2:4])[0]
    if magic != 42:
        return False, 0
    
    ifd0_offset = struct.unpack(f'{endian}I', data[4:8])[0]
    return little_endian, ifd0_offset

def find_subifd_offsets(data: bytes, ifd_offset: int, little_endian: bool) -> List[int]:
    """Find SubIFD offsets"""
    endian = '<' if little_endian else '>'
    
    try:
        num_entries = struct.unpack(f'{endian}H', data[ifd_offset:ifd_offset+2])[0]
        offset = ifd_offset + 2
        
        for i in range(num_entries):
            if offset + 12 > len(data):
                break
                
            tag = struct.unpack(f'{endian}H', data[offset:offset+2])[0]
            count = struct.unpack(f'{endian}I', data[offset+4:offset+8])[0]
            value_offset = offset + 8
            
            if tag == 0x014a:  # SubIFDs tag
                subifd_offsets = []
                for j in range(count):
                    if count == 1:
                        sub_offset = struct.unpack(f'{endian}I', data[value_offset:value_offset+4])[0]
                    else:
                        array_offset = struct.unpack(f'{endian}I', data[value_offset:value_offset+4])[0]
                        sub_offset = struct.unpack(f'{endian}I', data[array_offset+j*4:array_offset+j*4+4])[0]
                    subifd_offsets.append(sub_offset)
                return subifd_offsets
            
            offset += 12
        
        return []
    except Exception:
        return []

def extract_jpeg_from_ifd(data: bytes, ifd_offset: int, little_endian: bool) -> Optional[bytes]:
    """Extract JPEG from IFD"""
    endian = '<' if little_endian else '>'
    
    try:
        num_entries = struct.unpack(f'{endian}H', data[ifd_offset:ifd_offset+2])[0]
        offset = ifd_offset + 2
        
        jpeg_offset = None
        jpeg_length = None
        
        for i in range(num_entries):
            if offset + 12 > len(data):
                break
                
            tag = struct.unpack(f'{endian}H', data[offset:offset+2])[0]
            value_offset = offset + 8
            
            if tag == 0x0201:
                jpeg_offset = struct.unpack(f'{endian}I', data[value_offset:value_offset+4])[0]
            elif tag == 0x0202:
                jpeg_length = struct.unpack(f'{endian}I', data[value_offset:value_offset+4])[0]
            
            if jpeg_offset is not None and jpeg_length is not None:
                return data[jpeg_offset:jpeg_offset+jpeg_length]
            
            offset += 12
        
        return None
    except Exception:
        return None

def test_tier2_subifd(filepath: Path, output_dir: Path) -> Dict:
    """Test TIFF SubIFD parser"""
    try:
        data = filepath.read_bytes()
        
        little_endian, ifd0_offset = parse_tiff_header(data)
        if ifd0_offset == 0:
            return {'success': False, 'message': '✗ Invalid TIFF header'}
        
        subifd_offsets = find_subifd_offsets(data, ifd0_offset, little_endian)
        
        if not subifd_offsets:
            return {'success': False, 'message': '✗ No SubIFDs found'}
        
        for i, subifd_offset in enumerate(subifd_offsets):
            jpeg_data = extract_jpeg_from_ifd(data, subifd_offset, little_endian)
            if jpeg_data:
                output_file = output_dir / f"{filepath.stem}_tier2.jpg"
                output_file.write_bytes(jpeg_data)
                size = len(jpeg_data)
                quality = measure_preview_quality(output_file)
                
                return {
                    'success': True,
                    'size': size,
                    'output_file': str(output_file),
                    **quality,
                    'message': f"✓ {size / 1024:.1f} KB, {quality.get('megapixels', 0):.1f} MP (SubIFD{i})"
                }
        
        return {'success': False, 'message': f'✗ Found {len(subifd_offsets)} SubIFD(s) but no JPEG'}
        
    except Exception as e:
        return {'success': False, 'message': f'✗ Error: {str(e)}'}

# ============================================================================
# TIER 3: JPEG Marker Scanning
# ============================================================================

def test_tier3_marker_scan(filepath: Path, output_dir: Path) -> Dict:
    """Test JPEG SOI/EOI marker scanning"""
    try:
        data = filepath.read_bytes()
        
        # Find all SOI markers
        soi_markers = []
        for i in range(512, len(data) - 1):
            if data[i] == 0xFF and data[i+1] == 0xD8:
                soi_markers.append(i)
        
        if not soi_markers:
            return {'success': False, 'message': '✗ No JPEG SOI markers found'}
        
        # Find complete JPEGs
        candidates = []
        for start in soi_markers:
            for i in range(start + 2, len(data) - 1):
                if data[i] == 0xFF and data[i+1] == 0xD9:
                    end = i + 2
                    size = end - start
                    if size > 10000:
                        candidates.append((start, end, size))
                    break
        
        if not candidates:
            return {'success': False, 'message': f'✗ Found {len(soi_markers)} SOI(s) but no complete JPEGs >10KB'}
        
        # Select largest
        candidates.sort(key=lambda x: x[2], reverse=True)
        start, end, size = candidates[0]
        
        jpeg_data = data[start:end]
        output_file = output_dir / f"{filepath.stem}_tier3.jpg"
        output_file.write_bytes(jpeg_data)
        
        quality = measure_preview_quality(output_file)
        
        return {
            'success': True,
            'size': size,
            'output_file': str(output_file),
            **quality,
            'message': f"✓ {size / 1024:.1f} KB, {quality.get('megapixels', 0):.1f} MP (largest of {len(candidates)})"
        }
        
    except Exception as e:
        return {'success': False, 'message': f'✗ Error: {str(e)}'}

# ============================================================================
# Quality Measurement
# ============================================================================

def measure_preview_quality(jpeg_file: Path) -> Dict:
    """Measure preview quality (resolution, megapixels)"""
    try:
        if Image:
            with Image.open(jpeg_file) as img:
                width, height = img.size
                megapixels = (width * height) / 1_000_000
                return {
                    'width': width,
                    'height': height,
                    'megapixels': megapixels,
                    'aspect_ratio': width / height if height > 0 else 0
                }
        else:
            return {'megapixels': 0}
    except Exception:
        return {'megapixels': 0}

# ===========================================================================
# Main Test Runner
# ============================================================================

def find_nef_files(directory: str, limit: int = 10) -> List[Path]:
    """Find NEF files"""
    nef_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.nef'):
                nef_files.append(Path(root) / file)
                if len(nef_files) >= limit:
                    return nef_files
    return nef_files

def run_comprehensive_test(input_dir: str, output_dir: str, limit: int = 5):
    """Run comprehensive quality-focused test"""
    
    print(f"\n{Colors.BOLD}🔬 Comprehensive NEF Extraction Quality Test{Colors.END}")
    print(f"{'='*80}\n")
    print("Testing ALL tiers and measuring preview QUALITY (resolution + size)\n")
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True, parents=True)
    
    print(f"📂 Searching for NEF files in: {input_dir}")
    nef_files = find_nef_files(input_dir, limit)
    
    if not nef_files:
        print(f"{Colors.RED}✗ No NEF files found!{Colors.END}")
        return
    
    print(f"✓ Found {len(nef_files)} NEF file(s)\n")
    
    results = []
    
    for idx, filepath in enumerate(nef_files, 1):
        file_size = filepath.stat().st_size / (1024 * 1024)
        
        print(f"{Colors.BOLD}[{idx}/{len(nef_files)}] {filepath.name}{Colors.END} ({file_size:.2f} MB)")
        
        result = {
            'file': str(filepath),
            'file_size_mb': file_size,
            'tiers': {}
        }
        
        # Test all tiers
        tiers = [
            ('Tier 1a (ExifTool CLI)', 'tier1a', test_tier1a_exiftool_cli),
            ('Tier 1b (exiftool-vendored)', 'tier1b', test_tier1b_exiftool_vendored),
            ('Tier 2 (SubIFD Parser)', 'tier2', test_tier2_subifd),
            ('Tier 3 (Marker Scan)', 'tier3', test_tier3_marker_scan),
        ]
        
        for label, key, test_func in tiers:
            print(f"  {Colors.BLUE}{label}:{Colors.END} ", end='', flush=True)
            start = time.time()
            tier_result = test_func(filepath, output_path)
            elapsed = time.time() - start
            
            tier_result['time'] = elapsed
            result['tiers'][key] = tier_result
            
            color = Colors.GREEN if tier_result['success'] else Colors.RED
            print(f"{color}{tier_result['message']}{Colors.END} ({elapsed:.2f}s)")
        
        # Determine best quality tier
        best_tier = determine_best_tier(result['tiers'])
        if best_tier:
            result['best_tier'] = best_tier
            print(f"  {Colors.BOLD}🏆 Best Quality:{Colors.END} {best_tier}")
        
        print()
        results.append(result)
    
    # Generate report
    generate_quality_report(results, output_path)

def determine_best_tier(tiers: Dict) -> Optional[str]:
    """Determine which tier produced the highest quality preview"""
    successful_tiers = [(k, v) for k, v in tiers.items() if v['success']]
    
    if not successful_tiers:
        return None
    
    # Sort by megapixels (highest quality), then by file size
    successful_tiers.sort(
        key=lambda x: (x[1].get('megapixels', 0), x[1].get('size', 0)),
        reverse=True
    )
    
    best_key, best_result = successful_tiers[0]
    tier_names = {
        'tier1a': 'Tier 1a (ExifTool CLI)',
        'tier1b': 'Tier 1b (exiftool-vendored)',
        'tier2': 'Tier 2 (SubIFD Parser)',
        'tier3': 'Tier 3 (Marker Scan)'
    }
    return tier_names.get(best_key, best_key)

def generate_quality_report(results: List[Dict], output_path: Path):
    """Generate detailed quality report"""
    
    print(f"\n{Colors.BOLD}📊 Quality Test Summary{Colors.END}")
    print(f"{'='*80}\n")
    
    # Calculate stats
    tier_stats = {}
    tier_labels = {
        'tier1a': 'Tier 1a (ExifTool CLI)',
        'tier1b': 'Tier 1b (exiftool-vendored)',
        'tier2': 'Tier 2 (SubIFD Parser)',
        'tier3': 'Tier 3 (Marker Scan)'
    }
    
    for tier_key in tier_labels.keys():
        tier_stats[tier_key] = {
            'success': 0,
            'total': 0,
            'total_mp': 0,
            'total_size': 0,
            'max_mp': 0
        }
    
    for result in results:
        for tier_key, tier_result in result['tiers'].items():
            stats = tier_stats[tier_key]
            stats['total'] += 1
            
            if tier_result['success']:
                stats['success'] += 1
                mp = tier_result.get('megapixels', 0)
                size = tier_result.get('size', 0)
                stats['total_mp'] += mp
                stats['total_size'] += size
                stats['max_mp'] = max(stats['max_mp'], mp)
    
    # Print summary
    print(f"{'Tier':<35} {'Success Rate':<15} {'Avg MP':<12} {'Max MP':<12} {'Avg Size'}")
    print(f"{'-'*80}")
    
    for tier_key, label in tier_labels.items():
        stats = tier_stats[tier_key]
        success_rate = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0
        avg_mp = (stats['total_mp'] / stats['success']) if stats['success'] > 0 else 0
        avg_size = (stats['total_size'] / stats['success'] / 1024) if stats['success'] > 0 else 0
        
        color = Colors.GREEN if success_rate >= 80 else Colors.YELLOW if success_rate >= 50 else Colors.RED
        
        print(f"{label:<35} {color}{stats['success']}/{stats['total']} ({success_rate:.0f}%){Colors.END:<15} "
              f"{avg_mp:>10.1f} MP  {stats['max_mp']:>10.1f} MP  {avg_size:>10.1f} KB")
    
    # Generate markdown report
    report_file = output_path / "quality_test_report.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# NEF Extraction Quality Test Report\n\n")
        f.write("## Executive Summary\n\n")
        f.write("Comprehensive test of all extraction tiers with quality measurement.\n\n")
        
        # Summary table
        f.write("| Tier | Success Rate | Avg MP | Max MP | Avg Size |\n")
        f.write("|------|--------------|--------|--------|----------|\n")
        
        for tier_key, label in tier_labels.items():
            stats = tier_stats[tier_key]
            success_rate = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0
            avg_mp = (stats['total_mp'] / stats['success']) if stats['success'] > 0 else 0
            avg_size = (stats['total_size'] / stats['success'] / 1024) if stats['success'] > 0 else 0
            
            emoji = '✅' if success_rate >= 80 else '⚠️' if success_rate >= 50 else '❌'
            f.write(f"| {label} | {emoji} {stats['success']}/{stats['total']} ({success_rate:.0f}%) | "
                   f"{avg_mp:.1f} MP | {stats['max_mp']:.1f} MP | {avg_size:.1f} KB |\n")
        
        f.write("\n## Detailed Results\n\n")
        
        for result in results:
            filename = Path(result['file']).name
            f.write(f"### {filename}\n\n")
            f.write(f"File size: {result['file_size_mb']:.2f} MB\n\n")
            
            best_tier = result.get('best_tier', 'None')
            f.write(f"**Best Quality Tier**: {best_tier}\n\n")
            
            f.write("| Tier | Status | Resolution | MP | Size |\n")
            f.write("|------|--------|------------|----|----- |\n")
            
            for tier_key, label in tier_labels.items():
                tier_result = result['tiers'][tier_key]
                if tier_result['success']:
                    width = tier_result.get('width', 0)
                    height = tier_result.get('height', 0)
                    mp = tier_result.get('megapixels', 0)
                    size = tier_result.get('size', 0) / 1024
                    
                    f.write(f"| {label} | ✅ | {width}×{height} | {mp:.1f} | {size:.1f} KB |\n")
                else:
                    f.write(f"| {label} | ❌ | - | - | - |\n")
            
            f.write("\n")
        
        f.write("\n## Recommendation\n\n")
        
        # Find overall best tier
        best_overall = max(tier_stats.items(), key=lambda x: (x[1]['success'], x[1]['max_mp']))
        f.write(f"**Recommended tier**: {tier_labels[best_overall[0]]}\n\n")
        f.write(f"- Success rate: {best_overall[1]['success']}/{best_overall[1]['total']}\n")
        f.write(f"- Maximum quality: {best_overall[1]['max_mp']:.1f} MP\n")
        
        f.write(f"\n---\n\nGenerated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    print(f"\n✓ Quality report saved to: {report_file}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test NEF extraction quality across all tiers')
    parser.add_argument('input_dir', help='Directory containing NEF files')
    parser.add_argument('--output', default='test_quality_results', help='Output directory')
    parser.add_argument('--limit', type=int, default=5, help='Maximum number of files to test')
    
    args = parser.parse_args()
    
    run_comprehensive_test(args.input_dir, args.output, args.limit)
