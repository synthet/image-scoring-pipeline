import sys
import os
from pathlib import Path
from PIL import Image

path = r"D:\Photos\Z6ii\28-400mm\2025\2025-11-18\DSC_6336.NEF"

print(f"Testing {path}")
if not os.path.exists(path):
    print("File not found!")
    sys.exit(1)

try:
    with Image.open(path) as img:
        print(f"Format: {img.format}")
        print(f"Info keys: {img.info.keys()}")
        
        exif = img.getexif()
        print(f"getexif() returned type: {type(exif)}")
        if exif:
            print(f"getexif() keys: {list(exif.keys())}")
            # 306 = DateTime, 36867 = DateTimeOriginal
            print(f"306 (DateTime): {exif.get(306)}")
            print(f"36867 (DateTimeOriginal): {exif.get(36867)}")
            
        if hasattr(img, '_getexif'):
            print("_getexif() exists")
            pk = img._getexif()
            if pk:
                print(f"_getexif keys sample: {list(pk.keys())[:5]}")
                print(f"_getexif 36867: {pk.get(36867)}")
        
except Exception as e:
    print(f"Error: {e}")

import datetime
print(f"ctime: {datetime.datetime.fromtimestamp(os.path.getctime(path))}")
print(f"mtime: {datetime.datetime.fromtimestamp(os.path.getmtime(path))}")
