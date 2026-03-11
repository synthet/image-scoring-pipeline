"""
MCP (Model Context Protocol) Server for Image Scoring WebUI

Provides debugging and management tools for Cursor IDE and AI agents.
Uses FastMCP for automatic schema generation from type annotations.

Usage:
    python -m modules.mcp_server          # standalone
    ENABLE_MCP_SERVER=1 python webui.py   # integrated
"""

import asyncio
import json
import logging
import os
import re
import sys
from typing import Any, Optional

# MCP SDK imports
try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

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

# Annotation presets
_RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
_RW = ToolAnnotations(readOnlyHint=False, destructiveHint=False)


def _require_db(fn):
    """Decorator that returns an error dict if the database is not available."""
    import functools
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not _db_available:
            return {"error": "Database not available. Run migrate_to_firebird.py first."}
        return fn(*args, **kwargs)
    return wrapper


def set_runners(scoring_runner, tagging_runner, clustering_runner=None):
    """Set references to the runner instances from webui."""
    global _scoring_runner, _tagging_runner, _clustering_runner
    _scoring_runner = scoring_runner
    _tagging_runner = tagging_runner
    _clustering_runner = clustering_runner


# --- Create FastMCP server instance ---

if MCP_AVAILABLE:
    mcp = FastMCP("image-scoring")
else:
    # Fallback mock so module can be imported without MCP SDK
    class _MockMCP:
        def tool(self, *a, **kw):
            return lambda fn: fn
        def resource(self, *a, **kw):
            return lambda fn: fn
    mcp = _MockMCP()


# ============================================================
# Database & Query Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def get_database_stats() -> dict:
    """Get comprehensive database statistics including image counts, score distributions, and job summaries."""
    with db.connection() as conn:
        c = conn.cursor()
        stats = {}

        try:
            c.execute("SELECT COUNT(*) FROM images")
            stats["total_images"] = c.fetchone()[0]

            c.execute("""
                SELECT rating, COUNT(*) as cnt
                FROM images
                GROUP BY rating
                ORDER BY rating
            """)
            stats["by_rating"] = {str(row[0]): row[1] for row in c.fetchall()}

            c.execute("""
                SELECT COALESCE(label, 'None') as lbl, COUNT(*) as cnt
                FROM images
                GROUP BY label
                ORDER BY cnt DESC
            """)
            stats["by_label"] = {row[0]: row[1] for row in c.fetchall()}

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

            c.execute("SELECT COUNT(*) FROM folders")
            stats["total_folders"] = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM stacks")
            stats["total_stacks"] = c.fetchone()[0]

            c.execute("""
                SELECT status, COUNT(*) as cnt
                FROM jobs
                GROUP BY status
            """)
            stats["jobs_by_status"] = {row[0]: row[1] for row in c.fetchall()}

            c.execute("""
                SELECT COUNT(*) FROM images
                WHERE CAST(created_at AS DATE) = CURRENT_DATE
            """)
            stats["images_today"] = c.fetchone()[0]

        except Exception as e:
            stats["error"] = str(e)

        return stats


@mcp.tool(annotations=_RO)
@_require_db
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
    """Query images with flexible filtering and pagination. Supports filtering by score range, rating, label, keywords, and folder."""
    with db.connection() as conn:
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


@mcp.tool(annotations=_RO)
@_require_db
def get_image_details(file_path: str) -> dict:
    """Get full details for a specific image by file path."""
    return db.get_image_details(file_path)


@mcp.tool(annotations=_RO)
@_require_db
def execute_sql(query: str, params: list = None) -> dict:
    """Execute a read-only SQL SELECT query against the database. Only SELECT queries are allowed for safety."""
    query = query.strip()

    # Safety check - only allow SELECT queries
    if not query.upper().startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed for safety reasons"}

    # Block dangerous SQL patterns (word-boundary check to avoid
    # false positives on column names like "updated_at" or "created_at")
    dangerous_patterns = [
        r'\bDROP\b', r'\bDELETE\b', r'\bINSERT\b', r'\bUPDATE\b',
        r'\bALTER\b', r'\bCREATE\b', r'--', r';--',
    ]
    upper_query = query.upper()
    for pattern in dangerous_patterns:
        if re.search(pattern, upper_query):
            return {"error": f"Query contains forbidden pattern: {pattern}"}

    with db.connection() as conn:
        c = conn.cursor()

        try:
            # Defense-in-depth: start a read-only transaction so even if
            # SQL injection bypasses the regex, no writes can occur.
            try:
                from firebird.driver import tpb, Isolation, TraAccessMode
                ro_tpb = tpb(isolation=Isolation.READ_COMMITTED_RECORD_VERSION,
                             access_mode=TraAccessMode.READ)
                conn.begin(tpb=ro_tpb)
            except Exception:
                pass  # Fall back to default transaction if read-only TPB fails

            if params:
                c.execute(query, tuple(params))
            else:
                c.execute(query)

            rows = c.fetchall()
            columns = [description[0] for description in c.description] if c.description else []
            results = [dict(zip(columns, row)) for row in rows]

            return {
                "columns": columns,
                "row_count": len(results),
                "rows": results[:100]  # Limit to 100 rows
            }
        except Exception as e:
            return {"error": str(e)}


