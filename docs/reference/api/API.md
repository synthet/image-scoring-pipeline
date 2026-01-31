# REST API Documentation

The Image Scoring WebUI exposes a REST API layer for programmatic access to scoring and tagging operations.

## Schema Access

For LLM agents and automated tools, the API schema is available in multiple formats:

- **OpenAPI JSON Schema**: `http://127.0.0.1:7860/openapi.json` - Complete OpenAPI 3.0 specification
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

### Scoring Operations

#### Start Batch Scoring
```http
POST /api/scoring/start
Content-Type: application/json

{
  "input_path": "/path/to/images",
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
  }
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
  "tagging_available": true
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
- Paths are automatically converted between Windows and WSL formats when needed
- Jobs run asynchronously - use status endpoints to monitor progress
- The API uses the same runner instances as the web UI, so operations are synchronized

## Related Documents

- [Docs index](../../README.md)
- [API schema for LLMs](API_SCHEMA_LLM.md)
- [API schema implementation notes](API_SCHEMA_IMPLEMENTATION.md)
- [MCP debugging tools](../../technical/MCP_DEBUGGING_TOOLS.md)

