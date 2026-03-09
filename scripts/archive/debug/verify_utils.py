
import sys
import os

# Mock utils for unit checking if needed, but we want to test the real one.
sys.path.append(os.getcwd())
from modules import utils

print("--- Verifying Utils Fix ---")
test_cases = [
    ("/mnt/d/Photos", "D:/Photos"),
    ("\\mnt\\d\\Photos", "D:/Photos"),
    (r"\mnt\d\Photos", "D:/Photos"),
    ("/mnt", "/mnt"), # Should remain or be handled?
    ("/", "/") # Should remain?
]

for inp, expected in test_cases:
    out = utils.convert_path_to_local(inp)
    print(f"Input: {repr(inp)} -> Output: {repr(out)}")
