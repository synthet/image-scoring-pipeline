"""
MCP (Model Context Protocol) Server for Image Scoring WebUI

Provides debugging and management tools for Cursor IDE and AI agents.

Available Tools (17):
  Database & Query:
    - get_database_stats: Overall database statistics
    - query_images: Flexible image queries with filtering
    - get_image_details: Full details for specific image
    - execute_sql: Read-only SQL queries (SELECT only)
    - get_folder_tree: Folder structure with counts
    - get_stacks_summary: Stack/cluster analysis

  Error & Diagnostics:
    - get_failed_images: Images with missing/failed scores
    - get_error_summary: Summary of all errors and issues
    - check_database_health: Data integrity validation
    - validate_file_paths: Check if database paths exist on disk

  Monitoring & Jobs:
    - get_runner_status: Current scoring/tagging/clustering progress
    - get_recent_jobs: Recent job history
    - get_model_status: GPU availability, model loading status
    - run_processing_job: Trigger scoring, tagging, or clustering

  Configuration & Logs:
    - get_config: Read configuration
    - set_config_value: Update configuration
    - read_debug_log: Read debug log entries

Usage:
    python -m modules.mcp_server          # standalone
    ENABLE_MCP_SERVER=1 python webui.py   # integrated
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Optional

# MCP SDK imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    # Don't print warning at import time - handled by consumers

try:
    from mcp.server.sse import SseServerTransport
    MCP_SSE_AVAILABLE = True
except ImportError:
    MCP_SSE_AVAILABLE = False

# Add parent directory for imports when running standalone
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db, config

logger = logging.getLogger(__name__)

# Global reference to runners (set by webui when integrating)
_scoring_runner = None
_tagging_runner = None
_clustering_runner = None


# Set False if db.init_db() fails (e.g. Firebird not migrated); DB-using tools then return a clear error
_db_available = True

DB_TOOLS = frozenset({
    "get_database_stats", "query_images", "get_image_details", "execute_sql",
    "get_recent_jobs", "get_folder_tree", "get_stacks_summary",
    "get_failed_images", "get_error_summary", "check_database_health",
    "validate_file_paths", "run_processing_job", "search_similar_images",
    "find_near_duplicates"
    # Note: get_model_status, get_runner_status, get_config, set_config_value, read_debug_log don't require DB
})

def set_runners(scoring_runner, tagging_runner, clustering_runner=None):
    """Set references to the runner instances from webui."""
    global _scoring_runner, _tagging_runner, _clustering_runner
    _scoring_runner = scoring_runner
    _tagging_runner = tagging_runner
    _clustering_runner = clustering_runner


# --- Tool Implementations ---

def get_database_stats() -> dict:
    """Get comprehensive database statistics."""
    conn = db.get_db()
    c = conn.cursor()
    
    stats = {}
    
    try:
        # Total images
        c.execute("SELECT COUNT(*) FROM images")
        stats["total_images"] = c.fetchone()[0]
        
        # Images by rating
        c.execute("""
            SELECT rating, COUNT(*) as cnt 
            FROM images 
            GROUP BY rating 
            ORDER BY rating
        """)
        stats["by_rating"] = {str(row[0]): row[1] for row in c.fetchall()}
        
        # Images by label
        c.execute("""
            SELECT COALESCE(label, 'None') as lbl, COUNT(*) as cnt 
            FROM images 
            GROUP BY label 
            ORDER BY cnt DESC
        """)
        stats["by_label"] = {row[0]: row[1] for row in c.fetchall()}
        
        # Score distribution
        c.execute("""
            SELECT 
                CASE 
                    WHEN score_general < 0.2 THEN '0.0-0.2'
                    WHEN score_general < 0.4 THEN '0.2-0.4'
                    WHEN score_general < 0.6 THEN '0.4-0.6'
                    WHEN score_general < 0.8 THEN '0.6-0.8'
                    ELSE '0.8-1.0'
                END as range,
                COUNT(*) as cnt
            FROM images
            WHERE score_general IS NOT NULL
            GROUP BY range
            ORDER BY range
        """)
        stats["score_distribution"] = {row[0]: row[1] for row in c.fetchall()}
        
        # Average scores
        c.execute("""
            SELECT 
                AVG(score_general) as avg_general,
                AVG(score_technical) as avg_technical,
                AVG(score_aesthetic) as avg_aesthetic,
                AVG(score_spaq) as avg_spaq,
                AVG(score_koniq) as avg_koniq,
                AVG(score_liqe) as avg_liqe
            FROM images
            WHERE score_general IS NOT NULL
        """)
        row = c.fetchone()
        stats["average_scores"] = {
            "general": round(row[0] or 0, 4),
            "technical": round(row[1] or 0, 4),
            "aesthetic": round(row[2] or 0, 4),
            "spaq": round(row[3] or 0, 4),
            "koniq": round(row[4] or 0, 4),
            "liqe": round(row[5] or 0, 4)
        }
        
        # Total folders
        c.execute("SELECT COUNT(*) FROM folders")
        stats["total_folders"] = c.fetchone()[0]
        
        # Total stacks
        c.execute("SELECT COUNT(*) FROM stacks")
        stats["total_stacks"] = c.fetchone()[0]
        
        # Jobs summary
        c.execute("""
            SELECT status, COUNT(*) as cnt 
            FROM jobs 
            GROUP BY status
        """)
        stats["jobs_by_status"] = {row[0]: row[1] for row in c.fetchall()}
        
        # Recent activity
        c.execute("""
            SELECT COUNT(*) FROM images 
            WHERE CAST(created_at AS DATE) = CURRENT_DATE
        """)
        stats["images_today"] = c.fetchone()[0]
        
    except Exception as e:
        stats["error"] = str(e)
    finally:
        conn.close()
    
    return stats


def query_images(
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "created_at",
    order: str = "desc",
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    rating: Optional[int] = None,
    label: Optional[str] = None,
    keyword: Optional[str] = None,
    folder_path: Optional[str] = None
) -> list:
    """Query images with flexible filtering."""
    conn = db.get_db()
    c = conn.cursor()
    
    query = """
        SELECT 
            id, file_path, file_name, file_type,
            score_general, score_technical, score_aesthetic,
            score_spaq, score_koniq, score_liqe,
            rating, label, keywords, created_at
        FROM images
    """
    
    conditions = []
    params = []
    
    if min_score is not None:
        conditions.append("score_general >= ?")
        params.append(min_score)
    
    if max_score is not None:
        conditions.append("score_general <= ?")
        params.append(max_score)
    
    if rating is not None:
        conditions.append("rating = ?")
        params.append(rating)
    
    if label:
        if label.lower() == "none":
            conditions.append("(label IS NULL OR label = '')")
        else:
            conditions.append("label = ?")
            params.append(label)
    
    if keyword:
        conditions.append("keywords LIKE ?")
        params.append(f"%{keyword}%")
    
    if folder_path:
        folder_id = db.get_or_create_folder(folder_path)
        if folder_id:
            conditions.append("folder_id = ?")
            params.append(folder_id)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # Validate sort column
    valid_columns = ["id", "created_at", "score_general", "score_technical", 
                     "score_aesthetic", "rating", "file_name"]
    if sort_by not in valid_columns:
        sort_by = "created_at"
    
    order = "DESC" if order.lower() == "desc" else "ASC"
    query += f" ORDER BY {sort_by} {order} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
    params.extend([offset, limit])
    
    try:
        c.execute(query, tuple(params))
        rows = c.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        return [{"error": str(e)}]
    finally:
        conn.close()


def get_image_details(file_path: str) -> dict:
    """Get full details for a specific image."""
    return db.get_image_details(file_path)


def execute_sql(query: str, params: list = None) -> dict:
    """Execute a read-only SQL query (SELECT only for safety)."""
    query = query.strip()
    
    # Safety check - only allow SELECT queries
    if not query.upper().startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed for safety reasons"}
    
    # Block dangerous SQL statements (word-boundary check to avoid
    # false positives on column names like "updated_at" or "created_at")
    import re
    dangerous_patterns = [
        r'\bDROP\b', r'\bDELETE\b', r'\bINSERT\b', r'\bUPDATE\b',
        r'\bALTER\b', r'\bCREATE\b', r'--', r';--',
    ]
    upper_query = query.upper()
    for pattern in dangerous_patterns:
        if re.search(pattern, upper_query):
            return {"error": f"Query contains forbidden pattern: {pattern}"}
    
    conn = db.get_db()
    c = conn.cursor()
    
    try:
        if params:
            c.execute(query, tuple(params))
        else:
            c.execute(query)
        
        rows = c.fetchall()
        
        # Get column names
        columns = [description[0] for description in c.description] if c.description else []
        
        # Convert to list of dicts
        results = [dict(zip(columns, row)) for row in rows]
        
        return {
            "columns": columns,
            "row_count": len(results),
            "rows": results[:100]  # Limit to 100 rows for safety
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def get_recent_jobs(limit: int = 10) -> list:
    """Get recent jobs with their status."""
    rows = db.get_jobs(limit=limit)
    return [dict(row) for row in rows]


def get_runner_status() -> dict:
    """Get current status of scoring and tagging runners."""
    status = {
        "scoring": {"available": False},
        "tagging": {"available": False}
    }
    
    if _scoring_runner:
        try:
            is_running, log, status_msg, current, total = _scoring_runner.get_status()
            status["scoring"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""  # Last 2000 chars
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
                "recent_log": log[-2000:] if log else ""
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
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["clustering"]["error"] = str(e)
    else:
        status["clustering"] = {"available": False}

    
    return status


def get_config() -> dict:
    """Get current application configuration."""
    return config.load_config()


def set_config_value(key: str, value: Any) -> dict:
    """Set a configuration value."""
    try:
        config.save_config_value(key, value)
        return {"success": True, "key": key, "value": value}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_folder_tree(root_path: Optional[str] = None) -> list:
    """Get folder tree structure from database."""
    folders = db.get_all_folders()
    
    if root_path:
        root_path = os.path.normpath(root_path)
        folders = [f for f in folders if f.startswith(root_path)]
    
    # Build tree structure
    tree = []
    for folder in folders:
        # Count images in folder
        images = db.get_images_by_folder(folder)
        tree.append({
            "path": folder,
            "name": os.path.basename(folder) or folder,
            "image_count": len(images)
        })
    
    return tree



def read_debug_log(lines: int = 100) -> dict:
    """Read the debug log file."""
    from modules import utils
    log_path = utils.get_debug_log_path()
    
    if not os.path.exists(log_path):
        return {"error": "Debug log file not found", "path": log_path}
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        
        # Get last N lines
        recent = all_lines[-lines:]
        
        # Parse JSON entries
        entries = []
        for line in recent:
            try:
                entries.append(json.loads(line.strip()))
            except (json.JSONDecodeError, ValueError):
                entries.append({"raw": line.strip()})
        
        return {
            "total_lines": len(all_lines),
            "returned_lines": len(entries),
            "entries": entries
        }
    except Exception as e:
        return {"error": str(e)}



def get_stacks_summary(folder_path: Optional[str] = None) -> dict:
    """Get summary of image stacks."""
    conn = db.get_db()
    c = conn.cursor()
    
    summary = {}
    
    try:
        # Total stacks
        c.execute("SELECT COUNT(*) FROM stacks")
        summary["total_stacks"] = c.fetchone()[0]
        
        # Stacks by size
        c.execute("""
            SELECT 
                CASE 
                    WHEN cnt = 1 THEN 'single'
                    WHEN cnt BETWEEN 2 AND 5 THEN '2-5'
                    WHEN cnt BETWEEN 6 AND 10 THEN '6-10'
                    ELSE '10+'
                END as size_range,
                COUNT(*) as stack_count
            FROM (
                SELECT stack_id, COUNT(*) as cnt 
                FROM images 
                WHERE stack_id IS NOT NULL 
                GROUP BY stack_id
            )
            GROUP BY size_range
        """)
        summary["stacks_by_size"] = {row[0]: row[1] for row in c.fetchall()}
        
        # Unstacked images
        c.execute("SELECT COUNT(*) FROM images WHERE stack_id IS NULL")
        summary["unstacked_images"] = c.fetchone()[0]
        
        # Top stacks by image count
        c.execute("""
            SELECT s.id, s.name, COUNT(i.id) as image_count,
                   MAX(i.score_general) as best_score
            FROM stacks s
            JOIN images i ON s.id = i.stack_id
            GROUP BY s.id
            ORDER BY image_count DESC
            FETCH FIRST 10 ROWS ONLY
        """)
        summary["largest_stacks"] = [
            {"id": row[0], "name": row[1], "count": row[2], "best_score": row[3]}
            for row in c.fetchall()
        ]
        
    except Exception as e:
        summary["error"] = str(e)
    finally:
        conn.close()
    
    return summary


def get_failed_images(limit: int = 50) -> list:
    """Get images that failed processing or have errors."""
    conn = db.get_db()
    c = conn.cursor()
    
    try:
        # Find images with missing critical scores (all models failed)
        c.execute("""
            SELECT id, file_path, file_name, created_at,
                   score_general, score_technical, score_aesthetic,
                   score_spaq, score_koniq, score_liqe
            FROM images
            WHERE (score_general IS NULL OR score_general = 0)
               OR (score_technical IS NULL OR score_technical = 0)
               OR (score_spaq IS NULL OR score_spaq = 0)
               OR (score_koniq IS NULL OR score_koniq = 0)
            ORDER BY created_at DESC
            FETCH FIRST ? ROWS ONLY
        """, (limit,))
        
        rows = c.fetchall()
        results = []
        for row in rows:
            item = dict(row)
            # Identify which scores are missing
            missing = []
            if not item.get('score_general') or item.get('score_general', 0) == 0:
                missing.append('general')
            if not item.get('score_technical') or item.get('score_technical', 0) == 0:
                missing.append('technical')
            if not item.get('score_spaq') or item.get('score_spaq', 0) == 0:
                missing.append('spaq')
            if not item.get('score_koniq') or item.get('score_koniq', 0) == 0:
                missing.append('koniq')
            item['missing_scores'] = missing
            results.append(item)
        
        return results
    except Exception as e:
        return [{"error": str(e)}]
    finally:
        conn.close()


def get_error_summary() -> dict:
    """Get summary of errors and issues in the database."""
    conn = db.get_db()
    c = conn.cursor()
    
    summary = {}
    
    try:
        # Failed jobs
        c.execute("""
            SELECT COUNT(*) FROM jobs WHERE status = 'failed'
        """)
        summary["failed_jobs"] = c.fetchone()[0]
        
        # Images with missing scores
        c.execute("""
            SELECT COUNT(*) FROM images 
            WHERE score_general IS NULL OR score_general = 0
        """)
        summary["images_missing_general_score"] = c.fetchone()[0]
        
        c.execute("""
            SELECT COUNT(*) FROM images 
            WHERE score_technical IS NULL OR score_technical = 0
        """)
        summary["images_missing_technical_score"] = c.fetchone()[0]
        
        # Images with missing model scores
        models = ['spaq', 'koniq', 'ava', 'paq2piq', 'liqe']
        for model in models:
            col = f"score_{model}"
            c.execute(f"""
                SELECT COUNT(*) FROM images 
                WHERE {col} IS NULL OR {col} = 0
            """)
            summary[f"images_missing_{model}"] = c.fetchone()[0]
        
        # Orphaned images (no folder)
        c.execute("""
            SELECT COUNT(*) FROM images WHERE folder_id IS NULL
        """)
        summary["orphaned_images"] = c.fetchone()[0]
        
        # Images with invalid paths (check if file exists)
        # This is expensive, so we'll just count NULL paths
        c.execute("""
            SELECT COUNT(*) FROM images WHERE file_path IS NULL OR file_path = ''
        """)
        summary["images_with_empty_paths"] = c.fetchone()[0]
        
        # Recent failed jobs with log excerpt
        c.execute("""
            SELECT id, input_path, status, log, created_at
            FROM jobs
            WHERE status = 'failed'
            ORDER BY created_at DESC
            FETCH FIRST 10 ROWS ONLY
        """)
        summary["recent_failed_jobs"] = [dict(row) for row in c.fetchall()]
        
    except Exception as e:
        summary["error"] = str(e)
    finally:
        conn.close()
    
    return summary


def check_database_health() -> dict:
    """Check database for inconsistencies and orphaned records."""
    conn = db.get_db()
    c = conn.cursor()
    
    health = {
        "status": "healthy",
        "issues": [],
        "warnings": []
    }
    
    try:
        # Check for orphaned images (folder_id references non-existent folder)
        c.execute("""
            SELECT COUNT(*) FROM images i
            LEFT JOIN folders f ON i.folder_id = f.id
            WHERE i.folder_id IS NOT NULL AND f.id IS NULL
        """)
        orphaned_count = c.fetchone()[0]
        if orphaned_count > 0:
            health["issues"].append(f"{orphaned_count} images with invalid folder_id")
            health["status"] = "unhealthy"
        
        # Check for orphaned stack references
        c.execute("""
            SELECT COUNT(*) FROM images i
            LEFT JOIN stacks s ON i.stack_id = s.id
            WHERE i.stack_id IS NOT NULL AND s.id IS NULL
        """)
        orphaned_stacks = c.fetchone()[0]
        if orphaned_stacks > 0:
            health["issues"].append(f"{orphaned_stacks} images with invalid stack_id")
            health["status"] = "unhealthy"
        
        # Check for duplicate file paths
        c.execute("""
            SELECT file_path, COUNT(*) as cnt
            FROM images
            WHERE file_path IS NOT NULL
            GROUP BY file_path
            HAVING COUNT(*) > 1
        """)
        duplicates = c.fetchall()
        if duplicates:
            health["warnings"].append(f"{len(duplicates)} duplicate file paths found")
        
        # Check for images with hash but no file_path
        c.execute("""
            SELECT COUNT(*) FROM images
            WHERE image_hash IS NOT NULL AND (file_path IS NULL OR file_path = '')
        """)
        hash_no_path = c.fetchone()[0]
        if hash_no_path > 0:
            health["warnings"].append(f"{hash_no_path} images with hash but no path")
        
        # Check for folders with no images
        c.execute("""
            SELECT COUNT(*) FROM folders f
            LEFT JOIN images i ON f.id = i.folder_id
            WHERE i.id IS NULL
        """)
        empty_folders = c.fetchone()[0]
        if empty_folders > 0:
            health["warnings"].append(f"{empty_folders} folders with no images")
        
        # Check for stacks with no images
        c.execute("""
            SELECT COUNT(*) FROM stacks s
            LEFT JOIN images i ON s.id = i.stack_id
            WHERE i.id IS NULL
        """)
        empty_stacks = c.fetchone()[0]
        if empty_stacks > 0:
            health["warnings"].append(f"{empty_stacks} stacks with no images")
        
        health["summary"] = {
            "total_issues": len(health["issues"]),
            "total_warnings": len(health["warnings"])
        }
        
    except Exception as e:
        health["status"] = "error"
        health["error"] = str(e)
    finally:
        conn.close()
    
    return health


def validate_file_paths(limit: int = 100) -> dict:
    """Validate that file paths in database actually exist."""
    conn = db.get_db()
    c = conn.cursor()
    
    results = {
        "checked": 0,
        "exists": 0,
        "missing": 0,
        "missing_files": []
    }
    
    try:
        c.execute("""
            SELECT id, file_path FROM images
            WHERE file_path IS NOT NULL AND file_path != ''
            ORDER BY created_at DESC
            FETCH FIRST ? ROWS ONLY
        """, (limit,))
        
        rows = c.fetchall()
        results["checked"] = len(rows)
        
        for row in rows:
            file_path = row[1]
            if os.path.exists(file_path):
                results["exists"] += 1
            else:
                results["missing"] += 1
                results["missing_files"].append({
                    "id": row[0],
                    "file_path": file_path
                })
        
    except Exception as e:
        results["error"] = str(e)
    finally:
        conn.close()
    
    return results


def run_processing_job(job_type: str, input_path: str, args: dict = None) -> dict:
    """
    Trigger a background processing job.
    
    Args:
        job_type: "scoring", "tagging", or "clustering" (stacks)
        input_path: Folder path to process
        args: Optional arguments:
            - scoring: {"rescore": bool}
            - tagging: {"overwrite": bool, "custom_keywords": list}
            - clustering: {"threshold": float, "time_gap": int, "force_rescan": bool}
    """
    import uuid
    
    if args is None:
        args = {}
        
    job_id = f"mcp_{job_type}_{uuid.uuid4().hex[:8]}"
    
    if not os.path.exists(input_path) and not (job_type == "clustering" and (not input_path or not input_path.strip())):
        return {"error": f"Input path not found: {input_path}"}

    if job_type == "scoring":
        if not _scoring_runner:
            return {"error": "Scoring runner not available"}
        
        # Check if running
        if _scoring_runner.is_running:
            return {"error": "Scoring job already running"}
            
        res = _scoring_runner.start_batch(
            input_path, 
            job_id, 
            skip_existing=not args.get("rescore", False)
        )
        return {"status": res, "job_id": job_id}
        
    elif job_type == "tagging":
        if not _tagging_runner:
            return {"error": "Tagging runner not available"}
            
        if _tagging_runner.is_running:
            return {"error": "Tagging job already running"}
            
        custom_keywords = args.get("custom_keywords")
        res = _tagging_runner.start_batch(
            input_path,
            overwrite=args.get("overwrite", False),
            custom_keywords=custom_keywords
        )
        return {"status": res, "job_id": job_id}
        
    elif job_type == "clustering":
        if not _clustering_runner:
            return {"error": "Clustering runner not available (not initialized)"}
            
        if _clustering_runner.is_running:
            return {"error": "Clustering job already running"}
        
        # Allow empty input_path for clustering (processes all unprocessed folders)
        cluster_path = input_path.strip() if input_path and input_path.strip() else None
            
        res = _clustering_runner.start_batch(
            cluster_path,
            threshold=args.get("threshold"),
            time_gap=args.get("time_gap"),
            force_rescan=args.get("force_rescan", False)
        )
        return {"status": res, "job_id": job_id}
        
    else:
        return {"error": f"Unknown job type: {job_type}"}


def get_model_status() -> dict:
    """Get status of loaded models and GPU availability."""
    status = {
        "models": {},
        "gpu": {},
        "scorer_available": False
    }
    
    try:
        # Check if scorer is available
        if _scoring_runner and _scoring_runner.shared_scorer:
            status["scorer_available"] = True
            scorer = _scoring_runner.shared_scorer
            
            # Get model version
            try:
                status["models"]["version"] = getattr(scorer, 'VERSION', 'unknown')
            except Exception:
                pass
            
            # Check which models are loaded
            model_names = ['spaq', 'ava', 'koniq', 'paq2piq']
            for model_name in model_names:
                try:
                    model_attr = getattr(scorer, f'{model_name}_model', None)
                    status["models"][model_name] = {
                        "loaded": model_attr is not None
                    }
                except Exception:
                    status["models"][model_name] = {"loaded": False}
        else:
            status["models"]["note"] = "Scorer not initialized"
        
        # Check GPU availability
        try:
            import tensorflow as tf
            gpus = tf.config.list_physical_devices('GPU')
            status["gpu"]["tensorflow_available"] = True
            status["gpu"]["physical_gpus"] = len(gpus)
            status["gpu"]["cuda_built"] = tf.test.is_built_with_cuda()
            if gpus:
                status["gpu"]["gpu_names"] = [str(gpu) for gpu in gpus]
        except ImportError:
            status["gpu"]["tensorflow_available"] = False
        except Exception as e:
            status["gpu"]["error"] = str(e)
        
        # Check PyTorch GPU
        try:
            import torch
            status["gpu"]["pytorch_available"] = True
            status["gpu"]["pytorch_cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                status["gpu"]["pytorch_device_count"] = torch.cuda.device_count()
                status["gpu"]["pytorch_device_name"] = torch.cuda.get_device_name(0)
        except ImportError:
            status["gpu"]["pytorch_available"] = False
        except Exception as e:
            status["gpu"]["pytorch_error"] = str(e)
        
        # Check NVIDIA driver
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                status["gpu"]["nvidia_driver"] = "available"
                lines = result.stdout.strip().split('\n')
                status["gpu"]["gpu_info"] = lines
            else:
                status["gpu"]["nvidia_driver"] = "not_available"
        except (OSError, Exception):
            status["gpu"]["nvidia_driver"] = "not_checked"
        
    except Exception as e:
        status["error"] = str(e)
    
    return status


# --- MCP Server Setup ---

def create_mcp_server() -> "Server":
    """Create and configure the MCP server with all tools."""
    if not MCP_AVAILABLE:
        raise RuntimeError("MCP SDK not available. Install with: pip install mcp")
    
    server = Server("image-scoring-debug")
    
    @server.list_tools()
    async def list_tools():
        """List all available debugging tools."""
        return [
            Tool(
                name="get_database_stats",
                description="Get comprehensive database statistics including image counts, score distributions, and job summaries",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="query_images",
                description="Query images with flexible filtering and pagination. Supports filtering by score range, rating, label, keywords, and folder.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max number of results (default: 20)", "default": 20},
                        "offset": {"type": "integer", "description": "Offset for pagination", "default": 0},
                        "sort_by": {"type": "string", "description": "Column to sort by", "enum": ["id", "created_at", "score_general", "score_technical", "score_aesthetic", "rating", "file_name"]},
                        "order": {"type": "string", "enum": ["asc", "desc"], "default": "desc"},
                        "min_score": {"type": "number", "description": "Minimum general score (0-1)"},
                        "max_score": {"type": "number", "description": "Maximum general score (0-1)"},
                        "rating": {"type": "integer", "description": "Filter by rating (0-5)"},
                        "label": {"type": "string", "description": "Filter by color label (Red, Yellow, Green, Blue, Purple, None)"},
                        "keyword": {"type": "string", "description": "Filter by keyword (partial match)"},
                        "folder_path": {"type": "string", "description": "Filter by folder path"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="get_image_details",
                description="Get full details for a specific image by file path",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Full path to the image file"}
                    },
                    "required": ["file_path"]
                }
            ),
            Tool(
                name="execute_sql",
                description="Execute a read-only SQL SELECT query against the database. Only SELECT queries are allowed for safety.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL SELECT query to execute"},
                        "params": {"type": "array", "items": {"type": "string"}, "description": "Query parameters for prepared statements"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="get_recent_jobs",
                description="Get recent scoring/tagging jobs with their status",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of jobs to return", "default": 10}
                    },
                    "required": []
                }
            ),
            Tool(
                name="get_runner_status",
                description="Get current status of scoring and tagging background runners including progress and recent logs",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="get_config",
                description="Get current application configuration from config.json",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="set_config_value",
                description="Set a configuration value in config.json",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Configuration key to set"},
                        "value": {"description": "Value to set (any JSON-compatible type)"}
                    },
                    "required": ["key", "value"]
                }
            ),
            Tool(
                name="get_folder_tree",
                description="Get folder tree structure from database with image counts",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "root_path": {"type": "string", "description": "Optional root path to filter folders"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="read_debug_log",
                description="Read recent entries from the debug log file",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "lines": {"type": "integer", "description": "Number of recent lines to read", "default": 100}
                    },
                    "required": []
                }
            ),
            Tool(
                name="get_stacks_summary",
                description="Get summary of image stacks/clusters including size distribution and largest stacks",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "folder_path": {"type": "string", "description": "Optional folder path to filter stacks"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="get_failed_images",
                description="Get images that failed processing or have missing scores",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max number of results", "default": 50}
                    },
                    "required": []
                }
            ),
            Tool(
                name="get_error_summary",
                description="Get summary of errors and issues in the database including failed jobs and missing scores",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="check_database_health",
                description="Check database for inconsistencies, orphaned records, and data integrity issues",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="validate_file_paths",
                description="Validate that file paths in database actually exist on the filesystem",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max number of paths to check", "default": 100}
                    },
                    "required": []
                }
            ),
            Tool(
                name="get_model_status",
                description="Get status of loaded models, GPU availability, and CUDA/PyTorch/TensorFlow configuration",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="run_processing_job",
                description="Trigger a background processing job (scoring, tagging, or clustering/stacks)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_type": {
                            "type": "string",
                            "enum": ["scoring", "tagging", "clustering"], 
                            "description": "Type of job to run"
                        },
                        "input_path": {
                            "type": "string", 
                            "description": "Full path to the folder or file to process"
                        },
                        "args": {
                            "type": "object",
                            "description": "Optional arguments specific to the job type",
                            "properties": {
                                "rescore": {"type": "boolean", "description": "For scoring: Force rescore existing images"},
                                "overwrite": {"type": "boolean", "description": "For tagging: Overwrite existing tags"},
                                "custom_keywords": {"type": "array", "items": {"type": "string"}, "description": "For tagging: Custom keywords to add"},
                                "threshold": {"type": "number", "description": "For clustering: Similarity threshold"},
                                "time_gap": {"type": "integer", "description": "For clustering: Max time gap in seconds"},
                                "force_rescan": {"type": "boolean", "description": "For clustering: Force rescan of all images"}
                            }
                        }
                    },
                    "required": ["job_type", "input_path"]
                }
            ),
            Tool(
                name="search_similar_images",
                description="Find images visually similar to an example image using stored MobileNetV2 embeddings and cosine similarity. Provide either example_path or example_image_id.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "example_path": {"type": "string", "description": "File path of the example image to search for"},
                        "example_image_id": {"type": "integer", "description": "Database ID of the example image (alternative to example_path)"},
                        "limit": {"type": "integer", "description": "Max results to return (default: 20)", "default": 20},
                        "folder_path": {"type": "string", "description": "Restrict search to images in this folder"},
                        "min_similarity": {"type": "number", "description": "Minimum cosine similarity threshold (0-1)"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="find_near_duplicates",
                description="Detect visually duplicate or near-duplicate images even when file hashes differ. Returns a list of near-duplicate image pairs.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "threshold": {"type": "number", "description": "Minimum cosine similarity threshold (default: 0.98)"},
                        "folder_path": {"type": "string", "description": "Optional folder path to restrict duplicate search to a specific directory"},
                        "limit": {"type": "integer", "description": "Max number of duplicate pairs to return (defaults to configured duplicate_max_pairs)"}
                    },
                    "required": []
                }
            )
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if name in DB_TOOLS and not _db_available:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Database not available. Run migrate_to_firebird.py first."}, indent=2)
                )]
            if name == "get_database_stats":
                result = get_database_stats()
            elif name == "query_images":
                result = query_images(**arguments)
            elif name == "get_image_details":
                result = get_image_details(arguments["file_path"])
            elif name == "execute_sql":
                result = execute_sql(
                    arguments["query"],
                    arguments.get("params")
                )
            elif name == "get_recent_jobs":
                result = get_recent_jobs(arguments.get("limit", 10))
            elif name == "get_runner_status":
                result = get_runner_status()
            elif name == "get_config":
                result = get_config()
            elif name == "set_config_value":
                result = set_config_value(arguments["key"], arguments["value"])
            elif name == "get_folder_tree":
                result = get_folder_tree(arguments.get("root_path"))
            elif name == "read_debug_log":
                result = read_debug_log(arguments.get("lines", 100))
            elif name == "get_stacks_summary":
                result = get_stacks_summary(arguments.get("folder_path"))
            elif name == "get_failed_images":
                result = get_failed_images(arguments.get("limit", 50))
            elif name == "get_error_summary":
                result = get_error_summary()
            elif name == "check_database_health":
                result = check_database_health()
            elif name == "validate_file_paths":
                result = validate_file_paths(arguments.get("limit", 100))
            elif name == "get_model_status":
                result = get_model_status()
            elif name == "run_processing_job":
                result = run_processing_job(
                    arguments["job_type"], 
                    arguments["input_path"],
                    arguments.get("args")
                )
            elif name == "search_similar_images":
                from modules import similar_search
                result = similar_search.search_similar_images(
                    example_path=arguments.get("example_path"),
                    example_image_id=arguments.get("example_image_id"),
                    limit=arguments.get("limit", 20),
                    folder_path=arguments.get("folder_path"),
                    min_similarity=arguments.get("min_similarity"),
                )
            elif name == "find_near_duplicates":
                from modules import similar_search
                result = similar_search.find_near_duplicates(
                    threshold=arguments.get("threshold"),
                    folder_path=arguments.get("folder_path"),
                    limit=arguments.get("limit")
                )
            else:
                result = {"error": f"Unknown tool: {name}"}
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str)
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({"error": str(e)}, indent=2)
            )]
    
    return server


def prepare_mcp_embedded():
    """Initialize DB and set _db_available for embedded (SSE) or stdio runs. Idempotent."""
    global _db_available
    try:
        db.init_db()
        _db_available = True
    except Exception as e:
        logger.warning("DB init failed (%s). DB tools will return 'Database not available'.", e)
        _db_available = False


def create_mcp_sse_app(mount_path: str = "/mcp"):
    """
    Create a Starlette ASGI app that exposes MCP over SSE, to be mounted in FastAPI.
    Cursor connects via url e.g. http://localhost:7860/mcp/sse
    """
    if not MCP_AVAILABLE or not MCP_SSE_AVAILABLE:
        raise RuntimeError("MCP SDK with SSE required. Install: pip install mcp")

    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.requests import Request

    prepare_mcp_embedded()
    server = create_mcp_server()
    messages_path = f"{mount_path.rstrip('/')}/messages/"
    transport = SseServerTransport(messages_path)

    async def handle_sse(request: Request):
        async with transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )

    routes = [
        # Accept both with and without trailing slash to avoid client redirect issues
        Route("/sse", endpoint=handle_sse),
        Route("/sse/", endpoint=handle_sse),
        Mount("/messages/", app=transport.handle_post_message),
    ]
    return Starlette(routes=routes)


async def run_server():
    """Run the MCP server using stdio transport."""
    if not MCP_AVAILABLE:
        print("Error: MCP SDK not installed. Run: pip install mcp")
        return

    prepare_mcp_embedded()
    server = create_mcp_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def start_mcp_server_background():
    """Start MCP server in a background thread (for integration with webui)."""
    import threading
    
    def run_async():
        asyncio.run(run_server())
    
    thread = threading.Thread(target=run_async, daemon=True)
    thread.start()
    logger.info("MCP server started in background")
    return thread


if __name__ == "__main__":
    # Run standalone - NO print statements allowed! MCP uses stdio for JSON protocol.
    # All output must go to stderr, not stdout.
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    logger.info("Starting Image Scoring MCP Server...")
    
    # Initialize runners for standalone mode
    try:
        from modules.clustering import ClusteringRunner
        # Note: ScoringRunner/TaggingRunner require shared_scorer which is heavy. 
        # Clustering runs its own lightweight model.
        clustering_runner = ClusteringRunner()
        set_runners(None, None, clustering_runner)
        logger.info("Initialized ClusteringRunner for standalone mode")
    except Exception as e:
        logger.warning(f"Failed to initialize clustering runner: {e}")

    asyncio.run(run_server())

