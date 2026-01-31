#!/usr/bin/env python3
"""
Test script for the keyword extraction tool.
Tests basic functionality with a sample image.
"""

import os
import sys
import tempfile
from pathlib import Path
import pytest

# Add project root to Python path
# Current file is in tests/, project root is parent
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def test_keyword_extractor():
    """Test the keyword extraction tool with a sample image."""
    
    # Check if we can import the required modules
    try:
        from scripts.python.keyword_extractor import KeywordExtractor
        print("✓ Successfully imported KeywordExtractor")
    except ImportError as e:
        print(f"✗ Failed to import KeywordExtractor: {e}")
        return False
    
    # Check if we can create a temporary test image
    try:
        from PIL import Image
        import numpy as np
        
        # Create a simple test image
        test_image = Image.new('RGB', (224, 224), color='blue')
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
            test_image.save(tmp_file.name)
            test_image_path = tmp_file.name
        
        print(f"✓ Created test image: {test_image_path}")
        
    except Exception as e:
        print(f"✗ Failed to create test image: {e}")
        return False
    
    try:
        # Test keyword extraction
        print("Testing keyword extraction...")
        extractor = KeywordExtractor(device="cpu", confidence_threshold=0.01)
        
        result = extractor.extract_keywords(test_image_path)
        
        if "error" in result:
            print(f"✗ Keyword extraction failed: {result['error']}")
            return False
        
        print("✓ Keyword extraction successful!")
        print(f"  Caption: {result['caption']}")
        print(f"  Keywords found: {len(result['keywords'])}")
        
        # Show top 5 keywords
        if result['keywords']:
            print("  Top keywords:")
            for i, kw in enumerate(result['keywords'][:5], 1):
                print(f"    {i}. {kw['keyword']} (confidence: {kw['confidence']:.3f})")
        
        return True
        
    except Exception as e:
        print(f"✗ Error during testing: {e}")
        return False
    
    finally:
        # Clean up test image
        try:
            if 'test_image_path' in locals():
                os.unlink(test_image_path)
                print("✓ Cleaned up test image")
        except:
            pass

def test_dependencies():
    """Test if all required dependencies are available."""
    print("Testing dependencies...")
    
    dependencies = [
        ('torch', 'PyTorch'),
        ('transformers', 'Transformers'),
        ('keybert', 'KeyBERT'),
        ('spacy', 'spaCy'),
        ('PIL', 'Pillow'),
        ('numpy', 'NumPy')
    ]
    
    all_good = True
    
    for module, name in dependencies:
        try:
            __import__(module)
            print(f"✓ {name} is available")
        except ImportError:
            print(f"✗ {name} is not available")
            all_good = False
    
    return all_good


def test_keyword_extractor_main():
    """Run all tests."""
    print("=" * 50)
    print("Keyword Extraction Tool - Test Suite")
    print("=" * 50)
    
    # Test dependencies first
    if not test_dependencies():
        print("\n✗ Dependency test failed. Please install missing dependencies:")
        print("pip install -r requirements/requirements_keyword_extraction.txt")
        print("python -m spacy download en_core_web_sm")
        return False
    
    print("\n" + "=" * 50)
    
    # Test keyword extraction
    if test_keyword_extractor():
        print("\n✓ All tests passed!")
        return True
    else:
        print("\n✗ Tests failed!")
        return False

def test_keyword_extractor_pytest():
    """Pytest-compatible wrapper."""
    if not test_dependencies():
        pytest.skip("Dependencies missing")
    success = test_keyword_extractor()
    assert success, "Keyword extraction failed"

if __name__ == "__main__":
    success = test_keyword_extractor_main()
    sys.exit(0 if success else 1)
