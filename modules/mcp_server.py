"""
MCP (Model Context Protocol) Server for Image Scoring WebUI

Provides comprehensive debugging tools for Cursor IDE and AI agents to interact with:
- Database operations: Query images, get statistics, check data integrity
- Error diagnostics: Find failed images, error summaries, health checks
- Performance monitoring: Track metrics, job status, pipeline state
- System diagnostics: GPU/model status, configuration validation
- File validation: Verify file paths exist, check consistency
- Log access: Read debug logs for investigation
- Configuration: Read and update application settings

Available Tools (21 total):
  Database & Stats:
    - get_database_stats: Overall database statistics
    - query_images: Flexible image queries with filtering
    - get_image_details: Full details for specific image
    - execute_sql: Read-only SQL queries (SELECT only)
  
  Error & Diagnostics:
    - get_failed_images: Images with missing/failed scores
    - get_error_summary: Summary of all errors and issues
    - check_database_health: Data integrity validation
    - validate_file_paths: Check if database paths exist
  
  Performance & Monitoring:
    - get_performance_metrics: Processing speed and success rates
    - get_runner_status: Current job status and progress
    - get_recent_jobs: Recent job history
    - get_pipeline_stats: Active pipeline state and queues
  
  System Diagnostics:
    - get_model_status: GPU availability, model loading status
    - validate_config: Configuration validation
    - read_debug_log: Read debug log entries
  
  Analysis & Utilities:
    - get_incomplete_images: Images missing data
    - get_stacks_summary: Stack/cluster analysis
    - get_folder_tree: Folder structure with counts
    - search_images_by_hash: Find image by content hash
    - get_config: Read configuration
    - set_config_value: Update configuration

Usage:
    Start alongside webui.py or run standalone:
    python -m modules.mcp_server
    
    Or set environment variable when running webui:
    ENABLE_MCP_SERVER=1 python webui.py

For AI Agents:
    See docs/technical/MCP_DEBUGGING_TOOLS.md for detailed documentation
    See .agent/mcp_tools_reference.md for quick reference guide
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

# Set False if db.init_db() fails (e.g. Firebird not migrated); DB-using tools then return a clear error
_db_available = True

DB_TOOLS = frozenset({
    "get_database_stats", "query_images", "get_image_details", "execute_sql",
    "get_recent_jobs", "get_folder_tree", "get_incomplete_images",
    "search_images_by_hash", "get_stacks_summary",
    "get_failed_images", "get_error_summary", "check_database_health",
    "validate_file_paths", "get_performance_metrics",
    # Note: get_model_status, validate_config, get_pipeline_stats don't require DB
})

def set_runners(scoring_runner, tagging_runner):
    """Set references to the runner instances from webui."""
    global _scoring_runner, _tagging_runner
    _scoring_runner = scoring_runner
    _tagging_runner = tagging_runner

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
            SELECT rating, COUNT(*) as count 
            FROM images 
            GROUP BY rating 
            ORDER BY rating
        """)
        stats["by_rating"] = {str(row[0]): row[1] for row in c.fetchall()}
        
        # Images by label
        c.execute("""
            SELECT COALESCE(label, 'None') as lbl, COUNT(*) as count 
            FROM images 
            GROUP BY label 
            ORDER BY count DESC
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
                COUNT(*) as count
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
            SELECT status, COUNT(*) as count 
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
    
    # Block dangerous patterns
    dangerous_patterns = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "--", ";--"]
    for pattern in dangerous_patterns:
        if pattern in query.upper():
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


def get_incomplete_images(limit: int = 50) -> list:
    """Get images with missing or incomplete data."""
    rows = db.get_incomplete_records()
    results = []
    
    for row in rows[:limit]:
        item = dict(row)
        # Identify what's missing
        missing = []
        if not item.get('score') or item.get('score', 0) <= 0:
            missing.append('score')
        if not item.get('rating') or item.get('rating', 0) <= 0:
            missing.append('rating')
        if not item.get('label'):
            missing.append('label')
        if not item.get('score_liqe') or item.get('score_liqe', 0) <= 0:
            missing.append('liqe')
            
        item['missing_fields'] = missing
        results.append(item)
    
    return results


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
            except:
                entries.append({"raw": line.strip()})
        
        return {
            "total_lines": len(all_lines),
            "returned_lines": len(entries),
            "entries": entries
        }
    except Exception as e:
        return {"error": str(e)}


def search_images_by_hash(image_hash: str) -> dict:
    """Search for an image by its content hash."""
    return db.get_image_by_hash(image_hash)


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


# --- New Debugging Tools ---

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
        
        # Recent failed jobs with error messages
        c.execute("""
            SELECT id, job_type, status, error_message, created_at
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


def get_performance_metrics() -> dict:
    """Get performance metrics from recent jobs."""
    conn = db.get_db()
    c = conn.cursor()
    
    metrics = {}
    
    try:
        # Average job duration
        c.execute("""
            SELECT 
                AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_duration,
                COUNT(*) as total_jobs
            FROM jobs
            WHERE status = 'completed' 
              AND updated_at IS NOT NULL 
              AND created_at IS NOT NULL
        """)
        row = c.fetchone()
        if row and row[0]:
            metrics["avg_job_duration_seconds"] = round(row[0], 2)
            metrics["total_completed_jobs"] = row[1]
        
        # Images processed per hour (recent jobs)
        c.execute("""
            SELECT 
                SUM(image_count) as total_images,
                SUM(EXTRACT(EPOCH FROM (updated_at - created_at))) as total_seconds
            FROM jobs
            WHERE status = 'completed'
              AND image_count > 0
              AND updated_at IS NOT NULL
              AND created_at IS NOT NULL
              AND created_at > CURRENT_DATE - 7
        """)
        row = c.fetchone()
        if row and row[0] and row[1] and row[1] > 0:
            images_per_hour = (row[0] / row[1]) * 3600
            metrics["images_per_hour"] = round(images_per_hour, 2)
            metrics["total_images_last_7_days"] = row[0]
        
        # Job success rate
        c.execute("""
            SELECT 
                status,
                COUNT(*) as count
            FROM jobs
            GROUP BY status
        """)
        status_counts = {row[0]: row[1] for row in c.fetchall()}
        total = sum(status_counts.values())
        if total > 0:
            metrics["job_success_rate"] = round(
                (status_counts.get('completed', 0) / total) * 100, 2
            )
            metrics["job_status_breakdown"] = status_counts
        
    except Exception as e:
        metrics["error"] = str(e)
    finally:
        conn.close()
    
    return metrics


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
            except:
                pass
            
            # Check which models are loaded
            model_names = ['spaq', 'ava', 'koniq', 'paq2piq']
            for model_name in model_names:
                try:
                    model_attr = getattr(scorer, f'{model_name}_model', None)
                    status["models"][model_name] = {
                        "loaded": model_attr is not None
                    }
                except:
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
        except:
            status["gpu"]["nvidia_driver"] = "not_checked"
        
    except Exception as e:
        status["error"] = str(e)
    
    return status


def validate_config() -> dict:
    """Validate configuration values."""
    validation = {
        "valid": True,
        "issues": [],
        "warnings": []
    }
    
    try:
        cfg = config.load_config()
        
        # Check required paths
        if 'paths' in cfg:
            paths = cfg['paths']
            if 'image_directories' in paths:
                dirs = paths['image_directories']
                if isinstance(dirs, list):
                    for dir_path in dirs:
                        if not os.path.exists(dir_path):
                            validation["warnings"].append(f"Image directory does not exist: {dir_path}")
                            validation["valid"] = False
                else:
                    validation["issues"].append("image_directories should be a list")
        
        # Check processing config
        if 'processing' in cfg:
            proc = cfg['processing']
            queue_sizes = ['prep_queue_size', 'scoring_queue_size', 'result_queue_size']
            for qs in queue_sizes:
                if qs in proc:
                    val = proc[qs]
                    if not isinstance(val, int) or val < 1:
                        validation["issues"].append(f"{qs} must be a positive integer")
                        validation["valid"] = False
        
        validation["config_keys"] = list(cfg.keys())
        
    except Exception as e:
        validation["valid"] = False
        validation["error"] = str(e)
    
    return validation


def get_pipeline_stats() -> dict:
    """Get statistics about the processing pipeline."""
    stats = {
        "runners": {},
        "queues": {},
        "processor": {}
    }
    
    try:
        # Get runner status
        runner_status = get_runner_status()
        stats["runners"] = runner_status
        
        # Try to get processor information
        if _scoring_runner:
            stats["processor"]["scorer_initialized"] = _scoring_runner.shared_scorer is not None
            stats["processor"]["is_running"] = getattr(_scoring_runner, 'is_running', False)
            stats["processor"]["job_type"] = getattr(_scoring_runner, 'job_type', None)
            stats["processor"]["status_message"] = getattr(_scoring_runner, 'status_message', 'Unknown')
            
            # Get progress information
            if hasattr(_scoring_runner, 'current_count') and hasattr(_scoring_runner, 'total_count'):
                stats["processor"]["current_count"] = _scoring_runner.current_count
                stats["processor"]["total_count"] = _scoring_runner.total_count
                if _scoring_runner.total_count > 0:
                    stats["processor"]["progress_percent"] = round(
                        (_scoring_runner.current_count / _scoring_runner.total_count * 100), 2
                    )
            
            # Check if processor is active
            if _scoring_runner.current_processor:
                processor = _scoring_runner.current_processor
                stats["processor"]["has_active_processor"] = True
                stats["processor"]["processed_count"] = getattr(processor, 'processed_count', 0)
                stats["processor"]["total_count"] = getattr(processor, 'total_count', 0)
                stats["processor"]["stop_requested"] = getattr(processor, 'stop_event', None) and processor.stop_event.is_set() if hasattr(processor, 'stop_event') else False
            else:
                stats["processor"]["has_active_processor"] = False
        else:
            stats["processor"]["note"] = "Scoring runner not available"
        
        # Get config-based queue sizes
        try:
            processing_config = config.get_config_section('processing')
            stats["queues"] = {
                "prep_queue_size": processing_config.get('prep_queue_size', 'not_set'),
                "scoring_queue_size": processing_config.get('scoring_queue_size', 'not_set'),
                "result_queue_size": processing_config.get('result_queue_size', 'not_set')
            }
        except:
            stats["queues"]["note"] = "Could not read queue sizes from config"
        
    except Exception as e:
        stats["error"] = str(e)
    
    return stats


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
                name="get_incomplete_images",
                description="Get images with missing or incomplete scoring data",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max number of results", "default": 50}
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
                name="search_images_by_hash",
                description="Search for an image by its content hash (SHA256)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "image_hash": {"type": "string", "description": "SHA256 hash of the image content"}
                    },
                    "required": ["image_hash"]
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
                name="get_performance_metrics",
                description="Get performance metrics from recent jobs including processing speed and success rates",
                inputSchema={
                    "type": "object",
                    "properties": {},
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
                name="validate_config",
                description="Validate configuration values and check for issues",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="get_pipeline_stats",
                description="Get statistics about the processing pipeline including queue sizes and worker status",
                inputSchema={
                    "type": "object",
                    "properties": {},
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
            elif name == "get_incomplete_images":
                result = get_incomplete_images(arguments.get("limit", 50))
            elif name == "read_debug_log":
                result = read_debug_log(arguments.get("lines", 100))
            elif name == "search_images_by_hash":
                result = search_images_by_hash(arguments["image_hash"])
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
            elif name == "get_performance_metrics":
                result = get_performance_metrics()
            elif name == "get_model_status":
                result = get_model_status()
            elif name == "validate_config":
                result = validate_config()
            elif name == "get_pipeline_stats":
                result = get_pipeline_stats()
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
    asyncio.run(run_server())

