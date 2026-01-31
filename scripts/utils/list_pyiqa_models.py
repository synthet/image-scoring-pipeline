
try:
    import pyiqa
    print("PyIQA Version:", pyiqa.__version__)
    print("\nAvailable Models:")
    models = pyiqa.list_models()
    for m in models:
        print(f" - {m}")
except ImportError:
    print("PyIQA not installed.")
except Exception as e:
    print(f"Error: {e}")
