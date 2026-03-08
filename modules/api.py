"""
REST API layer for the Image Scoring WebUI.

Provides endpoints to trigger actions (start/stop/refresh/fetch) and retrieve
the status of running actions for scoring, tagging, and clustering operations.
Includes data query endpoints for Electron app integration.

Endpoints:
    Scoring:
        POST /api/scoring/start - Start batch scoring
        POST /api/scoring/stop - Stop running scoring job
        GET /api/scoring/status - Get scoring job status
        POST /api/scoring/fix-db - Start database fix operation
        POST /api/scoring/single - Score a single image

    Tagging:
        POST /api/tagging/start - Start batch tagging
        POST /api/tagging/stop - Stop running tagging job
        GET /api/tagging/status - Get tagging job status
        POST /api/tagging/single - Tag a single image

    Clustering:
        POST /api/clustering/start - Start clustering job
        POST /api/clustering/stop - Stop running clustering job
        GET /api/clustering/status - Get clustering job status

    Data Queries:
        GET /api/images - Query images with filters and pagination
        GET /api/images/{image_id} - Get single image details
        GET /api/folders - Get folder listing
        GET /api/stacks - Get stacks listing
        GET /api/stacks/{stack_id}/images - Get images in a stack
        GET /api/stats - Get database statistics

    Pipeline:
        POST /api/pipeline/submit - Submit to processing pipeline

    General:
        GET /api/status - Get status of all runners
        GET /api/health - Health check endpoint
"""

from fastapi import APIRouter, HTTPException, Body, Query
from fastapi.responses import FileResponse

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
import os
from pathlib import Path


# Request/Response Models with comprehensive descriptions for LLM agents
class ScoringStartRequest(BaseModel):
    """Request model for starting a batch image scoring job.
    
    This endpoint initiates quality assessment of images using multiple AI models
    (SPAQ, AVA, KonIQ, PaQ2PiQ, LIQE) to generate technical, aesthetic, and general quality scores.
    
    Attributes:
        input_path: Directory path containing images to score. Supports Windows (D:\\...)
                   and WSL (/mnt/...) paths. Required.
        skip_existing: If True, skip images that already have complete scores in database. 
                      Default: True. Set to False to force re-scoring.
        force_rescore: If True, overwrite existing scores even if complete. 
                      Takes precedence over skip_existing. Default: False.
    
    Example:
        {
            "input_path": "D:/Photos/2024",
            "skip_existing": true,
            "force_rescore": false
        }
    """
    input_path: str = Field(
        ...,
        description="Directory path containing images to score. Supports Windows (D:\\...) and WSL (/mnt/...) paths.",
        example="D:/Photos/2024"
    )
    skip_existing: bool = Field(
        True,
        description="If True, skip images that already have complete scores. Set to False to force re-scoring.",
        example=True
    )
    force_rescore: bool = Field(
        False,
        description="If True, overwrite existing scores even if complete. Takes precedence over skip_existing.",
        example=False
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "input_path": "D:/Photos/2024",
            "skip_existing": True,
            "force_rescore": False
        }
    })


class TaggingStartRequest(BaseModel):
    """Request model for starting a batch image tagging/keyword extraction job.
    
    Uses CLIP (Contrastive Language-Image Pre-Training) to automatically tag images
    with relevant keywords and optionally generate captions using BLIP.
    
    Attributes:
        input_path: Directory path containing images to tag. Empty string processes all images in database.
        custom_keywords: Optional list of custom keywords to use instead of default set.
                       If None, uses default keywords (landscape, portrait, urban, etc.).
        overwrite: If True, overwrite existing keywords in database. Default: False.
        generate_captions: If True, generate image captions using BLIP model. Default: False.
    
    Example:
        {
            "input_path": "D:/Photos/2024",
            "custom_keywords": ["landscape", "sunset", "nature"],
            "overwrite": false,
            "generate_captions": true
        }
    """
    input_path: str = Field(
        "",
        description="Directory path containing images to tag. Empty string processes all images in database.",
        example="D:/Photos/2024"
    )
    custom_keywords: Optional[List[str]] = Field(
        None,
        description="Optional list of custom keywords. If None, uses default keyword set.",
        example=["landscape", "sunset", "nature"]
    )
    overwrite: bool = Field(
        False,
        description="If True, overwrite existing keywords in database.",
        example=False
    )
    generate_captions: bool = Field(
        False,
        description="If True, generate image captions using BLIP model.",
        example=True
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "input_path": "D:/Photos/2024",
            "custom_keywords": ["landscape", "sunset"],
            "overwrite": False,
            "generate_captions": True
        }
    })


class SingleImageRequest(BaseModel):
    """Request model for single image operations.
    
    Used for scoring or fixing metadata for a single image file.
    
    Attributes:
        file_path: Full path to the image file. Supports Windows and WSL paths.
    
    Example:
        {
            "file_path": "D:/Photos/2024/image.jpg"
        }
    """
    file_path: str = Field(
        ...,
        description="Full path to the image file. Supports Windows (D:\\...) and WSL (/mnt/...) paths.",
        example="D:/Photos/2024/image.jpg"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "file_path": "D:/Photos/2024/image.jpg"
        }
    })


class TaggingSingleRequest(BaseModel):
    """Request model for tagging a single image.
    
    Attributes:
        file_path: Full path to the image file.
        custom_keywords: Optional list of custom keywords. If None, uses default set.
        generate_captions: If True, generate caption for the image. Default: True.
    
    Example:
        {
            "file_path": "D:/Photos/2024/image.jpg",
            "custom_keywords": ["landscape"],
            "generate_captions": true
        }
    """
    file_path: str = Field(
        ...,
        description="Full path to the image file.",
        example="D:/Photos/2024/image.jpg"
    )
    custom_keywords: Optional[List[str]] = Field(
        None,
        description="Optional list of custom keywords. If None, uses default keyword set.",
        example=["landscape", "sunset"]
    )
    generate_captions: bool = Field(
        True,
        description="If True, generate caption for the image using BLIP model.",
        example=True
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "file_path": "D:/Photos/2024/image.jpg",
            "custom_keywords": ["landscape"],
            "generate_captions": True
        }
    })


