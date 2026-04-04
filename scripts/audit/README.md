# API Audit Scripts

These scripts were used to audit the REST API and OpenAPI consistency in early 2026.

- `compare_apis.py`: Compares the actual API routes in `modules/api.py` and `api_db.py` to the `docs/reference/api/openapi.yaml`.
- `detailed_comparison.py`: Detailed field-by-field comparison of models vs. docs.
- `extract_openapi.py`: Extracts OpenAPI definitions from the Python source using regex/ast.
- `extract_routes.py`: Lists all defined FastAPI routes.
- `final_audit.py`: A synthesis script for final verification of the system state.

These can be run locally using the project's Python environment.