@mcp.tool(annotations=_RO)
@_require_db
def get_folder_tree(root_path: Optional[str] = None) -> list:
    """Get folder tree structure from database with image counts."""
    with db.connection() as conn:
        c = conn.cursor()
        try:
            if root_path:
                root_path = os.path.normpath(root_path)
                c.execute("""
                    SELECT f.path, COUNT(i.id) as image_count
                    FROM folders f
                    LEFT JOIN images i ON f.id = i.folder_id
                    WHERE f.path STARTING WITH ?
                    GROUP BY f.path
                    ORDER BY f.path
                """, (root_path,))
            else:
                c.execute("""
                    SELECT f.path, COUNT(i.id) as image_count
                    FROM folders f
                    LEFT JOIN images i ON f.id = i.folder_id
                    GROUP BY f.path
                    ORDER BY f.path
                """)
            return [
                {"path": row[0], "name": os.path.basename(row[0]) or row[0], "image_count": row[1]}
                for row in c.fetchall()
            ]
        except Exception as e:
            return [{"error": str(e)}]


@mcp.tool(annotations=_RO)
@_require_db
def get_stacks_summary(folder_path: Optional[str] = None) -> dict:
    """Get summary of image stacks/clusters including size distribution and largest stacks."""
    with db.connection() as conn:
        c = conn.cursor()
        summary = {}

        try:
            c.execute("SELECT COUNT(*) FROM stacks")
            summary["total_stacks"] = c.fetchone()[0]

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

            c.execute("SELECT COUNT(*) FROM images WHERE stack_id IS NULL")
            summary["unstacked_images"] = c.fetchone()[0]

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

        return summary


# ============================================================
# Error & Diagnostics Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def get_failed_images(limit: int = 50) -> list:
    """Get images that failed processing or have missing scores."""
    with db.connection() as conn:
        c = conn.cursor()

        try:
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


@mcp.tool(annotations=_RO)
@_require_db
def get_error_summary() -> dict:
    """Get summary of errors and issues in the database including failed jobs and missing scores."""
    with db.connection() as conn:
        c = conn.cursor()
        summary = {}

        try:
            c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'failed'")
            summary["failed_jobs"] = c.fetchone()[0]

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

            models = ['spaq', 'koniq', 'ava', 'paq2piq', 'liqe']
            for model in models:
                col = f"score_{model}"
                c.execute(f"""
                    SELECT COUNT(*) FROM images
                    WHERE {col} IS NULL OR {col} = 0
                """)
                summary[f"images_missing_{model}"] = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM images WHERE folder_id IS NULL")
            summary["orphaned_images"] = c.fetchone()[0]

            c.execute("""
                SELECT COUNT(*) FROM images WHERE file_path IS NULL OR file_path = ''
            """)
            summary["images_with_empty_paths"] = c.fetchone()[0]

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

        return summary


