
import sys
import os
import logging
from typing import Dict, Any

# Add project root to path
sys.path.append(os.getcwd())

# Mock the logger
def mock_logger(msg):
    print(f"[LOG] {msg}")

try:
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ
except ImportError:
    # If running from project root
    sys.path.append(os.path.join(os.getcwd(), 'scripts', 'python'))
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ

def test_crash():
    print("Initializing MultiModelMUSIQ...")
    scorer = MultiModelMUSIQ(skip_gpu=True)
    
    # Create a dummy image file
    with open("dummy_test_image.jpg", "wb") as f:
        f.write(b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xFF\xDB\x00C\x00\x03\x02\x02\x03\x02\x02\x03\x03\x03\x03\x04\x03\x03\x04\x05\x08\x05\x05\x04\x04\x05\n\x07\x07\x06\x08\x0c\n\x0c\x0c\x0b\n\x0b\x0b\r\x0e\x12\x10\r\x0e\x11\x0e\x0b\x0b\x10\x16\x10\x11\x13\x14\x15\x15\x15\x0c\x0f\x17\x18\x16\x14\x18\x12\x14\x15\x14\xFF\xC0\x00\x11\x08\x00\x10\x00\x10\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01\xFF\xDA\x00\x0C\x03\x01\x00\x02\x11\x03\x11\x00\x3F\x00\xBF\x00\xFF\xD9')

    # Simulate external scores WITHOUT normalized_score
    # This reflects what happens when ResultWorker passes backfilled scores 
    # or when remote_scoring.py returns a result that hasn't been normalized yet
    external_scores = {
        'everypixel': {
            'score': 0.85, 
            'status': 'success'
            # 'normalized_score' is MISSING, which should cause the crash
        }
    }

    print("\n[TEST] Running run_all_models with missing normalized_score...")
    try:
        results = scorer.run_all_models(
            "dummy_test_image.jpg", 
            external_scores=external_scores,
            logger=mock_logger,
            write_metadata=False
        )
        print("\n[SUCCESS] Pipeline finished without crashing!")
        print(f"Results models keys: {results['models'].keys()}")
        if 'everypixel' in results['models']:
            print(f"EveryPixel Result: {results['models']['everypixel']}")
            
    except KeyError as e:
        print(f"\n[FAILURE] Crashed as expected with KeyError: {e}")
    except Exception as e:
        print(f"\n[FAILURE] Crashed with unexpected exception: {e}")
    finally:
        if os.path.exists("dummy_test_image.jpg"):
            os.remove("dummy_test_image.jpg")
            
if __name__ == "__main__":
    test_crash()
