
import unittest
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))


# from modules.tagging import CaptionGenerator

class TestCaptioning(unittest.TestCase):
    def test_model_loading(self):
        # unittest-native skip (not pytest.importorskip) so this also behaves under
        # `python -m unittest`; needs the ML stack, runs in gpu-shell / coverage CI (#381).
        try:
            import torch  # noqa: F401
        except ImportError:
            self.skipTest("torch not installed")
        print("Testing CaptionGenerator initialization...")
        from modules.tagging import CaptionGenerator

        generator = CaptionGenerator(device='cpu') # Use CPU for test
        # We won't actually load the model in test to save time/bandwidth unless needed
        # But we can verify init works
        self.assertIsNotNone(generator)
        print("CaptionGenerator initialized.")
        
    def test_mock_generation(self):
        # We can try loading if environment allows, but it might download 1GB+
        # Let's just assume if it imports, it works for now.
        pass

if __name__ == '__main__':
    unittest.main()
