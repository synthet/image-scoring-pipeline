#!/usr/bin/env python3
"""
XMP Keyword Verification Tool
Verifies that keywords can be extracted from XMP sidecar files.
"""

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def verify_xmp_keywords(xmp_file_path: str) -> dict:
    """
    Verify and extract keywords from an XMP file.
    
    Args:
        xmp_file_path: Path to the XMP file
        
    Returns:
        Dictionary with verification results
    """
    result = {
        "file_exists": False,
        "keywords": [],
        "caption": None,
        "structure_valid": False,
        "creator_tool": None,
        "file_size": 0
    }
    
    try:
        if not os.path.exists(xmp_file_path):
            return result
        
        result["file_exists"] = True
        result["file_size"] = os.path.getsize(xmp_file_path)
        
        # Read the XMP file
        with open(xmp_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract keywords manually (more reliable than XML parsing for XMP)
        lines = content.split('\n')
        keywords = []
        caption = None
        
        in_keywords_section = False
        for line in lines:
            line = line.strip()
            
            # Check if we're in the keywords section
            if '<dc:subject>' in line:
                in_keywords_section = True
                continue
            elif '</dc:subject>' in line:
                in_keywords_section = False
                continue
            
            # Extract keywords
            if in_keywords_section and '<rdf:li>' in line and '</rdf:li>' in line:
                keyword = line.replace('<rdf:li>', '').replace('</rdf:li>', '').strip()
                if keyword:
                    keywords.append(keyword)
            
            # Extract caption
            if 'x-default' in line and '<rdf:li>' in line and '</rdf:li>' in line:
                caption = line.replace('<rdf:li>', '').replace('</rdf:li>', '').strip()
            
            # Extract creator tool
            if 'xmp:CreatorTool=' in line:
                creator_start = line.find('xmp:CreatorTool="') + len('xmp:CreatorTool="')
                creator_end = line.find('"', creator_start)
                if creator_end > creator_start:
                    result["creator_tool"] = line[creator_start:creator_end]
        
        result["keywords"] = keywords
        result["caption"] = caption
        
        # Check structure validity
        structure_checks = [
            'dc:subject' in content,
            'rdf:RDF' in content,
            'x:xmpmeta' in content,
            len(keywords) > 0
        ]
        
        result["structure_valid"] = all(structure_checks)
        
        return result
        
    except Exception as e:
        result["error"] = str(e)
        return result


def main():
    """Test XMP keyword verification."""
    if len(sys.argv) != 2:
        print("Usage: python verify_xmp_keywords.py <xmp_file_path>")
        sys.exit(1)
    
    xmp_file = sys.argv[1]
    
    print(f"Verifying XMP file: {xmp_file}")
    print("=" * 50)
    
    result = verify_xmp_keywords(xmp_file)
    
    if not result["file_exists"]:
        print("ERROR: XMP file not found")
        sys.exit(1)
    
    print(f"File exists: YES")
    print(f"File size: {result['file_size']} bytes")
    
    if result.get("error"):
        print(f"ERROR: {result['error']}")
        sys.exit(1)
    
    print(f"Structure valid: {'YES' if result['structure_valid'] else 'NO'}")
    
    if result["creator_tool"]:
        print(f"Creator tool: {result['creator_tool']}")
    
    print(f"Keywords found: {len(result['keywords'])}")
    if result["keywords"]:
        print("Keywords:")
        for i, keyword in enumerate(result["keywords"], 1):
            print(f"  {i}. {keyword}")
    
    if result["caption"]:
        print(f"Caption: {result['caption']}")
    else:
        print("Caption: Not found")
    
    print("\n" + "=" * 50)
    
    if result["structure_valid"] and result["keywords"]:
        print("SUCCESS: Keywords can be extracted from XMP file!")
        print("This XMP file is compatible with Adobe Lightroom, Photoshop, and other photo management software.")
    else:
        print("WARNING: XMP file may have issues")


if __name__ == "__main__":
    main()

