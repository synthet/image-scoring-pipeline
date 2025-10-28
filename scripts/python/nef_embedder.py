#!/usr/bin/env python3
"""
NEF Keyword Embedding Utility
Embeds keywords into NEF files using proper metadata handling.
"""

import os
import sys
from pathlib import Path
import json

try:
    import piexif
    from PIL import Image
    from PIL.ExifTags import TAGS
except ImportError as e:
    print(f"Missing required dependencies: {e}")
    print("Please install with: pip install piexif pillow")
    sys.exit(1)


def embed_keywords_in_nef(nef_path: str, keywords: list, caption: str = "") -> bool:
    """
    Embed keywords and caption into NEF file metadata using a safer approach.
    
    Args:
        nef_path: Path to the NEF file
        keywords: List of keywords to embed
        caption: Optional caption to embed
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Create a backup of the original file
        backup_path = nef_path + '.backup'
        if not os.path.exists(backup_path):
            import shutil
            shutil.copy2(nef_path, backup_path)
            print(f"Created backup: {backup_path}")
        
        # Load the image with PIL
        image = Image.open(nef_path)
        
        # Get existing EXIF data
        exif_dict = image.getexif()
        
        # Convert to piexif format
        exif_bytes = piexif.dump(exif_dict)
        
        # Prepare keywords for embedding (limit to reasonable number)
        keywords_to_embed = keywords[:15]  # Limit to 15 keywords
        
        # Create new EXIF data with keywords
        new_exif_dict = piexif.load(exif_bytes)
        
        # Add keywords to ImageDescription (tag 270)
        if caption:
            new_exif_dict['0th'][piexif.ImageIFD.ImageDescription] = caption.encode('utf-8')
        
        # Add keywords as a comma-separated string in UserComment (tag 37510)
        if keywords_to_embed:
            keywords_string = ', '.join(keywords_to_embed)
            new_exif_dict['Exif'][piexif.ExifIFD.UserComment] = keywords_string.encode('utf-8')
        
        # Convert back to bytes
        new_exif_bytes = piexif.dump(new_exif_dict)
        
        # Save the image with new EXIF data
        image.save(nef_path, exif=new_exif_bytes)
        
        print(f"Successfully embedded {len(keywords_to_embed)} keywords into {os.path.basename(nef_path)}")
        return True
        
    except Exception as e:
        print(f"Error embedding keywords in {nef_path}: {e}")
        return False


def main():
    """Test the NEF embedding functionality."""
    if len(sys.argv) != 2:
        print("Usage: python nef_embedder.py <nef_file_path>")
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
        "monument", "statue", "public art", "urban", "city", "landmark"
    ]
    
    test_caption = "A man standing in front of a large sculpture"
    
    print(f"Testing keyword embedding for: {nef_path}")
    print(f"Keywords: {', '.join(test_keywords)}")
    print(f"Caption: {test_caption}")
    
    success = embed_keywords_in_nef(nef_path, test_keywords, test_caption)
    
    if success:
        print("✅ Keywords successfully embedded!")
    else:
        print("❌ Failed to embed keywords")


if __name__ == "__main__":
    main()
