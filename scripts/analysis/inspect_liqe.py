import pyiqa
import torch

try:
    metric = pyiqa.create_metric('liqe', device='cpu')
    print(f"Metric Type: {type(metric)}")
    print(f"Lower Bound: {getattr(metric, 'lower_bound', 'Unknown')}")
    print(f"Upper Bound: {getattr(metric, 'upper_bound', 'Unknown')}")
    
    # Try to inspect input requirements if documented in docstring
    print(f"Docstring: {metric.__doc__}")

    # Create dummy input (0-1 float)
    dummy_01 = torch.rand(1, 3, 224, 224)
    score_01 = metric(dummy_01).item()
    print(f"Score for 0-1 input: {score_01}")

    # Create dummy input (0-255 float)
    dummy_255 = dummy_01 * 255.0
    score_255 = metric(dummy_255).item()
    print(f"Score for 0-255 input: {score_255}")

except Exception as e:
    print(f"Error: {e}")