@mcp.tool(annotations=_RO)
@_require_db
def check_database_health() -> dict:
    """Check database for inconsistencies, orphaned records, and data integrity issues."""
    with db.connection() as conn:
        c = conn.cursor()
        health = {
            "status": "healthy",
            "issues": [],
            "warnings": []
        }

        try:
            c.execute("""
                SELECT COUNT(*) FROM images i
                LEFT JOIN folders f ON i.folder_id = f.id
                WHERE i.folder_id IS NOT NULL AND f.id IS NULL
            """)
            orphaned_count = c.fetchone()[0]
            if orphaned_count > 0:
                health["issues"].append(f"{orphaned_count} images with invalid folder_id")
                health["status"] = "unhealthy"

            c.execute("""
                SELECT COUNT(*) FROM images i
                LEFT JOIN stacks s ON i.stack_id = s.id
                WHERE i.stack_id IS NOT NULL AND s.id IS NULL
            """)
            orphaned_stacks = c.fetchone()[0]
            if orphaned_stacks > 0:
                health["issues"].append(f"{orphaned_stacks} images with invalid stack_id")
                health["status"] = "unhealthy"

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

            c.execute("""
                SELECT COUNT(*) FROM images
                WHERE image_hash IS NOT NULL AND (file_path IS NULL OR file_path = '')
            """)
            hash_no_path = c.fetchone()[0]
            if hash_no_path > 0:
                health["warnings"].append(f"{hash_no_path} images with hash but no path")

            c.execute("""
                SELECT COUNT(*) FROM folders f
                LEFT JOIN images i ON f.id = i.folder_id
                WHERE i.id IS NULL
            """)
            empty_folders = c.fetchone()[0]
            if empty_folders > 0:
                health["warnings"].append(f"{empty_folders} folders with no images")

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

        return health


@mcp.tool(annotations=_RO)
@_require_db
def validate_file_paths(limit: int = 100) -> dict:
    """Validate that file paths in database actually exist on the filesystem."""
    with db.connection() as conn:
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

        return results


# ============================================================
# Monitoring & Jobs Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def get_recent_jobs(limit: int = 10) -> list:
    """Get recent scoring/tagging jobs with their status."""
    rows = db.get_jobs(limit=limit)
    return [dict(row) for row in rows]


@mcp.tool(annotations=_RO)
def get_runner_status() -> dict:
    """Get current status of scoring and tagging background runners including progress and recent logs."""
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
                "recent_log": log[-2000:] if log else ""
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

    return status


@mcp.tool(annotations=_RO)
def get_model_status() -> dict:
    """Get status of loaded models, GPU availability, and CUDA/PyTorch/TensorFlow configuration."""
    status = {
        "models": {},
        "gpu": {},
        "scorer_available": False
    }

    try:
        if _scoring_runner and _scoring_runner.shared_scorer:
            status["scorer_available"] = True
            scorer = _scoring_runner.shared_scorer

            try:
                status["models"]["version"] = getattr(scorer, 'VERSION', 'unknown')
            except Exception:
                pass

            model_names = ['spaq', 'ava', 'koniq', 'paq2piq']
            for model_name in model_names:
                try:
                    model_attr = getattr(scorer, f'{model_name}_model', None)
                    status["models"][model_name] = {"loaded": model_attr is not None}
                except Exception:
                    status["models"][model_name] = {"loaded": False}
        else:
            status["models"]["note"] = "Scorer not initialized"

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


@mcp.tool(annotations=_RW)
@_require_db
def run_processing_job(job_type: str, input_path: str, args: dict = None) -> dict:
    """Trigger a background processing job (scoring, tagging, or clustering/stacks)."""
    import uuid

    if args is None:
        args = {}

    job_id = f"mcp_{job_type}_{uuid.uuid4().hex[:8]}"

    if not os.path.exists(input_path) and not (job_type == "clustering" and (not input_path or not input_path.strip())):
        return {"error": f"Input path not found: {input_path}"}

    if job_type == "scoring":
        if not _scoring_runner:
            return {"error": "Scoring runner not available"}
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


# ============================================================
# Configuration & Logs Tools
# ============================================================

@mcp.tool(annotations=_RO)
def get_config() -> dict:
    """Get current application configuration from config.json."""
    return config.load_config()


@mcp.tool(annotations=_RW)
def set_config_value(key: str, value: Any) -> dict:
    """Set a configuration value in config.json."""
    try:
        config.save_config_value(key, value)
        return {"success": True, "key": key, "value": value}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(annotations=_RO)
def read_debug_log(lines: int = 100) -> dict:
    """Read recent entries from the debug log file."""
    from modules import utils
    log_path = utils.get_debug_log_path()

    if not os.path.exists(log_path):
        return {"error": "Debug log file not found", "path": log_path}

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        recent = all_lines[-lines:]
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


