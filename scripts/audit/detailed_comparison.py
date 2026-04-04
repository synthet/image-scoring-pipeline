import yaml
import re

# Extract API routes with more detail
def extract_api_routes_detailed(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    pattern = r'@router\.(get|post|put|patch|delete|head|options)\(\s*["\']([^"\']+)["\']'
    matches = re.findall(pattern, content)
    return {f"{method.upper()} {path}": path for method, path in matches}

api_routes = extract_api_routes_detailed("modules/api.py")
api_db_routes = extract_api_routes_detailed("modules/api_db.py")
all_api_routes = {**api_routes, **api_db_routes}

# Extract OpenAPI paths
with open("docs/reference/api/openapi.yaml", 'r') as f:
    spec = yaml.safe_load(f)

openapi_details = {}
for path, methods in spec['paths'].items():
    for method, details in methods.items():
        if method in ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']:
            key = f"{method.upper()} {path}"
            summary = details.get('summary', 'No summary')
            params = details.get('parameters', [])
            param_names = [p.get('name', '') for p in params]
            openapi_details[key] = {
                'path': path,
                'summary': summary,
                'params': param_names
            }

# Documented routes (in spec)
documented = set(openapi_details.keys())
implemented = set(all_api_routes.keys())

# Routes in both
in_both = implemented & documented
only_in_api = implemented - documented
only_in_spec = documented - implemented

print("\n" + "=" * 100)
print("DOCUMENTED ROUTES (in openapi.yaml)")
print("=" * 100)
for route in sorted(documented):
    print(f"{route:50} - {openapi_details[route]['summary']}")

print("\n" + "=" * 100)
print("ROUTES MISSING FROM OPENAPI.YAML (94 routes)")
print("=" * 100)
print("\nDEBUG/INTERNAL (likely shouldn't be documented):")
debug_routes = [r for r in sorted(only_in_api) if 'debug' in r.lower() or 'ipc' in r.lower()]
for route in debug_routes:
    print(f"  {route}")

print("\nDATABASE/INTERNAL API (api_db.py - likely internal):")
db_routes = [r for r in sorted(only_in_api) if r in api_db_routes]
for route in sorted(db_routes):
    print(f"  {route}")

print("\nMAIN API ROUTES (api.py - should likely be documented):")
main_routes = [r for r in sorted(only_in_api) if r in api_routes and 'debug' not in r.lower() and 'ipc' not in r.lower()]
for route in main_routes:
    print(f"  {route}")
