#!/usr/bin/env python3
"""
GPU Test Script
Tests if GPU is available and working with TensorFlow
"""

import os
import sys

# Set environment variables
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Reduce TensorFlow logging

def test_gpu_functional():
    """Test GPU functionality with assertions."""
    import pytest
    try:
        import tensorflow as tf
    except ImportError:
        pytest.skip("TensorFlow not installed")
        
    success = test_gpu()
    assert success, "GPU test failed"

def test_musiq_gpu_functional():
    """Test MUSIQ GPU implementation with assertions."""
    import pytest
    try:
        import tensorflow as tf
        import torch # run_musiq_gpu might use torch or just TF
    except ImportError:
        pytest.skip("Machine learning dependencies not installed")
        
    success = test_musiq_gpu()
    assert success, "MUSIQ GPU test failed"

if __name__ == "__main__":
    print("GPU and MUSIQ Test Suite")
    print("=" * 50)
    
    gpu_ok = test_gpu()
    
    if gpu_ok:
        musiq_ok = test_musiq_gpu()
        
        if musiq_ok:
            print("\n🎉 All tests passed! GPU is working correctly.")
            print("You can now use the GPU implementation of MUSIQ.")
        else:
            print("\n⚠️  GPU is working but MUSIQ GPU implementation has issues.")
            print("You can still use the CPU fallback.")
    else:
        print("\n❌ GPU tests failed.")
        print("The MUSIQ implementation will fall back to CPU.")
    
    print("\nTo run MUSIQ with GPU:")
    print("python run_musiq_gpu.py --image sample.jpg")
