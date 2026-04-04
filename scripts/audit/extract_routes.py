import re
import sys

def extract_routes(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Pattern for decorator with method and path
    pattern = r'@router\.(get|post|put|patch|delete|head|options)\(\s*["\']([^"\']+)["\']'
    
    matches = re.findall(pattern, content)
    return matches

# Extract from api.py
api_routes = extract_routes("modules/api.py")
api_db_routes = extract_routes("modules/api_db.py")

print("=== api.py routes ===")
for method, path in api_routes:
    print(f"{method.upper():6} {path}")

print("\n=== api_db.py routes ===")
for method, path in api_db_routes:
    print(f"{method.upper():6} {path}")
