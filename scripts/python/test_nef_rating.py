#!/usr/bin/env python3
"""
Test script for Nikon NEF rating functionality.
Demonstrates how to write ratings to NEF files based on MUSIQ quality scores.
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from run_all_musiq_models import MultiModelMUSIQ


def test_nef_rating():
    """Test NEF rating functionality with sample scores."""
    scorer = MultiModelMUSIQ()
    
    # Test score to rating conversion
    test_scores = [0.95, 0.8, 0.65, 0.45, 0.2]
    print("Score to Rating Conversion Test:")
    print("=" * 40)
    for score in test_scores:
        rating = scorer.score_to_rating(score)
        print(f"Score: {score:.2f} -> Rating: {rating}/5 stars")
    
    print("\n" + "=" * 40)
    print("NEF Rating Test:")
    print("=" * 40)
    
    # Test with a sample NEF file path (won't actually write unless file exists)
    sample_nef = "D:/Photos/Export/2025/002/DSC_2756.NEF"
    
    if scorer.is_nef_file(sample_nef):
        print(f"✓ File identified as NEF: {sample_nef}")
        
        # Test rating write (will fail gracefully if file doesn't exist)
        rating = 4
        success = scorer.write_rating_to_nef(sample_nef, rating)
        print(f"Rating write test: {'SUCCESS' if success else 'FAILED (expected if file missing)'}")
    else:
        print(f"✗ File not identified as NEF: {sample_nef}")
    
    print("\n" + "=" * 40)
    print("Installation Requirements:")
    print("=" * 40)
    print("For best NEF rating support, install:")
    print("  pip install pyexiv2")
    print("\nAlternative (command line tool):")
    print("  Install exiftool from https://exiftool.org/")
    print("\nFor RAW processing:")
    print("  pip install rawpy")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Test Nikon NEF rating functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_nef_rating.py
  python test_nef_rating.py --nef-file "D:/Photos/test.NEF" --rating 5
        """
    )
    
    parser.add_argument('--nef-file', help='Specific NEF file to test rating on')
    parser.add_argument('--rating', type=int, choices=range(1, 6), help='Rating to write (1-5)')
    
    args = parser.parse_args()
    
    if args.nef_file and args.rating:
        # Test specific file
        scorer = MultiModelMUSIQ()
        
        if not os.path.exists(args.nef_file):
            print(f"Error: File not found: {args.nef_file}")
            return
        
        if not scorer.is_nef_file(args.nef_file):
            print(f"Error: File is not a Nikon NEF file: {args.nef_file}")
            return
        
        print(f"Writing rating {args.rating}/5 to: {args.nef_file}")
        success = scorer.write_rating_to_nef(args.nef_file, args.rating)
        
        if success:
            print("✓ Rating written successfully!")
        else:
            print("✗ Failed to write rating")
    else:
        # Run general test
        test_nef_rating()


if __name__ == "__main__":
    main()
