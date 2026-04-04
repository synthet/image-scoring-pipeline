import yaml
import re

# Extract API routes
def extract_api_routes(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    pattern = r'@router\.(get|post|put|patch|delete|head|options)\(\s*["\']([^"\']+)["\']'
    matches = re.findall(pattern, content)
    return set(f"{method.upper()} {path}" for method, path in matches)

api_routes = extract_api_routes("modules/api.py")
api_db_routes = extract_api_routes("modules/api_db.py")
all_api_routes = api_routes | api_db_routes

# Extract OpenAPI paths
with open("docs/reference/api/openapi.yaml", 'r') as f:
    spec = yaml.safe_load(f)

openapi_routes = set()
for path, methods in spec['paths'].items():
    for method in methods.keys():
        if method in ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']:
            openapi_routes.add(f"{method.upper()} {path}")

# Find differences
missing_from_openapi = all_api_routes - openapi_routes
missing_from_api = openapi_routes - all_api_routes

print("=" * 80)
print("ROUTES MISSING FROM openapi.yaml (exist in code but not in spec)")
print("=" * 80)
for route in sorted(missing_from_openapi):
    print(f"  {route}")

print("\n" + "=" * 80)
print("ROUTES MISSING FROM CODE (exist in openapi.yaml but not in code)")
print("=" * 80)
for route in sorted(missing_from_api):
    print(f"  {route}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Total routes in api.py: {len(api_routes)}")
print(f"Total routes in api_db.py: {len(api_db_routes)}")
print(f"Total routes in code: {len(all_api_routes)}")
print(f"Total routes in openapi.yaml: {len(openapi_routes)}")
print(f"\nMissing from spec: {len(missing_from_openapi)}")
print(f"Missing from code: {len(missing_from_api)}")
print(f"In sync: {len(all_api_routes & openapi_routes)}")
