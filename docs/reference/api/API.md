# REST API Documentation

The Image Scoring WebUI exposes a REST API layer for programmatic access to scoring and tagging operations.

## Schema Access

For LLM agents and automated tools, the API schema is available in multiple formats:

- **OpenAPI JSON Schema**: `http://127.0.0.1:7860/openapi.json` - Complete OpenAPI 3.0 specification (runtime)
- **OpenAPI YAML**: [openapi.yaml](openapi.yaml) - Standalone OpenAPI 3.0 schema (source)
- **API Contract Summary**: [API_CONTRACT.md](../../technical/API_CONTRACT.md) - Concise endpoint and model reference
- **Simplified Schema**: `http://127.0.0.1:7860/api/schema` - LLM-optimized format
- **Interactive Docs**: `http://127.0.0.1:7860/docs` - Swagger UI for interactive exploration
- **ReDoc**: `http://127.0.0.1:7860/redoc` - Alternative documentation interface

For detailed LLM agent usage, see [API_SCHEMA_LLM.md](API_SCHEMA_LLM.md).

## Base URL

All API endpoints are prefixed with `/api`:
- Development: `http://127.0.0.1:7860/api`
- Production: `http://your-server:7860/api`

## Authentication

Currently, the API does not require authentication. Consider adding authentication for production deployments.

## Endpoints

### Shared Selector Options
- `image_ids`
- `image_paths`
- `folder_ids`
- `folder_paths`
- `recursive` (default `true`)

Overlapping selectors are deduplicated before execution.


### Scoring Operations

#### Start Batch Scoring
```http
POST /api/scoring/start
Content-Type: application/json

{
  "input_path": "/path/to/images",
  "folder_paths": ["/path/to/images"],
  "image_ids": [101, 102],
  "recursive": true,
  "skip_existing": true,
  "force_rescore": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Scoring job started successfully",
  "data": {
    "job_id": 123,
    "input_path": "/path/to/images"
  }
}
```

#### Stop Scoring
```http
POST /api/scoring/stop
```

**Response:**
```json
{
  "success": true,
  "message": "Stop signal sent to scoring job",
  "data": {
    "is_running": false
  }
}
```

#### Get Scoring Status
```http
GET /api/scoring/status
```

**Response:**
```json
{
  "is_running": true,
  "status_message": "Running...",
  "progress": {
    "current": 45,
    "total": 100
  },
  "log": "Starting batch processing...\n...",
  "job_type": "scoring"
}
```

#### Fix Database (Re-score Incomplete)
```http
POST /api/scoring/fix-db
```
No request body. Processes all incomplete records in the database.

**Response:**
```json
{
  "success": true,
  "message": "Database fix operation started",
  "data": {
    "job_id": 124
  }
}
```

#### Score Single Image
```http
POST /api/scoring/single
Content-Type: application/json

{
  "file_path": "/path/to/image.jpg"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Scoring Complete. General Score: 0.85",
  "data": {
    "file_path": "/path/to/image.jpg"
  }
}
```

#### Fix Image Metadata
```http
POST /api/scoring/fix-image
Content-Type: application/json

{
  "file_path": "/path/to/image.jpg"
}
```

Recalculates scores and updates metadata for a single image without running neural networks, using existing data.

### Tagging Operations

#### Start Batch Tagging
```http
POST /api/tagging/start
Content-Type: application/json

{
  "input_path": "/path/to/images",
  "folder_ids": [12],
  "image_paths": ["/path/to/images/a.jpg"],
  "recursive": true,
  "custom_keywords": ["landscape", "sunset"],
  "overwrite": false,
  "generate_captions": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Tagging job started successfully",
  "data": {
    "input_path": "/path/to/images"
  }
}
```

#### Stop Tagging
```http
POST /api/tagging/stop
```

#### Get Tagging Status
```http
GET /api/tagging/status
```

**Response:** Same format as scoring status

#### Tag Single Image
```http
POST /api/tagging/single
Content-Type: application/json

{
  "file_path": "/path/to/image.jpg",
  "custom_keywords": ["landscape"],
  "generate_captions": true
}
```

