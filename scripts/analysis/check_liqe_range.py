import pyiqa
try:
    metric = pyiqa.create_metric('liqe', device='cpu')
    print(f"Score Range: {getattr(metric, 'score_range', 'Unknown')}")
    print(f"Lower: {getattr(metric, 'lower_bound', 'Unknown')}")
    print(f"Upper: {getattr(metric, 'upper_bound', 'Unknown')}")
except Exception as e:
    print(f"Error: {e}")
