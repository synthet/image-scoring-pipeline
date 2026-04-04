import yaml

with open("docs/reference/api/openapi.yaml", 'r') as f:
    spec = yaml.safe_load(f)

openapi_paths = {}
for path, methods in spec['paths'].items():
    for method in methods.keys():
        if method in ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']:
            key = f"{method.upper()} {path}"
            openapi_paths[key] = methods[method].get('summary', '')

print("=== OpenAPI spec paths ===")
for path in sorted(openapi_paths.keys()):
    summary = openapi_paths[path]
    print(f"{path:60} - {summary}")