#### Propagate Tags by Visual Similarity
```http
POST /api/tagging/propagate
Content-Type: application/json

{
  "folder_path": "/path/to/images",
  "dry_run": true,
  "min_votes": 2,
  "min_similarity": 0.85,
  "max_keywords": 10,
  "recursive": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Tag propagation completed",
  "data": {
    "dry_run": true,
    "processed_images": 125,
    "tagged_images": 0,
    "suggestions": [
      {
        "image_id": 901,
        "file_path": "/path/to/images/IMG_0901.jpg",
        "keywords": ["mountain", "sunset"],
        "source_neighbors": [120, 145]
      }
    ]
  }
}
```

### Similarity Operations

#### Find Similar Images
```http
GET /api/similarity/similar?image_id=123&limit=20&min_similarity=0.80
```

**Response:**
```json
{
  "success": true,
  "message": "Found 3 similar images",
  "data": {
    "results": [
      {
        "image_id": 456,
        "file_path": "/path/to/images/IMG_0456.jpg",
        "similarity": 0.942311
      }
    ]
  }
}
```

#### Find Near-Duplicate Pairs
```http
GET /api/similarity/duplicates?threshold=0.98&limit=100
```

**Response:**
```json
{
  "success": true,
  "message": "Found 2 duplicate pairs",
  "data": {
    "results": [
      {
        "image_id_a": 1001,
        "image_id_b": 1002,
        "file_path_a": "/path/to/images/IMG_1001.jpg",
        "file_path_b": "/path/to/images/IMG_1002.jpg",
        "similarity": 0.996501
      }
    ]
  }
}
```

#### Find Visual Outliers
```http
GET /api/similarity/outliers?folder_path=/path/to/images&z_threshold=2.0&k=10
```

**Response:**
```json
{
  "success": true,
  "message": "Found 4 outliers",
  "data": {
    "results": [
      {
        "image_id": 777,
        "file_path": "/path/to/images/IMG_0777.jpg",
        "mean_knn_similarity": 0.321441,
        "z_score": -2.41,
        "nearest_neighbors": [
          { "image_id": 701, "similarity": 0.441122 },
          { "image_id": 702, "similarity": 0.438510 }
        ]
      }
    ]
  }
}
```

### Import Operations

#### Register Images from Folder (Import Without Scoring)
```http
POST /api/import/register
Content-Type: application/json

{
  "folder_path": "/path/to/images",
  "recursive": true,
  "extensions": ["jpg", "jpeg", "png", "nef"],
  "skip_existing": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Import registration completed",
  "data": {
    "registered": 342,
    "skipped_existing": 118,
    "failed": 0,
    "folder_id": 42
  }
}
```

### General Operations

#### Get All Status
```http
GET /api/status
```

**Response:**
```json
{
  "scoring": {
    "available": true,
    "is_running": false,
    "status_message": "Idle",
    "progress": {
      "current": 0,
      "total": 0
    },
    "log": "",
    "job_type": null
  },
  "tagging": {
    "available": true,
    "is_running": false,
    "status_message": "Idle",
    "progress": {
      "current": 0,
      "total": 0
    },
    "log": ""
  },
  "clustering": {
    "available": true,
    "is_running": false,
    "status_message": "Idle",
    "progress": { "current": 0, "total": 0 },
    "log": ""
  }
}
```

### Clustering Operations

#### Start Clustering
```http
POST /api/clustering/start
Content-Type: application/json

{
  "input_path": "/path/to/folder",
  "threshold": 0.15,
  "time_gap": 5,
  "force_rescan": false
}
```

#### Stop Clustering
```http
POST /api/clustering/stop
```

#### Get Clustering Status
```http
GET /api/clustering/status
```

### Data Query Endpoints

#### Query Images (paginated)
```http
GET /api/images?page=1&page_size=50&sort_by=score&order=desc&rating=3,4,5&folder_path=/path
```

#### Get Image Details
```http
GET /api/images/{image_id}
```

#### Get Folders
```http
GET /api/folders
```

#### Get Stacks
```http
GET /api/stacks?folder_path=/path
```

