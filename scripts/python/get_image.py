
import sys
import os
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

from modules import db

conn = db.get_db()
c = conn.cursor()
c.execute("SELECT first 1 file_path FROM images")
row = c.fetchone()
print(row[0])
conn.close()