# ============================================================
# Advanced Search Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def search_similar_images(
    example_path: Optional[str] = None,
    example_image_id: Optional[int] = None,
    limit: int = 20,
    folder_path: Optional[str] = None,
    min_similarity: Optional[float] = None
) -> dict:
    """Find images visually similar to an example image using stored MobileNetV2 embeddings and cosine similarity. Provide either example_path or example_image_id."""
    from modules import similar_search
    return similar_search.search_similar_images(
        example_path=example_path,
        example_image_id=example_image_id,
        limit=limit,
        folder_path=folder_path,
        min_similarity=min_similarity,
    )


@mcp.tool(annotations=_RO)
@_require_db
def find_near_duplicates(
    threshold: Optional[float] = None,
    folder_path: Optional[str] = None,
    limit: Optional[int] = None
) -> dict:
    """Detect visually duplicate or near-duplicate images even when file hashes differ. Returns a list of near-duplicate image pairs."""
    from modules import similar_search
    return similar_search.find_near_duplicates(
        threshold=threshold,
        folder_path=folder_path,
        limit=limit
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False) if MCP_AVAILABLE else None)
@_require_db
def propagate_tags(
    folder_path: Optional[str] = None,
    dry_run: bool = True,
    k: Optional[int] = None,
    min_similarity: Optional[float] = None,
    min_keyword_confidence: Optional[float] = None
) -> dict:
    """Propagate keywords from tagged images to untagged neighbors using embedding cosine similarity. Uses weighted voting with configurable thresholds. Defaults to dry_run=true for safe preview."""
    from modules.tagging import propagate_tags as _propagate_tags
    return _propagate_tags(
        folder_path=folder_path,
        dry_run=dry_run,
        k=k,
        min_similarity=min_similarity,
        min_keyword_confidence=min_keyword_confidence,
    )


@mcp.tool(annotations=_RO)
@_require_db
def find_outliers(
    folder_path: str = "",
    z_threshold: Optional[float] = None,
    k: Optional[int] = None,
    limit: Optional[int] = None
) -> dict:
    """Identify visually atypical images in a folder using embedding similarity analysis. Computes top-K mean cosine similarity per image and flags statistical outliers via z-score. Returns flagged images with explainability (nearest neighbors, folder stats)."""
    from modules import similar_search
    return similar_search.find_outliers(
        folder_path=folder_path,
        z_threshold=z_threshold,
        k=k,
        limit=limit,
    )


# ============================================================
# MCP Resources
# ============================================================

if MCP_AVAILABLE:
    @mcp.resource("config://current")
    def config_resource() -> str:
        """Current application configuration from config.json."""
        return json.dumps(config.load_config(), indent=2)


# ============================================================
# Server Setup & Transport
# ============================================================

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
    if not MCP_AVAILABLE:
        raise RuntimeError("MCP SDK required. Install: pip install mcp")

    prepare_mcp_embedded()
    app = mcp.sse_app(mount_path=mount_path)
    
    # Cursor sometimes sends POST/DELETE to /mcp/sse directly instead of the endpoint URL.
    # Let's alias POST /sse to the /messages handler and handle DELETE gracefully.
    try:
        from starlette.routing import Route, Mount
        from starlette.responses import Response
        
        # Find the messages mount
        messages_mount = next((r for r in app.routes if isinstance(r, Mount) and r.path == '/messages'), None)
        
        if messages_mount:
            async def sse_post_alias(scope, receive, send):
                # Rewrite path internally to match the mount's expectations
                scope["path"] = "/messages"
                await messages_mount.handle(scope, receive, send)
                
            app.routes.insert(0, Route('/sse', endpoint=sse_post_alias, methods=['POST']))
            
        async def dummy_delete_handler(request):
            return Response(status_code=200)
            
        app.routes.insert(0, Route('/sse', endpoint=dummy_delete_handler, methods=['DELETE']))
    except Exception as e:
        logger.warning(f"Failed to alias POST/DELETE routes for SSE: {e}")

    return app


async def run_server():
    """Run the MCP server using stdio transport."""
    if not MCP_AVAILABLE:
        print("Error: MCP SDK not installed. Run: pip install mcp")
        return

    prepare_mcp_embedded()
    await mcp.run_stdio_async()


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
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    logger.info("Starting Image Scoring MCP Server...")

    # Initialize runners for standalone mode
    try:
        from modules.clustering import ClusteringRunner
        clustering_runner = ClusteringRunner()
        set_runners(None, None, clustering_runner)
        logger.info("Initialized ClusteringRunner for standalone mode")
    except Exception as e:
        logger.warning(f"Failed to initialize clustering runner: {e}")

    asyncio.run(run_server())