#### Get Stack Images
```http
GET /api/stacks/{stack_id}/images
```

#### Get Database Stats
```http
GET /api/stats
```
Returns: `total_images`, `by_rating`, `by_label`, `score_distribution`, `average_scores`, `total_folders`, `total_stacks`, `jobs_by_status`, `images_today`. Does not include `scored_images` or `tagged_images`. May include `error` on exception.

### Import Register (Electron integration)

Register images from a folder without scoring. Used by the Electron app when the backend is available.

```http
POST /api/import/register
Content-Type: application/json

{
  "folder_path": "D:/Photos/2024"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Import complete: 42 added, 10 skipped",
  "data": {
    "added": 42,
    "skipped": 10,
    "errors": []
  }
}
```

Path conversion: when the backend runs on Linux (WSL), Windows paths are converted to WSL; when the backend runs natively on Windows, paths are kept as-is.

### Pipeline Submit

Submit to the score→tag→cluster pipeline. Starts the first operation immediately; returns `remaining_operations` for chaining.

```http
POST /api/pipeline/submit
Content-Type: application/json

{
  "input_path": "/path/to/folder",
  "operations": ["score", "tag", "cluster"],
  "skip_existing": true,
  "custom_keywords": ["landscape"],
  "generate_captions": false,
  "clustering_threshold": 0.15
}
```

#### Health Check
```http
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "scoring_available": true,
  "tagging_available": true,
  "clustering_available": true
}
```

#### Get Recent Jobs
```http
GET /api/jobs/recent?limit=10
```

**Response:**
```json
[
  {
    "id": 123,
    "input_path": "/path/to/images",
    "status": "completed",
    "created_at": "2026-01-23T10:00:00",
    "updated_at": "2026-01-23T10:30:00"
  }
]
```

#### Get Job Details
```http
GET /api/jobs/{job_id}
```

### Utilities

#### Get RAW File Preview
```http
GET /api/raw-preview?path=<url-encoded-file-path>
```
Use query param `path` (not `file_path`). Returns a JPEG image.

## Error Responses

All endpoints return standard HTTP status codes:
- `200 OK` - Success
- `400 Bad Request` - Invalid request (e.g., path not found)
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error
- `503 Service Unavailable` - Runner not available

Error response format:
```json
{
  "detail": "Error message here"
}
```

## Examples

### Python Example

```python
import requests

BASE_URL = "http://127.0.0.1:7860/api"

# Start scoring
response = requests.post(
    f"{BASE_URL}/scoring/start",
    json={
        "input_path": "D:/Photos/2024",
        "skip_existing": True
    }
)
print(response.json())

# Check status
response = requests.get(f"{BASE_URL}/scoring/status")
status = response.json()
print(f"Progress: {status['progress']['current']}/{status['progress']['total']}")

# Stop if needed
if status['is_running']:
    requests.post(f"{BASE_URL}/scoring/stop")
```

### cURL Example

```bash
# Start scoring
curl -X POST http://127.0.0.1:7860/api/scoring/start \
  -H "Content-Type: application/json" \
  -d '{"input_path": "/path/to/images", "skip_existing": true}'

# Get status
curl http://127.0.0.1:7860/api/scoring/status

# Stop scoring
curl -X POST http://127.0.0.1:7860/api/scoring/stop
```

## Notes

- All paths should use forward slashes (`/`) even on Windows
- **Path conversion:** When the backend runs on Linux (WSL), Windows paths are converted to WSL; when the backend runs natively on Windows, paths are kept as-is
- Jobs run asynchronously - use status endpoints to monitor progress
- The API uses the same runner instances as the web UI, so operations are synchronized

## Related Documents

- [Docs index](../../README.md)
- [API contract summary](../../technical/API_CONTRACT.md) - Concise endpoint and model reference
- [OpenAPI schema](openapi.yaml) - Standalone OpenAPI 3.0 YAML
- [API schema for LLMs](API_SCHEMA_LLM.md)
- [API schema implementation notes](API_SCHEMA_IMPLEMENTATION.md)
- [MCP debugging tools](../../technical/MCP_DEBUGGING_TOOLS.md)
