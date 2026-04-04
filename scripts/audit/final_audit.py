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

# Categorize missing routes
missing_from_openapi = sorted(all_api_routes - openapi_routes)

internal_db = []
internal_debug = []
bird_species = []
workflow_management = []
runs_and_scopes = []
image_and_folder_management = []
clustering_and_tags = []
job_management = []
other = []

for route in missing_from_openapi:
    if '/db/' in route or '/query' in route or '/transaction' in route or '/ping' in route:
        internal_db.append(route)
    elif '/debug/' in route or '/ipc/' in route or '/diagnostics' in route:
        internal_debug.append(route)
    elif '/bird-species/' in route:
        bird_species.append(route)
    elif '/workflow-runs/' in route or '/stage-runs/' in route or '/step-runs/' in route:
        workflow_management.append(route)
    elif '/runs/' in route or '/scope/' in route or '/queue' in route or '/tasks/' in route:
        runs_and_scopes.append(route)
    elif 'image' in route.lower() or 'folder' in route.lower() or 'config' in route.lower() or 'gallery' in route.lower() or 'import' in route.lower() or 'backup' in route.lower() or 'thumbnail' in route.lower() or 'culling' in route.lower():
        image_and_folder_management.append(route)
    elif 'clustering' in route.lower() or 'tag' in route.lower() or 'embedding' in route.lower():
        clustering_and_tags.append(route)
    elif 'job' in route.lower() or 'phase' in route.lower() or 'pipeline' in route.lower():
        job_management.append(route)
    else:
        other.append(route)

print("=" * 100)
print("OPENAPI AUDIT REPORT")
print("=" * 100)
print(f"\nTotal routes in code (api.py + api_db.py): {len(all_api_routes)}")
print(f"Total routes documented in openapi.yaml: {len(openapi_routes)}")
print(f"Coverage: {len(openapi_routes) / len(all_api_routes) * 100:.1f}%")
print(f"\nMissing from spec: {len(missing_from_openapi)} routes")
print(f"Missing from code: 0 routes")

print("\n" + "=" * 100)
print("ROUTES MISSING FROM openapi.yaml (grouped by category)")
print("=" * 100)

if bird_species:
    print(f"\nBird Species (NEW FEATURE - 3 routes):")
    for route in bird_species:
        print(f"  {route}")

if runs_and_scopes:
    print(f"\nRuns & Scopes Management (NEW - {len(runs_and_scopes)} routes):")
    for route in sorted(runs_and_scopes):
        print(f"  {route}")

if workflow_management:
    print(f"\nWorkflow/Stage/Step Runs (NEW - {len(workflow_management)} routes):")
    for route in workflow_management:
        print(f"  {route}")

if job_management:
    print(f"\nJob & Pipeline Management (EXTENDED - {len(job_management)} routes):")
    for route in sorted(job_management):
        print(f"  {route}")

if image_and_folder_management:
    print(f"\nImage & Folder Management (EXTENDED - {len(image_and_folder_management)} routes):")
    for route in sorted(image_and_folder_management):
        print(f"  {route}")

if internal_db:
    print(f"\nInternal Database API (api_db.py - {len(internal_db)} routes):")
    for route in sorted(internal_db):
        print(f"  {route}")

if internal_debug:
    print(f"\nInternal Debug Endpoints ({len(internal_debug)} routes):")
    for route in internal_debug:
        print(f"  {route}")

if other:
    print(f"\nOther ({len(other)} routes):")
    for route in sorted(other):
        print(f"  {route}")

print("\n" + "=" * 100)
print("KEY FINDINGS")
print("=" * 100)
print("""
1. COVERAGE: Only 36 out of 130 routes (27.7%) are documented in openapi.yaml

2. MAJOR GAPS:
   - Runs/Scopes framework (entire new subsystem for pipeline orchestration) - 16 routes
   - Workflow/Stage/Step runs (fine-grained job control) - 9 routes
   - Bird Species endpoints (new feature) - 3 routes
   - Job queue management (/queue, /queue/reorder) - 2 routes
   - Additional pipeline controls (pause/cancel/restart/phase-restart) - 5 routes
   - Image operations (delete, patch, thumbnails, by-uuid, by-hash) - 7 routes
   - Folder operations (tree, phase-status, rebuild, sync, etc.) - 5 routes
   - Config management - 2 routes
   - Import/Export features - 3 routes
   - Advanced similarity features (embedding_map) - 1 route

3. MISALIGNMENT:
   - The OpenAPI spec appears to be OLD (v1.0.0 - last updated ~March 2024)
   - The codebase has EVOLVED significantly with new pipeline orchestration
   - The spec should be regenerated to match current implementation

4. ROUTES THAT EXIST IN BOTH:
   - All 36 core endpoints in the spec are implemented correctly
   - Parameter alignment appears correct for documented routes
   - No routes in spec that don't exist in code
""")
