#!/usr/bin/env python3
"""
XMP Sidecar Creator for NEF Keywords
Creates XMP sidecar files with keywords for NEF files (more reliable than embedding).
"""

import os
import sys
from pathlib import Path
import json
from datetime import datetime


def create_xmp_sidecar(nef_path: str, keywords: list, caption: str = "") -> bool:
    """
    Create an XMP sidecar file with keywords for the NEF file.
    
    Args:
        nef_path: Path to the NEF file
        keywords: List of keywords to embed
        caption: Optional caption to embed
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Create XMP sidecar file path
        xmp_path = nef_path.replace('.NEF', '.xmp').replace('.nef', '.xmp')
        
        # Prepare keywords for XMP (limit to reasonable number)
        keywords_to_embed = keywords[:20]  # Limit to 20 keywords
        
        # Create XMP content
        xmp_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.6-c140 79.160451, 2017/05/06-01:08:21        ">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"
    xmlns:stEvt="http://ns.adobe.com/xap/1.0/sType/ResourceEvent#"
    xmlns:stRef="http://ns.adobe.com/xap/1.0/sType/ResourceRef#"
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    xmlns:exif="http://ns.adobe.com/exif/1.0/"
    xmlns:tiff="http://ns.adobe.com/tiff/1.0/"
    xmlns:aux="http://ns.adobe.com/exif/1.0/aux/"
    xmlns:lr="http://ns.adobe.com/lightroom/1.0/"
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"
    xmlns:stEvt="http://ns.adobe.com/xap/1.0/sType/ResourceEvent#"
    xmlns:stRef="http://ns.adobe.com/xap/1.0/sType/ResourceRef#"
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    xmlns:exif="http://ns.adobe.com/exif/1.0/"
    xmlns:tiff="http://ns.adobe.com/tiff/1.0/"
    xmlns:aux="http://ns.adobe.com/exif/1.0/aux/"
    xmlns:lr="http://ns.adobe.com/lightroom/1.0/"
    dc:format="image/x-nikon-nef"
    photoshop:ColorMode="3"
    photoshop:ICCProfile="Adobe RGB (1998)"
    xmp:CreatorTool="AI Keyword Extractor"
    xmp:CreateDate="{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
    xmp:ModifyDate="{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
    xmp:MetadataDate="{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
    xmpMM:DocumentID="xmp.did:{os.path.basename(nef_path)}"
    xmpMM:OriginalDocumentID="xmp.did:{os.path.basename(nef_path)}"
    xmpMM:InstanceID="xmp.iid:{os.path.basename(nef_path)}"
    xmpMM:History>
   <xmpMM:History>
    <rdf:Seq>
     <rdf:li rdf:parseType="Resource">
      <stEvt:action="created"
      stEvt:instanceID="xmp.iid:{os.path.basename(nef_path)}"
      stEvt:when="{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
      stEvt:softwareAgent="AI Keyword Extractor"/>
     </rdf:li>
    </rdf:Seq>
   </xmpMM:History>
   <dc:subject>
    <rdf:Bag>'''
        
        # Add keywords
        for keyword in keywords_to_embed:
            xmp_content += f'\n     <rdf:li>{keyword}</rdf:li>'
        
        xmp_content += '''
    </rdf:Bag>
   </dc:subject>'''
        
        # Add caption if provided
        if caption:
            xmp_content += f'''
   <dc:description>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">{caption}</rdf:li>
    </rdf:Alt>
   </dc:description>'''
        
        xmp_content += '''
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''
        
        # Write XMP file
        with open(xmp_path, 'w', encoding='utf-8') as f:
            f.write(xmp_content)
        
        print(f"Successfully created XMP sidecar with {len(keywords_to_embed)} keywords: {os.path.basename(xmp_path)}")
        return True
        
    except Exception as e:
        print(f"Error creating XMP sidecar for {nef_path}: {e}")
        return False


def verify_xmp_sidecar(nef_path: str) -> bool:
    """Verify that XMP sidecar file was created successfully."""
    try:
        xmp_path = nef_path.replace('.NEF', '.xmp').replace('.nef', '.xmp')
        
        if os.path.exists(xmp_path):
            with open(xmp_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if '<rdf:li>' in content and '</rdf:Bag>' in content:
                print(f"XMP sidecar verified: {os.path.basename(xmp_path)}")
                return True
        
        return False
        
    except Exception as e:
        print(f"Error verifying XMP sidecar for {nef_path}: {e}")
        return False


def main():
    """Test the XMP sidecar creation functionality."""
    if len(sys.argv) != 2:
        print("Usage: python xmp_sidecar_creator.py <nef_file_path>")
        sys.exit(1)
    
    nef_path = sys.argv[1]
    
    if not os.path.exists(nef_path):
        print(f"Error: File not found: {nef_path}")
        sys.exit(1)
    
    if not nef_path.lower().endswith('.nef'):
        print("Error: File must be a NEF file")
        sys.exit(1)
    
    # Test keywords
    test_keywords = [
        "sculpture", "man", "standing", "large", "art", "outdoor", 
        "monument", "statue", "public art", "urban", "city", "landmark",
        "photography", "nikon", "d90", "raw", "digital", "professional"
    ]
    
    test_caption = "A man standing in front of a large sculpture"
    
    print(f"Testing XMP sidecar creation for: {nef_path}")
    print(f"Keywords: {', '.join(test_keywords)}")
    print(f"Caption: {test_caption}")
    
    success = create_xmp_sidecar(nef_path, test_keywords, test_caption)
    
    if success:
        print("SUCCESS: XMP sidecar successfully created!")
        
        # Verify the sidecar
        print("\nVerifying XMP sidecar...")
        verify_success = verify_xmp_sidecar(nef_path)
        
        if verify_success:
            print("VERIFICATION: XMP sidecar confirmed!")
        else:
            print("VERIFICATION: Could not confirm XMP sidecar")
    else:
        print("FAILED: Failed to create XMP sidecar")


if __name__ == "__main__":
    main()
