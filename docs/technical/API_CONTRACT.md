# API Contract Summary

REST API for the Image Scoring WebUI. Base path: `/api`.

## Overview

| Category | Endpoints |
|----------|-----------|
| **Scoring** | start, stop, status, fix-db, single, fix-image |
| **Tagging** | start, stop, status, single |
| **Clustering** | start, stop, status |
| **Data Queries** | images, images/{id}, folders, stacks, stacks/{id}/images, stats |
| **Pipeline** | submit |
| **Import** | register |
| **General** | status, health, schema |
| **Jobs** | recent, {job_id} |
| **Utilities** | raw-preview, similar, duplicates/find |

### Utilities

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/raw-preview` | Get RAW file preview (JPEG) |

**GET /api/raw-preview** — Use query param `path` (not `file_path`):
```
GET /api/raw-preview?path=<url-encoded-file-path>
```

### fix-db (no request body)

`POST /api/scoring/fix-db` takes **no request body**. It processes all incomplete records in the database. Do not send `input_path`.

---

## Standard Response Models

### ApiResponse (operation results)
```json
{
  "success": true,
  "message": "string",
  "data": { ... }  // optional
}
```

### StatusResponse (job status)
```json
{
  "is_running": true,
  "status_message": "string",
  "progress": { "current": 0, "total": 0 },
  "log": "string",
  "job_type": "scoring|tagging|clustering|fix_db|null"
}
```

### HealthResponse
```json
{
  "status": "healthy",
  "scoring_available": true,
  "tagging_available": true,
  "clustering_available": true
}
```

---

## Clustering Endpoints (New)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/clustering/start` | Start clustering job |
| POST | `/api/clustering/stop` | Stop clustering job |
| GET | `/api/clustering/status` | Get clustering status |

### ClusteringStartRequest
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| input_path | string | No | Folder path; null = all unprocessed |
| threshold | float | No | Distance threshold (lower = stricter) |
| time_gap | int | No | Time gap (seconds) for burst grouping |
| force_rescan | bool | No | Re-cluster even if processed (default: false) |

---

## Data Query Endpoints (New)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/images` | Paginated image query with filters |
| GET | `/api/images/{image_id}` | Single image details |
| GET | `/api/folders` | Folder listing |
| GET | `/api/stacks` | Stacks with cover images |
| GET | `/api/stacks/{stack_id}/images` | Images in a stack |
| GET | `/api/stats` | Database statistics |

### GET /api/images — Query Parameters
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| page | int | 1 | Page number |
| page_size | int | 50 | Items per page (1–500) |
| sort_by | string | "score" | score, date, name, rating, score_general, score_aesthetic, score_technical |
| order | string | "desc" | asc, desc |
| rating | string | — | Comma-separated (e.g. "3,4,5") |
| label | string | — | Comma-separated (e.g. "Green,Blue") |
| keyword | string | — | Partial match |
| min_score_general | float | 0 | 0–1 |
| min_score_aesthetic | float | 0 | 0–1 |
| min_score_technical | float | 0 | 0–1 |
| folder_path | string | — | Filter by folder |
| stack_id | int | — | Filter by stack |

### GET /api/images — Response
```json
{
  "images": [...],
  "total": 1234,
  "page": 1,
  "page_size": 50,
  "total_pages": 25
}
```

### GET /api/folders — Response
```json
{
  "folders": [...],
  "count": 42
}
```

### GET /api/stacks — Query Parameters
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| folder_path | string | — | Filter by folder |
| sort_by | string | "score_general" | Sort field |
| order | string | "desc" | asc, desc |

### GET /api/stacks — Response
```json
{
  "stacks": [...],
  "count": 15
}
```

### GET /api/stacks/{stack_id}/images — Response
```json
{
  "images": [...],
  "count": 8,
  "stack_id": 42
}
```

### GET /api/stats — Response (DatabaseStats)

| Field | Type | Description |
|-------|------|-------------|
| total_images | int | Total image count |
| by_rating | Record<string, number> | Counts by rating (1–5) |
| by_label | Record<string, number> | Counts by label (Red, Yellow, Green, etc.) |
| score_distribution | Record<string, number> | Buckets (e.g. "0.0-0.2", "0.2-0.4") |
| average_scores | object | general, technical, aesthetic, spaq, koniq, liqe |
| total_folders | int | Folder count |
| total_stacks | int | Stack count |
| jobs_by_status | Record<string, number> | Counts by job status |
| images_today | int | Images created today |
| error | string? | Present only when an exception occurred |

**Note:** Does not include `scored_images` or `tagged_images`.

---


| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/import/register` | Register images from folder (no scoring) |

### ImportRegisterRequest
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| folder_path | string | Yes | Folder path (Windows or WSL) |

Used by Electron when the backend is available. Path conversion applies per backend platform (see Design Notes).

---

## Pipeline Endpoint (New)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/pipeline/submit` | Submit to score→tag→cluster pipeline |

### PipelineSubmitRequest
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| input_path | string | Yes | File or directory path |
| operations | string[] | No | ["score","tag","cluster"] (default: ["score","tag"]) |
| skip_existing | bool | No | Skip images with results (default: true) |
| custom_keywords | string[] | No | For tagging |
| generate_captions | bool | No | For tagging (default: false) |
| clustering_threshold | float | No | For clustering |

### Pipeline Submit Behavior
- Starts the **first** operation immediately.
- Returns `remaining_operations` in `data` for the client to chain.
- Electron app chains by polling status and re-submitting with the next operation.
- Single files: only `score` and `tag` supported; `cluster` requires a folder.

### Pipeline Submit Response (success)
```json
{
  "success": true,
  "message": "Pipeline started: scoring",
  "data": {
    "job_id": 123,
    "input_path": "D:/Photos/2024",
    "current_operation": "score",
    "remaining_operations": ["tag", "cluster"]
  }
}
```

---

## GET /api/status — Extended

Now includes `clustering` runner state:

```json
{
  "scoring": { "available": true, "is_running": false, ... },
  "tagging": { "available": true, "is_running": false, ... },
  "clustering": { "available": true, "is_running": false, ... }
}
```

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request (invalid path, invalid operations, etc.) |
| 404 | Not Found (image, job, etc.) |
| 500 | Internal Server Error |
| 503 | Service Unavailable (runner not initialized) |

---

## Design Notes

- **Data query endpoints** delegate to existing `db.py` functions; no new DB code.
- **Stats endpoint** reuses `get_database_stats()` from the MCP server module.
- All endpoints follow existing patterns: Pydantic models, `ApiResponse` wrapper, rate limiting, path validation.
- **Path conversion:** When the backend runs on Linux (WSL), Windows paths are converted to WSL via `utils.convert_path_to_wsl`. When the backend runs natively on Windows, paths are kept as-is.