class StatusResponse(BaseModel):
    """Response model for job status information.
    
    Provides real-time status of running or completed jobs including progress,
    logs, and current state.
    
    Attributes:
        is_running: True if job is currently running, False if idle or completed.
        status_message: Human-readable status message (e.g., "Running...", "Idle", "Done").
        progress: Dictionary with "current" and "total" counts of processed items.
        log: Full log output from the job (may be truncated for long logs).
        job_type: Type of job: "scoring", "fix_db", "tagging", or None if idle.
    
    Example:
        {
            "is_running": true,
            "status_message": "Running...",
            "progress": {"current": 45, "total": 100},
            "log": "Starting batch processing...\\nProcessing image 1...",
            "job_type": "scoring"
        }
    """
    is_running: bool = Field(
        ...,
        description="True if job is currently running, False if idle or completed.",
        example=True
    )
    status_message: str = Field(
        ...,
        description="Human-readable status message (e.g., 'Running...', 'Idle', 'Done').",
        example="Running..."
    )
    progress: Dict[str, int] = Field(
        ...,
        description="Dictionary with 'current' and 'total' counts of processed items.",
        example={"current": 45, "total": 100}
    )
    log: str = Field(
        ...,
        description="Full log output from the job. May be truncated for very long logs.",
        example="Starting batch processing...\nProcessing image 1..."
    )
    job_type: Optional[str] = Field(
        None,
        description="Type of job: 'scoring', 'fix_db', 'tagging', or None if idle.",
        example="scoring"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "is_running": True,
            "status_message": "Running...",
            "progress": {"current": 45, "total": 100},
            "log": "Starting batch processing...\nProcessing image 1...",
            "job_type": "scoring"
        }
    })


class HealthResponse(BaseModel):
    """Response model for health check endpoint.
    
    Indicates API availability and which runners are initialized.
    
    Attributes:
        status: Health status, typically "healthy".
        scoring_available: True if scoring runner is initialized and available.
        tagging_available: True if tagging runner is initialized and available.
    
    Example:
        {
            "status": "healthy",
            "scoring_available": true,
            "tagging_available": true
        }
    """
    status: str = Field(
        ...,
        description="Health status, typically 'healthy'.",
        example="healthy"
    )
    scoring_available: bool = Field(
        ...,
        description="True if scoring runner is initialized and available.",
        example=True
    )
    tagging_available: bool = Field(
        ...,
        description="True if tagging runner is initialized and available.",
        example=True
    )
    clustering_available: bool = Field(
        False,
        description="True if clustering runner is initialized and available.",
        example=True
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "healthy",
            "scoring_available": True,
            "clustering_available": True,
        }
    })


class FindDuplicatesRequest(BaseModel):
    """Request model for finding near-duplicate images."""
    threshold: Optional[float] = Field(
        None,
        description="Minimum cosine similarity threshold (default: 0.98).",
        example=0.98
    )
    folder_path: Optional[str] = Field(
        None,
        description="Optional folder path to restrict duplicate search to a specific directory.",
        example="D:/Photos/2024"
    )
    limit: Optional[int] = Field(
        None,
        description="Max number of duplicate pairs to return (defaults to configured duplicate_max_pairs).",
        example=5000
    )


class ClusteringStartRequest(BaseModel):
    """Request model for starting a clustering job.

    Clusters images in a folder based on visual similarity and temporal proximity.

    Attributes:
        input_path: Directory path containing images to cluster. If empty, clusters all unprocessed folders.
        threshold: Distance threshold for clustering (lower = stricter grouping).
        time_gap: Time gap in seconds for burst grouping.
        force_rescan: If True, re-cluster even if already processed.
    """
    input_path: Optional[str] = Field(
        None,
        description="Directory path containing images to cluster. None clusters all unprocessed.",
        example="D:/Photos/2024"
    )
    threshold: Optional[float] = Field(
        None,
        description="Distance threshold for clustering (lower = stricter).",
        example=0.15
    )
    time_gap: Optional[int] = Field(
        None,
        description="Time gap in seconds for burst grouping.",
        example=5
    )
    force_rescan: bool = Field(
        False,
        description="If True, re-cluster folders even if already processed.",
        example=False
    )


class PipelineSubmitRequest(BaseModel):
    """Request model for submitting images/folders to the processing pipeline.

    Chains requested operations sequentially (score -> tag -> cluster).

    Attributes:
        input_path: File or directory path to process.
        operations: List of operations to run in order. Valid: "score", "tag", "cluster".
        options: Optional per-operation options.
    """
    input_path: str = Field(
        ...,
        description="File or directory path to process.",
        example="D:/Photos/2024"
    )
    operations: List[str] = Field(
        ["score", "tag"],
        description="Operations to run in order. Valid values: 'score', 'tag', 'cluster'.",
        example=["score", "tag", "cluster"]
    )
    skip_existing: bool = Field(
        True,
        description="Skip images that already have results for each operation.",
        example=True
    )
    custom_keywords: Optional[List[str]] = Field(
        None,
        description="Custom keywords for tagging (if 'tag' is in operations)."
    )
    generate_captions: bool = Field(
        False,
        description="Generate captions during tagging.",
        example=False
    )
    clustering_threshold: Optional[float] = Field(
        None,
        description="Distance threshold for clustering (if 'cluster' is in operations)."
    )


class ApiResponse(BaseModel):
    """Standard API response model for operation results.
    
    Used for all operation endpoints (start, stop, etc.) to provide consistent
    success/failure feedback.
    
    Attributes:
        success: True if operation succeeded, False otherwise.
        message: Human-readable message describing the result.
        data: Optional dictionary with additional result data (e.g., job_id, file_path).
    
    Example:
        {
            "success": true,
            "message": "Scoring job started successfully",
            "data": {"job_id": 123, "input_path": "D:/Photos/2024"}
        }
    """
    success: bool = Field(
        ...,
        description="True if operation succeeded, False otherwise.",
        example=True
    )
    message: str = Field(
        ...,
        description="Human-readable message describing the result.",
        example="Scoring job started successfully"
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional dictionary with additional result data (e.g., job_id, file_path).",
        example={"job_id": 123, "input_path": "D:/Photos/2024"}
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "success": True,
            "message": "Operation completed successfully",
            "data": {"job_id": 123}
        }
    })


# Global references to runners (set by webui.py)
_scoring_runner = None
_tagging_runner = None
_clustering_runner = None


def set_runners(scoring_runner, tagging_runner, clustering_runner=None):
    """Set the runner instances for API access."""
    global _scoring_runner, _tagging_runner, _clustering_runner
    _scoring_runner = scoring_runner
    _tagging_runner = tagging_runner
    _clustering_runner = clustering_runner


