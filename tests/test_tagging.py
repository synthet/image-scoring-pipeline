
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())


# from modules.tagging import KeywordScorer

def test_loading():
    print("Testing KeywordScorer loading...")
    from modules.tagging import KeywordScorer
    scorer = KeywordScorer()
    # Mock load
    try:
        scorer.load_model()
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Model load failed (expected if no model): {e}")

    
    # Test inference if image available (optional)
    # print(scorer.predict("test_image.jpg"))

if __name__ == "__main__":
    test_loading()