def create_api_router() -> APIRouter:
    """Create and configure the API router with comprehensive documentation.
    
    Returns:
        APIRouter: Configured FastAPI router with all API endpoints.
    """
    router = APIRouter(
        prefix="/api",
        tags=["Image Scoring API"],
        responses={
            400: {"description": "Bad Request - Invalid input parameters"},
            404: {"description": "Not Found - Resource not found"},
            500: {"description": "Internal Server Error"},
            503: {"description": "Service Unavailable - Runner not initialized"}
        }
    )
    
    # Add schema endpoint for LLM agents
    @router.get(
        "/schema",
        summary="Get API schema (LLM-optimized)",
        description="""
        Get API schema in a format optimized for LLM agents.
        
        Returns a simplified, readable schema description that LLM agents
        can easily parse and understand. This is a simplified version of
        the full OpenAPI schema available at /openapi.json.
        
        **Use Cases:**
        - LLM agent API discovery
        - Code generation
        - API understanding without parsing full OpenAPI spec
        
        **Note:** For complete OpenAPI 3.0 schema, use /openapi.json instead.
        """
    )
    async def get_api_schema():
        """Get API schema in a format optimized for LLM agents."""
        from fastapi.openapi.utils import get_openapi
        from fastapi import Request
        
        # This will be populated when the router is included in the main app
        # For now, return a structured description
        return {
            "api_name": "Image Scoring WebUI API",
            "version": "1.0.0",
            "base_url": "/api",
            "description": "REST API for image quality assessment and tagging operations",
            "endpoints": {
                "scoring": {
                    "start": {
                        "method": "POST",
                        "path": "/api/scoring/start",
                        "description": "Start batch image scoring job",
                        "request_body": {
                            "type": "object",
                            "required": ["input_path"],
                            "properties": {
                                "input_path": {"type": "string", "description": "Directory path containing images"},
                                "skip_existing": {"type": "boolean", "default": True},
                                "force_rescore": {"type": "boolean", "default": False}
                            }
                        },
                        "response": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "message": {"type": "string"},
                                "data": {"type": "object"}
                            }
                        }
                    },
                    "stop": {
                        "method": "POST",
                        "path": "/api/scoring/stop",
                        "description": "Stop running scoring job"
                    },
                    "status": {
                        "method": "GET",
                        "path": "/api/scoring/status",
                        "description": "Get current scoring job status",
                        "response": {
                            "type": "object",
                            "properties": {
                                "is_running": {"type": "boolean"},
                                "status_message": {"type": "string"},
                                "progress": {"type": "object"},
                                "log": {"type": "string"},
                                "job_type": {"type": "string"}
                            }
                        }
                    },
                    "fix-db": {
                        "method": "POST",
                        "path": "/api/scoring/fix-db",
                        "description": "Start database fix operation (re-score incomplete records)"
                    },
                    "single": {
                        "method": "POST",
                        "path": "/api/scoring/single",
                        "description": "Score a single image",
                        "request_body": {
                            "type": "object",
                            "required": ["file_path"],
                            "properties": {
                                "file_path": {"type": "string"}
                            }
                        }
                    },
                    "fix-image": {
                        "method": "POST",
                        "path": "/api/scoring/fix-image",
                        "description": "Fix metadata for a single image (recalculate from existing data)"
                    }
                },
                "tagging": {
                    "start": {
                        "method": "POST",
                        "path": "/api/tagging/start",
                        "description": "Start batch tagging job",
                        "request_body": {
                            "type": "object",
                            "properties": {
                                "input_path": {"type": "string"},
                                "custom_keywords": {"type": "array", "items": {"type": "string"}},
                                "overwrite": {"type": "boolean", "default": False},
                                "generate_captions": {"type": "boolean", "default": False}
                            }
                        }
                    },
                    "stop": {
                        "method": "POST",
                        "path": "/api/tagging/stop",
                        "description": "Stop running tagging job"
                    },
                    "status": {
                        "method": "GET",
                        "path": "/api/tagging/status",
                        "description": "Get current tagging job status"
                    },
                    "single": {
                        "method": "POST",
                        "path": "/api/tagging/single",
                        "description": "Tag a single image"
                    }
                },
                "clustering": {
                    "start": {
                        "method": "POST",
                        "path": "/api/clustering/start",
                        "description": "Start clustering job (group similar images into stacks)",
                        "request_body": {
                            "type": "object",
                            "properties": {
                                "input_path": {"type": "string", "description": "Folder path (null for all)"},
                                "threshold": {"type": "number"},
                                "time_gap": {"type": "integer"},
                                "force_rescan": {"type": "boolean", "default": False}
                            }
                        }
                    },
                    "stop": {
                        "method": "POST",
                        "path": "/api/clustering/stop",
                        "description": "Stop running clustering job"
                    },
                    "status": {
                        "method": "GET",
                        "path": "/api/clustering/status",
                        "description": "Get current clustering job status"
                    }
                },
                "data": {
                    "images": {
                        "method": "GET",
                        "path": "/api/images",
                        "description": "Query images with filters, sorting, and pagination",
                        "query_params": {
                            "page": {"type": "integer", "default": 1},
                            "page_size": {"type": "integer", "default": 50},
                            "sort_by": {"type": "string", "default": "score"},
                            "order": {"type": "string", "default": "desc"},
                            "rating": {"type": "string", "description": "Comma-separated ratings"},
                            "label": {"type": "string", "description": "Comma-separated labels"},
                            "keyword": {"type": "string"},
                            "folder_path": {"type": "string"},
                            "stack_id": {"type": "integer"},
                            "min_score_general": {"type": "number"},
                            "min_score_aesthetic": {"type": "number"},
                            "min_score_technical": {"type": "number"}
                        }
                    },
                    "image_details": {
                        "method": "GET",
                        "path": "/api/images/{image_id}",
                        "description": "Get full details for a single image"
                    },
                    "folders": {
                        "method": "GET",
                        "path": "/api/folders",
                        "description": "Get all folders in the database"
                    },
                    "stacks": {
                        "method": "GET",
                        "path": "/api/stacks",
                        "description": "Get stacks listing with cover images"
                    },
                    "stack_images": {
                        "method": "GET",
                        "path": "/api/stacks/{stack_id}/images",
                        "description": "Get all images in a stack"
                    },
                    "stats": {
                        "method": "GET",
                        "path": "/api/stats",
                        "description": "Get comprehensive database statistics"
                    }
                },
                "pipeline": {
                    "submit": {
                        "method": "POST",
                        "path": "/api/pipeline/submit",
                        "description": "Submit image/folder to processing pipeline (score -> tag -> cluster)",
                        "request_body": {
                            "type": "object",
                            "required": ["input_path"],
                            "properties": {
                                "input_path": {"type": "string"},
                                "operations": {"type": "array", "items": {"type": "string"}, "default": ["score", "tag"]},
                                "skip_existing": {"type": "boolean", "default": True},
                                "custom_keywords": {"type": "array", "items": {"type": "string"}},
                                "generate_captions": {"type": "boolean", "default": False},
                                "clustering_threshold": {"type": "number"}
                            }
                        }
                    }
                },
                "general": {
                    "status": {
                        "method": "GET",
                        "path": "/api/status",
                        "description": "Get status of all runners (scoring, tagging, clustering)"
                    },
                    "health": {
                        "method": "GET",
                        "path": "/api/health",
                        "description": "Health check endpoint"
                    },
                    "jobs_recent": {
                        "method": "GET",
                        "path": "/api/jobs/recent",
                        "description": "Get recent job history",
                        "query_params": {
                            "limit": {"type": "integer", "default": 10}
                        }
                    },
                    "job_details": {
                        "method": "GET",
                        "path": "/api/jobs/{job_id}",
                        "description": "Get details for a specific job",
                        "path_params": {
                            "job_id": {"type": "integer"}
                        }
                    }
                }
            },
            "note": "For complete OpenAPI schema, visit /openapi.json or /docs"
        }
    
    # ========== Scoring Endpoints ==========
    
    @router.post(
        "/scoring/start",
        response_model=ApiResponse,
        summary="Start batch image scoring",
        description="""
        Initiates a batch image quality assessment job for all images in the specified directory.
        
        The scoring process uses multiple AI models to evaluate images:
        - **SPAQ**: Spatial Perception of Aesthetic Quality
        - **AVA**: Aesthetic Visual Analysis
        - **KonIQ**: Konstanz Image Quality
        - **PaQ2PiQ**: Perceptual Quality to Perceptual Image Quality
        - **LIQE**: Learning Image Quality Evaluator
        
        Results include:
        - Technical score (sharpness, noise, exposure)
        - Aesthetic score (composition, appeal)
        - General quality score (weighted combination)
        - Rating (1-5 stars) and color label (Red/Yellow/Green/Blue/Purple)
        
        The job runs asynchronously. Use GET /api/scoring/status to monitor progress.
        
        **Path Handling:**
        - Windows paths: `D:/Photos/2024` or `D:\\Photos\\2024`
        - WSL paths: `/mnt/d/Photos/2024`
        - Paths are automatically converted between formats when needed
        
        **Skip Logic:**
        - If `skip_existing=True`: Images with complete scores are skipped
        - If `force_rescore=True`: All images are re-scored regardless of existing data
        - Incomplete scores (missing models or metadata) are always completed
        
        **Example Request:**
        ```json
        {
            "input_path": "D:/Photos/2024",
            "skip_existing": true,
            "force_rescore": false
        }
        ```
        
        **Example Response:**
        ```json
        {
            "success": true,
            "message": "Scoring job started successfully",
            "data": {
                "job_id": 123,
                "input_path": "D:/Photos/2024"
            }
        }
        ```
        """,
        response_description="Job start confirmation with job_id",
        responses={
            200: {
                "description": "Job started successfully",
                "content": {
                    "application/json": {
                        "example": {
                            "success": True,
                            "message": "Scoring job started successfully",
                            "data": {"job_id": 123, "input_path": "D:/Photos/2024"}
                        }
                    }
                }
            },
            400: {"description": "Invalid input path or path not found"},
            503: {"description": "Scoring runner not available"}
        }
    )
    async def start_scoring(request: ScoringStartRequest):
        """
        Start a batch scoring job.

        Args:
            request: ScoringStartRequest with input_path and options

        Returns:
            ApiResponse with success status and job_id if started
        """
        from modules.ui.app import _check_rate_limit
        _check_rate_limit("scoring_start")

        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if _scoring_runner.is_running:
            return ApiResponse(
                success=False,
                message="Scoring job is already running",
                data={"is_running": True}
            )
        
        # Validate path
        if not os.path.exists(request.input_path):
            raise HTTPException(
                status_code=400,
                detail=f"Path not found: {request.input_path}"
            )
        
        # Create job ID
        from modules import db
        job_id = db.create_job(request.input_path)
        
        # Start batch
        skip_existing = not request.force_rescore if request.force_rescore else request.skip_existing
        result = _scoring_runner.start_batch(request.input_path, job_id, skip_existing)
        
        if result == "Started":
            return ApiResponse(
                success=True,
                message="Scoring job started successfully",
                data={"job_id": job_id, "input_path": request.input_path}
            )
        else:
            return ApiResponse(
                success=False,
                message=result,
                data={"error": result}
            )
    
    @router.post(
        "/scoring/stop",
        response_model=ApiResponse,
        summary="Stop scoring job",
        description="""
        Sends a stop signal to the currently running scoring job.
        
        The job will finish processing the current image and then stop gracefully.
        Use GET /api/scoring/status to verify the job has stopped.
        
        **Note:** If no job is running, returns success=False with appropriate message.
        """,
        response_description="Stop confirmation"
    )
    async def stop_scoring():
        """Stop the currently running scoring job."""
        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if not _scoring_runner.is_running:
            return ApiResponse(
                success=False,
                message="No scoring job is currently running",
                data={"is_running": False}
            )
        
        _scoring_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to scoring job",
            data={"is_running": _scoring_runner.is_running}
        )
    
    @router.get(
        "/scoring/status",
        response_model=StatusResponse,
        summary="Get scoring status",
        description="""
        Returns the current status of the scoring job including:
        - Whether a job is currently running
        - Progress information (current/total images)
        - Status message
        - Full log output
        - Job type (scoring, fix_db, etc.)
        
        **Polling:** This endpoint can be polled periodically to monitor job progress.
        Recommended polling interval: 2-5 seconds.
        """,
        response_description="Current scoring job status"
    )
    async def get_scoring_status():
        """Get the current status of the scoring job."""
        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        is_running, log_text, status_message, current, total = _scoring_runner.get_status()
        
        return StatusResponse(
            is_running=is_running,
            status_message=status_message,
            progress={"current": current, "total": total},
            log=log_text,
            job_type=getattr(_scoring_runner, 'job_type', None)
        )
    
    @router.post(
        "/scoring/fix-db",
        response_model=ApiResponse,
        summary="Fix database (re-score incomplete)",
        description="""
        Starts a database fix operation that re-scores images with incomplete data.
        
        This operation:
        - Finds images missing scores from one or more models
        - Finds images missing metadata (rating or label)
        - Re-runs scoring only for missing components
        - Updates database with complete scores
        
        Useful for:
        - Backfilling scores after adding new models
        - Fixing corrupted or incomplete records
        - Updating metadata for images scored before metadata features were added
        
        The operation runs asynchronously. Monitor progress with GET /api/scoring/status.
        """,
        response_description="Fix operation start confirmation"
    )
    async def fix_database():
        """Start database fix operation (re-score incomplete records)."""
        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if _scoring_runner.is_running:
            return ApiResponse(
                success=False,
                message="Scoring job is already running",
                data={"is_running": True}
            )
        
        from modules import db
        job_id = db.create_job("DB_FIX_OPERATION")
        result = _scoring_runner.start_fix_db(job_id)
        
        if result == "Started":
            return ApiResponse(
                success=True,
                message="Database fix operation started",
                data={"job_id": job_id}
            )
        else:
            return ApiResponse(
                success=False,
                message=result,
                data={"error": result}
            )
    
    @router.post(
        "/scoring/single",
        response_model=ApiResponse,
        summary="Score single image",
        description="""
        Scores a single image file using all available models.
        
        This is a blocking operation that runs the full scoring pipeline for one image.
        Use this for testing or when you need immediate results for a single file.
        
        For batch operations, use POST /api/scoring/start instead.
        
        **Supported formats:** JPG, JPEG, PNG, NEF, NRW, DNG, CR2, ARW, ORF, CR3, RW2
        """,
        response_description="Scoring result with success status and message"
    )
    async def score_single_image(request: SingleImageRequest):
        """Score a single image."""
        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=400,
                detail=f"File not found: {request.file_path}"
            )
        
        success, message = _scoring_runner.run_single_image(request.file_path)
        
        return ApiResponse(
            success=success,
            message=message,
            data={"file_path": request.file_path}
        )
    
    # ========== Tagging Endpoints ==========
    
    @router.post(
        "/tagging/start",
        response_model=ApiResponse,
        summary="Start batch tagging",
        description="""
        Initiates a batch image tagging job using CLIP (Contrastive Language-Image Pre-Training).
        
        The tagging process:
        - Extracts relevant keywords from images using zero-shot classification
        - Optionally generates captions using BLIP (Bootstrapping Language-Image Pre-training)
        - Writes metadata to XMP sidecar files and embedded metadata
        - Updates database with keywords, title, and description
        
        **Keyword Extraction:**
        - Uses default keyword set if custom_keywords not provided
        - Default keywords: landscape, portrait, urban, cityscape, nature, wildlife, etc.
        - Returns top 5 most relevant keywords per image
        
        **Caption Generation:**
        - Enabled with generate_captions=True
        - Uses BLIP model to generate natural language descriptions
        - Title is auto-generated from caption (first 50 chars)
        
        **Path Handling:**
        - Empty input_path processes all images in database
        - Directory path processes images in that folder and subfolders
        - Paths are automatically converted between Windows/WSL formats
        
        The job runs asynchronously. Use GET /api/tagging/status to monitor progress.
        """,
        response_description="Tagging job start confirmation"
    )
    async def start_tagging(request: TaggingStartRequest):
        """Start a batch tagging job."""
        from modules.ui.app import _check_rate_limit
        _check_rate_limit("tagging_start")

        if _tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
        if _tagging_runner.is_running:
            return ApiResponse(
                success=False,
                message="Tagging job is already running",
                data={"is_running": True}
            )
        
        # Validate path if provided
        if request.input_path and not os.path.exists(request.input_path):
            raise HTTPException(
                status_code=400,
                detail=f"Path not found: {request.input_path}"
            )
        
        # Create job ID
        from modules import db
        job_id = db.create_job(request.input_path or "ALL_IMAGES_TAGGING")
        
        result = _tagging_runner.start_batch(
            request.input_path,
            job_id=job_id,
            custom_keywords=request.custom_keywords,
            overwrite=request.overwrite,
            generate_captions=request.generate_captions
        )
        
        if result == "Started":
            return ApiResponse(
                success=True,
                message="Tagging job started successfully",
                data={
                    "job_id": job_id,
                    "input_path": request.input_path or "all images"
                }
            )
        else:
            return ApiResponse(
                success=False,
                message=result,
                data={"error": result}
            )
    
    @router.post(
        "/tagging/stop",
        response_model=ApiResponse,
        summary="Stop tagging job",
        description="Sends a stop signal to the currently running tagging job."
    )
    async def stop_tagging():
        """Stop the currently running tagging job."""
        if _tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
        if not _tagging_runner.is_running:
            return ApiResponse(
                success=False,
                message="No tagging job is currently running",
                data={"is_running": False}
            )
        
        _tagging_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to tagging job",
            data={"is_running": _tagging_runner.is_running}
        )
    
    @router.get(
        "/tagging/status",
        response_model=StatusResponse,
        summary="Get tagging status",
        description="Returns the current status of the tagging job including progress and logs."
    )
    async def get_tagging_status():
        """Get the current status of the tagging job."""
        if _tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
        is_running, log_text, status_message, current, total = _tagging_runner.get_status()
        
        return StatusResponse(
            is_running=is_running,
            status_message=status_message,
            progress={"current": current, "total": total},
            log=log_text,
            job_type="tagging"
        )
    
    @router.post(
        "/tagging/single",
        response_model=ApiResponse,
        summary="Tag single image",
        description="""
        Tags a single image file with keywords and optionally generates a caption.
        
        This is a blocking operation that processes one image immediately.
        For batch operations, use POST /api/tagging/start instead.
        """
    )
    async def tag_single_image(request: TaggingSingleRequest):
        """Tag a single image."""
        if _tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=400,
                detail=f"File not found: {request.file_path}"
            )
        
        success, message = _tagging_runner.run_single_image(
            request.file_path,
            request.custom_keywords,
            request.generate_captions
        )
        
        return ApiResponse(
            success=success,
            message=message,
            data={"file_path": request.file_path}
        )
    
    # ========== General Endpoints ==========
    
    @router.get(
        "/status",
        response_model=Dict[str, Any],
        summary="Get all runners status",
        description="""
        Returns the status of all runners (scoring and tagging) in a single response.
        
        Useful for monitoring the overall system state. Each runner's status includes:
        - Availability (whether runner is initialized)
        - Running state
        - Progress information
        - Status message
        - Recent log output (last 2000 characters)
        
        **Response Structure:**
        ```json
        {
            "scoring": {
                "available": true,
                "is_running": false,
                "status_message": "Idle",
                "progress": {"current": 0, "total": 0},
                "log": "",
                "job_type": null
            },
            "tagging": {
                "available": true,
                "is_running": false,
                "status_message": "Idle",
                "progress": {"current": 0, "total": 0},
                "log": ""
            }
        }
        ```
        """
    )
    async def get_all_status():
        """Get status of all runners."""
        status = {
            "scoring": {"available": False},
            "tagging": {"available": False},
            "clustering": {"available": False}
        }

        if _scoring_runner:
            try:
                is_running, log, status_msg, current, total = _scoring_runner.get_status()
                status["scoring"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "log": log[-2000:] if log else "",  # Last 2000 chars
                    "job_type": getattr(_scoring_runner, 'job_type', None)
                }
            except Exception as e:
                status["scoring"]["error"] = str(e)

        if _tagging_runner:
            try:
                is_running, log, status_msg, current, total = _tagging_runner.get_status()
                status["tagging"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "log": log[-2000:] if log else ""
                }
            except Exception as e:
                status["tagging"]["error"] = str(e)

        if _clustering_runner:
            try:
                is_running, log, status_msg, current, total = _clustering_runner.get_status()
                status["clustering"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "log": log[-2000:] if log else ""
                }
            except Exception as e:
                status["clustering"]["error"] = str(e)

        return status
    
    @router.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check",
        description="""
        Simple health check endpoint to verify API availability and runner initialization.
        
        Returns:
        - status: "healthy" if API is operational
        - scoring_available: True if scoring runner is initialized
        - tagging_available: True if tagging runner is initialized
        
        Use this endpoint for:
        - Health monitoring
        - Service discovery
        - Initial API capability detection
        """
    )
    async def health_check():
        """Health check endpoint."""
        return HealthResponse(
            status="healthy",
            scoring_available=_scoring_runner is not None,
            tagging_available=_tagging_runner is not None,
            clustering_available=_clustering_runner is not None
        )
    
    # ========== Utility Endpoints ==========
    
    @router.post(
        "/scoring/fix-image",
        response_model=ApiResponse,
        summary="Fix image metadata",
        description="""
        Recalculates scores and updates metadata for a single image without running neural networks.
        
        This operation:
        - Uses existing model scores from the database
        - Recalculates weighted scores (technical, aesthetic, general)
        - Updates rating and color label based on recalculated scores
        - Writes updated metadata to XMP sidecar and embedded metadata
        - Regenerates thumbnail if needed
        
        **Use Cases:**
        - Fixing metadata after score recalculation logic changes
        - Updating ratings/labels without re-running expensive model inference
        - Correcting corrupted metadata
        
        **Requirements:**
        - Image must exist in database
        - At least one model score must be present
        - If all scores missing, operation will fail
        
        This is much faster than full re-scoring as it doesn't run AI models.
        """
    )
    async def fix_image_metadata(request: SingleImageRequest):
        """Fix metadata for a single image (recalculate scores from existing data)."""
        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=400,
                detail=f"File not found: {request.file_path}"
            )
        
        success, message = _scoring_runner.fix_image_metadata(request.file_path)
        
        return ApiResponse(
            success=success,
            message=message,
            data={"file_path": request.file_path}
        )
    
    @router.get(
        "/raw-preview",
        summary="Get RAW file preview",
        description="""
        Extracts or generates a JPEG preview for a RAW image file.
        
        This endpoint is optimized for performance:
        - Tries to extract embedded JPEG preview first (fastest)
        - Falls back to full RAW decode if needed
        - Caches generated previews
        - Returns a JPEG image directly
        
        **Query Parameters:**
        - path: Full path to the specific image file (URL encoded)
        """
    )
    async def get_raw_preview(path: str = Query(..., description="Full path to the image file")):
        """Get or generate a preview for a RAW file."""
        import urllib.parse
        from modules import thumbnails
        from modules import db
        
        decoded_path = urllib.parse.unquote(path)
        
        # specific handler for simple filenames (look up in DB)
        if not os.path.exists(decoded_path) and not os.path.isabs(decoded_path):
            try:
                # Try to find file in database by filename
                conn = db.get_db()
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT file_path FROM images WHERE file_name = ?", (decoded_path,))
                    row = cursor.fetchone()
                    if row:
                        decoded_path = row[0]
                except Exception as e:
                    print(f"Error looking up path for {decoded_path}: {e}")
                finally:
                    conn.close()
            except Exception:
                pass

        if not os.path.exists(decoded_path):
            # Try converting WSL path to Windows if running on Windows
            if decoded_path.startswith('/mnt/'):
                try:
                    parts = decoded_path.split('/')
                    if len(parts) > 2:
                        drive = parts[2].upper()
                        rest = os.sep.join(parts[3:])
                        win_path = f"{drive}:{os.sep}{rest}"
                        if os.path.exists(win_path):
                            decoded_path = win_path
                except (OSError, IndexError, ValueError):
                    pass

        if not os.path.exists(decoded_path):
             # Try appending to current working directory if just a relative path
             abs_path = os.path.abspath(decoded_path)
             if os.path.exists(abs_path):
                 decoded_path = abs_path
             else:
                 raise HTTPException(status_code=404, detail=f"File not found: {decoded_path}")

        try:
            preview_path = thumbnails.generate_preview(decoded_path)
            
            if preview_path and os.path.exists(preview_path):
                return FileResponse(preview_path, media_type="image/jpeg")
            else:
                 raise HTTPException(status_code=500, detail="Failed to generate preview")
                 
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get(
        "/jobs/recent",
        response_model=List[Dict[str, Any]],
        summary="Get recent jobs",
        description="""
        Returns a list of recent job history entries.
        
        Jobs are ordered by creation time (most recent first).
        Each job entry includes:
        - id: Unique job identifier
        - input_path: Path that was processed
        - status: Job status (pending, running, completed, failed)
        - created_at: Job creation timestamp
        - updated_at: Last update timestamp
        - log: Job log output (if available)
        
        **Query Parameters:**
        - limit: Maximum number of jobs to return (default: 10, max: 1000)
        """
    )
    async def get_recent_jobs(limit: int = 10):
        """Get recent job history."""
        from modules import db
        try:
            jobs = db.get_jobs(limit=limit)
            return jobs
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get(
        "/jobs/{job_id}",
        response_model=Dict[str, Any],
        summary="Get job details",
        description="""
        Returns detailed information for a specific job by ID.
        
        **Path Parameters:**
        - job_id: Integer job identifier
        
        **Returns:**
        - Full job record including status, timestamps, logs, etc.
        - 404 if job not found
        """
    )
    async def get_job_details(job_id: int):
        """Get details for a specific job."""
        from modules import db
        try:
            job = db.get_job_by_id(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            job["phases"] = db.get_job_phases(job_id)
            return job
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    # ========== Similar Images Endpoint ==========

    @router.get(
        "/similar",
        summary="Find similar images",
        description="""
        Find images visually similar to a given image using embedding-based cosine similarity.
        
        **Query Parameters:**
        - image_id: Required. Integer ID of the query image.
        - limit: Maximum number of results (default: 20).
        - folder_path: Optional. Scope search to a specific folder path.
        - min_similarity: Minimum similarity threshold 0.0-1.0 (default: 0.80).
        
        **Returns:**
        - query_image_id: ID of the query image
        - results: List of {image_id, file_path, similarity}
        - count: Number of results returned
        
        **Errors:**
        - 400: Missing or invalid image_id
        - 404: Image not found
        - 400: No embeddings (run clustering first)
        """
    )
    def get_similar_images(
        image_id: int = Query(..., description="ID of the query image"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        folder_path: Optional[str] = Query(None, description="Scope search to folder"),
        min_similarity: Optional[float] = Query(0.80, ge=0.0, le=1.0, description="Minimum similarity threshold"),
    ):
        """Find images similar to the given image by ID."""
        from modules import similar_search, db
        # Verify image exists before searching
        conn = db.get_db()
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM images WHERE id = ?", (image_id,))
            if c.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")
        finally:
            conn.close()
        result = similar_search.search_similar_images(
            example_image_id=image_id,
            limit=limit,
            folder_path=folder_path,
            min_similarity=min_similarity,
        )
        if isinstance(result, dict) and "error" in result:
            if "not found" in result["error"].lower():
                raise HTTPException(status_code=404, detail=result["error"])
            if "no embeddings" in result["error"].lower() or "clustering" in result["error"].lower():
                raise HTTPException(status_code=400, detail=result["error"])
            raise HTTPException(status_code=400, detail=result["error"])
        return {
            "query_image_id": image_id,
            "results": result,
            "count": len(result),
        }

    # ========== Find Duplicates Endpoints ==========

    @router.post("/duplicates/find", response_model=ApiResponse)
    def find_duplicates(req: FindDuplicatesRequest = Body(...)):
        """Find near-duplicate image pairs in the database."""
        try:
            from modules import similar_search
            results = similar_search.find_near_duplicates(
                threshold=req.threshold,
                folder_path=req.folder_path,
                limit=req.limit
            )
            return ApiResponse(
                success=True, 
                message=f"Found {len(results)} near-duplicate pairs",
                data={"duplicates": results}
            )
        except Exception as e:
            return ApiResponse(success=False, message=str(e))

    # ========== Clustering Endpoints ==========

    @router.post(
        "/clustering/start",
        response_model=ApiResponse,
        summary="Start clustering job",
        description="""
        Starts a clustering job that groups visually similar images into stacks.

        Uses MobileNetV2 embeddings and cosine similarity to find groups of related images.
        Optionally uses EXIF timestamps for burst detection.

        The job runs asynchronously. Use GET /api/clustering/status to monitor progress.
        """
    )
    async def start_clustering(request: ClusteringStartRequest):
        """Start a batch clustering job."""
        from modules.ui.app import _check_rate_limit
        _check_rate_limit("clustering_start")

        if _clustering_runner is None:
            raise HTTPException(status_code=503, detail="Clustering runner not available")

        if _clustering_runner.is_running:
            return ApiResponse(
                success=False,
                message="Clustering job is already running",
                data={"is_running": True}
            )

        # Validate path if provided
        if request.input_path and not os.path.exists(request.input_path):
            raise HTTPException(
                status_code=400,
                detail=f"Path not found: {request.input_path}"
            )

        from modules import db
        job_id = db.create_job(request.input_path or "ALL_FOLDERS_CLUSTERING")

        result = _clustering_runner.start_batch(
            request.input_path,
            threshold=request.threshold,
            time_gap=request.time_gap,
            force_rescan=request.force_rescan,
            job_id=job_id
        )

        if result == "Started":
            return ApiResponse(
                success=True,
                message="Clustering job started successfully",
                data={"job_id": job_id, "input_path": request.input_path or "all folders"}
            )
        else:
            return ApiResponse(
                success=False,
                message=result,
                data={"error": result}
            )

    @router.post(
        "/clustering/stop",
        response_model=ApiResponse,
        summary="Stop clustering job",
        description="Sends a stop signal to the currently running clustering job."
    )
    async def stop_clustering():
        """Stop the currently running clustering job."""
        if _clustering_runner is None:
            raise HTTPException(status_code=503, detail="Clustering runner not available")

        if not _clustering_runner.is_running:
            return ApiResponse(
                success=False,
                message="No clustering job is currently running",
                data={"is_running": False}
            )

        _clustering_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to clustering job",
            data={"is_running": _clustering_runner.is_running}
        )

    @router.get(
        "/clustering/status",
        response_model=StatusResponse,
        summary="Get clustering status",
        description="Returns the current status of the clustering job including progress and logs."
    )
    async def get_clustering_status():
        """Get the current status of the clustering job."""
        if _clustering_runner is None:
            raise HTTPException(status_code=503, detail="Clustering runner not available")

        is_running, log_text, status_message, current, total = _clustering_runner.get_status()

        return StatusResponse(
            is_running=is_running,
            status_message=status_message,
            progress={"current": current, "total": total},
            log=log_text,
            job_type="clustering"
        )

    # ========== Data Query Endpoints (for Electron integration) ==========

    @router.get(
        "/images",
        summary="Query images with filters",
        description="""
        Returns a paginated list of images with optional filtering by rating, label,
        keyword, score ranges, folder, and stack. Supports sorting and pagination.

        This endpoint replaces direct DB access from the Electron app.
        """
    )
    async def query_images(
        page: int = Query(1, ge=1, description="Page number (1-based)"),
        page_size: int = Query(50, ge=1, le=500, description="Items per page"),
        sort_by: str = Query("score", description="Sort field (score, date, name, rating, score_general, score_aesthetic, score_technical)"),
        order: str = Query("desc", description="Sort order: asc or desc"),
        rating: Optional[str] = Query(None, description="Comma-separated ratings to filter (e.g. '3,4,5')"),
        label: Optional[str] = Query(None, description="Comma-separated labels to filter (e.g. 'Green,Blue')"),
        keyword: Optional[str] = Query(None, description="Keyword to filter by (partial match)"),
        min_score_general: float = Query(0, ge=0, le=1, description="Minimum general score"),
        min_score_aesthetic: float = Query(0, ge=0, le=1, description="Minimum aesthetic score"),
        min_score_technical: float = Query(0, ge=0, le=1, description="Minimum technical score"),
        folder_path: Optional[str] = Query(None, description="Filter by folder path"),
        stack_id: Optional[int] = Query(None, description="Filter by stack ID"),
    ):
        """Query images with filtering, sorting, and pagination."""
        from modules import db

        rating_filter = [int(r) for r in rating.split(",")] if rating else None
        label_filter = label.split(",") if label else None

        try:
            images, total_count = db.get_images_paginated_with_count(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                order=order,
                rating_filter=rating_filter,
                label_filter=label_filter,
                keyword_filter=keyword,
                min_score_general=min_score_general,
                min_score_aesthetic=min_score_aesthetic,
                min_score_technical=min_score_technical,
                folder_path=folder_path,
                stack_id=stack_id,
            )

            return {
                "images": [dict(img) for img in images],
                "total": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 0,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/images/{image_id}",
        summary="Get image details by ID",
        description="Returns full details for a single image including all scores, metadata, and file paths."
    )
    async def get_image_by_id(image_id: int):
        """Get detailed information for a single image."""
        from modules import db

        conn = db.get_db()
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM images WHERE id = ?", (image_id,))
            row = c.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")

            data = dict(row)
            data['file_paths'] = db.get_all_paths(image_id)
            data['resolved_path'] = db.get_resolved_path(image_id, verified_only=False)
            return data
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            conn.close()

    @router.get(
        "/folders",
        summary="Get folder list",
        description="Returns all folders in the database with their paths. Use folder_path query param on /api/images to browse folder contents."
    )
    async def get_folders():
        """Get all folders in the database."""
        from modules import db
        try:
            folders = db.get_all_folders()
            return {"folders": folders, "count": len(folders)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/stacks",
        summary="Get stacks listing",
        description="Returns stacks (image groups) with cover images and metadata. Optionally filter by folder."
    )
    async def get_stacks(
        folder_path: Optional[str] = Query(None, description="Filter stacks by folder path"),
        sort_by: str = Query("score_general", description="Sort field for cover image selection"),
        order: str = Query("desc", description="Sort order: asc or desc"),
    ):
        """Get stacks with cover images for display."""
        from modules import db
        try:
            stacks = db.get_stacks_for_display(
                folder_path=folder_path,
                sort_by=sort_by,
                order=order
            )
            return {
                "stacks": [dict(s) if hasattr(s, 'keys') else s for s in stacks],
                "count": len(stacks),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/stacks/{stack_id}/images",
        summary="Get images in a stack",
        description="Returns all images belonging to a specific stack, sorted by general score descending."
    )
    async def get_stack_images(stack_id: int):
        """Get all images in a stack."""
        from modules import db
        try:
            images = db.get_images_in_stack(stack_id)
            return {
                "images": [dict(img) for img in images],
                "count": len(images),
                "stack_id": stack_id,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/stats",
        summary="Get database statistics",
        description="""
        Returns comprehensive database statistics including total counts,
        score distributions, averages by rating/label, folder and stack counts.
        """
    )
    async def get_stats():
        """Get comprehensive database statistics."""
        from modules.mcp_server import get_database_stats
        try:
            stats = get_database_stats()
            return stats
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ========== Pipeline Submit Endpoint ==========

    @router.post(
        "/pipeline/submit",
        response_model=ApiResponse,
        summary="Submit to processing pipeline",
        description="""
        Submits an image file or folder for sequential processing through the pipeline.

        Operations are executed in order: score -> tag -> cluster.
        Only the first applicable operation is started immediately; subsequent operations
        should be triggered by the Electron app after the previous one completes
        (via status polling or WebSocket events).

        For single files, only 'score' and 'tag' operations are supported.
        'cluster' requires a folder path.
        """
    )
    async def submit_pipeline(request: PipelineSubmitRequest):
        """Submit image/folder to the processing pipeline."""
        from modules.ui.app import _check_rate_limit
        _check_rate_limit("pipeline_submit")

        if not os.path.exists(request.input_path):
            raise HTTPException(status_code=400, detail=f"Path not found: {request.input_path}")

        valid_ops = {"score", "tag", "cluster"}
        invalid_ops = [op for op in request.operations if op not in valid_ops]
        if invalid_ops:
            raise HTTPException(status_code=400, detail=f"Invalid operations: {invalid_ops}. Valid: {sorted(valid_ops)}")
        if not request.operations:
            raise HTTPException(status_code=400, detail="At least one operation is required")

        is_file = os.path.isfile(request.input_path)
        if is_file and "cluster" in request.operations:
            raise HTTPException(status_code=400, detail="Clustering requires a folder path, not a single file")

        from modules import db
        first_op = request.operations[0]
        phase_plan = list(request.operations)

        if is_file:
            if first_op == "score":
                if _scoring_runner is None:
                    raise HTTPException(status_code=503, detail="Scoring runner not available")
                if _scoring_runner.is_running:
                    return ApiResponse(success=False, message="Scoring runner is busy", data={"is_running": True})
                success, message = _scoring_runner.run_single_image(request.input_path)
            elif first_op == "tag":
                if _tagging_runner is None:
                    raise HTTPException(status_code=503, detail="Tagging runner not available")
                if _tagging_runner.is_running:
                    return ApiResponse(success=False, message="Tagging runner is busy", data={"is_running": True})
                success, message = _tagging_runner.run_single_image(
                    request.input_path,
                    request.custom_keywords,
                    request.generate_captions,
                )
            else:
                raise HTTPException(status_code=400, detail="Single-file pipeline supports score/tag only")

            return ApiResponse(
                success=success,
                message=message,
                data={
                    "file_path": request.input_path,
                    "completed_operation": first_op,
                    "phase_plan": [{"phase_order": 0, "phase_code": first_op, "state": "completed"}],
                },
            )

        job_id = db.create_job(request.input_path, job_type="pipeline")
        phase_rows = db.create_job_phases(job_id, phase_plan)

        if first_op == "score":
            if _scoring_runner is None:
                raise HTTPException(status_code=503, detail="Scoring runner not available")
            if _scoring_runner.is_running:
                return ApiResponse(success=False, message="Scoring runner is busy", data={"is_running": True, "job_id": job_id, "phase_plan": phase_rows})
            result = _scoring_runner.start_batch(request.input_path, job_id, request.skip_existing)
            op_name = "scoring"
        elif first_op == "tag":
            if _tagging_runner is None:
                raise HTTPException(status_code=503, detail="Tagging runner not available")
            if _tagging_runner.is_running:
                return ApiResponse(success=False, message="Tagging runner is busy", data={"is_running": True, "job_id": job_id, "phase_plan": phase_rows})
            result = _tagging_runner.start_batch(
                request.input_path,
                job_id=job_id,
                custom_keywords=request.custom_keywords,
                overwrite=not request.skip_existing,
                generate_captions=request.generate_captions,
            )
            op_name = "tagging"
        else:
            if _clustering_runner is None:
                raise HTTPException(status_code=503, detail="Clustering runner not available")
            if _clustering_runner.is_running:
                return ApiResponse(success=False, message="Clustering runner is busy", data={"is_running": True, "job_id": job_id, "phase_plan": phase_rows})
            result = _clustering_runner.start_batch(request.input_path, threshold=request.clustering_threshold, job_id=job_id)
            op_name = "clustering"

        if result == "Started":
            return ApiResponse(
                success=True,
                message=f"Pipeline started: {op_name}",
                data={
                    "job_id": job_id,
                    "input_path": request.input_path,
                    "current_operation": first_op,
                    "phase_plan": db.get_job_phases(job_id),
                },
            )

        db.set_job_phase_state(job_id, first_op, "failed", error_message=result)
        db.update_job_status(job_id, "failed", result)
        return ApiResponse(success=False, message=result, data={"error": result, "job_id": job_id, "phase_plan": db.get_job_phases(job_id)})

    return router
